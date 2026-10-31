# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.subscription_line
#
# Subscription Line items for Brightloop Subscription Intelligence
#
# PHASE 6 SCOPE
# -------------
# - Represents individual recurring product items on a subscription contract.
# - Retains links to source quotation lines (`source_order_line_id`).
# - Product, variant, subscription plan, quantity, and unit price synchronization.
# - Currency-aware subtotal computation.
#
# PHASE 7 ADDITIONS
# -----------------
# - discount_id: link to brightloop.discount rule applied at creation.
# - tax_amount: computed via brightloop.tax.service.
# - price_total: price_subtotal + tax_amount.
# - tax_breakdown: stored JSON for Phase 8 recurring invoice generation.
# =============================================================================

import json
import logging
from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class BrightloopSubscriptionLine(models.Model):
    _name = 'brightloop.subscription.line'
    _inherit = ['brightloop.base']
    _description = 'Brightloop Subscription Line'
    _order = 'id asc'

    subscription_id = fields.Many2one(
        comodel_name='brightloop.subscription',
        string='Subscription',
        required=True,
        ondelete='cascade',
        index=True,
        check_company=True,
    )

    source_order_line_id = fields.Many2one(
        comodel_name='sale.order.line',
        string='Source Quotation Line',
        readonly=True,
        copy=False,
        index=True,
        help='Traceability reference to the confirmed quotation line.',
    )

    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product / Variant',
        required=True,
        check_company=True,
        index=True,
        help='Product or variant under recurring subscription.',
    )

    subscription_plan_id = fields.Many2one(
        comodel_name='brightloop.subscription.plan',
        string='Subscription Plan',
        check_company=True,
        index=True,
        help='Associated commercial subscription plan.',
    )

    quantity = fields.Float(
        string='Quantity',
        required=True,
        default=1.0,
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        related='subscription_id.currency_id',
        store=True,
        readonly=True,
    )

    price_unit = fields.Monetary(
        string='Unit Price',
        currency_field='currency_id',
        required=True,
        default=0.0,
    )

    discount = fields.Float(
        string='Discount (%)',
        default=0.0,
    )

    discount_id = fields.Many2one(
        comodel_name='brightloop.discount',
        string='Applied Discount Rule',
        readonly=True,
        copy=False,
        index=True,
        help='Brightloop discount rule applied to this subscription line.',
    )

    tax_amount = fields.Monetary(
        string='Tax Amount',
        currency_field='currency_id',
        compute='_compute_tax_amount',
        store=True,
        help='Total tax amount computed by brightloop.tax.service for this subscription line.',
    )

    price_total = fields.Monetary(
        string='Total (Tax Included)',
        currency_field='currency_id',
        compute='_compute_tax_amount',
        store=True,
        help='Final total including all taxes.',
    )

    tax_breakdown = fields.Text(
        string='Tax Breakdown (JSON)',
        readonly=True,
        copy=False,
        help='Structured JSON tax breakdown from brightloop.tax.service. '
             'Used by Phase 8 recurring invoice generation.',
    )

    price_subtotal = fields.Monetary(
        string='Subtotal',
        currency_field='currency_id',
        compute='_compute_price_subtotal',
        store=True,
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

    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================

    @api.depends('quantity', 'price_unit', 'discount', 'currency_id')
    def _compute_price_subtotal(self):
        for line in self:
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            subtotal = price * line.quantity
            line.price_subtotal = line.currency_id.round(subtotal) if line.currency_id else subtotal

    @api.depends('price_subtotal', 'product_id', 'currency_id')
    def _compute_tax_amount(self):
        has_tax_service = 'brightloop.tax.service' in self.env
        tax_service = self.env['brightloop.tax.service'] if has_tax_service else None
        for line in self:
            if not line.product_id or not has_tax_service:
                line.tax_amount = 0.0
                line.price_total = line.price_subtotal
                line.tax_breakdown = False
                continue
            try:
                tax_res = tax_service.compute_taxes_for_subscription_line(line)
                line.tax_amount = tax_res.get('total_tax', 0.0)
                line.price_total = tax_res.get('total_included', line.price_subtotal)
                line.tax_breakdown = json.dumps(tax_res)
            except Exception as e:
                _logger.warning('Failed to compute taxes for subscription line %s: %s', line.id, e)
                line.tax_amount = 0.0
                line.price_total = line.price_subtotal
                line.tax_breakdown = False

    # =========================================================================
    # DATA INTEGRITY CONSTRAINTS
    # =========================================================================

    @api.constrains('quantity')
    def _check_quantity_positive(self):
        for line in self:
            if line.quantity is None or line.quantity <= 0.0:
                raise ValidationError('Subscription line quantity must be strictly greater than zero.')

    @api.constrains('price_unit')
    def _check_price_unit_non_negative(self):
        for line in self:
            if line.price_unit is not None and line.price_unit < 0.0:
                raise ValidationError('Subscription line unit price cannot be negative.')

    @api.constrains('product_id')
    def _check_product_active(self):
        for line in self:
            if line.product_id and not line.product_id.active:
                raise ValidationError(f'Cannot have archived product "{line.product_id.name}" on a subscription line.')

    @api.constrains('subscription_plan_id', 'quantity')
    def _check_plan_rules(self):
        for line in self:
            if line.subscription_plan_id:
                if not line.subscription_plan_id.active:
                    raise ValidationError(f'Cannot reference archived subscription plan "{line.subscription_plan_id.name}".')
                if line.quantity < line.subscription_plan_id.minimum_quantity:
                    raise ValidationError(
                        f'Quantity {line.quantity} is below plan minimum quantity '
                        f'({line.subscription_plan_id.minimum_quantity}) for "{line.subscription_plan_id.name}".'
                    )

