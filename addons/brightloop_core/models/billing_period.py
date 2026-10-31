# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.billing_period
#
# Subscription Billing Period Model for Brightloop Subscription Intelligence
#
# PHASE 8 SCOPE
# -------------
# - Represents discrete contract billing cycles (e.g., month, quarter, year).
# - Stores unique deterministic idempotency key for duplicate prevention.
# - Enforces PostgreSQL-level uniqueness constraints.
# - Tracks invoice creation, status transitions, failure reasons, and retries.
# - Links to native account.move customer invoices.
# - Maintains financial totals (untaxed, tax, total) for the billing cycle.
# =============================================================================

import logging
from odoo import api, fields, models
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class BrightloopBillingPeriod(models.Model):
    """
    Subscription Billing Period.

    Represents a single billing cycle for a subscription contract.
    Guarantees strict 1:1 traceability between a subscription billing period
    and a generated customer invoice.
    """
    _name = 'brightloop.billing.period'
    _inherit = ['brightloop.base']
    _description = 'Brightloop Subscription Billing Period'
    _order = 'billing_period_start desc, id desc'

    # =========================================================================
    # CORE CONTRACT & PARTNER REFERENCES
    # =========================================================================

    subscription_id = fields.Many2one(
        comodel_name='brightloop.subscription',
        string='Subscription',
        required=True,
        ondelete='cascade',
        index=True,
        check_company=True,
        help='The subscription contract for which this billing period applies.',
    )

    customer_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer',
        required=True,
        index=True,
        check_company=True,
        help='Customer billed for this period.',
    )

    # =========================================================================
    # PERIOD DATES & CALENDAR DEFINITION
    # =========================================================================

    billing_period_start = fields.Date(
        string='Period Start (Inclusive)',
        required=True,
        index=True,
        help='First day of service for this billing cycle.',
    )

    billing_period_end = fields.Date(
        string='Period End (Inclusive)',
        required=True,
        index=True,
        help='Last day of service for this billing cycle.',
    )

    billing_date = fields.Date(
        string='Billing / Invoice Date',
        required=True,
        index=True,
        help='Date when the invoice is scheduled or generated.',
    )

    billing_interval = fields.Selection(
        selection=[
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('yearly', 'Yearly'),
        ],
        string='Billing Frequency',
        required=True,
        default='monthly',
    )

    billing_interval_count = fields.Integer(
        string='Billing Interval Count',
        required=True,
        default=1,
    )

    # =========================================================================
    # STATUS & INVOICE TRACEABILITY
    # =========================================================================

    status = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('invoiced', 'Invoiced'),
            ('failed', 'Failed'),
            ('skipped', 'Skipped'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        required=True,
        default='pending',
        index=True,
    )

    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Customer Invoice',
        readonly=True,
        copy=False,
        index=True,
        help='Generated native Odoo customer invoice for this billing period.',
    )

    # =========================================================================
    # IDEMPOTENCY & CONCURRENCY
    # =========================================================================

    idempotency_key = fields.Char(
        string='Idempotency Key',
        required=True,
        readonly=True,
        index=True,
        copy=False,
        help='Deterministic hash: sub_{sub_id}_{start_date}_{end_date}. '
             'Enforces database-level uniqueness to prevent duplicate invoices.',
    )

    # =========================================================================
    # RETRY & ERROR TRACKING
    # =========================================================================

    retry_count = fields.Integer(
        string='Retry Count',
        default=0,
        readonly=True,
        help='Number of times invoice generation was retried after failure.',
    )

    last_attempt_date = fields.Datetime(
        string='Last Attempt Date',
        readonly=True,
    )

    failure_reason = fields.Text(
        string='Failure Reason',
        readonly=True,
        help='Descriptive error message captured if invoice generation failed.',
    )

    # =========================================================================
    # FINANCIAL TOTALS
    # =========================================================================

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )

    amount_untaxed = fields.Monetary(
        string='Untaxed Amount',
        currency_field='currency_id',
        default=0.0,
    )

    amount_tax = fields.Monetary(
        string='Tax Amount',
        currency_field='currency_id',
        default=0.0,
    )

    amount_total = fields.Monetary(
        string='Total Amount',
        currency_field='currency_id',
        default=0.0,
    )

    # =========================================================================
    # CONSTRAINTS (Odoo 20 models.Constraint)
    # =========================================================================

    _idempotency_key_uniq = models.Constraint(
        'UNIQUE (idempotency_key)',
        'A billing period with this idempotency key already exists. Duplicate period creation is prohibited.',
    )

    _period_range_uniq = models.Constraint(
        'UNIQUE (subscription_id, billing_period_start, billing_period_end)',
        'A billing period for this subscription and date range already exists.',
    )

    @api.constrains('billing_period_start', 'billing_period_end')
    def _check_period_dates(self):
        for period in self:
            if period.billing_period_start and period.billing_period_end:
                if period.billing_period_start > period.billing_period_end:
                    raise ValidationError(
                        f'Billing period start date ({period.billing_period_start}) '
                        f'cannot be later than end date ({period.billing_period_end}).'
                    )

    # =========================================================================
    # ACTIONS
    # =========================================================================

    def action_retry(self):
        """
        Authorized manual retry of a failed billing period.
        """
        for period in self:
            if period.status != 'failed':
                raise UserError(f'Only failed billing periods can be retried (current status: {period.status}).')
            self.env['brightloop.billing.service'].retry_failed_billing(period)
        return True

    @api.model
    def _cron_process_due_billing(self, limit=100):
        """
        Scheduled action: process due subscription recurring billing batch.
        """
        service = self.env['brightloop.billing.service']
        return service.process_due_billing_batch(limit=limit)

    @api.model
    def _cron_retry_failed_periods(self, batch_size=50):
        """
        Scheduled action: automatically retry failed billing periods with retry_count < 3.
        """
        failed_periods = self.search([
            ('status', '=', 'failed'),
            ('retry_count', '<', 3),
        ], limit=batch_size)
        retried = 0
        service = self.env['brightloop.billing.service']
        for period in failed_periods:
            try:
                with self.env.cr.savepoint():
                    service.retry_failed_billing(period)
                    retried += 1
            except Exception as e:
                _logger.warning('Cron retry failed for period %s: %s', period.id, e)
        return retried
