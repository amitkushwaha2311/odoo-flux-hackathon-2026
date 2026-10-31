# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.pricing_service
#
# Dedicated Pricing Service for Product Variants & Currency-Aware Calculations
#
# PHASE 3 SCOPE
# -------------
# Provides deterministic, currency-rounded price calculations for variants:
#   - Base template price retrieval
#   - Variant attribute extra price aggregation
#   - Currency precision rounding
#   - Protection against double-counting of extra prices
#   - Validation against archived or unavailable variants
# =============================================================================

import logging
from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BrightloopPricingService(models.AbstractModel):
    """
    Service responsible for calculating and auditing product variant prices.
    """
    _name = 'brightloop.pricing.service'
    _description = 'Brightloop Variant Pricing Service'

    @api.model
    def calculate_variant_price(self, variant, currency=None) -> float:
        """
        Calculate the exact effective sales price for a product variant.

        Formula:
            effective_price = base_template_price + sum(attribute_value.price_extra)

        Guarantees:
          - Validates variant is active and available.
          - The additional price is applied exactly once.
          - Respects currency rounding precision.

        :param variant: product.product record
        :param currency: optional target res.currency record (defaults to variant currency)
        :return: Float rounded according to currency precision
        :raises UserError: If the variant or parent template is archived
        """
        if not variant:
            raise UserError('Variant record is required for price calculation.')

        # Availability check
        variant.check_available_for_sale()

        template = variant.product_tmpl_id
        target_currency = currency or variant.currency_id or template.currency_id

        # 1. Base price from template
        base_price = template.list_price or 0.0

        # 2. Attribute value extra prices applied exactly once
        attribute_values = variant.product_template_attribute_value_ids
        total_extra = sum(ptav.price_extra for ptav in attribute_values)

        # 3. Combined effective price
        effective_price = base_price + total_extra

        # 4. Currency rounding
        if target_currency:
            effective_price = target_currency.round(effective_price)

        return effective_price

    @api.model
    def get_variant_price_breakdown(self, variant, currency=None) -> dict:
        """
        Return a detailed, transparent breakdown of the variant price calculation.

        :param variant: product.product record
        :param currency: optional target res.currency record
        :return: Dict containing base_price, extra breakdown, total_extra, effective_price
        """
        if not variant:
            raise UserError('Variant record is required.')

        variant.check_available_for_sale()

        template = variant.product_tmpl_id
        target_currency = currency or variant.currency_id or template.currency_id

        base_price = template.list_price or 0.0

        extras_detail = []
        total_extra = 0.0
        for ptav in variant.product_template_attribute_value_ids:
            extra = ptav.price_extra or 0.0
            total_extra += extra
            extras_detail.append({
                'attribute_id': ptav.attribute_id.id,
                'attribute_name': ptav.attribute_id.name,
                'value_id': ptav.product_attribute_value_id.id,
                'value_name': ptav.name,
                'price_extra': extra,
            })

        effective_price = base_price + total_extra
        if target_currency:
            effective_price = target_currency.round(effective_price)
            base_price = target_currency.round(base_price)
            total_extra = target_currency.round(total_extra)

        return {
            'product_id': variant.id,
            'template_id': template.id,
            'display_name': variant.display_name,
            'currency_id': target_currency.id if target_currency else False,
            'currency_symbol': target_currency.symbol if target_currency else '',
            'base_price': base_price,
            'attribute_extras': extras_detail,
            'total_extra': total_extra,
            'effective_price': effective_price,
        }

