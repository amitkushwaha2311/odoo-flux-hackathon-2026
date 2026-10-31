# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.tests.test_subscriptions
#
# Phase 6 Automated Tests — Subscription Lifecycle Engine
#
# Coverage:
#   - Subscription creation from confirmed quotations & line filtering (tests 01–08)
#   - State machine transitions & write guards (tests 09–16)
#   - Activation & calendar-aware billing schedule integration (tests 17–21)
#   - Pause & resume policies with billing date extension (tests 22–27)
#   - Early closure & cron automatic closure eligibility (tests 28–33)
#   - Renewal workflows & contract traceability (tests 34–38)
#   - Lifecycle history & security audit trail (tests 39–43)
#   - Role-based access control & customer isolation (tests 44–48)
# =============================================================================

from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestSubscriptionLifecycle(TransactionCase):
    """
    Phase 6 test suite: Subscription Lifecycle Engine.
    Validates transformation of quotations into managed subscriptions,
    lifecycle state transitions, calendar billing dates, pause/resume policy,
    auto-closure, renewals, history immutability, RBAC, and audit events.
    """

    def setUp(self):
        super().setUp()

        self.SaleOrder = self.env['sale.order']
        self.SaleOrderLine = self.env['sale.order.line']
        self.Subscription = self.env['brightloop.subscription']
        self.SubscriptionLine = self.env['brightloop.subscription.line']
        self.SubscriptionHistory = self.env['brightloop.subscription.history']
        self.SubscriptionPlan = self.env['brightloop.subscription.plan']
        self.ProductTemplate = self.env['product.template']
        self.ProductAttribute = self.env['product.attribute']
        self.ProductAttributeValue = self.env['product.attribute.value']
        self.SecurityAudit = self.env['brightloop.security.audit']
        self.Users = self.env['res.users']
        self.Partner = self.env['res.partner']

        self.admin_group = self.env.ref('brightloop_core.group_brightloop_admin')
        self.staff_group = self.env.ref('brightloop_core.group_brightloop_staff')
        self.customer_group = self.env.ref('brightloop_core.group_brightloop_customer')
        self.internal_group = self.env.ref('base.group_user')

        # 1. Admin user
        partner_admin = self.Partner.create({
            'name': 'Lifecycle Admin',
            'email': 'lifecycle.admin@brightloop.io',
        })
        self.admin_user = self.Users.create({
            'name': 'Lifecycle Admin',
            'login': 'lifecycle.admin@brightloop.io',
            'email': 'lifecycle.admin@brightloop.io',
            'partner_id': partner_admin.id,
            'group_ids': [(6, 0, [self.admin_group.id, self.internal_group.id])],
        })

        # 2. Staff user
        partner_staff = self.Partner.create({
            'name': 'Lifecycle Staff',
            'email': 'lifecycle.staff@brightloop.io',
        })
        self.staff_user = self.Users.create({
            'name': 'Lifecycle Staff',
            'login': 'lifecycle.staff@brightloop.io',
            'email': 'lifecycle.staff@brightloop.io',
            'partner_id': partner_staff.id,
            'group_ids': [(6, 0, [self.staff_group.id, self.internal_group.id])],
        })

        # 3. Customer A user (portal)
        self.customer_user_a = self.Users.register_customer(
            name='Lifecycle Customer A',
            email='customer.a.lifecycle@brightloop.io',
            password='CustomerSecurePass123!',
        )
        self.partner_a = self.customer_user_a.partner_id

        # 4. Customer B user (portal)
        self.customer_user_b = self.Users.register_customer(
            name='Lifecycle Customer B',
            email='customer.b.lifecycle@brightloop.io',
            password='CustomerSecurePass123!',
        )
        self.partner_b = self.customer_user_b.partner_id

        # 5. Regular one-time product
        self.regular_tmpl = self.ProductTemplate.create({
            'name': 'One-Time Setup Fee',
            'type': 'service',
            'list_price': 500.0,
        })
        self.regular_product = self.regular_tmpl.product_variant_ids[0]

        # 6. SaaS Subscription Product & Variant (₹2,000 base + ₹560 surcharge = ₹2,560)
        attr = self.ProductAttribute.create({'name': 'Edition'})
        val_std = self.ProductAttributeValue.create({'name': 'Standard', 'attribute_id': attr.id})
        val_odoo = self.ProductAttributeValue.create({'name': 'Odoo', 'attribute_id': attr.id})

        self.variant_tmpl = self.ProductTemplate.create({
            'name': 'Brightloop SaaS Platform',
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

        # 7. Subscription Plans
        self.plan_monthly = self.SubscriptionPlan.create({
            'name': 'Monthly Pro Plan',
            'product_id': self.odoo_variant.id,
            'billing_interval': 'monthly',
            'billing_interval_count': 1,
            'list_price': 2560.0,
            'minimum_quantity': 1.0,
            'allow_pause': True,
            'allow_early_closure': True,
            'allow_renewal': True,
            'auto_close': True,
        })

        self.plan_no_pause = self.SubscriptionPlan.create({
            'name': 'Strict No-Pause Plan',
            'product_id': self.odoo_variant.id,
            'billing_interval': 'monthly',
            'billing_interval_count': 1,
            'list_price': 2560.0,
            'allow_pause': False,
            'allow_early_closure': False,
            'allow_renewal': False,
            'auto_close': False,
        })

    # =========================================================================
    # 1. SUBSCRIPTION CREATION & LINE CONVERSION (tests 01–08)
    # =========================================================================

    def test_01_create_subscription_from_confirmed_quotation(self):
        """Confirmed quotation with subscription lines successfully converts to a subscription."""
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

        subs = order.action_create_subscriptions()
        self.assertEqual(len(subs), 1)
        sub = subs[0]

        self.assertEqual(sub.state, 'draft')
        self.assertEqual(sub.customer_id, self.partner_a)
        self.assertEqual(sub.source_order_id, order)
        self.assertEqual(sub.billing_interval, 'monthly')
        self.assertEqual(sub.billing_interval_count, 1)
        self.assertEqual(len(sub.subscription_line_ids), 1)
        self.assertEqual(sub.subscription_line_ids[0].product_id, self.odoo_variant)
        self.assertEqual(sub.subscription_line_ids[0].subscription_plan_id, self.plan_monthly)
        self.assertAlmostEqual(sub.recurring_amount, 2560.0, places=2)

    def test_02_conversion_ignores_regular_product_lines(self):
        """One-time products in confirmed quotation are excluded from subscription lines."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        # 1 regular line
        self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.regular_product.id,
            'product_uom_qty': 1.0,
            'price_unit': 500.0,
        })
        # 1 subscription line
        self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.odoo_variant.id,
            'subscription_plan_id': self.plan_monthly.id,
            'product_uom_qty': 1.0,
            'price_unit': 2560.0,
        })
        order.action_confirm()

        subs = order.action_create_subscriptions()
        self.assertEqual(len(subs), 1)
        sub = subs[0]

        # Only subscription line was converted
        self.assertEqual(len(sub.subscription_line_ids), 1)
        self.assertEqual(sub.subscription_line_ids[0].product_id, self.odoo_variant)
        self.assertAlmostEqual(sub.recurring_amount, 2560.0, places=2)

    def test_03_multi_line_subscription_conversion(self):
        """Quotation with multiple subscription lines converts all recurring lines."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.odoo_variant.id,
            'subscription_plan_id': self.plan_monthly.id,
            'product_uom_qty': 2.0,
            'price_unit': 2560.0,
        })
        self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.odoo_variant.id,
            'subscription_plan_id': self.plan_monthly.id,
            'product_uom_qty': 1.0,
            'price_unit': 2560.0,
        })
        order.action_confirm()

        subs = order.action_create_subscriptions()
        self.assertEqual(len(subs), 1)
        sub = subs[0]
        self.assertEqual(len(sub.subscription_line_ids), 2)
        self.assertEqual(sub.quantity, 3.0)
        self.assertAlmostEqual(sub.recurring_amount, 7680.0, places=2)

    def test_04_reject_draft_quotation_conversion(self):
        """Attempting to convert an unconfirmed (draft) quotation raises UserError."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.odoo_variant.id,
            'subscription_plan_id': self.plan_monthly.id,
            'product_uom_qty': 1.0,
        })
        self.assertEqual(order.state, 'draft')

        with self.assertRaises(UserError):
            order.action_create_subscriptions()

    def test_05_reject_cancelled_quotation_conversion(self):
        """Attempting to convert a cancelled quotation raises UserError."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        order._action_cancel()

        with self.assertRaises(UserError):
            order.action_create_subscriptions()

    def test_06_reject_quotation_without_subscription_lines(self):
        """Quotation with only regular products raises UserError upon subscription creation."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.regular_product.id,
            'product_uom_qty': 1.0,
            'price_unit': 500.0,
        })
        order.action_confirm()

        with self.assertRaises(UserError):
            order.action_create_subscriptions()

    def test_07_prevent_duplicate_conversion(self):
        """Repeated call to action_create_subscriptions raises UserError to prevent duplicates."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.odoo_variant.id,
            'subscription_plan_id': self.plan_monthly.id,
            'product_uom_qty': 1.0,
            'price_unit': 2560.0,
        })
        order.action_confirm()
        order.action_create_subscriptions()

        # Second call must be blocked
        with self.assertRaises(UserError):
            order.action_create_subscriptions()

    def test_08_database_uniqueness_on_source_order(self):
        """Creating a secondary subscription pointing to the same source_order_id raises ValidationError."""
        order = self.SaleOrder.create({'partner_id': self.partner_a.id})
        self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.odoo_variant.id,
            'subscription_plan_id': self.plan_monthly.id,
            'product_uom_qty': 1.0,
        })
        order.action_confirm()
        order.action_create_subscriptions()

        with self.assertRaises((ValidationError, Exception)):
            self.Subscription.create({
                'customer_id': self.partner_a.id,
                'source_order_id': order.id,
                'billing_interval': 'monthly',
                'start_date': date.today(),
            })

    # =========================================================================
    # 2. STATE MACHINE & ACTION METHODS (tests 09–16)
    # =========================================================================

    def _create_standard_sub(self, plan=None):
        sub = self.Subscription.create({
            'customer_id': self.partner_a.id,
            'subscription_plan_id': (plan or self.plan_monthly).id,
            'billing_interval': (plan or self.plan_monthly).billing_interval,
            'billing_interval_count': (plan or self.plan_monthly).billing_interval_count,
            'start_date': date.today(),
            'subscription_line_ids': [(0, 0, {
                'product_id': self.odoo_variant.id,
                'subscription_plan_id': (plan or self.plan_monthly).id,
                'quantity': 1.0,
                'price_unit': 2560.0,
            })],
        })
        return sub

    def test_09_state_draft_to_confirmed(self):
        """Subscription transitions from draft to confirmed via action_confirm."""
        sub = self._create_standard_sub()
        self.assertEqual(sub.state, 'draft')
        sub.action_confirm()
        self.assertEqual(sub.state, 'confirmed')

    def test_10_state_confirmed_to_active(self):
        """Subscription transitions from confirmed to active via action_activate."""
        sub = self._create_standard_sub()
        sub.action_confirm()
        sub.action_activate()
        self.assertEqual(sub.state, 'active')
        self.assertTrue(sub.next_billing_date)

    def test_11_state_active_to_paused(self):
        """Subscription transitions from active to paused via action_pause."""
        sub = self._create_standard_sub()
        sub.action_confirm()
        sub.action_activate()
        sub.action_pause(reason='Customer vacation')
        self.assertEqual(sub.state, 'paused')
        self.assertEqual(sub.pause_date, date.today())

    def test_12_state_paused_to_active(self):
        """Subscription transitions from paused back to active via action_resume."""
        sub = self._create_standard_sub()
        sub.action_confirm()
        sub.action_activate()
        sub.action_pause()
        sub.action_resume()
        self.assertEqual(sub.state, 'active')
        self.assertEqual(sub.resume_date, date.today())

    def test_13_state_active_to_closed(self):
        """Subscription transitions from active to closed via action_close."""
        sub = self._create_standard_sub()
        sub.action_confirm()
        sub.action_activate()
        sub.action_close(reason='Contract ended')
        self.assertEqual(sub.state, 'closed')
        self.assertEqual(sub.closure_date, date.today())

    def test_14_state_paused_to_closed(self):
        """Subscription can transition from paused to closed directly."""
        sub = self._create_standard_sub()
        sub.action_confirm()
        sub.action_activate()
        sub.action_pause()
        sub.action_close(reason='Closed during suspension')
        self.assertEqual(sub.state, 'closed')

    def test_15_invalid_state_transition_rejected(self):
        """Draft subscription cannot be directly activated or paused."""
        sub = self._create_standard_sub()
        with self.assertRaises(UserError):
            sub.action_activate()
        with self.assertRaises(UserError):
            sub.action_pause()

    def test_16_direct_state_write_rejected(self):
        """Direct write to state field via ORM write() is blocked by state guard."""
        sub = self._create_standard_sub()
        with self.assertRaises(UserError):
            sub.write({'state': 'active'})

    # =========================================================================
    # 3. ACTIVATION & BILLING SCHEDULE (tests 17–21)
    # =========================================================================

    def test_17_activation_computes_next_billing_date(self):
        """Activating a monthly subscription sets next_billing_date 1 month ahead."""
        sub = self._create_standard_sub()
        sub.start_date = date(2026, 11, 1)
        sub.action_confirm()
        sub.action_activate()

        expected = date(2026, 12, 1)
        self.assertEqual(sub.next_billing_date, expected)

    def test_18_activation_future_start_date(self):
        """Subscription with a future start date activates and schedules future billing."""
        future_start = date.today() + relativedelta(days=30)
        sub = self._create_standard_sub()
        sub.start_date = future_start
        sub.action_confirm()
        sub.action_activate()

        self.assertEqual(sub.state, 'active')
        expected_bill = future_start + relativedelta(months=1)
        self.assertEqual(sub.next_billing_date, expected_bill)

    def test_19_repeated_activation_rejected(self):
        """Cannot activate an already active subscription."""
        sub = self._create_standard_sub()
        sub.action_confirm()
        sub.action_activate()

        with self.assertRaises(UserError):
            sub.action_activate()

    def test_20_activation_blocked_by_archived_plan(self):
        """Subscription cannot be activated if its plan has been archived."""
        sub = self._create_standard_sub()
        sub.action_confirm()

        # Archive plan
        self.plan_monthly.write({'active': False})
        with self.assertRaises(UserError):
            sub.action_activate()

    def test_21_activation_blocked_by_archived_product(self):
        """Subscription cannot be confirmed if a product variant is archived."""
        sub = self._create_standard_sub()
        self.odoo_variant.product_tmpl_id.write({'active': False})

        with self.assertRaises(UserError):
            sub.action_confirm()

    # =========================================================================
    # 4. PAUSE & RESUME POLICIES (tests 22–27)
    # =========================================================================

    def test_22_pause_rejected_if_plan_disallows(self):
        """Subscription under a plan with allow_pause=False raises UserError on pause."""
        sub = self._create_standard_sub(plan=self.plan_no_pause)
        sub.action_confirm()
        sub.action_activate()

        with self.assertRaises(UserError):
            sub.action_pause()

    def test_23_pause_from_invalid_state_rejected(self):
        """Cannot pause a draft or closed subscription."""
        sub = self._create_standard_sub()
        with self.assertRaises(UserError):
            sub.action_pause()

    def test_24_resume_from_invalid_state_rejected(self):
        """Cannot resume an active or confirmed subscription."""
        sub = self._create_standard_sub()
        sub.action_confirm()
        sub.action_activate()

        with self.assertRaises(UserError):
            sub.action_resume()

    def test_25_resume_extends_next_billing_date(self):
        """
        Explicit pause policy:
        When a subscription is paused for 10 days, resuming it extends next_billing_date by 10 days.
        """
        sub = self._create_standard_sub()
        sub.start_date = date.today()
        sub.action_confirm()
        sub.action_activate()

        original_bill_date = sub.next_billing_date
        sub.action_pause()

        # Simulate 10 days of suspension
        simulated_pause_date = date.today() - relativedelta(days=10)
        sub.with_context(bypass_state_guard=True).write({'pause_date': simulated_pause_date})

        sub.action_resume()
        self.assertEqual(sub.state, 'active')
        expected_bill_date = original_bill_date + relativedelta(days=10)
        self.assertEqual(sub.next_billing_date, expected_bill_date)

    def test_26_duplicate_pause_rejected(self):
        """Attempting to pause a subscription that is already paused raises UserError."""
        sub = self._create_standard_sub()
        sub.action_confirm()
        sub.action_activate()
        sub.action_pause()

        with self.assertRaises(UserError):
            sub.action_pause()

    def test_27_duplicate_resume_rejected(self):
        """Attempting to resume an active subscription raises UserError."""
        sub = self._create_standard_sub()
        sub.action_confirm()
        sub.action_activate()
        sub.action_pause()
        sub.action_resume()

        with self.assertRaises(UserError):
            sub.action_resume()

    # =========================================================================
    # 5. CLOSURE & AUTOMATIC CLOSURE (tests 28–33)
    # =========================================================================

    def test_28_authorized_early_closure(self):
        """Active subscription can be closed early when permitted by plan."""
        sub = self._create_standard_sub()
        sub.end_date = date.today() + relativedelta(days=90)
        sub.action_confirm()
        sub.action_activate()

        sub.action_close(reason='Customer request')
        self.assertEqual(sub.state, 'closed')
        self.assertEqual(sub.closure_reason, 'Customer request')
        self.assertEqual(sub.closure_date, date.today())

    def test_29_early_closure_rejected_if_disallowed(self):
        """Closing early before end_date on a plan with allow_early_closure=False raises UserError."""
        sub = self._create_standard_sub(plan=self.plan_no_pause)
        sub.end_date = date.today() + relativedelta(days=90)
        sub.action_confirm()
        sub.action_activate()

        with self.assertRaises(UserError):
            sub.action_close()

    def test_30_cron_auto_close_eligible_subscriptions(self):
        """Cron auto-closes subscriptions that reached end_date with auto_close=True."""
        sub = self._create_standard_sub()
        # Set term in the past so end_date is yesterday
        sub.write({
            'start_date': date.today() - relativedelta(days=30),
            'end_date': date.today() - relativedelta(days=1),
        })
        sub.action_confirm()
        sub.action_activate()

        count = self.Subscription.cron_auto_close_eligible_subscriptions()
        self.assertGreaterEqual(count, 1)
        self.assertEqual(sub.state, 'closed')
        self.assertIn('end date', sub.closure_reason.lower())

    def test_31_cron_does_not_close_before_end_date(self):
        """Cron does NOT close subscriptions whose end_date is in the future."""
        sub = self._create_standard_sub()
        sub.end_date = date.today() + relativedelta(days=15)
        sub.action_confirm()
        sub.action_activate()

        self.Subscription.cron_auto_close_eligible_subscriptions()
        self.assertEqual(sub.state, 'active')

    def test_32_cron_does_not_close_plan_without_auto_close(self):
        """Cron does NOT close subscriptions if plan.auto_close is False."""
        sub = self._create_standard_sub(plan=self.plan_no_pause)
        sub.write({
            'start_date': date.today() - relativedelta(days=30),
            'end_date': date.today() - relativedelta(days=1),
        })
        sub.action_confirm()
        sub.action_activate()

        self.Subscription.cron_auto_close_eligible_subscriptions()
        self.assertEqual(sub.state, 'active')

    def test_33_cron_idempotent_on_already_closed(self):
        """Running the auto-close cron repeatedly is safe and idempotent."""
        sub = self._create_standard_sub()
        sub.write({
            'start_date': date.today() - relativedelta(days=30),
            'end_date': date.today() - relativedelta(days=1),
        })
        sub.action_confirm()
        sub.action_activate()

        count1 = self.Subscription.cron_auto_close_eligible_subscriptions()
        self.assertEqual(sub.state, 'closed')

        # Run second time
        count2 = self.Subscription.cron_auto_close_eligible_subscriptions()
        self.assertEqual(sub.state, 'closed')

    # =========================================================================
    # 6. SUBSCRIPTION RENEWAL (tests 34–38)
    # =========================================================================

    def test_34_successful_renewal(self):
        """Renewing an active subscription creates a new subscription with incremented renewal_count."""
        sub = self._create_standard_sub()
        sub.end_date = date.today() + relativedelta(days=30)
        sub.action_confirm()
        sub.action_activate()

        new_sub = sub.action_renew(notes='Annual extension')
        self.assertTrue(new_sub.id)
        self.assertEqual(new_sub.previous_subscription_id, sub)
        self.assertEqual(new_sub.renewal_count, 1)
        self.assertEqual(new_sub.customer_id, sub.customer_id)
        self.assertEqual(new_sub.start_date, sub.end_date + relativedelta(days=1))
        self.assertEqual(sub.state, 'closed')  # Previous sub closed

    def test_35_renewal_rejected_if_disallowed_by_plan(self):
        """Renewal raises UserError if plan allow_renewal is False."""
        sub = self._create_standard_sub(plan=self.plan_no_pause)
        sub.action_confirm()
        sub.action_activate()

        with self.assertRaises(UserError):
            sub.action_renew()

    def test_36_renewal_from_invalid_state_rejected(self):
        """Draft or paused subscriptions cannot be renewed."""
        sub = self._create_standard_sub()
        with self.assertRaises(UserError):
            sub.action_renew()

        sub.action_confirm()
        sub.action_activate()
        sub.action_pause()
        with self.assertRaises(UserError):
            sub.action_renew()

    def test_37_renewal_lineage_traceability(self):
        """Renewed subscription points back to original and parent points forward."""
        sub = self._create_standard_sub()
        sub.action_confirm()
        sub.action_activate()

        new_sub = sub.action_renew()
        self.assertIn(new_sub, sub.renewed_subscription_ids)
        self.assertEqual(new_sub.previous_subscription_id, sub)

    def test_38_renewal_preserves_product_and_quantities(self):
        """New renewed subscription copies original line items, quantities, and pricing."""
        sub = self._create_standard_sub()
        sub.action_confirm()
        sub.action_activate()

        new_sub = sub.action_renew()
        self.assertEqual(len(new_sub.subscription_line_ids), 1)
        self.assertEqual(new_sub.subscription_line_ids[0].product_id, self.odoo_variant)
        self.assertEqual(new_sub.subscription_line_ids[0].quantity, 1.0)
        self.assertAlmostEqual(new_sub.subscription_line_ids[0].price_unit, 2560.0, places=2)

    # =========================================================================
    # 7. HISTORY & AUDIT TRAIL (tests 39–43)
    # =========================================================================

    def test_39_history_records_every_transition(self):
        """Full lifecycle (create -> confirm -> activate -> pause -> resume -> close) records history."""
        sub = self._create_standard_sub()
        sub.action_confirm()
        sub.action_activate()
        sub.action_pause()
        sub.action_resume()
        sub.action_close()

        history_events = sub.history_ids.mapped('event_type')
        self.assertIn('created', history_events)
        self.assertIn('confirmed', history_events)
        self.assertIn('activated', history_events)
        self.assertIn('paused', history_events)
        self.assertIn('resumed', history_events)
        self.assertIn('closed', history_events)

    def test_40_history_immutability_write_rejected(self):
        """Attempting to modify a history record raises UserError."""
        sub = self._create_standard_sub()
        history = sub.history_ids[0]

        with self.assertRaises(UserError):
            history.write({'reason': 'Tampered history'})

    def test_41_history_immutability_unlink_rejected(self):
        """Attempting to delete a history record raises UserError."""
        sub = self._create_standard_sub()
        history = sub.history_ids[0]

        with self.assertRaises(UserError):
            history.unlink()

    def test_42_audit_events_created_for_transitions(self):
        """State transitions log security audit records."""
        before = self.SecurityAudit.search_count([('event_type', '=', 'subscription_activated')])
        sub = self._create_standard_sub()
        sub.action_confirm()
        sub.action_activate()
        after = self.SecurityAudit.search_count([('event_type', '=', 'subscription_activated')])
        self.assertGreater(after, before)

    def test_43_date_modification_logs_audit(self):
        """Modifying subscription dates creates a subscription_date_modified audit entry."""
        sub = self._create_standard_sub()
        before = self.SecurityAudit.search_count([('event_type', '=', 'subscription_date_modified')])
        sub.write({'end_date': date.today() + relativedelta(days=180)})
        after = self.SecurityAudit.search_count([('event_type', '=', 'subscription_date_modified')])
        self.assertGreater(after, before)

    # =========================================================================
    # 8. ROLE-BASED ACCESS CONTROL & CUSTOMER ISOLATION (tests 44–48)
    # =========================================================================

    def test_44_admin_full_lifecycle_access(self):
        """Administrator has full lifecycle execution permissions."""
        sub = self.Subscription.with_user(self.admin_user).create({
            'customer_id': self.partner_a.id,
            'billing_interval': 'monthly',
            'start_date': date.today(),
            'subscription_line_ids': [(0, 0, {
                'product_id': self.odoo_variant.id,
                'subscription_plan_id': self.plan_monthly.id,
                'quantity': 1.0,
                'price_unit': 2560.0,
            })],
        })
        self.assertTrue(sub.id)
        sub.with_user(self.admin_user).action_confirm()
        sub.with_user(self.admin_user).action_activate()
        self.assertEqual(sub.state, 'active')

    def test_45_staff_operational_permissions(self):
        """Staff can create, confirm, activate, and manage subscriptions."""
        sub = self.Subscription.with_user(self.staff_user).create({
            'customer_id': self.partner_a.id,
            'billing_interval': 'monthly',
            'start_date': date.today(),
            'subscription_line_ids': [(0, 0, {
                'product_id': self.odoo_variant.id,
                'subscription_plan_id': self.plan_monthly.id,
                'quantity': 1.0,
                'price_unit': 2560.0,
            })],
        })
        sub.with_user(self.staff_user).action_confirm()
        self.assertEqual(sub.state, 'confirmed')

    def test_46_customer_reads_own_subscription_only(self):
        """Customer A can read their own subscription but NOT Customer B's subscription."""
        sub_a = self._create_standard_sub()
        sub_b = self.Subscription.create({
            'customer_id': self.partner_b.id,
            'billing_interval': 'monthly',
            'start_date': date.today(),
            'subscription_line_ids': [(0, 0, {
                'product_id': self.odoo_variant.id,
                'subscription_plan_id': self.plan_monthly.id,
                'quantity': 1.0,
                'price_unit': 2560.0,
            })],
        })

        # Customer A searches subscriptions
        cust_a_subs = self.Subscription.with_user(self.customer_user_a).search([])
        self.assertIn(sub_a.id, cust_a_subs.ids)
        self.assertNotIn(sub_b.id, cust_a_subs.ids, "Customer A must not see Customer B's subscription.")

    def test_47_customer_cannot_create_subscription_directly(self):
        """Customer user attempting to create a subscription directly raises AccessError."""
        with self.assertRaises(AccessError):
            self.Subscription.with_user(self.customer_user_a).create({
                'customer_id': self.partner_a.id,
                'billing_interval': 'monthly',
                'start_date': date.today(),
            })

    def test_48_customer_cannot_call_lifecycle_actions(self):
        """Customer attempting to pause or close subscription directly raises AccessError."""
        sub = self._create_standard_sub()
        sub.action_confirm()
        sub.action_activate()

        with self.assertRaises((AccessError, UserError)):
            sub.with_user(self.customer_user_a).action_pause()

        with self.assertRaises((AccessError, UserError)):
            sub.with_user(self.customer_user_a).action_close()

