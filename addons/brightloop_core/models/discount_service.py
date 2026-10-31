# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.discount_service
#
# Brightloop Discount Eligibility & Calculation Service
#
# PHASE 7 SCOPE
# -------------
# - Deterministic discount eligibility evaluation with clear rejection reasons.
# - Percentage and fixed discount calculation.
# - Maximum discount cap enforcement.
# - Negative total prevention.
# - Quantity-aware calculation.
# - Non-stackable discount conflict detection.
# - No discount applied twice (idempotency guard).
# - Ordered multi-discount application (priority desc, stackable-aware).
# - Reusable by Phase 8 recurring invoice generation.
#
# CALCULATION ORDER
# -----------------
# 1. Resolve product/variant base price.
# 2. Multiply by quantity to get gross line total.
# 3. Collect all eligible discounts for the line (sorted by priority desc).
# 4. Apply non-stackable discounts (only the highest priority non-stackable one).
# 5. Apply all stackable discounts cumulatively on the post-non-stackable price.
# 6. Enforce maximum_discount_amount per discount.
# 7. Prevent negative line totals (floor at 0.00).
# 8. Return a structured breakdown for the tax service and audit purposes.
# =============================================================================

import logging
from datetime import date
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class BrightloopDiscountService(models.AbstractModel):
    """
    Brightloop Discount Eligibility and Calculation Service.

    Provides deterministic evaluation of discount eligibility and application.
    This is a stateless AbstractModel service — all state is passed as arguments.

    Designed to be reused by:
    - Quotation line computation (Phase 5/7).
    - Subscription line computation (Phase 6/7).
    - Recurring invoice generation (Phase 8).
    """
    _name = 'brightloop.discount.service'
    _description = 'Brightloop Discount Eligibility & Calculation Service'

    # =========================================================================
    # ELIGIBILITY CHECK
    # =========================================================================

    @api.model
    def check_eligibility(
        self,
        discount,
        product=None,
        subscription_plan=None,
        quantity=0.0,
        purchase_amount=0.0,
        target_date=None,
        company=None,
        currency=None,
    ):
        """
        Evaluate a single discount for eligibility against a transaction context.

        Returns a dict:
        {
            'eligible': bool,
            'reason': str,           # 'ok' if eligible, rejection reason otherwise
        }

        :param discount: brightloop.discount record
        :param product: product.product record or None
        :param subscription_plan: brightloop.subscription.plan record or None
        :param quantity: float — line quantity
        :param purchase_amount: float — line total before discount (price_unit * quantity)
        :param target_date: date — evaluation date (defaults to today)
        :param company: res.company record (defaults to env.company)
        :param currency: res.currency record (for amount comparison, defaults to discount.currency_id)
        """
        today = target_date or date.today()
        company = company or self.env.company
        currency = currency or discount.currency_id

        # 1. Active check
        if not discount.active:
            return {'eligible': False, 'reason': 'Discount is inactive.'}

        # 2. Date validity
        if discount.start_date and today < discount.start_date:
            return {'eligible': False, 'reason': f'Discount is not yet valid (starts {discount.start_date}).'}
        if discount.end_date and today > discount.end_date:
            return {
                'eligible': False,
                'reason': f'Discount has expired (expired {discount.end_date}).',
            }

        # 3. Company match
        if discount.company_id and discount.company_id != company:
            return {
                'eligible': False,
                'reason': f'Discount belongs to company "{discount.company_id.name}", not "{company.name}".',
            }

        # 4. Currency compatibility
        if discount.discount_type == 'fixed' and currency and discount.currency_id != currency:
            return {
                'eligible': False,
                'reason': (
                    f'Fixed discount currency ({discount.currency_id.name}) '
                    f'does not match transaction currency ({currency.name}).'
                ),
            }

        # 5. Usage limit
        if discount.usage_limit > 0 and discount.usage_count >= discount.usage_limit:
            return {
                'eligible': False,
                'reason': f'Discount usage limit ({discount.usage_limit}) has been exhausted.',
            }

        # 6. Minimum purchase amount
        if discount.minimum_purchase_amount > 0.0:
            if purchase_amount < discount.minimum_purchase_amount:
                return {
                    'eligible': False,
                    'reason': (
                        f'Purchase amount ({purchase_amount:.2f}) does not meet '
                        f'minimum required ({discount.minimum_purchase_amount:.2f}).'
                    ),
                }

        # 7. Minimum quantity
        if discount.minimum_quantity > 0.0:
            if quantity < discount.minimum_quantity:
                return {
                    'eligible': False,
                    'reason': (
                        f'Quantity ({quantity}) does not meet '
                        f'minimum required ({discount.minimum_quantity}).'
                    ),
                }

        # 8. Scope — product eligibility
        scope = discount.application_scope
        if scope == 'product':
            if not product:
                return {'eligible': False, 'reason': 'No product provided for product-scoped discount.'}
            if product not in discount.product_ids:
                return {
                    'eligible': False,
                    'reason': f'Product "{product.display_name}" is not in discount\'s eligible products.',
                }

        # 9. Scope — category eligibility
        elif scope == 'category':
            if not product:
                return {'eligible': False, 'reason': 'No product provided for category-scoped discount.'}
            product_categ = product.categ_id
            if product_categ not in discount.product_category_ids:
                return {
                    'eligible': False,
                    'reason': f'Product category "{product_categ.complete_name}" is not eligible.',
                }

        # 10. Scope — subscription plan eligibility
        elif scope == 'subscription_plan':
            if not subscription_plan:
                return {'eligible': False, 'reason': 'No subscription plan provided for plan-scoped discount.'}
            if subscription_plan not in discount.subscription_plan_ids:
                return {
                    'eligible': False,
                    'reason': f'Subscription plan "{subscription_plan.name}" is not in eligible plans.',
                }

        return {'eligible': True, 'reason': 'ok'}

    # =========================================================================
    # DISCOUNT CALCULATION
    # =========================================================================

    @api.model
    def calculate_discount_amount(self, discount, price_unit, quantity, currency=None):
        """
        Calculate the monetary discount amount for a single line.

        :param discount: brightloop.discount record
        :param price_unit: float — unit price before discount
        :param quantity: float — line quantity
        :param currency: res.currency record for rounding
        :return: float — discount amount (always >= 0, never exceeds gross total)

        Calculation:
          gross = price_unit * quantity
          For percentage: raw_discount = gross * (discount_value / 100)
              Capped by maximum_discount_amount if > 0.
          For fixed: raw_discount = min(discount_value, gross)  # cannot exceed line total
        """
        currency = currency or discount.currency_id
        gross = price_unit * quantity

        if discount.discount_type == 'percentage':
            raw_discount = gross * (discount.discount_value / 100.0)
            # Apply maximum cap
            if discount.maximum_discount_amount > 0.0:
                raw_discount = min(raw_discount, discount.maximum_discount_amount)
        else:  # fixed
            raw_discount = discount.discount_value

        # Discount cannot exceed the gross line total
        discount_amount = min(raw_discount, gross)
        discount_amount = max(discount_amount, 0.0)

        if currency:
            discount_amount = currency.round(discount_amount)

        return discount_amount

    # =========================================================================
    # MULTI-DISCOUNT APPLICATION ENGINE
    # =========================================================================

    @api.model
    def apply_discounts(
        self,
        discounts,
        price_unit,
        quantity,
        product=None,
        subscription_plan=None,
        currency=None,
        target_date=None,
        company=None,
        increment_usage=False,
    ):
        """
        Apply a prioritized list of discounts to a line and return a full breakdown.

        Stacking rules:
        1. Sort discounts by priority descending.
        2. Among non-stackable discounts, only the highest-priority one is applied.
        3. All stackable discounts are applied cumulatively on the remaining price
           AFTER non-stackable discounts.
        4. Same discount cannot be applied twice (idempotency: de-duplicate input).
        5. Final line total cannot be negative (floored at 0.00).

        :param discounts: list/recordset of brightloop.discount records
        :param price_unit: float — base unit price
        :param quantity: float — line quantity
        :param product: product.product record or None
        :param subscription_plan: brightloop.subscription.plan record or None
        :param currency: res.currency record
        :param target_date: date for validity checks (defaults to today)
        :param company: res.company (defaults to env.company)
        :param increment_usage: bool — if True, increment usage_count for applied discounts
        :return: dict with full calculation breakdown
        """
        currency = currency or self.env.company.currency_id
        company = company or self.env.company
        gross = price_unit * quantity
        purchase_amount = gross

        # De-duplicate discounts by ID
        seen_ids = set()
        unique_discounts = []
        for d in discounts:
            if d.id not in seen_ids:
                seen_ids.add(d.id)
                unique_discounts.append(d)

        # Sort by priority descending
        sorted_discounts = sorted(unique_discounts, key=lambda d: d.priority, reverse=True)

        applied = []
        rejected = []
        total_discount = 0.0
        current_price = gross

        # Separate stackable and non-stackable
        non_stackable_applied = False
        stackable_pool = []
        non_stackable_pool = []

        for d in sorted_discounts:
            result = self.check_eligibility(
                discount=d,
                product=product,
                subscription_plan=subscription_plan,
                quantity=quantity,
                purchase_amount=purchase_amount,
                target_date=target_date,
                company=company,
                currency=currency,
            )
            if not result['eligible']:
                rejected.append({
                    'discount_id': d.id,
                    'discount_name': d.name,
                    'reason': result['reason'],
                })
                self.env['brightloop.security.audit'].log_event(
                    event_type='discount_rejected',
                    summary=f'Discount rejected: {d.name}',
                    details=result['reason'],
                )
                continue

            if d.stackable:
                stackable_pool.append(d)
            else:
                non_stackable_pool.append(d)

        # Apply highest-priority non-stackable first
        if non_stackable_pool:
            d = non_stackable_pool[0]  # already sorted by priority
            disc_amt = self.calculate_discount_amount(d, price_unit, quantity, currency)
            if increment_usage:
                d._increment_usage()
            applied.append({
                'discount_id': d.id,
                'discount_name': d.name,
                'discount_type': d.discount_type,
                'discount_value': d.discount_value,
                'discount_amount': disc_amt,
            })
            total_discount += disc_amt
            current_price -= disc_amt
            non_stackable_applied = True

            # Log rejected non-stackables (lower priority, same non-stackable slot)
            for skipped in non_stackable_pool[1:]:
                rejected.append({
                    'discount_id': skipped.id,
                    'discount_name': skipped.name,
                    'reason': 'Non-stackable discount: higher-priority discount already applied.',
                })

        # Apply stackable discounts sequentially on remaining price
        for d in stackable_pool:
            if current_price <= 0.0:
                rejected.append({
                    'discount_id': d.id,
                    'discount_name': d.name,
                    'reason': 'Line total already reduced to zero; stackable discount has no effect.',
                })
                continue
            # Recalculate per-unit from current remaining price
            remaining_unit = current_price / quantity if quantity else 0.0
            disc_amt = self.calculate_discount_amount(d, remaining_unit, quantity, currency)
            if increment_usage:
                d._increment_usage()
            applied.append({
                'discount_id': d.id,
                'discount_name': d.name,
                'discount_type': d.discount_type,
                'discount_value': d.discount_value,
                'discount_amount': disc_amt,
            })
            total_discount += disc_amt
            current_price -= disc_amt

        # Floor at zero
        final_total = max(current_price, 0.0)
        if currency:
            final_total = currency.round(final_total)
            total_discount = currency.round(total_discount)

        breakdown = {
            'gross_amount': gross,
            'total_discount': total_discount,
            'final_amount_before_tax': final_total,
            'applied_discounts': applied,
            'rejected_discounts': rejected,
            'effective_discount_percent': round((total_discount / gross * 100), 4) if gross else 0.0,
        }

        if applied:
            self.env['brightloop.security.audit'].log_event(
                event_type='discount_applied',
                summary=f'{len(applied)} discount(s) applied',
                details=(
                    f'Applied discounts: {[a["discount_name"] for a in applied]}. '
                    f'Total discount: {total_discount}. '
                    f'Final amount before tax: {final_total}.'
                ),
            )

        return breakdown

    # =========================================================================
    # SUBSCRIPTION RECURRING ELIGIBILITY VALIDATION
    # =========================================================================

    @api.model
    def validate_recurring_discount(self, discount, billing_date, subscription_plan=None,
                                     product=None, quantity=0.0, purchase_amount=0.0,
                                     company=None, currency=None):
        """
        Re-evaluate discount eligibility for a recurring billing period.

        Discounts must be re-validated for EVERY billing cycle because:
        - End dates may have passed since initial application.
        - Usage limits may have been exhausted by other contracts.
        - Plans or products may have been changed.

        :param billing_date: date — the date of the billing cycle being computed
        :return: eligibility dict from check_eligibility
        """
        return self.check_eligibility(
            discount=discount,
            product=product,
            subscription_plan=subscription_plan,
            quantity=quantity,
            purchase_amount=purchase_amount,
            target_date=billing_date,
            company=company,
            currency=currency,
        )

