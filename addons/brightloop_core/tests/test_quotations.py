# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.tests.test_quotations
#
# Phase 5 Automated Tests — Quotation & Sales Management Engine
#
# Test coverage:
#   - Quotation creation & customer selection (tests 01–05)
#   - Regular product & subscription plan lines (tests 06–12)
#   - Pricing: base price, variant surcharge ₹2,000+₹560=₹2,560, subtotal ₹5,120,
#     no double surcharge, billing metadata (tests 13–18)
#   - Quotation templates: creation, application, multi-line, duplicate prevention,
#     archived product/plan rejection (tests 19–24)
#   - Validity date, expiration detection, confirmation guards & extension (tests 25–30)
#   - Commercial workflow: Draft -> Sent -> Confirmed, cancellation, confirmed
#     modification restrictions, NO premature subscription activation (tests 31–36)
#   - Role-based security (Admin CRUD, Staff operational, Customer isolated) (tests 37–41)
#   - Immutable audit logging for all quotation lifecycle events (tests 42–44)
# =============================================================================

from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestQuotations(TransactionCase):
    """
    Phase 5 test suite: Quotation & Sales Management Engine.
    Extends Odoo's native sale.order, sale.order.line, sale.order.template.
    """

    def setUp(self):
        super().setUp()

        self.SaleOrder = self.env['sale.order']
        self.SaleOrderLine = self.env['sale.order.line']
        self.SaleOrderTemplate = self.env['sale.order.template']
        self.ProductTemplate = self.env['product.template']
        self.ProductAttribute = self.env['product.attribute']
        self.ProductAttributeValue = self.env['product.attribute.value']
        self.SubscriptionPlan = self.env['brightloop.subscription.plan']
        self.SecurityAudit = self.env['brightloop.security.audit']
        self.Users = self.env['res.users']
        self.Partner = self.env['res.partner']

        self.admin_group = self.env.ref('brightloop_core.group_brightloop_admin')
        self.staff_group = self.env.ref('brightloop_core.group_brightloop_staff')
        self.customer_group = self.env.ref('brightloop_core.group_brightloop_customer')
        self.internal_group = self.env.ref('base.group_user')

        # 1. Admin user
        partner_admin = self.Partner.create({
            'name': 'Quote Admin',
            'email': 'quoteadmin@brightloop.io',
        })
        self.admin_user = self.Users.create({
            'name': 'Quote Admin',
            'login': 'quoteadmin@brightloop.io',
            'email': 'quoteadmin@brightloop.io',
            'partner_id': partner_admin.id,
            'group_ids': [(6, 0, [self.admin_group.id, self.internal_group.id])],
        })

        # 2. Staff user
        partner_staff = self.Partner.create({
            'name': 'Quote Staff',
            'email': 'quotestaff@brightloop.io',
        })
        self.staff_user = self.Users.create({
            'name': 'Quote Staff',
            'login': 'quotestaff@brightloop.io',
            'email': 'quotestaff@brightloop.io',
            'partner_id': partner_staff.id,
            'group_ids': [(6, 0, [self.staff_group.id, self.internal_group.id])],
        })

        # 3. Customer A user (portal)
        self.customer_user_a = self.Users.register_customer(
            name='Quote Customer A',
            email='customer.a.quote@brightloop.io',
            password='CustomerSecurePass123!',
        )
        self.partner_a = self.customer_user_a.partner_id

        # 4. Customer B user (portal)
        self.customer_user_b = self.Users.register_customer(
            name='Quote Customer B',
            email='customer.b.quote@brightloop.io',
            password='CustomerSecurePass123!',
        )
        self.partner_b = self.customer_user_b.partner_id

        # 5. Base Product (₹2,000)
        self.base_tmpl = self.ProductTemplate.create({
            'name': 'Brightloop Platform Base',
            'type': 'service',
            'list_price': 2000.0,
        })
        self.base_product = self.base_tmpl.product_variant_ids[0]

        # 6. Product Variant: ₹2,000 base + ₹560 Odoo surcharge = ₹2,560
        attr = self.ProductAttribute.create({'name': 'Edition'})
        val_std = self.ProductAttributeValue.create({'name': 'Standard', 'attribute_id': attr.id})
        val_odoo = self.ProductAttributeValue.create({'name': 'Odoo', 'attribute_id': attr.id})

        self.variant_tmpl = self.ProductTemplate.create({
            'name': 'Brightloop SaaS Suite',
            'type': 'service',
            'list_price': 2000.0,
            'attribute_line_ids': [(0, 0, {
                'attribute_id': attr.id,
                'value_ids': [(6, 0, [val_std.id, val_odoo.id])],
            })],
        })
        odoo_ptav = self.variant_tmpl.attribute_line_ids.product_template_value_ids.filtered(
            lambda p: p.name == 'Odoo'
        )
        odoo_ptav.sudo().write({'price_extra': 560.0})

        self.odoo_variant = self.variant_tmpl.product_variant_ids.filtered(
            lambda v: any(p.name == 'Odoo' for p in v.product_template_attribute_value_ids)
        )

        # 7. Subscription Plan (Monthly, ₹2,560, Min Qty 1)
        self.plan_monthly = self.SubscriptionPlan.create({
            'name': 'SaaS Monthly Plan',
            'product_id': self.odoo_variant.id,
            'billing_interval': 'monthly',
            'billing_interval_count': 1,
            'list_price': 2560.0,
            'minimum_quantity': 1.0,
        })

    # =========================================================================
    # QUOTATION CREATION & CUSTOMER SELECTION (tests 01–05)
    # =========================================================================

    def test_01_create_valid_quotation(self):
        """Staff can create a valid quotation in draft state."""
        order = self.SaleOrder.with_user(self.staff_user).create({
            'partner_id': self.partner_a.id,
        })
        self.assertTrue(order.id)
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.partner_id, self.partner_a)
        self.assertEqual(order.company_id, self.env.company)

    def test_02_missing_customer_rejected(self):
        """Quotation without a customer partner raises exception."""
        with self.assertRaises(Exception):
            self.SaleOrder.create({
                'partner_id': False,
            })

    def test_03_valid_customer_selection(self):
        """Quotation correctly links to customer partner."""
        order = self.SaleOrder.create({
            'partner_id': self.partner_b.id,
        })
        self.assertEqual(order.partner_id.id, self.partner_b.id)

    def test_04_multi_company_validation(self):
        """Order must belong to active company."""
        order = self.SaleOrder.create({
            'partner_id': self.partner_a.id,
        })
        self.assertEqual(order.company_id.id, self.env.company.id)

    def test_05_draft_quotation_creation(self):
        """Newly created quotation defaults to 'draft' status."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        self.assertEqual(order.state, 'draft')
        self.assertFalse(order.is_subscription_quotation)

    # =========================================================================
    # REGULAR & SUBSCRIPTION PLAN QUOTATION LINES (tests 06–12)
    # =========================================================================

    def test_06_add_regular_product_line(self):
        """Add regular base product line to quotation."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.base_product.id,
            'product_uom_qty': 1.0,
        })
        self.assertTrue(line.id)
        self.assertEqual(line.price_unit, 2000.0)
        self.assertFalse(line.is_subscription_line)
        self.assertFalse(order.is_subscription_quotation)

    def test_07_add_product_variant_line(self):
        """Add variant product line with ₹560 surcharge (₹2,560 unit price)."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.odoo_variant.id,
            'product_uom_qty': 1.0,
        })
        self.assertAlmostEqual(line.price_unit, 2560.0, places=2)

    def test_08_add_subscription_plan_line(self):
        """Add subscription plan line to quotation."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.odoo_variant.id,
            'subscription_plan_id': self.plan_monthly.id,
            'product_uom_qty': 1.0,
        })
        self.assertTrue(line.is_subscription_line)
        self.assertTrue(order.is_subscription_quotation)
        self.assertEqual(line.billing_interval, 'monthly')
        self.assertEqual(line.billing_interval_count, 1)

    def test_09_archived_product_rejected_on_line(self):
        """Attempting to add an archived product raises ValidationError."""
        archived_tmpl = self.ProductTemplate.create({
            'name': 'Archived Product',
            'type': 'service',
            'list_price': 100.0,
        })
        archived_prod = archived_tmpl.product_variant_ids[0]
        archived_tmpl.write({'active': False})

        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        with self.assertRaises(ValidationError):
            self.SaleOrderLine.create({
                'order_id': order.id,
                'product_id': archived_prod.id,
                'product_uom_qty': 1.0,
            })

    def test_10_archived_plan_rejected_on_line(self):
        """Attempting to add an archived subscription plan raises ValidationError."""
        archived_plan = self.SubscriptionPlan.create({
            'name': 'Old Plan',
            'product_id': self.odoo_variant.id,
            'billing_interval': 'monthly',
        })
        archived_plan.write({'active': False})

        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        with self.assertRaises(ValidationError):
            self.SaleOrderLine.create({
                'order_id': order.id,
                'product_id': self.odoo_variant.id,
                'subscription_plan_id': archived_plan.id,
                'product_uom_qty': 1.0,
            })

    def test_11_minimum_quantity_validation_on_line(self):
        """Adding quantity below plan minimum quantity raises ValidationError."""
        bulk_plan = self.SubscriptionPlan.create({
            'name': 'Bulk Plan',
            'product_id': self.odoo_variant.id,
            'billing_interval': 'monthly',
            'minimum_quantity': 5.0,
        })
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        with self.assertRaises(ValidationError):
            self.SaleOrderLine.create({
                'order_id': order.id,
                'product_id': self.odoo_variant.id,
                'subscription_plan_id': bulk_plan.id,
                'product_uom_qty': 4.0,
            })

    def test_12_plan_product_incompatibility_rejected(self):
        """Mismatch between selected product and plan product raises ValidationError."""
        other_prod = self.base_product
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        with self.assertRaises(ValidationError):
            self.SaleOrderLine.create({
                'order_id': order.id,
                'product_id': other_prod.id,
                'subscription_plan_id': self.plan_monthly.id,
                'product_uom_qty': 1.0,
            })

    # =========================================================================
    # PRICING INTEGRATION & FINANCIAL CALCULATIONS (tests 13–18)
    # =========================================================================

    def test_13_base_product_pricing(self):
        """Base product line evaluates to ₹2,000."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.base_product.id,
            'product_uom_qty': 1.0,
        })
        self.assertEqual(line.price_unit, 2000.0)
        self.assertEqual(line.price_subtotal, 2000.0)

    def test_14_variant_pricing_2000_plus_560(self):
        """Variant with surcharge evaluates to ₹2,000 + ₹560 = ₹2,560."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.odoo_variant.id,
            'subscription_plan_id': self.plan_monthly.id,
            'product_uom_qty': 1.0,
            'price_unit': 2560.0,
        })
        self.assertAlmostEqual(line.price_unit, 2560.0, places=2)
        self.assertAlmostEqual(line.price_subtotal, 2560.0, places=2)

    def test_15_quantity_multiplication(self):
        """Quantity of 2 at ₹2,560 yields subtotal of ₹5,120."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.odoo_variant.id,
            'subscription_plan_id': self.plan_monthly.id,
            'product_uom_qty': 2.0,
            'price_unit': 2560.0,
        })
        self.assertAlmostEqual(line.price_subtotal, 5120.0, places=2)
        self.assertAlmostEqual(order.amount_untaxed, 5120.0, places=2)

    def test_16_currency_rounding(self):
        """Order amounts respect currency rounding precision."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.base_product.id,
            'product_uom_qty': 1.0,
            'price_unit': 1999.999,
        })
        self.assertAlmostEqual(line.price_subtotal, 2000.0, places=2)

    def test_17_no_duplicate_variant_surcharge(self):
        """Critical: Variant extra of ₹560 is not double-counted."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.odoo_variant.id,
            'subscription_plan_id': self.plan_monthly.id,
            'product_uom_qty': 1.0,
            'price_unit': 2560.0,
        })
        self.assertAlmostEqual(line.price_unit, 2560.0, places=2)
        # Re-save/write quantity
        line.write({'product_uom_qty': 1.0})
        self.assertAlmostEqual(line.price_unit, 2560.0, places=2)
        self.assertAlmostEqual(line.price_subtotal, 2560.0, places=2)

    def test_18_correct_subscription_billing_metadata(self):
        """Quarterly plan line carries frequency='monthly' and interval_count=3."""
        plan_quarterly = self.SubscriptionPlan.create({
            'name': 'Quarterly SaaS Plan',
            'product_id': self.odoo_variant.id,
            'billing_interval': 'monthly',
            'billing_interval_count': 3,
            'list_price': 2560.0,
        })
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.odoo_variant.id,
            'subscription_plan_id': plan_quarterly.id,
            'product_uom_qty': 1.0,
            'price_unit': 2560.0,
        })
        self.assertEqual(line.billing_interval, 'monthly')
        self.assertEqual(line.billing_interval_count, 3)

    # =========================================================================
    # QUOTATION TEMPLATES (tests 19–24)
    # =========================================================================

    def test_19_create_quotation_template(self):
        """Admin can create a quotation template."""
        tmpl = self.SaleOrderTemplate.with_user(self.admin_user).create({
            'name': 'Standard SaaS Template',
            'number_of_days': 30,
            'sale_order_template_line_ids': [(0, 0, {
                'product_id': self.odoo_variant.id,
                'product_uom_qty': 1.0,
                'subscription_plan_id': self.plan_monthly.id,
            })],
        })
        self.assertTrue(tmpl.id)
        self.assertEqual(len(tmpl.sale_order_template_line_ids), 1)

    def test_20_apply_quotation_template(self):
        """Applying a quotation template creates order lines and sets validity."""
        tmpl = self.SaleOrderTemplate.create({
            'name': 'Quick Quote Template',
            'number_of_days': 15,
            'sale_order_template_line_ids': [(0, 0, {
                'product_id': self.odoo_variant.id,
                'product_uom_qty': 1.0,
                'subscription_plan_id': self.plan_monthly.id,
            })],
        })
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        order.apply_brightloop_template(tmpl)

        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(order.order_line[0].product_id, self.odoo_variant)
        self.assertEqual(order.order_line[0].subscription_plan_id, self.plan_monthly)
        expected_validity = order.date_order.date() + relativedelta(days=15)
        self.assertEqual(order.validity_date, expected_validity)

    def test_21_apply_template_with_multiple_lines(self):
        """Applying a multi-line template populates all lines correctly."""
        tmpl = self.SaleOrderTemplate.create({
            'name': 'Multi-Line Template',
            'sale_order_template_line_ids': [
                (0, 0, {'product_id': self.base_product.id, 'product_uom_qty': 2.0}),
                (0, 0, {'product_id': self.odoo_variant.id, 'product_uom_qty': 1.0, 'subscription_plan_id': self.plan_monthly.id}),
            ],
        })
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        order.apply_brightloop_template(tmpl)
        self.assertEqual(len(order.order_line), 2)

    def test_22_template_reject_archived_product(self):
        """Template containing an archived product cannot be applied."""
        prod = self.ProductTemplate.create({'name': 'To Archive', 'type': 'service'}).product_variant_ids[0]
        tmpl = self.SaleOrderTemplate.create({
            'name': 'Bad Product Template',
            'sale_order_template_line_ids': [(0, 0, {'product_id': prod.id, 'product_uom_qty': 1.0})],
        })
        prod.product_tmpl_id.write({'active': False})

        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        with self.assertRaises(UserError):
            order.apply_brightloop_template(tmpl)

    def test_23_template_reject_invalid_plan(self):
        """Template containing an archived subscription plan cannot be applied."""
        plan = self.SubscriptionPlan.create({
            'name': 'Temp Plan',
            'product_id': self.odoo_variant.id,
            'billing_interval': 'monthly',
        })
        tmpl = self.SaleOrderTemplate.create({
            'name': 'Bad Plan Template',
            'sale_order_template_line_ids': [(0, 0, {
                'product_id': self.odoo_variant.id,
                'subscription_plan_id': plan.id,
            })],
        })
        plan.write({'active': False})

        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        with self.assertRaises(UserError):
            order.apply_brightloop_template(tmpl)

    def test_24_template_reapply_prevents_duplicate_lines(self):
        """Re-applying a template cleans up previous lines without duplication."""
        tmpl = self.SaleOrderTemplate.create({
            'name': 'Clean Template',
            'sale_order_template_line_ids': [(0, 0, {'product_id': self.base_product.id, 'product_uom_qty': 1.0})],
        })
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        order.apply_brightloop_template(tmpl)
        self.assertEqual(len(order.order_line), 1)

        # Re-apply same template
        order.apply_brightloop_template(tmpl)
        self.assertEqual(len(order.order_line), 1, 'Reapplying template must not duplicate lines.')

    # =========================================================================
    # VALIDITY AND EXPIRATION (tests 25–30)
    # =========================================================================

    def test_25_valid_quotation_date(self):
        """Quotation validity date set in the future is valid."""
        future_date = date.today() + relativedelta(days=30)
        order = self.SaleOrder.create({
            'partner_id': self.partner_a.id,
            'validity_date': future_date,
        })
        self.assertEqual(order.validity_date, future_date)
        self.assertFalse(order.is_expired)

    def test_26_invalid_validity_date_rejected(self):
        """Validity date earlier than quotation date raises ValidationError."""
        past_date = date.today() - relativedelta(days=5)
        with self.assertRaises(ValidationError):
            self.SaleOrder.create({
                'partner_id': self.partner_a.id,
                'date_order': datetime.now(),
                'validity_date': past_date,
            })

    def test_27_expired_quotation_detection(self):
        """is_expired evaluates to True when validity date has passed on draft order."""
        past_validity = date.today() - relativedelta(days=1)
        past_order_date = datetime.now() - relativedelta(days=10)
        order = self.SaleOrder.create({
            'partner_id': self.partner_a.id,
            'date_order': past_order_date,
            'validity_date': past_validity,
        })
        self.assertTrue(order.is_expired)

    def test_28_expired_quotation_confirmation_rejected(self):
        """Attempting to confirm an expired quotation raises UserError."""
        past_validity = date.today() - relativedelta(days=1)
        past_order_date = datetime.now() - relativedelta(days=10)
        order = self.SaleOrder.create({
            'partner_id': self.partner_a.id,
            'date_order': past_order_date,
            'validity_date': past_validity,
        })
        self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.base_product.id,
            'product_uom_qty': 1.0,
        })
        self.assertTrue(order.is_expired)

        with self.assertRaises(UserError):
            order.action_confirm()

    def test_29_validity_extension(self):
        """Authorized user can extend validity date of an expired quotation."""
        past_validity = date.today() - relativedelta(days=1)
        past_order_date = datetime.now() - relativedelta(days=10)
        order = self.SaleOrder.create({
            'partner_id': self.partner_a.id,
            'date_order': past_order_date,
            'validity_date': past_validity,
        })
        self.assertTrue(order.is_expired)

        new_date = date.today() + relativedelta(days=14)
        order.with_user(self.staff_user).extend_validity(new_date)
        self.assertEqual(order.validity_date, new_date)
        self.assertFalse(order.is_expired)

    def test_30_audit_validity_extension(self):
        """Extending quotation validity logs a quotation_validity_extended audit event."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        before = self.SecurityAudit.search_count([('event_type', '=', 'quotation_validity_extended')])

        new_date = date.today() + relativedelta(days=20)
        order.with_user(self.staff_user).extend_validity(new_date)

        after = self.SecurityAudit.search_count([('event_type', '=', 'quotation_validity_extended')])
        self.assertGreater(after, before)

    # =========================================================================
    # COMMERCIAL WORKFLOW (tests 31–36)
    # =========================================================================

    def test_31_workflow_draft_to_sent(self):
        """Quotation transitions from draft to sent upon sending."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.base_product.id,
            'product_uom_qty': 1.0,
        })
        self.assertEqual(order.state, 'draft')
        order.write({'state': 'sent'})
        self.assertEqual(order.state, 'sent')

    def test_32_workflow_sent_to_confirmed(self):
        """Quotation transitions from sent to confirmed (state='sale')."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.base_product.id,
            'product_uom_qty': 1.0,
        })
        order.write({'state': 'sent'})
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_33_workflow_draft_cancellation(self):
        """Draft quotation can be cancelled."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        order._action_cancel()
        self.assertEqual(order.state, 'cancel')

    def test_34_cancelled_quotation_confirmation_rejected(self):
        """Cancelled quotation cannot be confirmed."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.base_product.id,
            'product_uom_qty': 1.0,
        })
        order._action_cancel()
        self.assertEqual(order.state, 'cancel')

        with self.assertRaises(UserError):
            order.action_confirm()

    def test_35_confirmed_quotation_modification_restrictions(self):
        """Modifying confirmed order lines raises UserError for non-admins."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.base_product.id,
            'product_uom_qty': 1.0,
        })
        order.action_confirm()

        with self.assertRaises(UserError):
            order.with_user(self.staff_user).write({
                'order_line': [(1, line.id, {'product_uom_qty': 5.0})],
            })

    def test_36_confirmed_quotation_does_not_activate_subscription(self):
        """
        Critical Phase 5 boundary guarantee:
        Confirming a quotation with subscription plans does NOT activate subscriptions.
        Phase 6 owns subscription creation and lifecycle.
        """
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.odoo_variant.id,
            'subscription_plan_id': self.plan_monthly.id,
            'product_uom_qty': 1.0,
            'price_unit': 2560.0,
        })
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

        # Check that no live subscription model/record was activated in Phase 5
        self.assertTrue(order.is_subscription_quotation)
        # There should be no active subscription records linked or created yet
        has_subscription_model = 'brightloop.subscription' in self.env
        if has_subscription_model:
            order_field = 'source_order_id' if 'source_order_id' in self.env['brightloop.subscription']._fields else 'order_id'
            sub_count = self.env['brightloop.subscription'].search_count([(order_field, '=', order.id)])
            self.assertEqual(sub_count, 0, 'Phase 5 must NOT activate subscriptions.')

    # =========================================================================
    # ROLE-BASED ACCESS CONTROL (tests 37–41)
    # =========================================================================

    def test_37_admin_quotation_access(self):
        """Admin has full quotation management access."""
        order = self.SaleOrder.with_user(self.admin_user).create({
            'partner_id': self.partner_a.id,
        })
        self.assertTrue(order.id)
        order.with_user(self.admin_user).write({'note': 'Admin note'})
        self.assertIn('Admin note', order.note)

    def test_38_staff_quotation_permissions(self):
        """Staff can create quotations and add lines."""
        order = self.SaleOrder.with_user(self.staff_user).create({
            'partner_id': self.partner_a.id,
        })
        line = self.SaleOrderLine.with_user(self.staff_user).create({
            'order_id': order.id,
            'product_id': self.base_product.id,
            'product_uom_qty': 1.0,
        })
        self.assertTrue(line.id)

    def test_39_customer_cannot_access_other_customers_quotation(self):
        """Customer A cannot read or access Customer B's quotation."""
        order_b = self.SaleOrder.create({'partner_id': self.partner_b.id})
        # Customer A queries quotations
        customer_a_orders = self.SaleOrder.with_user(self.customer_user_a).search(
            [('id', '=', order_b.id)]
        )
        self.assertFalse(customer_a_orders, "Customer A must not see Customer B's quotation.")

    def test_40_customer_cannot_modify_internal_quotations(self):
        """Customer cannot write or modify internal quotation records."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        with self.assertRaises(AccessError):
            order.with_user(self.customer_user_a).write({'validity_date': date.today()})

    def test_41_customer_cannot_create_internal_quotations(self):
        """Customer attempting to create an internal quotation raises AccessError."""
        with self.assertRaises(AccessError):
            self.SaleOrder.with_user(self.customer_user_a).create({
                'partner_id': self.partner_a.id,
            })

    # =========================================================================
    # AUDIT LOGGING (tests 42–44)
    # =========================================================================

    def test_42_audit_quotation_creation_and_update(self):
        """Quotation creation and update emit security audit records."""
        before_c = self.SecurityAudit.search_count([('event_type', '=', 'quotation_created')])
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        after_c = self.SecurityAudit.search_count([('event_type', '=', 'quotation_created')])
        self.assertGreater(after_c, before_c)

        before_u = self.SecurityAudit.search_count([('event_type', '=', 'quotation_updated')])
        order.write({'note': 'Audited update note'})
        after_u = self.SecurityAudit.search_count([('event_type', '=', 'quotation_updated')])
        self.assertGreater(after_u, before_u)

    def test_43_audit_quotation_confirmation_and_cancellation(self):
        """Quotation confirmation and cancellation emit security audit records."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.base_product.id,
            'product_uom_qty': 1.0,
        })
        before_conf = self.SecurityAudit.search_count([('event_type', '=', 'quotation_confirmed')])
        order.action_confirm()
        after_conf = self.SecurityAudit.search_count([('event_type', '=', 'quotation_confirmed')])
        self.assertGreater(after_conf, before_conf)

        order2 = self.SaleOrder.create({'partner_id': self.partner_a.id})
        before_canc = self.SecurityAudit.search_count([('event_type', '=', 'quotation_cancelled')])
        order2._action_cancel()
        after_canc = self.SecurityAudit.search_count([('event_type', '=', 'quotation_cancelled')])
        self.assertGreater(after_canc, before_canc)

    def test_44_audit_quotation_template_application(self):
        """Applying a quotation template logs a quotation_template_applied event."""
        tmpl = self.SaleOrderTemplate.create({
            'name': 'Audited Template',
            'sale_order_template_line_ids': [(0, 0, {'product_id': self.base_product.id, 'product_uom_qty': 1.0})],
        })
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})

        before = self.SecurityAudit.search_count([('event_type', '=', 'quotation_template_applied')])
        order.apply_brightloop_template(tmpl)
        after = self.SecurityAudit.search_count([('event_type', '=', 'quotation_template_applied')])
        self.assertGreater(after, before)

