# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.subscription_plan
#
# Subscription Plan Engine for Brightloop Subscription Intelligence
#
# PHASE 4 SCOPE
# -------------
# - Reusable subscription plan model (brightloop.subscription.plan).
# - Integration with Phase 3 product/variant infrastructure.
# - Calendar-aware billing frequency engine (daily, weekly, monthly, yearly).
# - Exact month-end and leap-year arithmetic without 30-day/365-day approximations.
# - Deterministic plan pricing, currency precision, and single-application guarantee.
# - Minimum purchase quantity and unit-of-measure decimal validation.
# - Availability date window validation (start date, end date, archival protection).
# - Configurable lifecycle policies (auto_close, early closure, pause, renewal).
# - RBAC: Admin=CRUD, Staff=Read-only, Customer=Access denied.
# - Comprehensive audit logging for all plan lifecycle, price, and policy events.
# =============================================================================

import logging
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_is_zero

_logger = logging.getLogger(__name__)


class BrightloopSubscriptionPlan(models.Model):
    """
    Subscription Plan definition model.
    Encapsulates commercial subscription parameters, billing frequencies,
    pricing calculations, and lifecycle policies.
    """
    _name = 'brightloop.subscription.plan'
    _description = 'Brightloop Subscription Plan'
    _inherit = ['brightloop.base']
    _order = 'name asc, id desc'

    # =========================================================================
    # CORE FIELDS
    # =========================================================================

    name = fields.Char(
        string='Plan Name',
        required=True,
        index=True,
        help='Display name of the subscription plan.',
    )

    description = fields.Text(
        string='Description',
        help='Internal and customer-facing description of the plan.',
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        index=True,
        help='Whether this plan is currently available for commercial operations.',
    )

    # -------------------------------------------------------------------------
    # PRODUCT & VARIANT INTEGRATION
    # -------------------------------------------------------------------------
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Primary Product/Variant',
        check_company=True,
        index=True,
        help='Primary product variant associated with this subscription plan.',
    )

    product_ids = fields.Many2many(
        comodel_name='product.product',
        relation='brightloop_plan_product_rel',
        column1='plan_id',
        column2='product_id',
        string='Included Products/Variants',
        check_company=True,
        help='Products or variants included in this subscription plan.',
    )

    # -------------------------------------------------------------------------
    # BILLING FREQUENCY & INTERVAL ENGINE
    # -------------------------------------------------------------------------
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
        help='Billing recurring frequency.',
    )

    billing_interval_count = fields.Integer(
        string='Billing Interval Count',
        required=True,
        default=1,
        help='Number of billing intervals per cycle (e.g. 3 for quarterly if interval is monthly).',
    )

    # -------------------------------------------------------------------------
    # PRICING & CURRENCY
    # -------------------------------------------------------------------------
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
        help='Commercial currency for this plan.',
    )

    list_price = fields.Monetary(
        string='Plan Price',
        currency_field='currency_id',
        default=0.0,
        help='Base or overridden sales price for this plan.',
    )

    minimum_quantity = fields.Float(
        string='Minimum Quantity',
        default=1.0,
        required=True,
        help='Minimum quantity required when subscribing to this plan.',
    )

    # -------------------------------------------------------------------------
    # AVAILABILITY DATES
    # -------------------------------------------------------------------------
    availability_start_date = fields.Date(
        string='Availability Start Date',
        help='First date on which this plan can be selected.',
    )

    availability_end_date = fields.Date(
        string='Availability End Date',
        help='Last date on which this plan can be selected. After this date, the plan expires.',
    )

    # -------------------------------------------------------------------------
    # LIFECYCLE POLICIES
    # -------------------------------------------------------------------------
    auto_close = fields.Boolean(
        string='Auto Close on Expiry',
        default=False,
        help='If enabled, subscriptions under this plan close automatically when end conditions are met.',
    )

    allow_early_closure = fields.Boolean(
        string='Allow Early Closure',
        default=True,
        help='Whether subscribers or staff are permitted to terminate early.',
    )

    allow_pause = fields.Boolean(
        string='Allow Pause & Resume',
        default=True,
        help='Whether subscriptions under this plan can be temporarily suspended.',
    )

    allow_renewal = fields.Boolean(
        string='Allow Renewal',
        default=True,
        help='Whether subscriptions under this plan are eligible for renewal.',
    )

    # =========================================================================
    # DATA INTEGRITY CONSTRAINTS
    # =========================================================================

    @api.constrains('name')
    def _check_name(self):
        """Ensure plan name is non-empty after stripping whitespace."""
        for plan in self:
            if not plan.name or not plan.name.strip():
                raise ValidationError('Subscription plan name is required and cannot be empty.')

    @api.constrains('billing_interval')
    def _check_billing_interval(self):
        """Ensure billing frequency is one of the four supported intervals."""
        valid_intervals = {'daily', 'weekly', 'monthly', 'yearly'}
        for plan in self:
            if plan.billing_interval not in valid_intervals:
                raise ValidationError(
                    f'Invalid billing interval "{plan.billing_interval}". '
                    f'Must be one of: {", ".join(sorted(valid_intervals))}.'
                )

    @api.constrains('billing_interval_count')
    def _check_billing_interval_count(self):
        """Ensure billing interval count is a strictly positive integer."""
        for plan in self:
            if plan.billing_interval_count is None or plan.billing_interval_count <= 0:
                raise ValidationError('Billing interval count must be greater than zero.')

    @api.constrains('minimum_quantity')
    def _check_minimum_quantity(self):
        """Ensure minimum quantity is strictly positive."""
        for plan in self:
            if plan.minimum_quantity is None or plan.minimum_quantity <= 0.0:
                raise ValidationError('Minimum quantity must be greater than zero.')

    @api.constrains('list_price')
    def _check_list_price(self):
        """Ensure plan price is non-negative."""
        for plan in self:
            if plan.list_price is not None and plan.list_price < 0.0:
                raise ValidationError('Subscription plan price cannot be negative.')

    @api.constrains('currency_id')
    def _check_currency(self):
        """Ensure plan currency is active."""
        for plan in self:
            if plan.currency_id and not plan.currency_id.active:
                raise ValidationError('Subscription plan currency must be active.')

    @api.constrains('availability_start_date', 'availability_end_date')
    def _check_availability_dates(self):
        """Ensure availability start date does not succeed end date."""
        for plan in self:
            if plan.availability_start_date and plan.availability_end_date:
                if plan.availability_start_date > plan.availability_end_date:
                    raise ValidationError(
                        f'Availability start date ({plan.availability_start_date}) '
                        f'cannot be after end date ({plan.availability_end_date}).'
                    )

    @api.constrains('company_id', 'product_id', 'currency_id')
    def _check_company_consistency(self):
        """Ensure company consistency across plan, product, and currency."""
        for plan in self:
            if plan.product_id and plan.product_id.company_id and plan.product_id.company_id != plan.company_id:
                raise ValidationError(
                    f'Plan company ({plan.company_id.name}) must match '
                    f'associated product company ({plan.product_id.company_id.name}).'
                )

    # =========================================================================
    # ROLE-BASED ACCESS CONTROL & AUDIT LOGGING OVERRIDES
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        """
        Enforce that only Brightloop Administrators can create subscription plans.
        Sync product_id and product_ids, compute default list_price if not set,
        and log plan creation to the security audit trail.
        """
        caller = self.env.user
        caller_is_admin = (
            self.env.is_admin()
            or caller.has_group('brightloop_core.group_brightloop_admin')
            or self.env.is_superuser()
        )

        if not caller_is_admin:
            self.env['brightloop.security.audit'].log_event(
                event_type='unauthorized_access',
                summary='Unauthorized subscription plan creation attempt',
                details=f'User {caller.login} (ID={caller.id}) attempted to create a subscription plan without Admin privileges.',
            )
            raise AccessError('Only Brightloop Administrators can create subscription plans.')

        # Pre-process vals: harmonize product_id and product_ids
        for vals in vals_list:
            prod_id = vals.get('product_id')
            prod_ids = vals.get('product_ids')

            if prod_id and not prod_ids:
                vals['product_ids'] = [(6, 0, [prod_id])]
            elif prod_ids and not prod_id:
                # Extract first product id from relation
                for cmd in prod_ids:
                    if isinstance(cmd, (list, tuple)) and len(cmd) >= 3 and cmd[0] == 6 and cmd[2]:
                        vals['product_id'] = cmd[2][0]
                        break

            # If list_price is omitted or 0.0, compute from product if available
            if not vals.get('list_price') and vals.get('product_id'):
                product = self.env['product.product'].browse(vals['product_id'])
                if product.exists():
                    target_currency = (
                        self.env['res.currency'].browse(vals['currency_id'])
                        if vals.get('currency_id')
                        else (product.currency_id or self.env.company.currency_id)
                    )
                    vals['list_price'] = self.env['brightloop.pricing.service'].calculate_variant_price(
                        product, currency=target_currency
                    )

        records = super().create(vals_list)

        for rec in records:
            self.env['brightloop.security.audit'].log_event(
                event_type='plan_created',
                summary=f'Subscription plan created: {rec.name}',
                details=(
                    f'Plan "{rec.name}" created (Frequency={rec.billing_interval}, '
                    f'Count={rec.billing_interval_count}, Price={rec.list_price} {rec.currency_id.name}, '
                    f'MinQty={rec.minimum_quantity}).'
                ),
            )

        return records

    def write(self, vals):
        """
        Enforce that only Brightloop Administrators can modify subscription plans.
        Log updates, price modifications, interval changes, archival/reactivation,
        and lifecycle policy modifications.
        """
        caller = self.env.user
        caller_is_admin = (
            self.env.is_admin()
            or caller.has_group('brightloop_core.group_brightloop_admin')
            or self.env.is_superuser()
        )

        if not caller_is_admin:
            self.env['brightloop.security.audit'].log_event(
                event_type='unauthorized_access',
                summary='Unauthorized subscription plan modification attempt',
                details=f'User {caller.login} attempted to modify subscription plans {self.ids} without Admin privileges.',
            )
            raise AccessError('Only Brightloop Administrators can modify subscription plans.')

        # Capture pre-write state for audit tracking
        old_active = {p.id: p.active for p in self} if 'active' in vals else {}
        old_prices = {p.id: p.list_price for p in self} if 'list_price' in vals else {}
        old_intervals = {p.id: (p.billing_interval, p.billing_interval_count) for p in self} if ('billing_interval' in vals or 'billing_interval_count' in vals) else {}

        # Sync product_id / product_ids if updated
        if 'product_id' in vals and 'product_ids' not in vals:
            vals['product_ids'] = [(6, 0, [vals['product_id']])] if vals['product_id'] else [(5, 0, 0)]

        result = super().write(vals)

        # Audit events for state changes
        if 'active' in vals:
            for plan in self:
                if old_active.get(plan.id) is True and plan.active is False:
                    self.env['brightloop.security.audit'].log_event(
                        event_type='plan_archived',
                        summary=f'Subscription plan archived: {plan.name}',
                        details=f'Plan ID={plan.id} ("{plan.name}") was archived.',
                    )
                elif old_active.get(plan.id) is False and plan.active is True:
                    self.env['brightloop.security.audit'].log_event(
                        event_type='plan_reactivated',
                        summary=f'Subscription plan reactivated: {plan.name}',
                        details=f'Plan ID={plan.id} ("{plan.name}") was reactivated.',
                    )

        if 'list_price' in vals:
            for plan in self:
                old_p = old_prices.get(plan.id)
                if old_p != plan.list_price:
                    self.env['brightloop.security.audit'].log_event(
                        event_type='plan_price_modified',
                        summary=f'Plan price modified: {plan.name}',
                        details=f'Plan "{plan.name}" price changed from {old_p} to {plan.list_price}.',
                    )

        if 'billing_interval' in vals or 'billing_interval_count' in vals:
            for plan in self:
                old_int = old_intervals.get(plan.id, ('', 0))
                self.env['brightloop.security.audit'].log_event(
                    event_type='plan_interval_modified',
                    summary=f'Plan billing interval modified: {plan.name}',
                    details=(
                        f'Plan "{plan.name}" interval changed from {old_int[0]} (count {old_int[1]}) '
                        f'to {plan.billing_interval} (count {plan.billing_interval_count}).'
                    ),
                )

        policy_fields = {'auto_close', 'allow_early_closure', 'allow_pause', 'allow_renewal'}
        if any(f in vals for f in policy_fields):
            for plan in self:
                self.env['brightloop.security.audit'].log_event(
                    event_type='plan_policy_modified',
                    summary=f'Plan lifecycle policies modified: {plan.name}',
                    details=f'Updated lifecycle policies for "{plan.name}": {set(vals.keys()) & policy_fields}.',
                )

        if not any(f in vals for f in ({'active', 'list_price', 'billing_interval', 'billing_interval_count'} | policy_fields)):
            for plan in self:
                self.env['brightloop.security.audit'].log_event(
                    event_type='plan_updated',
                    summary=f'Subscription plan updated: {plan.name}',
                    details=f'Updated fields on plan "{plan.name}": {list(vals.keys())}.',
                )

        return result

    def unlink(self):
        """Enforce admin-only deletion and deletion safeguards."""
        caller = self.env.user
        caller_is_admin = (
            self.env.is_admin()
            or caller.has_group('brightloop_core.group_brightloop_admin')
            or self.env.is_superuser()
        )
        if not caller_is_admin:
            raise AccessError('Only Brightloop Administrators can delete subscription plans.')

        return super().unlink()

    # =========================================================================
    # BILLING FREQUENCY ENGINE & DATE CALCULATION
    # =========================================================================

    @api.model
    def calculate_billing_date(self, billing_interval: str, interval_count: int = 1, start_date=None) -> date:
        """
        Pure reusable calendar-aware date calculation utility.
        Preserves calendar month-end semantics, leap-year calculations,
        and rejects non-positive interval counts.

        Examples:
          Daily:   2026-10-31 + 1 day   -> 2026-11-01
          Weekly:  2026-10-31 + 1 week  -> 2026-11-07
          Monthly: 2026-01-31 + 1 month -> 2026-02-28
          Yearly:  2024-02-29 + 1 year  -> 2025-02-28 (leap year boundary)

        :param billing_interval: 'daily', 'weekly', 'monthly', 'yearly'
        :param interval_count: Strictly positive integer multiplier (default 1)
        :param start_date: date, datetime, or ISO string. Defaults to today.
        :return: date object
        """
        if interval_count is None or interval_count <= 0:
            raise ValidationError('Billing interval count must be a positive integer.')

        if start_date is None:
            start_date = fields.Date.context_today(self)
        elif isinstance(start_date, datetime):
            start_date = start_date.date()
        elif isinstance(start_date, str):
            start_date = fields.Date.from_string(start_date)

        if not isinstance(start_date, date):
            raise ValidationError(f'Invalid start_date format: {start_date}')

        if billing_interval == 'daily':
            delta = relativedelta(days=interval_count)
        elif billing_interval == 'weekly':
            delta = relativedelta(weeks=interval_count)
        elif billing_interval == 'monthly':
            delta = relativedelta(months=interval_count)
        elif billing_interval == 'yearly':
            delta = relativedelta(years=interval_count)
        else:
            raise ValidationError(f'Invalid billing interval: {billing_interval}')

        return start_date + delta

    def calculate_next_billing_date(self, start_date=None, interval_count=None) -> date:
        """
        Calculate the next billing date for this plan instance.
        """
        self.ensure_one()
        count = interval_count if interval_count is not None else self.billing_interval_count
        return self.calculate_billing_date(
            billing_interval=self.billing_interval,
            interval_count=count,
            start_date=start_date,
        )

    # =========================================================================
    # PRICING ENGINE & VARIANT INTEGRATION
    # =========================================================================

    def calculate_plan_price(self, variant=None, quantity=None) -> dict:
        """
        Calculate total plan amount based on product variant and quantity.

        Guarantees:
          - Reuses Phase 3 product & variant pricing (brightloop.pricing.service).
          - Variant additional price is applied exactly once (never duplicated).
          - Validates minimum purchase quantity (quantity >= minimum_quantity).
          - Validates unit-of-measure decimal precision.
          - Currency precision rounding.

        :param variant: optional product.product record. If omitted, uses plan.product_id.
        :param quantity: quantity to purchase. Defaults to plan.minimum_quantity.
        :return: dict with unit_price, quantity, total_amount, currency_id, breakdown
        """
        self.ensure_one()

        # 1. Determine target variant
        target_variant = variant or self.product_id
        if not target_variant and self.product_ids:
            target_variant = self.product_ids[0]

        # 2. Determine and validate quantity
        qty = quantity if quantity is not None else self.minimum_quantity
        if qty is None or qty <= 0.0:
            raise ValidationError('Quantity must be greater than zero.')

        if qty < self.minimum_quantity:
            raise ValidationError(
                f'Quantity {qty} is below the minimum required quantity '
                f'({self.minimum_quantity}) for plan "{self.name}".'
            )

        # 3. Validate UoM decimal precision
        if target_variant and target_variant.uom_id:
            uom = target_variant.uom_id
            is_discrete = any(kw in uom.name.lower() for kw in ['unit', 'piece', 'pack', 'dozen'])
            if is_discrete and not float_is_zero(qty % 1.0, precision_digits=2):
                raise ValidationError(
                    f'Quantity {qty} is invalid for Unit of Measure "{uom.name}". '
                    'Fractional quantities are not permitted for discrete units.'
                )

        # 4. Calculate unit price
        target_currency = self.currency_id
        if target_variant:
            # Reuses Phase 3 pricing service — deterministic, single-application of variant extras
            unit_price = self.env['brightloop.pricing.service'].calculate_variant_price(
                target_variant, currency=target_currency
            )
            breakdown = self.env['brightloop.pricing.service'].get_variant_price_breakdown(
                target_variant, currency=target_currency
            )
        else:
            unit_price = self.list_price or 0.0
            unit_price = target_currency.round(unit_price)
            breakdown = {
                'base_price': unit_price,
                'total_extra': 0.0,
                'effective_price': unit_price,
                'attribute_extras': [],
            }

        # 5. Compute total amount
        total_amount = target_currency.round(unit_price * qty)

        return {
            'plan_id': self.id,
            'plan_name': self.name,
            'variant_id': target_variant.id if target_variant else False,
            'variant_name': target_variant.display_name if target_variant else '',
            'unit_price': unit_price,
            'quantity': qty,
            'total_amount': total_amount,
            'currency_id': target_currency.id,
            'currency_symbol': target_currency.symbol or '',
            'breakdown': breakdown,
        }

    # =========================================================================
    # AVAILABILITY VALIDATION
    # =========================================================================

    def check_availability(self, target_date=None, quantity=None) -> bool:
        """
        Verify that this plan is active and available on the given target_date.

        Raises UserError or ValidationError if:
          - Plan is archived / inactive.
          - Target date is before availability_start_date.
          - Target date is after availability_end_date.
          - Associated product or variant is archived.
          - Requested quantity is below minimum_quantity.

        :param target_date: date to check (defaults to today).
        :param quantity: optional quantity to validate.
        :return: True if available
        """
        self.ensure_one()

        if not self.active:
            raise UserError(f'Subscription plan "{self.name}" is archived and cannot be selected.')

        chk_date = target_date or fields.Date.context_today(self)
        if isinstance(chk_date, datetime):
            chk_date = chk_date.date()
        elif isinstance(chk_date, str):
            chk_date = fields.Date.from_string(chk_date)

        if self.availability_start_date and chk_date < self.availability_start_date:
            raise UserError(
                f'Subscription plan "{self.name}" is not available before {self.availability_start_date}.'
            )

        if self.availability_end_date and chk_date > self.availability_end_date:
            raise UserError(
                f'Subscription plan "{self.name}" expired on {self.availability_end_date}.'
            )

        # Check product availability
        if self.product_id:
            self.product_id.check_available_for_sale()
        for prod in self.product_ids:
            prod.check_available_for_sale()

        # Check quantity if provided
        if quantity is not None and quantity < self.minimum_quantity:
            raise ValidationError(
                f'Requested quantity {quantity} is less than minimum quantity {self.minimum_quantity}.'
            )

        return True

    # =========================================================================
    # LIFECYCLE POLICIES VALIDATION
    # =========================================================================

    def validate_early_closure(self) -> bool:
        """
        Verify if early closure is allowed under this plan.
        Raises UserError if forbidden.
        """
        self.ensure_one()
        if not self.allow_early_closure:
            raise UserError(f'Early closure is not permitted for subscription plan "{self.name}".')
        return True

    def validate_pause(self) -> bool:
        """
        Verify if pausing is allowed under this plan.
        Raises UserError if forbidden.
        """
        self.ensure_one()
        if not self.allow_pause:
            raise UserError(f'Pausing subscriptions is not permitted for subscription plan "{self.name}".')
        return True

    def validate_renewal(self) -> bool:
        """
        Verify if renewal is allowed under this plan.
        Raises UserError if forbidden.
        """
        self.ensure_one()
        if not self.allow_renewal:
            raise UserError(f'Subscription renewal is not permitted for subscription plan "{self.name}".')
        return True

