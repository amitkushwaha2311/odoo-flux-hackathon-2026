# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.payment_service
#
# Payment & Reconciliation Engine Service for Brightloop Subscription Intelligence
#
# PHASE 9 SCOPE
# -------------
# - Registers customer payments against native Odoo invoices (account.move).
# - Supports full payments, partial payments, and multi-invoice allocations.
# - Leverages native Odoo reconciliation (account.payment -> account.move.line).
# - Enforces PostgreSQL-level duplicate payment protection (idempotency).
# - Tracks outstanding balances, invoice payment states, and overdue invoices.
# - Provides end-to-end traceability from payments to subscriptions and billing periods.
# - Supports authorized payment reversal / cancellation with audit logging.
# - Enforces strict role-based access control and multi-company / customer isolation.
# =============================================================================

import logging
from datetime import date, datetime

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class BrightloopPaymentService(models.AbstractModel):
    """
    Brightloop Payment & Reconciliation Engine Service.

    Stateless AbstractModel service coordinating customer payment registration,
    reconciliation against subscription invoices, outstanding balance computation,
    overdue invoice tracking, and payment reversals.
    """
    _name = 'brightloop.payment.service'
    _description = 'Brightloop Payment & Reconciliation Engine Service'

    # =========================================================================
    # ROLE-BASED ACCESS HELPERS
    # =========================================================================

    def _check_can_register(self):
        """Only Brightloop Admin and Staff can register payments."""
        user = self.env.user
        is_admin = user.has_group('brightloop_core.group_brightloop_admin')
        is_staff = user.has_group('brightloop_core.group_brightloop_staff')
        if not (is_admin or is_staff or self.env.is_superuser()):
            self.env['brightloop.security.audit'].log_event(
                event_type='payment_unauthorized',
                summary='Unauthorized payment registration attempt',
                details=f'User {user.name} (login: {user.login}) attempted to register payment without permission.',
            )
            raise AccessError('Only Administrators and Staff can register payments.')

    def _check_can_reverse(self):
        """Only Brightloop Admin can reverse payments."""
        user = self.env.user
        is_admin = user.has_group('brightloop_core.group_brightloop_admin')
        if not (is_admin or self.env.is_superuser()):
            self.env['brightloop.security.audit'].log_event(
                event_type='payment_unauthorized',
                summary='Unauthorized payment reversal attempt',
                details=f'User {user.name} (login: {user.login}) attempted to reverse payment without admin privileges.',
            )
            raise AccessError('Only Administrators can reverse payments.')

    def _check_customer_isolation(self, partner):
        """If caller is in Customer group, verify they only access their own data."""
        user = self.env.user
        is_admin = user.has_group('brightloop_core.group_brightloop_admin')
        is_staff = user.has_group('brightloop_core.group_brightloop_staff')
        if not (is_admin or is_staff or self.env.is_superuser()):
            # Must be own partner
            user_partner = user.partner_id
            if partner.id != user_partner.id and partner.commercial_partner_id.id != user_partner.commercial_partner_id.id:
                raise AccessError('Access denied: You can only view your own payment records.')

    # =========================================================================
    # 1. PAYMENT VALIDATION
    # =========================================================================

    @api.model
    def validate_payment_request(self, invoices, amount, partner=None, journal=None, currency=None, company=None):
        """
        Validate all preconditions for payment registration.

        Rules:
        - Invoices must not be empty.
        - Invoices must be in state 'posted'.
        - Invoices must be customer invoices (out_invoice).
        - Invoices must have outstanding residual > 0.
        - Amount must be strictly positive (> 0).
        - Total payment amount cannot exceed sum of invoice residuals.
        - Partner must match invoices' commercial partner.
        - Company and currency must be compatible.
        - Journal must be an active bank or cash journal.

        :param invoices: account.move recordset
        :param amount: float
        :param partner: res.partner record or None
        :param journal: account.journal record or None
        :param currency: res.currency record or None
        :param company: res.company record or None
        :return: dict with validation result or raises ValidationError/UserError
        """
        if not invoices:
            raise ValidationError('At least one invoice is required for payment registration.')

        if amount <= 0:
            raise ValidationError(f'Payment amount must be strictly positive (got: {amount}).')

        total_residual = 0.0
        target_company = company or invoices[0].company_id
        target_currency = currency or invoices[0].currency_id
        target_partner = partner or invoices[0].partner_id

        for inv in invoices:
            if inv.state == 'draft':
                raise UserError(f'Cannot pay draft invoice "{inv.name}". Invoice must be posted first.')
            if inv.state == 'cancel':
                raise UserError(f'Cannot pay cancelled invoice "{inv.name}".')
            if inv.move_type not in ('out_invoice', 'out_refund'):
                raise UserError(f'Invoice "{inv.name}" is not a customer invoice (type: {inv.move_type}).')
            if inv.payment_state == 'paid' or inv.amount_residual <= 0:
                raise UserError(f'Invoice "{inv.name}" is already fully paid.')

            if inv.company_id.id != target_company.id:
                raise ValidationError(
                    f'Invoice "{inv.name}" belongs to company "{inv.company_id.name}", '
                    f'which does not match target company "{target_company.name}".'
                )

            if target_partner and inv.partner_id.commercial_partner_id.id != target_partner.commercial_partner_id.id:
                raise ValidationError(
                    f'Invoice "{inv.name}" customer "{inv.partner_id.name}" does not match '
                    f'payment customer "{target_partner.name}".'
                )

            total_residual += inv.amount_residual

        # Rounding check against residual
        curr = target_currency or invoices[0].currency_id
        if curr.compare_amounts(amount, total_residual) > 0:
            raise ValidationError(
                f'Payment amount ({amount} {curr.name}) exceeds total outstanding '
                f'residual ({total_residual} {curr.name}) across selected invoice(s).'
            )

        if journal:
            if journal.type not in ('bank', 'cash'):
                raise ValidationError(f'Journal "{journal.name}" must be of type Bank or Cash (got: {journal.type}).')
            if journal.company_id.id != target_company.id:
                raise ValidationError(
                    f'Journal "{journal.name}" company does not match payment company "{target_company.name}".'
                )

        return {
            'valid': True,
            'total_residual': total_residual,
            'company': target_company,
            'currency': target_currency,
            'partner': target_partner,
        }

    # =========================================================================
    # 2. PAYMENT REGISTRATION & RECONCILIATION
    # =========================================================================

    @api.model
    def register_payment(self, invoice_ids, amount, journal_id=None, payment_date=None,
                         memo=None, partner_id=None, currency_id=None, company_id=None,
                         idempotency_key=None):
        """
        Register and reconcile a customer payment against one or more invoices.

        Transactional workflow:
        1. Access check (Admin or Staff).
        2. Idempotency check: if key supplied, return existing payment if already registered.
        3. Precondition validation via validate_payment_request.
        4. Create native account.payment with inbound / customer configuration.
        5. Post payment via action_post() to generate journal entry.
        6. Native reconciliation: match receivable lines via js_assign_outstanding_line.
        7. Audit event logging.

        :param invoice_ids: int, list of ints, or account.move recordset
        :param amount: float (payment amount)
        :param journal_id: account.journal id or None (defaults to bank/cash journal of company)
        :param payment_date: date object or None (defaults to today)
        :param memo: str or None (payment communication)
        :param partner_id: res.partner id or None
        :param currency_id: res.currency id or None
        :param company_id: res.company id or None
        :param idempotency_key: unique str for duplicate protection
        :return: dict with registration results
        """
        self._check_can_register()

        # Resolve invoices recordset
        if isinstance(invoice_ids, models.Model):
            invoices = invoice_ids
        elif isinstance(invoice_ids, (list, tuple)):
            invoices = self.env['account.move'].browse(invoice_ids)
        elif isinstance(invoice_ids, int):
            invoices = self.env['account.move'].browse([invoice_ids])
        else:
            raise ValidationError('Invalid invoice_ids parameter.')

        if not invoices:
            raise ValidationError('At least one invoice is required for payment registration.')

        # Resolve company, currency, partner early for payload comparison
        company = self.env['res.company'].browse(company_id) if company_id else invoices[0].company_id
        currency = self.env['res.currency'].browse(currency_id) if currency_id else invoices[0].currency_id
        partner = self.env['res.partner'].browse(partner_id) if partner_id else invoices[0].partner_id

        # 1. Idempotency Check with Payload Conflict Validation
        if idempotency_key:
            existing_pay = self.env['account.payment'].search([('idempotency_key', '=', idempotency_key)], limit=1)
            if existing_pay:
                # Validate payload consistency: amount, customer, company, currency, invoice allocation
                existing_invoices = existing_pay.reconciled_invoice_ids or existing_pay.invoice_ids
                mismatches = []

                if currency.compare_amounts(amount, existing_pay.amount) != 0:
                    mismatches.append(f"amount (requested: {amount}, existing: {existing_pay.amount})")
                if existing_pay.partner_id.commercial_partner_id.id != partner.commercial_partner_id.id:
                    mismatches.append(f"customer (requested: {partner.name}, existing: {existing_pay.partner_id.name})")
                if existing_pay.company_id.id != company.id:
                    mismatches.append(f"company (requested: {company.name}, existing: {existing_pay.company_id.name})")
                if existing_pay.currency_id.id != currency.id:
                    mismatches.append(f"currency (requested: {currency.name}, existing: {existing_pay.currency_id.name})")
                if set(existing_invoices.ids) != set(invoices.ids):
                    mismatches.append(f"invoice allocation (requested: {sorted(invoices.ids)}, existing: {sorted(existing_invoices.ids)})")

                if mismatches:
                    err_msg = (
                        f"Idempotency conflict: Key '{idempotency_key}' was previously used with a different request payload: "
                        + "; ".join(mismatches)
                    )
                    self.env['brightloop.security.audit'].log_event(
                        event_type='payment_failed',
                        summary=f'Idempotency payload mismatch: {idempotency_key}',
                        details=err_msg,
                    )
                    raise ValidationError(err_msg)

                self.env['brightloop.security.audit'].log_event(
                    event_type='payment_duplicate_prevented',
                    summary=f'Duplicate payment prevented: {idempotency_key}',
                    details=f'Payment with key "{idempotency_key}" already exists (ID: {existing_pay.id}, State: {existing_pay.state}).',
                )
                return {
                    'success': True,
                    'duplicate': True,
                    'payment_id': existing_pay.id,
                    'payment_name': existing_pay.name,
                    'payment_state': existing_pay.state,
                    'amount': existing_pay.amount,
                    'invoices': [
                        {
                            'id': inv.id,
                            'name': inv.name,
                            'payment_state': inv.payment_state,
                            'amount_residual': inv.amount_residual,
                        }
                        for inv in invoices
                    ],
                }

        # Resolve journal
        Journal = self.env['account.journal']
        if journal_id:
            journal = Journal.browse(journal_id)
        else:
            journal = Journal.search([
                ('type', 'in', ('bank', 'cash')),
                ('company_id', '=', company.id),
            ], limit=1)
            if not journal:
                journal = Journal.search([('type', 'in', ('bank', 'cash'))], limit=1)
            if not journal:
                raise UserError(f'No bank or cash payment journal found for company "{company.name}".')

        # 2. Acquire Row-Level Lock on Invoices for Concurrent Allocation Safety
        invoices.flush_recordset(['amount_residual', 'state', 'payment_state'])
        self.env.cr.execute(
            'SELECT id, amount_residual FROM account_move WHERE id IN %s FOR UPDATE',
            (tuple(invoices.ids),)
        )

        # 3. Precondition Validation
        self.validate_payment_request(
            invoices=invoices,
            amount=amount,
            partner=partner,
            journal=journal,
            currency=currency,
            company=company,
        )

        p_date = payment_date or fields.Date.context_today(self)
        p_memo = memo or f"Payment for {', '.join(invoices.mapped('name'))}"

        # 3. Create native account.payment
        payment_vals = {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': partner.id,
            'amount': amount,
            'journal_id': journal.id,
            'company_id': company.id,
            'currency_id': currency.id,
            'date': p_date,
            'memo': p_memo,
            'idempotency_key': idempotency_key or False,
            'invoice_ids': [(6, 0, invoices.ids)],
        }

        try:
            payment = self.env['account.payment'].create(payment_vals)
            # 4. Post payment
            payment.action_post()
        except Exception as e:
            self.env['brightloop.security.audit'].log_event(
                event_type='payment_failed',
                summary=f'Payment registration failed for {partner.name}',
                details=f'Error creating or posting payment: {str(e)}',
            )
            raise

        # 5. Native Reconciliation
        # Find receivable lines on the payment move to assign to each invoice
        reconciled_invoices = []
        for inv in invoices:
            if inv.amount_residual > 0:
                rec_lines = payment.move_id.line_ids.filtered(
                    lambda l: l.account_type == 'asset_receivable' and not l.reconciled
                )
                if rec_lines:
                    inv.js_assign_outstanding_line(rec_lines[0].id)
                    inv.invalidate_recordset(['payment_state', 'amount_residual'])
            reconciled_invoices.append(inv)

        # Re-evaluate payment status & traceability
        payment.invalidate_recordset(['state', 'is_reconciled', 'reconciled_invoice_ids', 'subscription_id', 'billing_period_id'])

        # 6. Audit Trail Logging
        self.env['brightloop.security.audit'].log_event(
            event_type='payment_registered',
            summary=f'Payment registered: {payment.name or payment.id}',
            details=(
                f'Registered payment ID={payment.id} of {amount} {currency.name} for partner "{partner.name}" '
                f'(Journal: {journal.name}, Invoices: {", ".join(invoices.mapped("name"))}).'
            ),
        )

        self.env['brightloop.security.audit'].log_event(
            event_type='payment_reconciled',
            summary=f'Payment reconciled: {payment.name}',
            details=f'Reconciled payment {payment.name} against invoice(s): {", ".join(invoices.mapped("name"))}.',
        )

        # Check invoice states for partial or full settlement
        for inv in invoices:
            if inv.payment_state == 'paid':
                self.env['brightloop.security.audit'].log_event(
                    event_type='payment_settled',
                    summary=f'Invoice settled: {inv.name}',
                    details=f'Invoice "{inv.name}" is now fully settled (Residual: 0.0).',
                )
            elif inv.payment_state == 'partial':
                self.env['brightloop.security.audit'].log_event(
                    event_type='payment_partial',
                    summary=f'Partial payment applied: {inv.name}',
                    details=f'Partial payment applied to "{inv.name}". Remaining residual: {inv.amount_residual} {inv.currency_id.name}.',
                )

        return {
            'success': True,
            'duplicate': False,
            'payment_id': payment.id,
            'payment_name': payment.name,
            'payment_state': payment.state,
            'amount': payment.amount,
            'currency': currency.name,
            'invoices': [
                {
                    'id': inv.id,
                    'name': inv.name,
                    'payment_state': inv.payment_state,
                    'amount_residual': inv.amount_residual,
                }
                for inv in invoices
            ],
        }

    # =========================================================================
    # 3. OUTSTANDING BALANCE & STATUS
    # =========================================================================

    @api.model
    def get_outstanding_balance(self, invoice):
        """
        Get the current outstanding residual balance for an invoice.

        Uses native Odoo amount_residual as the single source of truth.
        """
        self._check_customer_isolation(invoice.partner_id)
        invoice.invalidate_recordset(['amount_residual', 'payment_state'])
        return invoice.amount_residual

    @api.model
    def get_invoice_payment_status(self, invoice):
        """
        Retrieve structured payment status for an invoice.

        :param invoice: account.move record
        :return: dict with detailed payment status
        """
        self._check_customer_isolation(invoice.partner_id)
        invoice.invalidate_recordset(['amount_residual', 'payment_state', 'state'])

        today = fields.Date.context_today(self)
        is_overdue = bool(
            invoice.invoice_date_due
            and invoice.invoice_date_due < today
            and invoice.amount_residual > 0
            and invoice.state == 'posted'
        )

        reconciled_payments = invoice._get_reconciled_payments() if hasattr(invoice, '_get_reconciled_payments') else self.env['account.payment']
        payment_list = [
            {
                'id': p.id,
                'name': p.name,
                'amount': p.amount,
                'date': p.date,
                'state': p.state,
                'journal': p.journal_id.name,
            }
            for p in reconciled_payments
        ]

        return {
            'invoice_id': invoice.id,
            'name': invoice.name,
            'state': invoice.state,
            'payment_state': invoice.payment_state,
            'amount_total': invoice.amount_total,
            'amount_residual': invoice.amount_residual,
            'currency': invoice.currency_id.name,
            'invoice_date': invoice.invoice_date,
            'due_date': invoice.invoice_date_due,
            'is_paid': invoice.payment_state == 'paid',
            'is_overdue': is_overdue,
            'payments': payment_list,
            'subscription_id': invoice.subscription_id.id if invoice.subscription_id else False,
            'billing_period_id': invoice.billing_period_id.id if invoice.billing_period_id else False,
        }

    # =========================================================================
    # 4. PAYMENT HISTORY
    # =========================================================================

    @api.model
    def get_customer_payment_history(self, partner, company=None, limit=100):
        """
        Retrieve payment history for a customer partner.

        Enforces customer partner isolation.
        """
        self._check_customer_isolation(partner)

        domain = [
            ('partner_id', 'child_of', partner.commercial_partner_id.id),
            ('payment_type', '=', 'inbound'),
            ('state', 'in', ('paid', 'reconciled')),
        ]
        if company:
            domain.append(('company_id', '=', company.id))

        payments = self.env['account.payment'].search(domain, order='date desc, id desc', limit=limit)
        results = []
        for p in payments:
            invoices = p.reconciled_invoice_ids or p.invoice_ids
            results.append({
                'payment_id': p.id,
                'name': p.name,
                'amount': p.amount,
                'currency': p.currency_id.name,
                'date': p.date,
                'memo': p.memo,
                'state': p.state,
                'journal': p.journal_id.name,
                'invoices': [{'id': inv.id, 'name': inv.name} for inv in invoices],
                'subscription_id': p.subscription_id.id if p.subscription_id else False,
                'billing_period_id': p.billing_period_id.id if p.billing_period_id else False,
            })
        return results

    @api.model
    def get_subscription_payment_history(self, subscription, limit=50):
        """
        Retrieve all payments associated with a subscription contract.
        """
        self._check_customer_isolation(subscription.customer_id)

        # Invoices linked to this subscription
        invoices = self.env['account.move'].search([
            ('subscription_id', '=', subscription.id),
            ('state', '=', 'posted'),
        ])

        if not invoices:
            return []

        # Find all payments reconciled with these invoices
        payments = self.env['account.payment'].search([
            ('reconciled_invoice_ids', 'in', invoices.ids),
            ('state', 'in', ('paid', 'reconciled')),
        ], order='date desc, id desc', limit=limit)

        results = []
        for p in payments:
            results.append({
                'payment_id': p.id,
                'name': p.name,
                'amount': p.amount,
                'currency': p.currency_id.name,
                'date': p.date,
                'memo': p.memo,
                'state': p.state,
                'journal': p.journal_id.name,
                'subscription_id': subscription.id,
                'billing_period_id': p.billing_period_id.id if p.billing_period_id else False,
                'invoices': [{'id': inv.id, 'name': inv.name} for inv in p.reconciled_invoice_ids],
            })
        return results

    # =========================================================================
    # 5. OVERDUE INVOICE MANAGEMENT
    # =========================================================================

    @api.model
    def get_overdue_invoices(self, company=None, target_date=None, limit=100):
        """
        Retrieve posted customer invoices that are overdue.

        Criteria:
        - state == 'posted'
        - move_type == 'out_invoice'
        - invoice_date_due < target_date (default today)
        - amount_residual > 0
        - payment_state in ('not_paid', 'partial')
        """
        today = target_date or fields.Date.context_today(self)
        domain = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('invoice_date_due', '<', today),
            ('amount_residual', '>', 0.0),
        ]
        if company:
            domain.append(('company_id', '=', company.id))

        overdue_invoices = self.env['account.move'].search(domain, order='invoice_date_due asc, id asc', limit=limit)
        results = []
        for inv in overdue_invoices:
            days_overdue = (today - inv.invoice_date_due).days if inv.invoice_date_due else 0
            results.append({
                'invoice_id': inv.id,
                'name': inv.name,
                'customer_id': inv.partner_id.id,
                'customer_name': inv.partner_id.name,
                'amount_total': inv.amount_total,
                'amount_residual': inv.amount_residual,
                'currency': inv.currency_id.name,
                'due_date': inv.invoice_date_due,
                'days_overdue': days_overdue,
                'payment_state': inv.payment_state,
                'subscription_id': inv.subscription_id.id if inv.subscription_id else False,
                'billing_period_id': inv.billing_period_id.id if inv.billing_period_id else False,
            })

            # Audit overdue event
            self.env['brightloop.security.audit'].log_event(
                event_type='overdue_invoice_detected',
                summary=f'Overdue invoice detected: {inv.name}',
                details=f'Invoice "{inv.name}" is overdue by {days_overdue} days (Residual: {inv.amount_residual} {inv.currency_id.name}).',
            )

        return results

    # =========================================================================
    # 6. REFUNDS & PAYMENT REVERSAL
    # =========================================================================

    @api.model
    def reverse_payment(self, payment, reason=''):
        """
        Safely reverse / cancel a customer payment using native Odoo cancellation.

        Cancelling the payment unlinks its journal entries, unreconciles any
        linked invoices, and restores their outstanding residuals.

        :param payment: account.payment record
        :param reason: str (reason for reversal)
        :return: dict with reversal results
        """
        self._check_can_reverse()

        if payment.state == 'canceled':
            raise UserError(f'Payment "{payment.name}" is already cancelled.')

        invoices_before = payment.reconciled_invoice_ids

        try:
            # Native Odoo payment cancellation
            payment.action_cancel()
        except Exception as e:
            self.env['brightloop.security.audit'].log_event(
                event_type='payment_failed',
                summary=f'Payment reversal failed: {payment.name}',
                details=f'Failed to reverse payment {payment.name}: {str(e)}',
            )
            raise UserError(f'Failed to reverse payment: {str(e)}')

        # Invalidate cache so residuals are fresh
        invoices_before.invalidate_recordset(['amount_residual', 'payment_state'])

        self.env['brightloop.security.audit'].log_event(
            event_type='payment_reversed',
            summary=f'Payment reversed: {payment.name}',
            details=(
                f'Reversed payment ID={payment.id} ({payment.name}) of {payment.amount} {payment.currency_id.name}. '
                f'Reason: {reason or "Administrative reversal"}. Invoices restored: {", ".join(invoices_before.mapped("name"))}.'
            ),
        )

        return {
            'success': True,
            'payment_id': payment.id,
            'payment_name': payment.name,
            'payment_state': payment.state,
            'restored_invoices': [
                {
                    'id': inv.id,
                    'name': inv.name,
                    'payment_state': inv.payment_state,
                    'amount_residual': inv.amount_residual,
                }
                for inv in invoices_before
            ],
        }

