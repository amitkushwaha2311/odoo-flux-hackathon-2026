# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.sale_order_template
#
# Extensions to native sale.order.template & sale.order.template.line
# for Brightloop Quotation Templates
#
# PHASE 5 SCOPE
# -------------
# - Template line subscription plan support (subscription_plan_id).
# - Safe propagation of subscription plan from template line to quotation line.
# - Validation ensuring templates do not reference archived products or plans.
# - Role-based permissions: Admin manages templates, Staff uses active templates.
# =============================================================================

import logging
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

_logger = logging.getLogger(__name__)


class SaleOrderTemplate(models.Model):
    _inherit = 'sale.order.template'

    # =========================================================================
    # ROLE-BASED ACCESS CONTROL
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        caller = self.env.user
        caller_is_admin = (
            self.env.is_admin()
            or caller.has_group('brightloop_core.group_brightloop_admin')
            or self.env.is_superuser()
        )
        if not caller_is_admin:
            raise AccessError('Only Brightloop Administrators can create quotation templates.')

        return super().create(vals_list)

    def write(self, vals):
        caller = self.env.user
        caller_is_admin = (
            self.env.is_admin()
            or caller.has_group('brightloop_core.group_brightloop_admin')
            or self.env.is_superuser()
        )
        if not caller_is_admin and any(f in vals for f in ['name', 'sale_order_template_line_ids', 'active', 'number_of_days']):
            raise AccessError('Only Brightloop Administrators can modify quotation templates.')

        return super().write(vals)

    def unlink(self):
        caller = self.env.user
        caller_is_admin = (
            self.env.is_admin()
            or caller.has_group('brightloop_core.group_brightloop_admin')
            or self.env.is_superuser()
        )
        if not caller_is_admin:
            raise AccessError('Only Brightloop Administrators can delete quotation templates.')

        return super().unlink()


class SaleOrderTemplateLine(models.Model):
    _inherit = 'sale.order.template.line'

    subscription_plan_id = fields.Many2one(
        comodel_name='brightloop.subscription.plan',
        string='Subscription Plan',
        help='Optional subscription plan associated with this template line.',
    )

    @api.constrains('product_id', 'subscription_plan_id')
    def _check_template_line_validity(self):
        for line in self:
            if line.product_id and not line.product_id.active:
                raise ValidationError(f'Cannot reference archived product "{line.product_id.name}" in template.')
            if line.subscription_plan_id and not line.subscription_plan_id.active:
                raise ValidationError(f'Cannot reference archived subscription plan "{line.subscription_plan_id.name}" in template.')

    def _prepare_order_line_values(self, fiscal_position, currency):
        """
        Extend native template line values to include the subscription_plan_id.
        """
        vals = super()._prepare_order_line_values(fiscal_position, currency)
        if self.subscription_plan_id:
            vals['subscription_plan_id'] = self.subscription_plan_id.id
            if not vals.get('product_id') and self.subscription_plan_id.product_id:
                vals['product_id'] = self.subscription_plan_id.product_id.id
        return vals

