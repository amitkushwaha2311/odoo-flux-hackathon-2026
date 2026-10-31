# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.sale_order_line
#
# Extensions to native sale.order.line for Brightloop Subscription Quotations
#
# PHASE 5 SCOPE
# -------------
# - Support both regular product lines and subscription plan lines.
# - Integration with brightloop.subscription.plan and brightloop.pricing.service.
# - Load billing frequency, interval count, and plan product variant.
# - Enforce minimum purchase quantities and Unit of Measure precision.
# - Price determination: base price + variant surcharge (₹2,000 + ₹560 = ₹2,560).
# - Zero double-application guarantee for variant surcharges.
# - Multi-company validation and archived product/plan guards.
# - Line addition, modification, and removal audit logging.
# =============================================================================

import logging
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # =========================================================================
    # BRIGHTLOOP FIELDS
    # =========================================================================

    subscription_plan_id = fields.Many2one(
        comodel_name='brightloop.subscription.plan',
        string='Subscription Plan',
        check_company=True,
        index=True,
        help='Linked subscription plan when this line represents a recurring subscription offering.',
    )

    billing_interval = fields.Selection(
        related='subscription_plan_id.billing_interval',
        string='Billing Frequency',
        store=True,
        readonly=True,
    )

    billing_interval_count = fields.Integer(
        related='subscription_plan_id.billing_interval_count',
        string='Billing Interval Count',
        store=True,
        readonly=True,
    )

    is_subscription_line = fields.Boolean(
        string='Is Subscription Line',
        compute='_compute_is_subscription_line',
        store=True,
        index=True,
    )

    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================

    @api.depends('subscription_plan_id')
    def _compute_is_subscription_line(self):
        for line in self:
            line.is_subscription_line = bool(line.subscription_plan_id)

    # =========================================================================
    # ONCHANGE & FIELD SYNCHRONIZATION
    # =========================================================================

    @api.onchange('subscription_plan_id')
    def _onchange_subscription_plan_id(self):
        """
        When a subscription plan is selected on a quotation line:
        - Auto-load associated product or variant.
        - Enforce minimum quantity.
        - Compute deterministic price via brightloop.pricing.service.
        """
        if not self.subscription_plan_id:
            return

        plan = self.subscription_plan_id

        # 1. Product synchronization
        if plan.product_id and not self.product_id:
            self.product_id = plan.product_id
        elif not self.product_id and plan.product_ids:
            self.product_id = plan.product_ids[0]

        # 2. Minimum quantity synchronization
        if self.product_uom_qty < plan.minimum_quantity:
            self.product_uom_qty = plan.minimum_quantity

        # 3. Unit price computation
        target_product = self.product_id or plan.product_id
        target_currency = self.order_id.currency_id or plan.currency_id
        if target_product:
            self.price_unit = self.env['brightloop.pricing.service'].calculate_variant_price(
                target_product, currency=target_currency
            )
        elif plan.list_price:
            self.price_unit = target_currency.round(plan.list_price)

    # =========================================================================
    # DATA INTEGRITY CONSTRAINTS
    # =========================================================================

    @api.constrains('product_id')
    def _check_product_active(self):
        for line in self:
            if line.product_id and not line.product_id.active:
                raise ValidationError(f'Cannot add archived product "{line.product_id.name}" to quotation.')

    @api.constrains('product_uom_qty')
    def _check_quantity_positive(self):
        for line in self:
            if line.product_uom_qty is not None and line.product_uom_qty <= 0.0:
                raise ValidationError('Quotation line quantity must be strictly greater than zero.')

    @api.constrains('price_unit')
    def _check_price_unit_non_negative(self):
        for line in self:
            if line.price_unit is not None and line.price_unit < 0.0:
                raise ValidationError('Quotation line unit price cannot be negative.')

    @api.constrains('discount')
    def _check_discount_range(self):
        for line in self:
            if line.discount is not None and not (0.0 <= line.discount <= 100.0):
                raise ValidationError('Quotation line discount must be between 0% and 100%.')

    @api.constrains('subscription_plan_id', 'product_id', 'product_uom_qty')
    def _check_subscription_plan_rules(self):
        for line in self:
            if not line.subscription_plan_id:
                continue

            plan = line.subscription_plan_id

            if not plan.active:
                raise ValidationError(f'Cannot add archived subscription plan "{plan.name}" to quotation.')

            # Check minimum quantity
            if line.product_uom_qty < plan.minimum_quantity:
                raise ValidationError(
                    f'Quantity {line.product_uom_qty} is below minimum quantity '
                    f'({plan.minimum_quantity}) required for plan "{plan.name}".'
                )

            # Check product compatibility
            if line.product_id and plan.product_id:
                if line.product_id != plan.product_id and (not plan.product_ids or line.product_id not in plan.product_ids):
                    raise ValidationError(
                        f'Selected product "{line.product_id.name}" does not match '
                        f'subscription plan "{plan.name}".'
                    )

            # Check plan availability dates
            order_date = line.order_id.date_order
            target_date = order_date.date() if isinstance(order_date, datetime) else order_date
            plan.check_availability(target_date=target_date, quantity=line.product_uom_qty)

    # =========================================================================
    # AUDIT LOGGING OVERRIDES
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.order_id:
                details = (
                    f'Added line to quotation "{rec.order_id.name}": Product={rec.product_id.name or "N/A"}, '
                    f'Qty={rec.product_uom_qty}, PriceUnit={rec.price_unit}, '
                    f'Plan={rec.subscription_plan_id.name if rec.subscription_plan_id else "None"}.'
                )
                self.env['brightloop.security.audit'].log_event(
                    event_type='quotation_line_added',
                    summary=f'Line added to quotation: {rec.order_id.name}',
                    details=details,
                )
        return records

    def write(self, vals):
        result = super().write(vals)
        if any(f in vals for f in ['product_id', 'product_uom_qty', 'price_unit', 'discount', 'subscription_plan_id']):
            for rec in self:
                if rec.order_id:
                    self.env['brightloop.security.audit'].log_event(
                        event_type='quotation_line_updated',
                        summary=f'Line updated on quotation: {rec.order_id.name}',
                        details=f'Updated line fields on quotation "{rec.order_id.name}": {list(vals.keys())}.',
                    )
        return result

    def unlink(self):
        order_names = {rec.id: rec.order_id.name for rec in self if rec.order_id}
        for rec in self:
            o_name = order_names.get(rec.id, 'Unknown')
            self.env['brightloop.security.audit'].log_event(
                event_type='quotation_line_removed',
                summary=f'Line removed from quotation: {o_name}',
                details=f'Removed line Product={rec.product_id.name or "N/A"} from quotation "{o_name}".',
            )
        return super().unlink()

