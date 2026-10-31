# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.billing_service
#
# Subscription Billing Engine Service for Brightloop Subscription Intelligence
#
# PHASE 8 SCOPE
# -------------
# - Discovers subscriptions due for recurring billing.
# - Computes gapless, calendar-aware billing periods preserving anchor dates.
# - Enforces PostgreSQL-level and transactional idempotency.
# - Generates native Odoo customer invoices (account.move) with full line traceability.
# - Revalidates recurring discounts and calculates real-time taxes.
# - Advances subscription billing schedules transactionally upon success.
# - Supports automated recovery of missed billing periods.
# - Provides bounded retry handling for temporary failures with failure isolation.
# - Exposes high-throughput batch processing for scheduled actions.
# =============================================================================

import json
import logging
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError, AccessError

_logger = logging.getLogger(__name__)


class BrightloopBillingService(models.AbstractModel):
    """
    Brightloop Automated Recurring Billing Service.

    Orchestrates recurring billing cycles, invoice generation, discount
    revalidation, tax application, and billing date progression.

    Stateless AbstractModel service suitable for CLI, API, crons, and manual triggers.
    """
    _name = 'brightloop.billing.service'
    _description = 'Brightloop Automated Recurring Billing Service'

    # =========================================================================
    # 1. DUE SUBSCRIPTION DISCOVERY
    # =========================================================================

    @api.model
    def get_due_subscriptions(self, company=None, target_date=None, limit=None):
        """
        Query active subscriptions whose next billing date has arrived.

        Rules:
        - Only state == 'active'.
        - Paused, closed, or draft subscriptions are strictly excluded.
        - next_billing_date <= target_date (default today).
        - Optionally scoped to a specific company.

        :param company: res.company record or None
        :param target_date: date object or None (defaults to today)
        :param limit: int or None for pagination / batch bounding
        :return: brightloop.subscription recordset
        """
        today = target_date or fields.Date.context_today(self)
        domain = [
            ('state', '=', 'active'),
            ('next_billing_date', '!=', False),
            ('next_billing_date', '<=', today),
        ]
        if company:
            domain.append(('company_id', '=', company.id))

        return self.env['brightloop.subscription'].search(domain, order='next_billing_date asc, id asc', limit=limit)

    # =========================================================================
    # 2. BILLING PERIOD CALCULATION
    # =========================================================================

    @api.model
    def calculate_billing_period(self, subscription, target_date=None):
        """
        Calculate the exact billing period boundaries for a subscription.

        Inclusive Boundary Convention:
          - billing_period_start: inclusive first day of the cycle.
          - billing_period_end: inclusive last day of the cycle.
          - next_cycle_start: billing_period_end + 1 day.

        Gapless Chain Rule:
          - If the subscription has prior billing periods, the new period starts
            on (latest_period.billing_period_end + 1 day).
          - Otherwise, it starts on subscription.start_date.

        Calendar & Anchor Preservation:
          - Uses Phase 4 calendar utilities to compute the cycle boundary,
            preserving month-end anchors (e.g. 31st).

        :param subscription: brightloop.subscription record
        :param target_date: evaluation date or None
        :return: dict with period dates and idempotency key
        """
        plan_obj = self.env['brightloop.subscription.plan']
        interval = subscription.billing_interval or 'monthly'
        interval_count = subscription.billing_interval_count or 1
        anchor = subscription.billing_anchor_date or subscription.start_date

        # Determine start date: chain from prior period or start_date
        prior_periods = self.env['brightloop.billing.period'].search([
            ('subscription_id', '=', subscription.id),
            ('status', 'not in', ('cancelled', 'skipped')),
        ], order='billing_period_end desc', limit=1)

        if prior_periods and prior_periods.billing_period_end:
            period_start = prior_periods.billing_period_end + relativedelta(days=1)
        else:
            period_start = subscription.start_date or fields.Date.context_today(self)

        # Compute next cycle start date preserving anchor
        next_cycle_date = plan_obj.calculate_billing_date(
            billing_interval=interval,
            interval_count=interval_count,
            start_date=period_start,
            anchor_date=anchor,
        )

        # Inclusive period end date is one day prior to next cycle start
        period_end = next_cycle_date - relativedelta(days=1)

        # The billing date is the subscription's scheduled next billing date
        billing_date = subscription.next_billing_date or period_start

        idempotency_key = f"sub_{subscription.id}_{period_start}_{period_end}"

        return {
            'period_start': period_start,
            'period_end': period_end,
            'billing_date': billing_date,
            'next_cycle_date': next_cycle_date,
            'idempotency_key': idempotency_key,
        }

    # =========================================================================
    # 3. BILLING PERIOD CREATION & IDEMPOTENCY
    # =========================================================================

    @api.model
    def create_or_get_billing_period(self, subscription, period_start, period_end, billing_date, idempotency_key):
        """
        Create a new billing period or return an existing one idempotently.

        Guarantees PostgreSQL-level duplicate prevention via UNIQUE constraint.

        :return: tuple (period_record, created_bool)
        """
        Period = self.env['brightloop.billing.period']
        existing = Period.search([('idempotency_key', '=', idempotency_key)], limit=1)
        if existing:
            self.env['brightloop.security.audit'].log_event(
                event_type='billing_duplicate_prevented',
                summary=f'Duplicate billing period detected: {idempotency_key}',
                details=f'Billing period with idempotency key "{idempotency_key}" already exists (Status: {existing.status}).',
            )
            return existing, False

        period_vals = {
            'subscription_id': subscription.id,
            'customer_id': subscription.customer_id.id,
            'company_id': subscription.company_id.id,
            'currency_id': subscription.currency_id.id,
            'billing_period_start': period_start,
            'billing_period_end': period_end,
            'billing_date': billing_date,
            'billing_interval': subscription.billing_interval,
            'billing_interval_count': subscription.billing_interval_count,
            'idempotency_key': idempotency_key,
            'status': 'pending',
        }
        period = Period.create(period_vals)

        self.env['brightloop.security.audit'].log_event(
            event_type='billing_period_created',
            summary=f'Billing period created: {subscription.name}',
            details=(
                f'Created billing period {period_start} to {period_end} for subscription "{subscription.name}" '
                f'(Key: {idempotency_key}).'
            ),
        )
        return period, True

    # =========================================================================
    # 4. INVOICE GENERATION
    # =========================================================================

    @api.model
    def generate_invoice(self, billing_period, _journal_cache=None):
        """
        Generate a native Odoo customer invoice (account.move) for a billing period.

        Idempotency:
        - If the period already has an invoice_id, return it immediately.
        - If the subscription is not active, marks period as skipped.

        Financial Processing:
        - Revalidates recurring discounts for each line via brightloop.discount.service.
        - Applies current product taxes via brightloop.tax.service.
        - Atomically consumes discount usage upon invoice creation.
        - Advances subscription next_billing_date upon success.

        :param billing_period: brightloop.billing.period record
        :param _journal_cache: optional dict keyed by company_id.id → account.journal record
                               (used by process_due_billing_batch to avoid repeated searches)
        :return: account.move record
        """
        subscription = billing_period.subscription_id

        # 1. Idempotency Check
        if billing_period.invoice_id:
            _logger.info('Billing period %s already invoiced with move %s.', billing_period.id, billing_period.invoice_id.id)
            return billing_period.invoice_id

        # 2. Subscription State Validation
        if subscription.state != 'active':
            billing_period.write({
                'status': 'skipped',
                'failure_reason': f'Subscription "{subscription.name}" is in state "{subscription.state}". Only active subscriptions are billed.',
                'last_attempt_date': fields.Datetime.now(),
            })
            self.env['brightloop.security.audit'].log_event(
                event_type='billing_period_skipped',
                summary=f'Billing period skipped: {subscription.name}',
                details=f'Subscription "{subscription.name}" is {subscription.state}; billing skipped.',
            )
            return False

        # 3. Locate Sales Journal — use caller-supplied cache for batch efficiency
        # During a 1,000-subscription batch, this avoids 1,000 repeated SQL searches.
        Journal = self.env['account.journal']
        company_id = subscription.company_id.id
        if _journal_cache is not None and company_id in _journal_cache:
            journal = _journal_cache[company_id]
        else:
            journal = Journal.search([
                ('type', '=', 'sale'),
                ('company_id', '=', company_id),
            ], limit=1)
            if not journal:
                journal = Journal.search([('type', '=', 'sale')], limit=1)
            if _journal_cache is not None:
                _journal_cache[company_id] = journal
        if not journal:
            raise UserError(f'No customer sales journal found for company "{subscription.company_id.name}".')

        billing_period.write({'status': 'processing', 'last_attempt_date': fields.Datetime.now()})

        # 4. Build Invoice Lines with Real-Time Discount & Tax Calculation
        invoice_lines_data = []
        applied_discounts_to_increment = []
        discount_service = self.env['brightloop.discount.service']

        for sub_line in subscription.subscription_line_ids:
            eff_discount = sub_line.discount or 0.0

            # Revalidate recurring discount
            if sub_line.discount_id:
                elig_result = discount_service.validate_recurring_discount(
                    discount=sub_line.discount_id,
                    billing_date=billing_period.billing_date,
                    subscription_plan=sub_line.subscription_plan_id,
                    product=sub_line.product_id,
                    quantity=sub_line.quantity,
                    purchase_amount=sub_line.price_unit * sub_line.quantity,
                    company=subscription.company_id,
                    currency=subscription.currency_id,
                )
                if elig_result.get('eligible'):
                    eff_discount = sub_line.discount
                    applied_discounts_to_increment.append(sub_line.discount_id)
                else:
                    _logger.info(
                        'Recurring discount "%s" is no longer eligible on subscription %s: %s. Discount dropped to 0%%.',
                        sub_line.discount_id.name, subscription.name, elig_result.get('reason')
                    )
                    eff_discount = 0.0

            # Real-time taxes from product
            taxes = sub_line.product_id.taxes_id if hasattr(sub_line.product_id, 'taxes_id') else self.env['account.tax']
            tax_ids = taxes.ids

            line_vals = {
                'product_id': sub_line.product_id.id,
                'quantity': sub_line.quantity,
                'price_unit': sub_line.price_unit,
                'discount': eff_discount,
                'tax_ids': [(6, 0, tax_ids)],
                'name': (
                    f"{sub_line.product_id.display_name} "
                    f"[{billing_period.billing_period_start} to {billing_period.billing_period_end}]"
                ),
                'subscription_id': subscription.id,
                'subscription_line_id': sub_line.id,
            }
            invoice_lines_data.append((0, 0, line_vals))

        if not invoice_lines_data:
            raise UserError(f'Subscription "{subscription.name}" has no lines to bill.')

        # 5. Create Native account.move Customer Invoice
        move_vals = {
            'move_type': 'out_invoice',
            'partner_id': billing_period.customer_id.id,
            'invoice_date': billing_period.billing_date,
            'company_id': subscription.company_id.id,
            'currency_id': subscription.currency_id.id,
            'journal_id': journal.id,
            'subscription_id': subscription.id,
            'billing_period_id': billing_period.id,
            'billing_period_start': billing_period.billing_period_start,
            'billing_period_end': billing_period.billing_period_end,
            'is_subscription_invoice': True,
            'invoice_line_ids': invoice_lines_data,
        }

        invoice = self.env['account.move'].create(move_vals)

        # 6. Consume discount usage atomically
        for disc in applied_discounts_to_increment:
            try:
                disc._increment_usage()
            except Exception as e:
                _logger.warning('Failed to increment usage for discount %s: %s', disc.name, e)

        # 7. Update Billing Period Record
        billing_period.write({
            'invoice_id': invoice.id,
            'status': 'invoiced',
            'amount_untaxed': invoice.amount_untaxed,
            'amount_tax': invoice.amount_tax,
            'amount_total': invoice.amount_total,
            'failure_reason': False,
        })

        # 8. Advance Subscription Billing Dates
        plan_obj = self.env['brightloop.subscription.plan']
        next_billing_date = plan_obj.calculate_billing_date(
            billing_interval=subscription.billing_interval,
            interval_count=subscription.billing_interval_count,
            start_date=billing_period.billing_period_start,
            anchor_date=subscription.billing_anchor_date or subscription.start_date,
        )

        subscription.write({
            'last_billing_date': billing_period.billing_date,
            'next_billing_date': next_billing_date,
        })

        # 9. Audit Logging
        self.env['brightloop.security.audit'].log_event(
            event_type='invoice_generated',
            summary=f'Recurring invoice generated: {invoice.name or invoice.id}',
            details=(
                f'Generated invoice ID={invoice.id} for subscription "{subscription.name}" '
                f'(Period: {billing_period.billing_period_start} to {billing_period.billing_period_end}, '
                f'Total: {invoice.amount_total} {invoice.currency_id.name}).'
            ),
        )

        self.env['brightloop.security.audit'].log_event(
            event_type='next_billing_date_updated',
            summary=f'Next billing date updated: {subscription.name}',
            details=f'Subscription "{subscription.name}" next billing date advanced to {next_billing_date}.',
        )

        subscription._record_history(
            event_type='invoice_generated',
            previous_state=subscription.state,
            new_state=subscription.state,
            reason=f'Recurring invoice generated for period {billing_period.billing_period_start} to {billing_period.billing_period_end}',
            metadata={'invoice_id': invoice.id, 'period_id': billing_period.id, 'total': invoice.amount_total},
        )

        return invoice

    # =========================================================================
    # 5. SINGLE SUBSCRIPTION BILLING ORCHESTRATION
    # =========================================================================

    @api.model
    def process_subscription_billing(self, subscription, target_date=None, _journal_cache=None):
        """
        Process a full billing cycle for a single subscription with row-level locking.

        Acquires PostgreSQL row lock (SELECT FOR UPDATE) on the subscription
        to guarantee concurrent processes cannot double-bill.

        :param subscription: brightloop.subscription record
        :param target_date: date object or None (default today)
        :param _journal_cache: optional dict keyed by company_id.id → account.journal record
                               (supplied by process_due_billing_batch to avoid repeated journal searches)
        :return: dict with processing result
        """
        today = target_date or fields.Date.context_today(self)

        # Flush only state-relevant fields before the raw SQL lock to minimise
        # ORM dirty-check overhead in large accumulated test transactions.
        subscription.flush_recordset(['state', 'next_billing_date'])

        # Acquire database row-level lock
        self.env.cr.execute(
            'SELECT id, state, next_billing_date FROM brightloop_subscription WHERE id = %s FOR UPDATE',
            (subscription.id,)
        )
        sub_row = self.env.cr.fetchone()
        if not sub_row:
            return {'success': False, 'error': f'Subscription {subscription.id} not found.'}

        sub_id, sub_state, sub_next_bill = sub_row
        if sub_state != 'active':
            return {'success': False, 'skipped': True, 'reason': f'Subscription is {sub_state}.'}

        if sub_next_bill and sub_next_bill > today:
            return {'success': False, 'skipped': True, 'reason': f'Not due yet (due {sub_next_bill}).'}

        self.env['brightloop.security.audit'].log_event(
            event_type='billing_started',
            summary=f'Billing cycle started: {subscription.name}',
            details=f'Starting billing evaluation for subscription "{subscription.name}" on {today}.',
        )

        # Calculate period
        calc_res = self.calculate_billing_period(subscription, target_date=today)
        period, created = self.create_or_get_billing_period(
            subscription=subscription,
            period_start=calc_res['period_start'],
            period_end=calc_res['period_end'],
            billing_date=calc_res['billing_date'],
            idempotency_key=calc_res['idempotency_key'],
        )

        if period.status == 'invoiced' and period.invoice_id:
            return {
                'success': True,
                'billing_period_id': period.id,
                'invoice_id': period.invoice_id.id,
                'existing': True,
            }

        try:
            invoice = self.generate_invoice(period, _journal_cache=_journal_cache)
            return {
                'success': True,
                'billing_period_id': period.id,
                'invoice_id': invoice.id if invoice else False,
                'existing': False,
            }
        except Exception as e:
            _logger.exception('Invoice generation failed for period %s: %s', period.id, e)
            period.write({
                'status': 'failed',
                'failure_reason': str(e),
                'retry_count': period.retry_count + 1,
                'last_attempt_date': fields.Datetime.now(),
            })
            self.env['brightloop.security.audit'].log_event(
                event_type='invoice_generation_failed',
                summary=f'Invoice generation failed: {subscription.name}',
                details=f'Failed billing period {period.id} for subscription "{subscription.name}": {str(e)}',
            )
            return {'success': False, 'error': str(e), 'billing_period_id': period.id}

    # =========================================================================
    # 6. MISSED BILLING RECOVERY
    # =========================================================================

    @api.model
    def recover_missed_billing(self, subscription, target_date=None, max_periods=12):
        """
        Recover consecutive missed billing periods for an active subscription.

        If a subscription is overdue by multiple cycles (e.g. server outage),
        this engine iterates sequentially, generating missing invoices in
        historical chronological order until next_billing_date is brought up
        to date.

        :param subscription: brightloop.subscription record
        :param target_date: date object (defaults to today)
        :param max_periods: safety ceiling to prevent infinite loops (default 12)
        :return: list of generated invoice records
        """
        today = target_date or fields.Date.context_today(self)
        generated_invoices = []
        count = 0

        while (
            subscription.state == 'active'
            and subscription.next_billing_date
            and subscription.next_billing_date <= today
            and count < max_periods
        ):
            res = self.process_subscription_billing(subscription, target_date=today)
            if not res.get('success'):
                _logger.warning('Recovery stopped for subscription %s due to error: %s', subscription.name, res.get('error'))
                break

            inv_id = res.get('invoice_id')
            if inv_id:
                inv = self.env['account.move'].browse(inv_id)
                generated_invoices.append(inv)

            count += 1
            # Re-read subscription to get updated next_billing_date
            subscription.invalidate_recordset(['next_billing_date', 'last_billing_date'])

        if generated_invoices:
            self.env['brightloop.security.audit'].log_event(
                event_type='billing_recovered',
                summary=f'Missed billing recovered: {subscription.name}',
                details=f'Recovered {len(generated_invoices)} missed billing periods for subscription "{subscription.name}".',
            )

        return generated_invoices

    # =========================================================================
    # 7. FAILED BILLING RETRIES
    # =========================================================================

    @api.model
    def retry_failed_billing(self, billing_period):
        """
        Retry invoice generation for a failed billing period.

        Bounded retry policy:
        - Max 3 automatic retries.
        - Increments retry_count.
        - Records new failure reason or marks invoiced upon success.

        :param billing_period: brightloop.billing.period record
        :return: account.move record or False
        """
        if billing_period.retry_count >= 3:
            raise UserError(
                f'Billing period {billing_period.id} has reached maximum retry attempts ({billing_period.retry_count}). '
                'Manual administrator intervention required.'
            )

        self.env['brightloop.security.audit'].log_event(
            event_type='invoice_generation_retried',
            summary=f'Retrying failed billing period: {billing_period.id}',
            details=f'Retry attempt {billing_period.retry_count + 1} for period {billing_period.id}.',
        )

        billing_period.write({
            'retry_count': billing_period.retry_count + 1,
            'last_attempt_date': fields.Datetime.now(),
        })

        try:
            invoice = self.generate_invoice(billing_period)
            return invoice
        except Exception as e:
            billing_period.write({
                'status': 'failed',
                'failure_reason': str(e),
            })
            raise

    # =========================================================================
    # 8. BATCH PROCESSING ENGINE (CRON ENTRYPOINT)
    # =========================================================================

    @api.model
    def process_due_billing_batch(self, company=None, target_date=None, batch_size=100):
        """
        Bounded batch processor for scheduled actions.

        Features:
        - Failure isolation: savepoint per subscription so one failure never
          aborts the remaining batch.
        - High-throughput query execution via a pre-built per-company journal cache.
          This eliminates N repeated SQL searches for the sales journal when
          processing a large batch with subscriptions on the same company.
        - Safe repeated execution (idempotent).

        :param company: res.company or None
        :param target_date: date or None
        :param batch_size: int (default 100)
        :return: dict with summary metrics (processed, success, failed, skipped)
        """
        due_subs = self.get_due_subscriptions(company=company, target_date=target_date, limit=batch_size)
        metrics = {'processed': 0, 'success': 0, 'failed': 0, 'skipped': 0, 'invoices_created': 0}

        # Pre-build sales journal cache keyed by company_id to avoid a SQL
        # journal search per subscription inside generate_invoice().
        journal_cache = {}

        for sub in due_subs:
            metrics['processed'] += 1
            try:
                with self.env.cr.savepoint():
                    res = self.process_subscription_billing(
                        sub, target_date=target_date, _journal_cache=journal_cache
                    )
                    if res.get('success'):
                        metrics['success'] += 1
                        if not res.get('existing'):
                            metrics['invoices_created'] += 1
                    elif res.get('skipped'):
                        metrics['skipped'] += 1
                    else:
                        metrics['failed'] += 1
            except Exception as e:
                _logger.exception('Unhandled exception processing subscription %s in batch: %s', sub.id, e)
                metrics['failed'] += 1

        return metrics

