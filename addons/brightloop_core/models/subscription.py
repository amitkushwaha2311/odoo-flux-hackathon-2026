# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.subscription
#
# Subscription Lifecycle Engine for Brightloop Subscription Intelligence
#
# PHASE 6 SCOPE
# -------------
# - Transforms confirmed quotations into managed subscription contracts.
# - Manages subscription lines, customer ownership, company and currency consistency.
# - State machine: Draft -> Confirmed -> Active <-> Paused -> Closed.
# - Dedicated lifecycle actions: confirm, activate, pause, resume, close, renew.
# - Explicit pause policy and billing schedule extension.
# - Automatic closure cron for contracts reaching configured end dates.
# - Full traceability, renewal lineage, and immutable lifecycle history.
# - Role-based permissions (Admin full CRUD, Staff operational, Customer isolated).
# - Immutable audit logging for all lifecycle transitions.
# =============================================================================

import json
import logging
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class BrightloopSubscription(models.Model):
    _name = 'brightloop.subscription'
    _inherit = ['brightloop.base']
    _description = 'Brightloop Subscription Contract'
    _order = 'id desc'

    _name_uniq = models.Constraint('UNIQUE (name)', 'Subscription reference must be unique.')
    _source_order_uniq = models.Constraint('UNIQUE (source_order_id)', 'A subscription has already been created for this source quotation.')

    # =========================================================================
    # CORE FIELDS & IDENTIFIERS
    # =========================================================================

    name = fields.Char(
        string='Subscription Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('brightloop.subscription') or 'New',
        index=True,
    )

    customer_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer',
        required=True,
        index=True,
        check_company=True,
        help='Subscriber partner holding commercial ownership of this contract.',
    )

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner',
        related='customer_id',
        store=True,
        readonly=True,
        index=True,
        help='Mirror partner field for Odoo partner security filters and portal record rules.',
    )

    source_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Source Quotation / Order',
        readonly=True,
        copy=False,
        index=True,
        check_company=True,
        help='Traceability to the confirmed sales order from which this subscription was generated.',
    )

    subscription_plan_id = fields.Many2one(
        comodel_name='brightloop.subscription.plan',
        string='Primary Subscription Plan',
        check_company=True,
        index=True,
        help='Primary commercial plan associated with this subscription header.',
    )

    subscription_line_ids = fields.One2many(
        comodel_name='brightloop.subscription.line',
        inverse_name='subscription_id',
        string='Subscription Lines',
        copy=True,
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
        help='Commercial currency of this subscription contract.',
    )

    # =========================================================================
    # DATES & BILLING SCHEDULE
    # =========================================================================

    start_date = fields.Date(
        string='Start Date',
        required=True,
        default=fields.Date.context_today,
        index=True,
        help='Contractual commencement date.',
    )

    end_date = fields.Date(
        string='End Date',
        index=True,
        help='Optional contract expiration date. Required for auto-close eligibility.',
    )

    next_billing_date = fields.Date(
        string='Next Billing Date',
        index=True,
        help='Next scheduled billing cycle execution date.',
    )

    last_billing_date = fields.Date(
        string='Last Billing Date',
        readonly=True,
        help='Date on which the last billing cycle was processed.',
    )

    billing_anchor_date = fields.Date(
        string='Billing Anchor Date',
        help='Persistent anchor date used to avoid month-end drift across calendar cycles (e.g. Jan 31 -> Feb 28 -> Mar 31).',
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
        index=True,
    )

    billing_interval_count = fields.Integer(
        string='Billing Interval Count',
        required=True,
        default=1,
        help='Number of billing intervals per cycle (e.g., 3 for quarterly).',
    )

    # =========================================================================
    # TOTALS & RECURRING FINANCIALS
    # =========================================================================

    quantity = fields.Float(
        string='Total Quantity',
        compute='_compute_totals',
        store=True,
        default=1.0,
    )

    recurring_amount = fields.Monetary(
        string='Recurring Amount',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
        help='Total recurring financial amount due every billing cycle.',
    )

    # =========================================================================
    # STATE MACHINE & LIFECYCLE DATES
    # =========================================================================

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('active', 'Active'),
            ('paused', 'Paused'),
            ('closed', 'Closed'),
        ],
        string='Status',
        required=True,
        default='draft',
        readonly=True,
        index=True,
    )

    pause_date = fields.Date(
        string='Pause Date',
        readonly=True,
        help='Date when subscription was suspended.',
    )

    resume_date = fields.Date(
        string='Resume Date',
        readonly=True,
        help='Date when subscription was resumed from suspension.',
    )

    closure_date = fields.Date(
        string='Closure Date',
        readonly=True,
        help='Date when subscription was terminated or expired.',
    )

    closure_reason = fields.Text(
        string='Closure Reason',
        readonly=True,
    )

    # =========================================================================
    # RENEWAL & TRACEABILITY
    # =========================================================================

    renewal_count = fields.Integer(
        string='Renewal Count',
        default=0,
        readonly=True,
        help='Number of times this subscription contract lineage has renewed.',
    )

    previous_subscription_id = fields.Many2one(
        comodel_name='brightloop.subscription',
        string='Previous Subscription',
        readonly=True,
        copy=False,
        index=True,
        help='Prior subscription contract that renewed into this record.',
    )

    renewed_subscription_ids = fields.One2many(
        comodel_name='brightloop.subscription',
        inverse_name='previous_subscription_id',
        string='Renewed Subscriptions',
        readonly=True,
    )

    history_ids = fields.One2many(
        comodel_name='brightloop.subscription.history',
        inverse_name='subscription_id',
        string='Lifecycle History',
        readonly=True,
    )

    billing_period_ids = fields.One2many(
        comodel_name='brightloop.billing.period',
        inverse_name='subscription_id',
        string='Billing Periods',
        readonly=True,
    )

    notes = fields.Text(
        string='Internal Notes',
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        help='Set to False to archive.',
    )

    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================

    @api.depends('subscription_line_ids.quantity', 'subscription_line_ids.price_subtotal')
    def _compute_totals(self):
        for sub in self:
            sub.quantity = sum(line.quantity for line in sub.subscription_line_ids) or 1.0
            sub.recurring_amount = sum(line.price_subtotal for line in sub.subscription_line_ids)

    # =========================================================================
    # CONSTRAINTS
    # =========================================================================

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for sub in self:
            if sub.start_date and sub.end_date and sub.start_date > sub.end_date:
                raise ValidationError(
                    f'Subscription start date ({sub.start_date}) cannot be later than end date ({sub.end_date}).'
                )

    @api.constrains('source_order_id')
    def _check_source_order_unique(self):
        for sub in self:
            if sub.source_order_id:
                existing = self.search([
                    ('source_order_id', '=', sub.source_order_id.id),
                    ('id', '!=', sub.id),
                ])
                if existing:
                    raise ValidationError(
                        f'A subscription ({existing[0].name}) already exists for quotation {sub.source_order_id.name}.'
                    )

    @api.constrains('billing_interval_count')
    def _check_interval_count(self):
        for sub in self:
            if sub.billing_interval_count is None or sub.billing_interval_count <= 0:
                raise ValidationError('Billing interval count must be strictly greater than zero.')

    # =========================================================================
    # ORM OVERRIDES & ACCESS GUARDS
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        caller = self.env.user
        caller_is_admin = (
            self.env.is_admin()
            or caller.has_group('brightloop_core.group_brightloop_admin')
            or self.env.is_superuser()
        )
        caller_is_staff = caller.has_group('brightloop_core.group_brightloop_staff')
        caller_is_customer = (
            caller.has_group('brightloop_core.group_brightloop_customer')
            and not caller_is_staff
            and not caller_is_admin
        )

        if caller_is_customer:
            self.env['brightloop.security.audit'].log_event(
                event_type='unauthorized_access',
                summary='Unauthorized subscription creation attempt',
                details=f'Customer {caller.login} (ID={caller.id}) attempted to create a subscription directly.',
            )
            raise AccessError('Customers cannot create subscriptions directly.')

        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                seq = self.env['ir.sequence'].next_by_code('brightloop.subscription')
                vals['name'] = seq or f'SUB/{fields.Date.today().year}/{self.search_count([]) + 1:05d}'

            # Default anchor date to start date if not explicitly provided
            if 'start_date' in vals and not vals.get('billing_anchor_date'):
                vals['billing_anchor_date'] = vals['start_date']

        records = super().create(vals_list)

        for rec in records:
            rec._record_history(
                event_type='created',
                previous_state=False,
                new_state=rec.state,
                reason='Subscription contract created.',
            )
            self.env['brightloop.security.audit'].log_event(
                event_type='subscription_created',
                summary=f'Subscription created: {rec.name}',
                details=f'Subscription "{rec.name}" created for customer "{rec.customer_id.name}" (Recurring: {rec.recurring_amount} {rec.currency_id.name}).',
            )

        return records

    def write(self, vals):
        caller = self.env.user
        caller_is_admin = (
            self.env.is_admin()
            or caller.has_group('brightloop_core.group_brightloop_admin')
            or self.env.is_superuser()
        )
        caller_is_staff = caller.has_group('brightloop_core.group_brightloop_staff')
        caller_is_customer = (
            caller.has_group('brightloop_core.group_brightloop_customer')
            and not caller_is_staff
            and not caller_is_admin
        )

        if caller_is_customer:
            self.env['brightloop.security.audit'].log_event(
                event_type='unauthorized_access',
                summary='Unauthorized subscription modification attempt',
                details=f'Customer {caller.login} attempted to modify subscription records {self.ids}.',
            )
            raise AccessError('Customers cannot modify subscriptions directly.')

        # Direct state modification guard
        if 'state' in vals and not self.env.context.get('bypass_state_guard'):
            raise UserError(
                'Direct modification of subscription state is prohibited. '
                'Use dedicated lifecycle actions (action_confirm, action_activate, action_pause, action_resume, action_close).'
            )

        # Sync billing anchor date if start_date changes and anchor is not explicitly specified
        if 'start_date' in vals and 'billing_anchor_date' not in vals:
            vals['billing_anchor_date'] = vals['start_date']

        # Audit date modifications
        date_fields = {'start_date', 'end_date', 'next_billing_date', 'billing_anchor_date'}
        date_modified = any(f in vals for f in date_fields)

        result = super().write(vals)

        if date_modified:
            for sub in self:
                self.env['brightloop.security.audit'].log_event(
                    event_type='subscription_date_modified',
                    summary=f'Subscription dates modified: {sub.name}',
                    details=f'Modified date fields on "{sub.name}": {set(vals.keys()) & date_fields}.',
                )
                sub._record_history(
                    event_type='date_modified',
                    previous_state=sub.state,
                    new_state=sub.state,
                    reason=f'Dates modified: {set(vals.keys()) & date_fields}',
                )

        return result

    # =========================================================================
    # LIFECYCLE HISTORY HELPER
    # =========================================================================

    def _record_history(self, event_type, previous_state, new_state, reason=None, metadata=None):
        """Append an immutable entry to the subscription's lifecycle history."""
        meta_str = json.dumps(metadata) if isinstance(metadata, dict) else (metadata or '')
        for sub in self:
            self.env['brightloop.subscription.history'].sudo().create({
                'subscription_id': sub.id,
                'event_type': event_type,
                'previous_state': previous_state,
                'new_state': new_state,
                'user_id': self.env.user.id,
                'timestamp': fields.Datetime.now(),
                'reason': reason or '',
                'metadata': meta_str,
            })

    # =========================================================================
    # STATE MACHINE ACTIONS
    # =========================================================================

    def _check_internal_access(self, action_name):
        caller = self.env.user
        caller_is_admin = (
            self.env.is_admin()
            or caller.has_group('brightloop_core.group_brightloop_admin')
            or self.env.is_superuser()
        )
        caller_is_staff = caller.has_group('brightloop_core.group_brightloop_staff')
        if not caller_is_admin and not caller_is_staff:
            raise AccessError(f'Only internal staff or administrators are permitted to perform "{action_name}".')

    def action_confirm(self):
        """
        Transition: Draft -> Confirmed.
        Validates customer, active products/plans, and line existence.
        """
        self._check_internal_access('action_confirm')
        for sub in self:
            if sub.state != 'draft':
                raise UserError(f'Subscription "{sub.name}" is in state "{sub.state}". Only draft subscriptions can be confirmed.')

            if not sub.customer_id:
                raise ValidationError('Customer is required to confirm subscription.')

            if not sub.subscription_line_ids:
                raise ValidationError(f'Cannot confirm subscription "{sub.name}" without at least one subscription line.')

            # Validate plan and product integrity
            for line in sub.subscription_line_ids:
                if not line.product_id.active:
                    raise UserError(f'Cannot confirm subscription with archived product "{line.product_id.name}".')
                if line.subscription_plan_id:
                    if not line.subscription_plan_id.active:
                        raise UserError(f'Cannot confirm subscription with archived plan "{line.subscription_plan_id.name}".')
                    line.subscription_plan_id.check_availability(
                        target_date=sub.start_date,
                        quantity=line.quantity,
                    )

            old_state = sub.state
            sub.with_context(bypass_state_guard=True).write({'state': 'confirmed'})

            sub._record_history(
                event_type='confirmed',
                previous_state=old_state,
                new_state='confirmed',
                reason='Subscription confirmed by authorized user.',
            )

            self.env['brightloop.security.audit'].log_event(
                event_type='subscription_confirmed',
                summary=f'Subscription confirmed: {sub.name}',
                details=f'Subscription "{sub.name}" transitioned from {old_state} to confirmed.',
            )

        return True

    def action_activate(self):
        """
        Transition: Confirmed -> Active.
        Calculates next billing date using Phase 4 calendar utilities.
        Supports future start dates without premature invoice generation.
        """
        self._check_internal_access('action_activate')
        for sub in self:
            if sub.state != 'confirmed':
                raise UserError(f'Subscription "{sub.name}" is in state "{sub.state}". Only confirmed subscriptions can be activated.')

            if not sub.start_date:
                raise ValidationError(f'Start date is required to activate subscription "{sub.name}".')

            # Revalidate plan availability
            if sub.subscription_plan_id:
                if not sub.subscription_plan_id.active:
                    raise UserError(f'Cannot activate subscription: Plan "{sub.subscription_plan_id.name}" is archived.')
                sub.subscription_plan_id.check_availability(target_date=sub.start_date, quantity=sub.quantity)

            # Establish anchor date
            anchor = sub.billing_anchor_date or sub.start_date

            # Calculate next billing date
            plan_obj = self.env['brightloop.subscription.plan']
            next_bill = plan_obj.calculate_billing_date(
                billing_interval=sub.billing_interval,
                interval_count=sub.billing_interval_count,
                start_date=sub.start_date,
                anchor_date=anchor,
            )

            old_state = sub.state
            sub.with_context(bypass_state_guard=True).write({
                'state': 'active',
                'next_billing_date': next_bill,
                'billing_anchor_date': anchor,
            })

            sub._record_history(
                event_type='activated',
                previous_state=old_state,
                new_state='active',
                reason=f'Subscription activated. Next billing scheduled for {next_bill}.',
                metadata={'next_billing_date': str(next_bill), 'anchor_date': str(anchor)},
            )

            self.env['brightloop.security.audit'].log_event(
                event_type='subscription_activated',
                summary=f'Subscription activated: {sub.name}',
                details=f'Subscription "{sub.name}" activated with start date {sub.start_date} and next billing {next_bill}.',
            )

        return True

    def action_pause(self, reason=None):
        """
        Transition: Active -> Paused.
        Enforces plan.allow_pause policy and records pause_date.
        """
        self._check_internal_access('action_pause')
        today = fields.Date.context_today(self)
        for sub in self:
            if sub.state != 'active':
                raise UserError(f'Subscription "{sub.name}" is in state "{sub.state}". Only active subscriptions can be paused.')

            # Check plan policy
            if sub.subscription_plan_id and not sub.subscription_plan_id.allow_pause:
                raise UserError(f'Subscription plan "{sub.subscription_plan_id.name}" does not allow pausing.')

            # Check individual lines if any
            for line in sub.subscription_line_ids:
                if line.subscription_plan_id and not line.subscription_plan_id.allow_pause:
                    raise UserError(f'Plan "{line.subscription_plan_id.name}" on line does not allow pausing.')

            old_state = sub.state
            sub.with_context(bypass_state_guard=True).write({
                'state': 'paused',
                'pause_date': today,
            })

            sub._record_history(
                event_type='paused',
                previous_state=old_state,
                new_state='paused',
                reason=reason or 'Subscription paused by user request.',
                metadata={'pause_date': str(today)},
            )

            self.env['brightloop.security.audit'].log_event(
                event_type='subscription_paused',
                summary=f'Subscription paused: {sub.name}',
                details=f'Subscription "{sub.name}" paused on {today}. Reason: {reason or "None"}.',
            )

        return True

    def action_resume(self):
        """
        Transition: Paused -> Active.
        Explicit Pause Policy:
          Calculates pause duration (resume_date - pause_date) and extends next_billing_date
          by that duration, ensuring the customer is not billed for the inactive period.
        """
        self._check_internal_access('action_resume')
        today = fields.Date.context_today(self)
        for sub in self:
            if sub.state != 'paused':
                raise UserError(f'Subscription "{sub.name}" is in state "{sub.state}". Only paused subscriptions can be resumed.')

            pause_dt = sub.pause_date or today
            pause_days = (today - pause_dt).days if today >= pause_dt else 0

            # Calculate adjusted next billing date
            plan_obj = self.env['brightloop.subscription.plan']
            if sub.next_billing_date:
                adjusted_bill_date = sub.next_billing_date + relativedelta(days=pause_days)
                if adjusted_bill_date < today:
                    # If extended date has still passed, schedule 1 cycle forward from resume date
                    adjusted_bill_date = plan_obj.calculate_billing_date(
                        billing_interval=sub.billing_interval,
                        interval_count=sub.billing_interval_count,
                        start_date=today,
                        anchor_date=sub.billing_anchor_date,
                    )
            else:
                adjusted_bill_date = plan_obj.calculate_billing_date(
                    billing_interval=sub.billing_interval,
                    interval_count=sub.billing_interval_count,
                    start_date=today,
                    anchor_date=sub.billing_anchor_date,
                )

            old_state = sub.state
            sub.with_context(bypass_state_guard=True).write({
                'state': 'active',
                'resume_date': today,
                'next_billing_date': adjusted_bill_date,
            })

            sub._record_history(
                event_type='resumed',
                previous_state=old_state,
                new_state='active',
                reason=f'Subscription resumed on {today}. Paused duration: {pause_days} days. Next billing adjusted to {adjusted_bill_date}.',
                metadata={
                    'resume_date': str(today),
                    'pause_days': pause_days,
                    'adjusted_billing_date': str(adjusted_bill_date),
                },
            )

            self.env['brightloop.security.audit'].log_event(
                event_type='subscription_resumed',
                summary=f'Subscription resumed: {sub.name}',
                details=f'Subscription "{sub.name}" resumed on {today}. Extended next billing date to {adjusted_bill_date}.',
            )

        return True

    def action_close(self, reason=None):
        """
        Transition: Active / Paused / Confirmed -> Closed.
        Enforces plan.allow_early_closure policy if terminated before end_date.
        """
        self._check_internal_access('action_close')
        today = fields.Date.context_today(self)
        for sub in self:
            if sub.state in ('draft', 'closed'):
                raise UserError(f'Subscription "{sub.name}" cannot be closed from state "{sub.state}".')

            # Early closure validation: if closing before end_date, verify permission
            if sub.end_date and today < sub.end_date:
                if sub.subscription_plan_id and not sub.subscription_plan_id.allow_early_closure:
                    raise UserError(f'Subscription plan "{sub.subscription_plan_id.name}" does not allow early closure.')
                for line in sub.subscription_line_ids:
                    if line.subscription_plan_id and not line.subscription_plan_id.allow_early_closure:
                        raise UserError(f'Plan "{line.subscription_plan_id.name}" on line does not allow early closure.')

            old_state = sub.state
            close_reason = reason or 'Contract closed by user request.'
            sub.with_context(bypass_state_guard=True).write({
                'state': 'closed',
                'closure_date': today,
                'closure_reason': close_reason,
            })

            sub._record_history(
                event_type='closed',
                previous_state=old_state,
                new_state='closed',
                reason=close_reason,
                metadata={'closure_date': str(today)},
            )

            self.env['brightloop.security.audit'].log_event(
                event_type='subscription_closed',
                summary=f'Subscription closed: {sub.name}',
                details=f'Subscription "{sub.name}" closed on {today}. Reason: {close_reason}.',
            )

        return True

    @api.model
    def cron_auto_close_eligible_subscriptions(self):
        """
        Bounded, idempotent scheduled job to identify and automatically close
        subscriptions that have reached their end_date and whose plans permit auto_close.
        """
        today = fields.Date.context_today(self)
        eligible = self.search([
            ('state', 'in', ('active', 'paused')),
            ('end_date', '!=', False),
            ('end_date', '<=', today),
        ])

        closed_count = 0
        for sub in eligible:
            # Check auto_close on plan
            should_close = False
            if sub.subscription_plan_id and sub.subscription_plan_id.auto_close:
                should_close = True
            elif any(line.subscription_plan_id and line.subscription_plan_id.auto_close for line in sub.subscription_line_ids):
                should_close = True

            if not should_close:
                continue

            old_state = sub.state
            reason = f'Automatic closure: contract end date ({sub.end_date}) reached.'
            sub.with_context(bypass_state_guard=True).write({
                'state': 'closed',
                'closure_date': today,
                'closure_reason': reason,
            })

            sub._record_history(
                event_type='auto_closed',
                previous_state=old_state,
                new_state='closed',
                reason=reason,
                metadata={'auto_closed': True, 'end_date': str(sub.end_date)},
            )

            self.env['brightloop.security.audit'].log_event(
                event_type='subscription_auto_closed',
                summary=f'Subscription auto-closed: {sub.name}',
                details=f'Subscription "{sub.name}" automatically closed on {today} (End date: {sub.end_date}).',
            )
            closed_count += 1

        _logger.info('cron_auto_close_eligible_subscriptions processed %s eligible subscriptions.', closed_count)
        return closed_count

    def action_renew(self, notes=None):
        """
        Renew an existing subscription contract (from Active or Closed state).
        Requirements:
          - Validates plan.allow_renewal.
          - Revalidates plan availability for current date.
          - Creates a new subscription record with traceable linkage.
          - Sets previous_subscription_id and increments renewal_count.
          - Computes new start date, next billing date, and end date using calendar arithmetic.
          - Closes the previous subscription if it was still active.
        """
        self._check_internal_access('action_renew')
        self.ensure_one()
        today = fields.Date.context_today(self)

        if self.state not in ('active', 'closed'):
            raise UserError(f'Cannot renew subscription "{self.name}" from state "{self.state}". Must be active or closed.')

        # Validate renewal policy
        if self.subscription_plan_id and not self.subscription_plan_id.allow_renewal:
            raise UserError(f'Subscription plan "{self.subscription_plan_id.name}" does not allow renewals.')

        for line in self.subscription_line_ids:
            if line.subscription_plan_id and not line.subscription_plan_id.allow_renewal:
                raise UserError(f'Plan "{line.subscription_plan_id.name}" on line does not allow renewals.')

        # Revalidate availability of primary plan
        if self.subscription_plan_id:
            if not self.subscription_plan_id.active:
                raise UserError(f'Cannot renew: Subscription plan "{self.subscription_plan_id.name}" is archived.')
            self.subscription_plan_id.check_availability(target_date=today, quantity=self.quantity)

        # Calculate new dates
        if self.end_date and self.end_date >= today:
            new_start_date = self.end_date + relativedelta(days=1)
        else:
            new_start_date = today

        # Calculate new end date if original contract had an end date
        new_end_date = False
        if self.start_date and self.end_date:
            duration = self.end_date - self.start_date
            new_end_date = new_start_date + duration

        plan_obj = self.env['brightloop.subscription.plan']
        new_next_billing = plan_obj.calculate_billing_date(
            billing_interval=self.billing_interval,
            interval_count=self.billing_interval_count,
            start_date=new_start_date,
            anchor_date=self.billing_anchor_date or new_start_date,
        )

        # Prepare new subscription lines
        new_lines_vals = []
        for line in self.subscription_line_ids:
            new_lines_vals.append((0, 0, {
                'product_id': line.product_id.id,
                'subscription_plan_id': line.subscription_plan_id.id if line.subscription_plan_id else False,
                'quantity': line.quantity,
                'price_unit': line.price_unit,
                'discount': line.discount,
            }))

        new_sub = self.sudo().create({
            'customer_id': self.customer_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'subscription_plan_id': self.subscription_plan_id.id if self.subscription_plan_id else False,
            'start_date': new_start_date,
            'end_date': new_end_date,
            'next_billing_date': new_next_billing,
            'billing_anchor_date': self.billing_anchor_date or new_start_date,
            'billing_interval': self.billing_interval,
            'billing_interval_count': self.billing_interval_count,
            'previous_subscription_id': self.id,
            'renewal_count': self.renewal_count + 1,
            'state': 'confirmed',
            'subscription_line_ids': new_lines_vals,
            'notes': notes or f'Renewed from {self.name}',
        })

        # If previous was active, close it
        if self.state == 'active':
            self.action_close(reason=f'Renewed into subscription {new_sub.name}.')

        self.env['brightloop.security.audit'].log_event(
            event_type='subscription_renewed',
            summary=f'Subscription renewed: {self.name} -> {new_sub.name}',
            details=f'Subscription "{self.name}" renewed into new subscription "{new_sub.name}" (Renewal #{new_sub.renewal_count}).',
        )

        return new_sub
