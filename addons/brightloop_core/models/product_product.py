# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.product_product
#
# Extensions to product.product for Brightloop Variant Management
#
# PHASE 3 SCOPE
# -------------
# - Variant-level price modification restrictions (Admin-only).
# - Lifecycle availability validation.
# =============================================================================

import logging
from odoo import api, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def write(self, vals):
        """
        Enforce that only Brightloop Administrators can modify variant pricing or cost.
        """
        caller = self.env.user
        caller_is_admin = self.env.is_admin() or caller.has_group('brightloop_core.group_brightloop_admin') or self.env.is_superuser()

        restricted_fields = {'lst_price', 'standard_price', 'active', 'default_code'}
        if not caller_is_admin and any(f in vals for f in restricted_fields):
            self.env['brightloop.security.audit'].log_event(
                event_type='unauthorized_access',
                summary='Unauthorized variant modification attempt',
                details=f'User {caller.login} attempted to modify variant fields {set(vals.keys()) & restricted_fields} on variants {self.ids}.',
            )
            raise AccessError('Only Brightloop Administrators can modify product variant pricing or configuration.')

        return super().write(vals)

    def check_available_for_sale(self):
        """
        Ensure variant is active and its parent template is active.
        """
        for variant in self:
            if not variant.active:
                raise UserError(f'Variant "{variant.display_name}" is archived and cannot be used in sales operations.')
            if not variant.product_tmpl_id.active:
                raise UserError(f'Parent product "{variant.product_tmpl_id.name}" is archived and cannot be used.')
        return True

