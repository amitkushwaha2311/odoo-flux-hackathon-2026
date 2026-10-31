# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.portal_service
#
# Customer Self-Service Portal Backend Engine for Brightloop Subscription Intelligence
#
# PHASE 10 SCOPE
# --------------
# - Secure, server-side customer self-service backend service.
# - Customer profile retrieval and permitted contact details updating.
# - Subscription self-service: list, details, pause, resume, early closure, renewal.
# - Strict enforcement of plan policies (allow_pause, allow_early_closure, allow_renewal).
# - Customer invoice access: listing, details, and secure PDF document rendering.
# - Customer payment history and partial payment transparency.
# - Consolidated chronological billing timeline across contracts, invoices, and payments.
# - Multi-level security: commercial partner isolation, cross-company isolation, no ID enumeration.
# - Abuse protection and rate limiting on mutation operations.
# - Immutable security audit logging for all portal operations.
# =============================================================================

import logging
import re
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

# Permitted profile fields for customer self-service updates
PERMITTED_PROFILE_FIELDS = {'name', 'phone', 'street', 'street2', 'city', 'zip', 'state_id', 'country_id'}

# Prohibited profile fields that must never be modified by customer
PROHIBITED_PROFILE_FIELDS = {
    'email', 'user_id', 'user_ids', 'company_id', 'parent_id', 'is_company',
    'credit_limit', 'property_account_receivable_id', 'property_account_payable_id',
    'property_payment_method_id', 'group_ids', 'role', 'active',
}


class BrightloopCustomerPortalService(models.AbstractModel):
    """
    Brightloop Customer Self-Service Portal Backend Engine.

    Stateless AbstractModel providing customer profile management, subscription
    lifecycle actions, invoice and document access, payment history, and consolidated
    billing timelines with multi-level commercial partner isolation.
    """
    _name = 'brightloop.portal.service'
    _description = 'Brightloop Customer Self-Service Portal Service'

    # In-memory sliding window rate-limiter cache: (key, user_id) -> list of timestamps
    _rate_limit_cache = {}

    # =========================================================================
    # 1. SECURITY & IDENTITY HELPERS
    # =========================================================================

    def _get_customer_partner(self, user=None):
        """
        Resolve the authorized commercial partner for the authenticated customer.

        Enforces authentication and strictly excludes public/anonymous users.

        :param user: res.users record or None (defaults to self.env.user)
        :return: res.partner record (commercial partner)
        :raises AccessError: if user is not authenticated or lacks customer identity
        """
        caller = user or self.env.user
        if not caller or caller._is_public() or caller.id == self.env.ref('base.public_user').id:
            raise AccessError('Authentication required. Anonymous access is strictly prohibited.')

        if not caller.partner_id:
            raise AccessError('Authenticated user has no associated customer partner record.')

        return caller.partner_id.commercial_partner_id

    def _log_unauthorized_audit(self, event_type, summary, details=''):
        """
        Write an unauthorized-access audit record in its own autonomous transaction.

        Audit records for security violations must survive the AccessError that is
        raised immediately after logging. Because the AccessError rolls back the
        caller's transaction, we open a fresh cursor and commit independently so
        the record is durably persisted regardless of what the caller does next.

        :param event_type: str  — selection key on brightloop.security.audit
        :param summary: str     — short human-readable description
        :param details: str     — supplementary safe context
        """
        try:
            with self.env.registry.cursor() as new_cr:
                new_env = self.env(cr=new_cr)
                new_env['brightloop.security.audit'].sudo().create({
                    'event_type': event_type,
                    'name': summary,
                    'details': details or '',
                    'user_id': self.env.user.id if self.env.user and self.env.user.id else False,
                    'timestamp': fields.Datetime.now(),
                    'company_id': self.env.company.id,
                })
                new_cr.commit()
                _logger.info(
                    '[AUDIT] %s | %s | actor=%s (autonomous tx)',
                    event_type, summary, self.env.user.id,
                )
        except Exception as exc:
            # Never let audit failures block the primary security rejection path
            _logger.exception('[AUDIT] Failed to write autonomous unauthorized audit: %s', exc)

    def _validate_subscription_ownership(self, subscription_id, user=None):
        """
        Validate that the authenticated customer owns the requested subscription.

        Prevents object-ID enumeration: returns generic AccessError on mismatch.

        :param subscription_id: int
        :param user: res.users record or None
        :return: brightloop.subscription record
        :raises AccessError: if subscription does not exist or belongs to another customer
        """
        commercial_partner = self._get_customer_partner(user=user)
        sub = self.env['brightloop.subscription'].sudo().browse(subscription_id)

        if not sub.exists() or sub.customer_id.commercial_partner_id.id != commercial_partner.id:
            self._log_unauthorized_audit(
                event_type='portal_unauthorized_access_attempt',
                summary=f'Unauthorized subscription access attempt: ID {subscription_id}',
                details=f'User {self.env.user.login} attempted to access subscription {subscription_id} not owned by their account.',
            )
            raise AccessError('Subscription not found or access denied.')

        return sub

    def _validate_invoice_ownership(self, invoice_id, user=None):
        """
        Validate that the authenticated customer owns the requested invoice.

        :param invoice_id: int
        :param user: res.users record or None
        :return: account.move record
        :raises AccessError: if invoice does not exist or belongs to another customer
        """
        commercial_partner = self._get_customer_partner(user=user)
        invoice = self.env['account.move'].sudo().browse(invoice_id)

        if (
            not invoice.exists()
            or invoice.move_type not in ('out_invoice', 'out_refund')
            or invoice.partner_id.commercial_partner_id.id != commercial_partner.id
        ):
            self._log_unauthorized_audit(
                event_type='portal_unauthorized_access_attempt',
                summary=f'Unauthorized invoice access attempt: ID {invoice_id}',
                details=f'User {self.env.user.login} attempted to access invoice {invoice_id} not owned by their account.',
            )
            raise AccessError('Invoice not found or access denied.')

        return invoice

    def _validate_payment_ownership(self, payment_id, user=None):
        """
        Validate that the authenticated customer owns the requested payment.

        :param payment_id: int
        :param user: res.users record or None
        :return: account.payment record
        :raises AccessError: if payment does not exist or belongs to another customer
        """
        commercial_partner = self._get_customer_partner(user=user)
        payment = self.env['account.payment'].sudo().browse(payment_id)

        if not payment.exists() or payment.partner_id.commercial_partner_id.id != commercial_partner.id:
            self._log_unauthorized_audit(
                event_type='portal_unauthorized_access_attempt',
                summary=f'Unauthorized payment access attempt: ID {payment_id}',
                details=f'User {self.env.user.login} attempted to access payment {payment_id} not owned by their account.',
            )
            raise AccessError('Payment not found or access denied.')

        return payment

    # =========================================================================
    # 2. RATE LIMITING & ABUSE PROTECTION
    # =========================================================================

    def _check_rate_limit(self, action_name, user=None, max_requests=10, window_seconds=60):
        """
        Sliding-window rate limiter preventing brute-force or spamming of mutation endpoints.

        :param action_name: str (e.g. 'pause', 'resume', 'close', 'renew')
        :param user: res.users record
        :param max_requests: int
        :param window_seconds: int
        :raises UserError: if threshold exceeded
        """
        caller = user or self.env.user
        now = datetime.now().timestamp()
        key = (action_name, caller.id)

        timestamps = self._rate_limit_cache.get(key, [])
        # Evict timestamps older than window
        cutoff = now - window_seconds
        valid_timestamps = [ts for ts in timestamps if ts > cutoff]

        if len(valid_timestamps) >= max_requests:
            self._log_unauthorized_audit(
                event_type='portal_unauthorized_access_attempt',
                summary=f'Rate limit exceeded for action: {action_name}',
                details=f'User {caller.login} exceeded rate limit ({max_requests} requests per {window_seconds}s) for {action_name}.',
            )
            raise UserError('Too many requests. Please wait a moment before trying again.')

        valid_timestamps.append(now)
        self._rate_limit_cache[key] = valid_timestamps

    # =========================================================================
    # 3. CUSTOMER PROFILE SERVICE
    # =========================================================================

    @api.model
    def get_profile(self, user=None):
        """
        Retrieve authenticated customer's contact profile details.

        :param user: res.users or None
        :return: dict with customer-facing profile details
        """
        partner = self._get_customer_partner(user=user)
        user_record = user or self.env.user

        return {
            'partner_id': partner.id,
            'name': partner.name,
            'email': partner.email,
            'phone': partner.phone or '',
            'street': partner.street or '',
            'street2': partner.street2 or '',
            'city': partner.city or '',
            'zip': partner.zip or '',
            'state_id': partner.state_id.id if partner.state_id else False,
            'state_name': partner.state_id.name if partner.state_id else '',
            'country_id': partner.country_id.id if partner.country_id else False,
            'country_name': partner.country_id.name if partner.country_id else '',
            'company_id': partner.company_id.id,
            'company_name': partner.company_id.name,
            'commercial_partner_id': partner.commercial_partner_id.id,
        }

    @api.model
    def update_profile(self, vals, user=None):
        """
        Update explicitly permitted profile fields for the authenticated customer.

        Rejects restricted fields (company, accounting, roles, security groups).
        Validates phone formatting and preserves audit trail.

        :param vals: dict of field updates
        :param user: res.users or None
        :return: dict of updated profile
        :raises AccessError: if restricted fields are included in vals
        :raises ValidationError: on invalid data formats
        """
        partner = self._get_customer_partner(user=user)

        # Check for prohibited fields
        prohibited = set(vals.keys()) & PROHIBITED_PROFILE_FIELDS
        if prohibited:
            self._log_unauthorized_audit(
                event_type='portal_unauthorized_access_attempt',
                summary='Prohibited profile field modification attempt',
                details=f'User {self.env.user.login} attempted to update prohibited fields: {", ".join(prohibited)}.',
            )
            raise AccessError(f'Modifying restricted profile fields is prohibited: {", ".join(prohibited)}.')

        # Whitelist permitted fields only
        clean_vals = {k: v for k, v in vals.items() if k in PERMITTED_PROFILE_FIELDS}
        if not clean_vals:
            raise ValidationError('No valid profile fields provided for update.')

        # Validate phone if provided
        if 'phone' in clean_vals and clean_vals['phone']:
            clean_phone = clean_vals['phone'].strip()
            if not re.match(r'^\+?[0-9\s\-\(\)]{6,20}$', clean_phone):
                raise ValidationError('Invalid phone number format.')
            clean_vals['phone'] = clean_phone

        # Validate name
        if 'name' in clean_vals and not clean_vals['name'].strip():
            raise ValidationError('Customer name cannot be empty.')

        partner.sudo().write(clean_vals)

        self.env['brightloop.security.audit'].log_event(
            event_type='customer_profile_updated',
            summary=f'Customer profile updated: {partner.name}',
            details=f'Customer updated fields: {", ".join(clean_vals.keys())}.',
        )

        return self.get_profile(user=user)

    # =========================================================================
    # 4. SUBSCRIPTION SELF-SERVICE
    # =========================================================================

    @api.model
    def list_subscriptions(self, user=None, limit=50, offset=0):
        """
        List all subscriptions belonging to the authenticated customer.

        :param user: res.users or None
        :param limit: int
        :param offset: int
        :return: dict with total count and subscription records
        """
        commercial_partner = self._get_customer_partner(user=user)
        domain = [('customer_id.commercial_partner_id', '=', commercial_partner.id)]

        Sub = self.env['brightloop.subscription'].sudo()
        total = Sub.search_count(domain)
        subs = Sub.search(domain, order='create_date desc, id desc', limit=limit, offset=offset)

        results = []
        for s in subs:
            plan = s.subscription_plan_id
            results.append({
                'id': s.id,
                'name': s.name,
                'state': s.state,
                'plan_id': plan.id if plan else False,
                'plan_name': plan.name if plan else '',
                'billing_interval': s.billing_interval,
                'billing_interval_count': s.billing_interval_count,
                'start_date': s.start_date,
                'end_date': s.end_date,
                'next_billing_date': s.next_billing_date,
                'last_billing_date': s.last_billing_date,
                'currency': s.currency_id.name,
                'can_pause': bool(s.state == 'active' and plan and plan.allow_pause),
                'can_resume': bool(s.state == 'paused'),
                'can_close': bool(s.state in ('active', 'paused') and (not plan or plan.allow_early_closure)),
                'can_renew': bool(s.state in ('active', 'closed') and (not plan or plan.allow_renewal)),
            })

        return {'total': total, 'limit': limit, 'offset': offset, 'subscriptions': results}

    @api.model
    def get_subscription_detail(self, subscription_id, user=None):
        """
        Retrieve granular subscription details including contract lines and policy flags.

        :param subscription_id: int
        :param user: res.users or None
        :return: dict with subscription metadata
        """
        sub = self._validate_subscription_ownership(subscription_id, user=user)
        plan = sub.subscription_plan_id

        lines = [
            {
                'id': l.id,
                'product_id': l.product_id.id,
                'product_name': l.product_id.display_name,
                'quantity': l.quantity,
                'price_unit': l.price_unit,
                'price_subtotal': l.price_subtotal,
                'discount': l.discount,
            }
            for l in sub.subscription_line_ids
        ]

        recent_periods = [
            {
                'id': p.id,
                'period_start': p.billing_period_start,
                'period_end': p.billing_period_end,
                'status': p.status,
                'invoice_id': p.invoice_id.id if p.invoice_id else False,
                'amount_total': p.amount_total,
            }
            for p in sub.billing_period_ids[:5]
        ]

        self.env['brightloop.security.audit'].log_event(
            event_type='portal_subscription_viewed',
            summary=f'Subscription viewed: {sub.name}',
            details=f'Customer viewed subscription {sub.name} (ID: {sub.id}).',
        )

        return {
            'id': sub.id,
            'name': sub.name,
            'state': sub.state,
            'plan_id': plan.id if plan else False,
            'plan_name': plan.name if plan else '',
            'start_date': sub.start_date,
            'end_date': sub.end_date,
            'next_billing_date': sub.next_billing_date,
            'last_billing_date': sub.last_billing_date,
            'billing_anchor_date': sub.billing_anchor_date,
            'billing_interval': sub.billing_interval,
            'billing_interval_count': sub.billing_interval_count,
            'currency': sub.currency_id.name,
            'lines': lines,
            'recent_billing_periods': recent_periods,
            'can_pause': bool(sub.state == 'active' and plan and plan.allow_pause),
            'can_resume': bool(sub.state == 'paused'),
            'can_close': bool(sub.state in ('active', 'paused') and (not plan or plan.allow_early_closure)),
            'can_renew': bool(sub.state in ('active', 'closed') and (not plan or plan.allow_renewal)),
        }

    @api.model
    def pause_subscription(self, subscription_id, reason=None, user=None):
        """
        Customer action: Pause an active subscription contract.

        Enforces plan.allow_pause and active state. Uses existing lifecycle logic.

        :param subscription_id: int
        :param reason: str or None
        :param user: res.users or None
        :return: dict with updated subscription detail
        """
        self._check_rate_limit('pause', user=user)
        sub = self._validate_subscription_ownership(subscription_id, user=user)

        if sub.state != 'active':
            raise UserError(f'Subscription is in state "{sub.state}". Only active subscriptions can be paused.')

        if sub.subscription_plan_id and not sub.subscription_plan_id.allow_pause:
            raise UserError(f'Subscription plan "{sub.subscription_plan_id.name}" does not permit pausing.')

        # Execute using Phase 6 lifecycle logic
        pause_reason = reason or 'Customer self-service pause request'
        sub.sudo().action_pause(reason=pause_reason)

        self.env['brightloop.security.audit'].log_event(
            event_type='portal_subscription_pause_requested',
            summary=f'Subscription paused by customer: {sub.name}',
            details=f'Customer requested pause for subscription {sub.name}. Reason: {pause_reason}.',
        )

        return self.get_subscription_detail(subscription_id, user=user)

    @api.model
    def resume_subscription(self, subscription_id, user=None):
        """
        Customer action: Resume a paused subscription contract.

        Uses existing Phase 6 lifecycle schedule adjustment logic.

        :param subscription_id: int
        :param user: res.users or None
        :return: dict with updated subscription detail
        """
        self._check_rate_limit('resume', user=user)
        sub = self._validate_subscription_ownership(subscription_id, user=user)

        if sub.state != 'paused':
            raise UserError(f'Subscription is in state "{sub.state}". Only paused subscriptions can be resumed.')

        # Execute using Phase 6 lifecycle logic
        sub.sudo().action_resume()

        self.env['brightloop.security.audit'].log_event(
            event_type='portal_subscription_resumed',
            summary=f'Subscription resumed by customer: {sub.name}',
            details=f'Customer resumed subscription {sub.name}. Next billing scheduled: {sub.next_billing_date}.',
        )

        return self.get_subscription_detail(subscription_id, user=user)

    @api.model
    def request_early_closure(self, subscription_id, reason=None, user=None):
        """
        Customer action: Request early contract closure.

        Enforces plan.allow_early_closure policy and active/paused state.

        :param subscription_id: int
        :param reason: str
        :param user: res.users or None
        :return: dict with updated subscription detail
        """
        self._check_rate_limit('close', user=user)
        sub = self._validate_subscription_ownership(subscription_id, user=user)

        if sub.state not in ('active', 'paused'):
            raise UserError(f'Subscription is in state "{sub.state}". Only active or paused contracts can be closed.')

        if sub.subscription_plan_id and not sub.subscription_plan_id.allow_early_closure:
            raise UserError(f'Subscription plan "{sub.subscription_plan_id.name}" does not permit early closure.')

        close_reason = reason or 'Customer self-service early closure request'
        sub.sudo().action_close(reason=close_reason)

        self.env['brightloop.security.audit'].log_event(
            event_type='portal_subscription_closure_requested',
            summary=f'Subscription closed by customer: {sub.name}',
            details=f'Customer closed subscription {sub.name}. Reason: {close_reason}.',
        )

        return self.get_subscription_detail(subscription_id, user=user)

    @api.model
    def renew_subscription(self, subscription_id, user=None):
        """
        Customer action: Renew a subscription contract.

        Enforces plan.allow_renewal policy and delegates to Phase 6 renewal engine.

        :param subscription_id: int
        :param user: res.users or None
        :return: dict with replacement subscription detail
        """
        self._check_rate_limit('renew', user=user)
        sub = self._validate_subscription_ownership(subscription_id, user=user)

        if sub.subscription_plan_id and not sub.subscription_plan_id.allow_renewal:
            raise UserError(f'Subscription plan "{sub.subscription_plan_id.name}" does not permit renewal.')

        # Execute using Phase 6 lifecycle renewal engine
        new_sub = sub.sudo().action_renew(notes='Customer self-service portal renewal')

        self.env['brightloop.security.audit'].log_event(
            event_type='portal_subscription_renewed',
            summary=f'Subscription renewed by customer: {sub.name} -> {new_sub.name}',
            details=f'Customer renewed subscription {sub.name}; new contract {new_sub.name} created.',
        )

        return self.get_subscription_detail(new_sub.id, user=user)

    # =========================================================================
    # 5. CUSTOMER INVOICE ACCESS
    # =========================================================================

    @api.model
    def list_invoices(self, user=None, limit=50, offset=0):
        """
        List posted customer invoices belonging to the authenticated customer.

        :param user: res.users or None
        :param limit: int
        :param offset: int
        :return: dict with total count and invoice list
        """
        commercial_partner = self._get_customer_partner(user=user)
        domain = [
            ('partner_id.commercial_partner_id', '=', commercial_partner.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
        ]

        Move = self.env['account.move'].sudo()
        total = Move.search_count(domain)
        invoices = Move.search(domain, order='invoice_date desc, id desc', limit=limit, offset=offset)

        results = []
        for inv in invoices:
            results.append({
                'id': inv.id,
                'name': inv.name,
                'invoice_date': inv.invoice_date,
                'due_date': inv.invoice_date_due,
                'amount_total': inv.amount_total,
                'amount_residual': inv.amount_residual,
                'currency': inv.currency_id.name,
                'payment_state': inv.payment_state,
                'is_subscription_invoice': inv.is_subscription_invoice,
                'subscription_id': inv.subscription_id.id if inv.subscription_id else False,
            })

        return {'total': total, 'limit': limit, 'offset': offset, 'invoices': results}

    @api.model
    def get_invoice_detail(self, invoice_id, user=None):
        """
        Retrieve granular invoice details with strict internal metadata redaction.

        :param invoice_id: int
        :param user: res.users or None
        :return: dict with customer-facing invoice metadata
        """
        invoice = self._validate_invoice_ownership(invoice_id, user=user)
        invoice.invalidate_recordset(['amount_residual', 'payment_state'])

        lines = [
            {
                'id': l.id,
                'product_name': l.product_id.display_name if l.product_id else l.name,
                'quantity': l.quantity,
                'price_unit': l.price_unit,
                'discount': l.discount,
                'price_subtotal': l.price_subtotal,
                'price_total': l.price_total,
            }
            for l in invoice.invoice_line_ids
        ]

        # Reconciled payments
        reconciled_payments = invoice._get_reconciled_payments() if hasattr(invoice, '_get_reconciled_payments') else self.env['account.payment']
        payment_list = [
            {
                'id': p.id,
                'name': p.name,
                'amount': p.amount,
                'date': p.date,
                'state': p.state,
            }
            for p in reconciled_payments
        ]

        self.env['brightloop.security.audit'].log_event(
            event_type='portal_invoice_viewed',
            summary=f'Invoice viewed: {invoice.name}',
            details=f'Customer viewed invoice {invoice.name} (ID: {invoice.id}).',
        )

        return {
            'id': invoice.id,
            'name': invoice.name,
            'invoice_date': invoice.invoice_date,
            'due_date': invoice.invoice_date_due,
            'amount_untaxed': invoice.amount_untaxed,
            'amount_tax': invoice.amount_tax,
            'amount_total': invoice.amount_total,
            'amount_residual': invoice.amount_residual,
            'currency': invoice.currency_id.name,
            'payment_state': invoice.payment_state,
            'subscription_id': invoice.subscription_id.id if invoice.subscription_id else False,
            'billing_period_id': invoice.billing_period_id.id if invoice.billing_period_id else False,
            'lines': lines,
            'payments': payment_list,
        }

    @api.model
    def get_invoice_pdf(self, invoice_id, user=None):
        """
        Securely render and retrieve invoice PDF document bytes.

        Validates customer ownership before rendering. Never exposes unrestricted URLs.

        :param invoice_id: int
        :param user: res.users or None
        :return: dict with filename, binary content bytes, and content_type
        """
        invoice = self._validate_invoice_ownership(invoice_id, user=user)

        # Render using native Odoo report action
        try:
            pdf_bytes, _ = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                'account.account_invoices', [invoice.id]
            )
        except Exception as e:
            # Fallback if wkhtmltopdf or specific report template raises
            _logger.warning("Portal PDF render fallback for invoice %s: %s", invoice.id, e)
            report_action = self.env['ir.actions.report'].sudo().search(
                [('model', '=', 'account.move')], limit=1
            )
            if report_action:
                pdf_bytes, _ = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                    report_action, [invoice.id]
                )
            else:
                raise UserError(f"Invoice report template error: {e}")

        safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', invoice.name or f"invoice_{invoice.id}")
        filename = f"{safe_name}.pdf"

        self.env['brightloop.security.audit'].log_event(
            event_type='portal_invoice_document_downloaded',
            summary=f'Invoice PDF downloaded: {invoice.name}',
            details=f'Customer downloaded PDF for invoice {invoice.name}.',
        )

        return {
            'filename': filename,
            'content': pdf_bytes,
            'content_type': 'application/pdf',
        }

    # =========================================================================
    # 6. CUSTOMER PAYMENT HISTORY
    # =========================================================================

    @api.model
    def list_payments(self, user=None, limit=50, offset=0):
        """
        List all inbound payments settled for the authenticated customer.

        Delegates to Phase 9 brightloop.payment.service with customer isolation.

        :param user: res.users or None
        :param limit: int
        :param offset: int
        :return: dict with total count and payments list
        """
        commercial_partner = self._get_customer_partner(user=user)
        PaymentService = self.env['brightloop.payment.service']

        payments = PaymentService.get_customer_payment_history(partner=commercial_partner, limit=limit)
        return {
            'total': len(payments),
            'limit': limit,
            'offset': offset,
            'payments': payments[offset:offset + limit],
        }

    @api.model
    def get_payment_detail(self, payment_id, user=None):
        """
        Retrieve granular payment detail with customer ownership validation.

        :param payment_id: int
        :param user: res.users or None
        :return: dict with payment metadata
        """
        pay = self._validate_payment_ownership(payment_id, user=user)
        invoices = pay.reconciled_invoice_ids or pay.invoice_ids

        return {
            'id': pay.id,
            'name': pay.name,
            'amount': pay.amount,
            'currency': pay.currency_id.name,
            'date': pay.date,
            'memo': pay.memo,
            'state': pay.state,
            'subscription_id': pay.subscription_id.id if pay.subscription_id else False,
            'billing_period_id': pay.billing_period_id.id if pay.billing_period_id else False,
            'invoices': [{'id': inv.id, 'name': inv.name, 'amount_total': inv.amount_total} for inv in invoices],
        }

    # =========================================================================
    # 7. CONSOLIDATED BILLING TIMELINE
    # =========================================================================

    @api.model
    def get_billing_timeline(self, subscription_id=None, user=None, limit=50, offset=0):
        """
        Retrieve a consolidated chronological timeline of billing events:
        - Contract lifecycle changes (activation, pause, resume, renewal, closure)
        - Billing periods created
        - Invoices generated
        - Payments applied

        Ordered descending by timestamp with pagination.

        :param subscription_id: int or None (filters to a specific contract if provided)
        :param user: res.users or None
        :param limit: int
        :param offset: int
        :return: dict with total count and timeline events
        """
        commercial_partner = self._get_customer_partner(user=user)
        events = []

        # 1. Subscription Contracts
        sub_domain = [('customer_id.commercial_partner_id', '=', commercial_partner.id)]
        if subscription_id:
            self._validate_subscription_ownership(subscription_id, user=user)
            sub_domain.append(('id', '=', subscription_id))

        subs = self.env['brightloop.subscription'].sudo().search(sub_domain)
        sub_ids = subs.ids

        # 2. Subscription Lifecycle History Events
        if sub_ids:
            histories = self.env['brightloop.subscription.history'].sudo().search([
                ('subscription_id', 'in', sub_ids)
            ], order='timestamp desc')
            for h in histories:
                events.append({
                    'timestamp': h.timestamp,
                    'event_type': f"subscription_{h.event_type}",
                    'summary': f"Subscription {h.subscription_id.name}: {h.event_type.title()}",
                    'details': h.reason or '',
                    'subscription_id': h.subscription_id.id,
                    'subscription_name': h.subscription_id.name,
                    'reference_id': h.id,
                    'category': 'lifecycle',
                })

        # 3. Invoices
        inv_domain = [
            ('partner_id.commercial_partner_id', '=', commercial_partner.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
        ]
        if sub_ids:
            inv_domain.append(('subscription_id', 'in', sub_ids))

        invoices = self.env['account.move'].sudo().search(inv_domain, order='invoice_date desc')
        for inv in invoices:
            dt = datetime.combine(inv.invoice_date, datetime.min.time()) if inv.invoice_date else inv.create_date
            events.append({
                'timestamp': dt,
                'event_type': 'invoice_generated',
                'summary': f"Invoice {inv.name} Generated ({inv.amount_total} {inv.currency_id.name})",
                'details': f"Payment status: {inv.payment_state.title()}, Residual: {inv.amount_residual} {inv.currency_id.name}",
                'subscription_id': inv.subscription_id.id if inv.subscription_id else False,
                'subscription_name': inv.subscription_id.name if inv.subscription_id else '',
                'reference_id': inv.id,
                'category': 'invoice',
            })

        # 4. Payments
        pay_domain = [
            ('partner_id.commercial_partner_id', '=', commercial_partner.id),
            ('payment_type', '=', 'inbound'),
            ('state', 'in', ('paid', 'reconciled')),
        ]
        if sub_ids:
            pay_domain.append(('subscription_id', 'in', sub_ids))

        payments = self.env['account.payment'].sudo().search(pay_domain, order='date desc')
        for p in payments:
            dt = datetime.combine(p.date, datetime.min.time()) if p.date else p.create_date
            events.append({
                'timestamp': dt,
                'event_type': 'payment_applied',
                'summary': f"Payment {p.name} Applied ({p.amount} {p.currency_id.name})",
                'details': f"Memo: {p.memo or 'Subscription Payment'}",
                'subscription_id': p.subscription_id.id if p.subscription_id else False,
                'subscription_name': p.subscription_id.name if p.subscription_id else '',
                'reference_id': p.id,
                'category': 'payment',
            })

        # Sort combined events descending by timestamp
        events.sort(key=lambda x: str(x['timestamp']), reverse=True)

        total = len(events)
        paged_events = events[offset:offset + limit]

        # Format timestamps as strings for serializable output
        formatted_events = []
        for e in paged_events:
            item = dict(e)
            item['timestamp'] = str(e['timestamp'])
            formatted_events.append(item)

        return {'total': total, 'limit': limit, 'offset': offset, 'timeline': formatted_events}

