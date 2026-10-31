# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.discount
#
# Brightloop Discount Configuration Model
#
# PHASE 7 SCOPE
# -------------
# - Configurable discount rules for products, categories, and subscription plans.
# - Percentage and fixed-amount discount types.
# - Minimum purchase amount and quantity conditions.
# - Date-based validity windows.
# - Usage limit tracking with concurrency-safe increment.
# - Company and currency awareness.
# - Multi-scope: product, category, subscription plan, quotation line, recurring invoice.
#
# USAGE POLICY
# ------------
# Usage is consumed (incremented) when a discount is applied to a CONFIRMED
# quotation or a recurring subscription invoice computation. If the transaction
# rolls back, the increment is not committed, ensuring no phantom usage.
# =============================================================================

import logging
from odoo import api, fields, models
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class BrightloopDiscount(models.Model):
    """
    Brightloop Discount Rule.

    Defines a reusable discount that can be applied to quotation lines,
    subscription lines, and future recurring invoice computations.

    Eligibility is evaluated by brightloop.discount.service before application.
    Usage tracking uses database-level SELECT FOR UPDATE to prevent concurrent
    over-redemption.
    """
    _name = 'brightloop.discount'
    _inherit = ['brightloop.base']
    _description = 'Brightloop Discount Rule'
    _order = 'priority desc, name asc'

    # =========================================================================
    # IDENTIFICATION
    # =========================================================================

    name = fields.Char(
        string='Discount Name',
        required=True,
        index=True,
        help='Human-readable name for this discount rule.',
    )

    description = fields.Text(
        string='Description',
        help='Detailed description of the discount purpose and conditions.',
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        index=True,
        help='Inactive discounts are excluded from eligibility checks.',
    )

    # =========================================================================
    # DISCOUNT TYPE & VALUE
    # =========================================================================

    discount_type = fields.Selection(
        selection=[
            ('percentage', 'Percentage (%)'),
            ('fixed', 'Fixed Amount'),
        ],
        string='Discount Type',
        required=True,
        default='percentage',
        help='Percentage: discount_value% of the line price. Fixed: flat currency amount.',
    )

    discount_value = fields.Float(
        string='Discount Value',
        required=True,
        default=0.0,
        help='For Percentage: value between 0 and 100. For Fixed: currency amount.',
    )

    maximum_discount_amount = fields.Monetary(
        string='Maximum Discount Amount',
        currency_field='currency_id',
        default=0.0,
        help='Cap for percentage discounts. 0 means no cap. Ignored for fixed discounts.',
    )

    # =========================================================================
    # CONDITIONS
    # =========================================================================

    minimum_purchase_amount = fields.Monetary(
        string='Minimum Purchase Amount',
        currency_field='currency_id',
        default=0.0,
        help='Minimum line total (before discount) required to qualify. 0 means no minimum.',
    )

    minimum_quantity = fields.Float(
        string='Minimum Quantity',
        default=0.0,
        help='Minimum quantity of the product on the line to qualify. 0 means no minimum.',
    )

    start_date = fields.Date(
        string='Valid From',
        index=True,
        help='Discount is not applicable before this date. Leave blank for no start restriction.',
    )

    end_date = fields.Date(
        string='Valid Until',
        index=True,
        help='Discount expires after this date. Leave blank for no expiry.',
    )

    usage_limit = fields.Integer(
        string='Usage Limit',
        default=0,
        help='Maximum number of times this discount may be applied. 0 means unlimited.',
    )

    usage_count = fields.Integer(
        string='Usage Count',
        default=0,
        readonly=True,
        help='Current number of times this discount has been applied.',
    )

    # =========================================================================
    # SCOPE
    # =========================================================================

    application_scope = fields.Selection(
        selection=[
            ('product', 'Specific Products'),
            ('category', 'Product Categories'),
            ('subscription_plan', 'Subscription Plans'),
            ('all', 'All Eligible Lines'),
        ],
        string='Application Scope',
        required=True,
        default='all',
        help='Controls which line types this discount may be applied to.',
    )

    product_ids = fields.Many2many(
        comodel_name='product.product',
        relation='brightloop_discount_product_rel',
        column1='discount_id',
        column2='product_id',
        string='Eligible Products',
        help='Restrict this discount to specific product variants.',
    )

    product_category_ids = fields.Many2many(
        comodel_name='product.category',
        relation='brightloop_discount_category_rel',
        column1='discount_id',
        column2='category_id',
        string='Eligible Product Categories',
        help='Restrict this discount to products in these categories.',
    )

    subscription_plan_ids = fields.Many2many(
        comodel_name='brightloop.subscription.plan',
        relation='brightloop_discount_plan_rel',
        column1='discount_id',
        column2='plan_id',
        string='Eligible Subscription Plans',
        help='Restrict this discount to specific subscription plans.',
    )

    # =========================================================================
    # STACKING & PRIORITY
    # =========================================================================

    stackable = fields.Boolean(
        string='Stackable',
        default=False,
        help='Whether this discount can be combined with other discounts on the same line.',
    )

    priority = fields.Integer(
        string='Priority',
        default=0,
        help='Higher priority discounts are evaluated and applied first.',
    )

    # =========================================================================
    # CURRENCY & COMPANY
    # =========================================================================

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
        help='Currency for fixed discount amounts and monetary thresholds.',
    )

    # =========================================================================
    # CONSTRAINTS
    # =========================================================================

    @api.constrains('discount_type', 'discount_value')
    def _check_discount_value(self):
        for rec in self:
            if rec.discount_value < 0.0:
                raise ValidationError('Discount value cannot be negative.')
            if rec.discount_type == 'percentage' and rec.discount_value > 100.0:
                raise ValidationError('Percentage discount cannot exceed 100%.')

    @api.constrains('maximum_discount_amount')
    def _check_maximum_discount_amount(self):
        for rec in self:
            if rec.maximum_discount_amount < 0.0:
                raise ValidationError('Maximum discount amount cannot be negative.')

    @api.constrains('minimum_purchase_amount')
    def _check_minimum_purchase_amount(self):
        for rec in self:
            if rec.minimum_purchase_amount < 0.0:
                raise ValidationError('Minimum purchase amount cannot be negative.')

    @api.constrains('minimum_quantity')
    def _check_minimum_quantity(self):
        for rec in self:
            if rec.minimum_quantity < 0.0:
                raise ValidationError('Minimum quantity cannot be negative.')

    @api.constrains('usage_limit')
    def _check_usage_limit(self):
        for rec in self:
            if rec.usage_limit < 0:
                raise ValidationError('Usage limit cannot be negative.')

    @api.constrains('start_date', 'end_date')
    def _check_date_range(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.start_date > rec.end_date:
                raise ValidationError(
                    f'Discount start date ({rec.start_date}) cannot be after end date ({rec.end_date}).'
                )

    # =========================================================================
    # USAGE TRACKING — CONCURRENCY SAFE
    # =========================================================================

    def _increment_usage(self):
        """
        Atomically increment usage_count using SELECT FOR UPDATE row locking.

        This method acquires a database-level exclusive lock on the discount
        row before reading and incrementing. Any concurrent transaction that
        attempts to increment the same row will block until this transaction
        commits or rolls back, preventing over-redemption.

        Business rule: usage is consumed when a discount is applied to a
        CONFIRMED quotation or a billing cycle computation. If the wrapping
        transaction rolls back (e.g., payment failure), the increment is not
        committed.

        Raises UserError if usage_limit is exhausted.
        """
        self.ensure_one()
        self.env.cr.execute(
            'SELECT usage_count, usage_limit FROM brightloop_discount WHERE id = %s FOR UPDATE',
            (self.id,)
        )
        row = self.env.cr.fetchone()
        if not row:
            raise UserError(f'Discount record {self.id} not found.')

        current_usage, limit = row
        if limit > 0 and current_usage >= limit:
            raise UserError(
                f'Discount "{self.name}" has reached its usage limit of {limit}. '
                'No further applications are permitted.'
            )

        new_usage = current_usage + 1
        self.env.cr.execute(
            'UPDATE brightloop_discount SET usage_count = %s WHERE id = %s',
            (new_usage, self.id)
        )
        # Invalidate ORM cache so subsequent reads see the updated value
        self.invalidate_recordset(['usage_count'])

        self.env['brightloop.security.audit'].log_event(
            event_type='discount_usage_updated',
            summary=f'Discount usage incremented: {self.name}',
            details=f'Discount "{self.name}" usage updated from {current_usage} to {new_usage} (limit: {limit or "unlimited"}).',
        )
        return new_usage

    # =========================================================================
    # CREATE / WRITE — AUDIT HOOKS
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            self.env['brightloop.security.audit'].log_event(
                event_type='discount_created',
                summary=f'Discount created: {rec.name}',
                details=f'Discount "{rec.name}" ({rec.discount_type}: {rec.discount_value}) created for company {rec.company_id.name}.',
            )
        return records

    def write(self, vals):
        result = super().write(vals)
        for rec in self:
            if 'active' in vals:
                evt = 'discount_activated' if vals['active'] else 'discount_deactivated'
                self.env['brightloop.security.audit'].log_event(
                    event_type=evt,
                    summary=f'Discount {"activated" if vals["active"] else "deactivated"}: {rec.name}',
                    details=f'Discount "{rec.name}" active status changed to {vals["active"]}.',
                )
            elif any(k in vals for k in ('discount_type', 'discount_value', 'maximum_discount_amount',
                                          'start_date', 'end_date', 'usage_limit', 'minimum_purchase_amount',
                                          'minimum_quantity', 'application_scope', 'stackable', 'priority')):
                self.env['brightloop.security.audit'].log_event(
                    event_type='discount_updated',
                    summary=f'Discount updated: {rec.name}',
                    details=f'Discount "{rec.name}" configuration modified. Changed fields: {list(vals.keys())}.',
                )
        return result

