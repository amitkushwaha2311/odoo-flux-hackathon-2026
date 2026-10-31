# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.tests.test_subscription_plans
#
# Phase 4 Automated Tests — Subscription Plan Engine
#
# Comprehensive test coverage:
#   - Plan creation and validation (tests 01–09)
#   - Calendar-aware date calculation (tests 10–16)
#   - Product, variant & minimum quantity pricing (tests 17–22)
#   - Plan availability & date window validation (tests 23–28)
#   - Lifecycle configuration & validation (tests 29–32)
#   - Role-based security (Admin, Staff, Customer) (tests 33–36)
#   - Security audit event logging (tests 37–41)
# =============================================================================

from datetime import date
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestSubscriptionPlans(TransactionCase):
    """
    Phase 4 test suite: Subscription Plan Engine.
    Covers model brightloop.subscription.plan, date calculation,
    variant pricing integration, availability, lifecycle, security, and audit.
    """

    def setUp(self):
        super().setUp()

        self.SubscriptionPlan = self.env['brightloop.subscription.plan']
        self.ProductTemplate = self.env['product.template']
        self.ProductAttribute = self.env['product.attribute']
        self.ProductAttributeValue = self.env['product.attribute.value']
        self.SecurityAudit = self.env['brightloop.security.audit']
        self.Users = self.env['res.users']

        self.admin_group = self.env.ref('brightloop_core.group_brightloop_admin')
        self.staff_group = self.env.ref('brightloop_core.group_brightloop_staff')
        self.customer_group = self.env.ref('brightloop_core.group_brightloop_customer')
        self.internal_group = self.env.ref('base.group_user')

        # Admin user
        partner_admin = self.env['res.partner'].create({
            'name': 'Plan Admin',
            'email': 'planadmin@brightloop.io',
        })
        self.admin_user = self.Users.create({
            'name': 'Plan Admin',
            'login': 'planadmin@brightloop.io',
            'email': 'planadmin@brightloop.io',
            'partner_id': partner_admin.id,
            'group_ids': [(6, 0, [self.admin_group.id, self.internal_group.id])],
        })

        # Staff user
        partner_staff = self.env['res.partner'].create({
            'name': 'Plan Staff',
            'email': 'planstaff@brightloop.io',
        })
        self.staff_user = self.Users.create({
            'name': 'Plan Staff',
            'login': 'planstaff@brightloop.io',
            'email': 'planstaff@brightloop.io',
            'partner_id': partner_staff.id,
            'group_ids': [(6, 0, [self.staff_group.id, self.internal_group.id])],
        })

        # Customer user
        self.customer_user = self.Users.register_customer(
            name='Plan Customer',
            email='plancustomer@brightloop.io',
            password='CustomerSecurePlan123!',
        )

        # Base product template (₹2,000)
        self.base_template = self.ProductTemplate.create({
            'name': 'Brightloop Core SaaS',
            'type': 'service',
            'list_price': 2000.0,
            'standard_price': 600.0,
        })

        # Attribute with Standard (₹0) and Odoo (₹560) variants
        attr = self.ProductAttribute.create({'name': 'Edition'})
        val_std = self.ProductAttributeValue.create({'name': 'Standard', 'attribute_id': attr.id})
        val_odoo = self.ProductAttributeValue.create({'name': 'Odoo', 'attribute_id': attr.id})

        self.variant_template = self.ProductTemplate.create({
            'name': 'Brightloop Platform Edition',
            'type': 'service',
            'list_price': 2000.0,
            'attribute_line_ids': [(0, 0, {
                'attribute_id': attr.id,
                'value_ids': [(6, 0, [val_std.id, val_odoo.id])],
            })],
        })

        # Set ₹560 extra on Odoo PTAV
        odoo_ptav = self.variant_template.attribute_line_ids.product_template_value_ids.filtered(
            lambda p: p.name == 'Odoo'
        )
        odoo_ptav.sudo().write({'price_extra': 560.0})

        self.std_variant = self.variant_template.product_variant_ids.filtered(
            lambda v: any(p.name == 'Standard' for p in v.product_template_attribute_value_ids)
        )
        self.odoo_variant = self.variant_template.product_variant_ids.filtered(
            lambda v: any(p.name == 'Odoo' for p in v.product_template_attribute_value_ids)
        )

    # =========================================================================
    # PLAN CREATION AND VALIDATION (tests 01–09)
    # =========================================================================

    def test_01_create_valid_daily_plan(self):
        """Admin can create a valid daily subscription plan."""
        plan = self.SubscriptionPlan.create({
            'name': 'Daily Cloud Compute Plan',
            'billing_interval': 'daily',
            'billing_interval_count': 1,
            'list_price': 100.0,
        })
        self.assertTrue(plan.id)
        self.assertEqual(plan.billing_interval, 'daily')
        self.assertEqual(plan.billing_interval_count, 1)
        self.assertEqual(plan.list_price, 100.0)
        self.assertTrue(plan.active)

    def test_02_create_valid_weekly_plan(self):
        """Admin can create a valid weekly subscription plan."""
        plan = self.SubscriptionPlan.create({
            'name': 'Weekly Sprint License Plan',
            'billing_interval': 'weekly',
            'billing_interval_count': 1,
            'list_price': 600.0,
        })
        self.assertTrue(plan.id)
        self.assertEqual(plan.billing_interval, 'weekly')
        self.assertEqual(plan.list_price, 600.0)

    def test_03_create_valid_monthly_plan(self):
        """Admin can create a valid monthly subscription plan."""
        plan = self.SubscriptionPlan.create({
            'name': 'Monthly Professional Plan',
            'billing_interval': 'monthly',
            'billing_interval_count': 1,
            'list_price': 2000.0,
        })
        self.assertTrue(plan.id)
        self.assertEqual(plan.billing_interval, 'monthly')
        self.assertEqual(plan.list_price, 2000.0)

    def test_04_create_valid_yearly_plan(self):
        """Admin can create a valid yearly subscription plan."""
        plan = self.SubscriptionPlan.create({
            'name': 'Annual Enterprise Plan',
            'billing_interval': 'yearly',
            'billing_interval_count': 1,
            'list_price': 20000.0,
        })
        self.assertTrue(plan.id)
        self.assertEqual(plan.billing_interval, 'yearly')
        self.assertEqual(plan.list_price, 20000.0)

    def test_05_missing_plan_name_rejected(self):
        """Empty or whitespace-only plan name must raise ValidationError."""
        with self.assertRaises(ValidationError):
            self.SubscriptionPlan.create({
                'name': '   ',
                'billing_interval': 'monthly',
                'list_price': 1000.0,
            })

    def test_06_invalid_billing_frequency_rejected(self):
        """Invalid billing interval must raise ValidationError or ValueError."""
        with self.assertRaises((ValidationError, ValueError)):
            self.SubscriptionPlan.create({
                'name': 'Invalid Frequency Plan',
                'billing_interval': 'hourly',
                'list_price': 500.0,
            })

    def test_07_negative_price_rejected(self):
        """Negative plan price must raise ValidationError."""
        with self.assertRaises(ValidationError):
            self.SubscriptionPlan.create({
                'name': 'Negative Price Plan',
                'billing_interval': 'monthly',
                'list_price': -50.0,
            })

    def test_08_invalid_minimum_quantity_rejected(self):
        """Non-positive minimum quantity (zero or negative) must raise ValidationError."""
        with self.assertRaises(ValidationError):
            self.SubscriptionPlan.create({
                'name': 'Zero Min Qty Plan',
                'billing_interval': 'monthly',
                'minimum_quantity': 0.0,
                'list_price': 100.0,
            })

    def test_09_invalid_interval_count_rejected(self):
        """Zero or negative interval count must raise ValidationError."""
        with self.assertRaises(ValidationError):
            self.SubscriptionPlan.create({
                'name': 'Bad Interval Count Plan',
                'billing_interval': 'monthly',
                'billing_interval_count': 0,
                'list_price': 100.0,
            })

    # =========================================================================
    # CALENDAR-AWARE DATE CALCULATION (tests 10–16)
    # =========================================================================

    def test_10_daily_date_calculation(self):
        """Daily: 2026-10-31 + 1 day -> 2026-11-01."""
        plan = self.SubscriptionPlan.create({
            'name': 'Daily Calculator Plan',
            'billing_interval': 'daily',
            'billing_interval_count': 1,
        })
        start = date(2026, 10, 31)
        next_date = plan.calculate_next_billing_date(start_date=start)
        self.assertEqual(next_date, date(2026, 11, 1), f'Expected 2026-11-01, got {next_date}')

    def test_11_weekly_date_calculation(self):
        """Weekly: 2026-10-31 + 1 week -> 2026-11-07."""
        plan = self.SubscriptionPlan.create({
            'name': 'Weekly Calculator Plan',
            'billing_interval': 'weekly',
            'billing_interval_count': 1,
        })
        start = date(2026, 10, 31)
        next_date = plan.calculate_next_billing_date(start_date=start)
        self.assertEqual(next_date, date(2026, 11, 7), f'Expected 2026-11-07, got {next_date}')

    def test_12_monthly_date_calculation(self):
        """Monthly: 2026-10-31 + 1 month -> 2026-11-30 (November has 30 days)."""
        plan = self.SubscriptionPlan.create({
            'name': 'Monthly Calculator Plan',
            'billing_interval': 'monthly',
            'billing_interval_count': 1,
        })
        start = date(2026, 10, 31)
        next_date = plan.calculate_next_billing_date(start_date=start)
        self.assertEqual(next_date, date(2026, 11, 30), f'Expected 2026-11-30, got {next_date}')

    def test_13_january_month_end_handling(self):
        """January Month-End: 2026-01-31 + 1 month -> 2026-02-28 (non-leap year February)."""
        plan = self.SubscriptionPlan.create({
            'name': 'Jan Month-End Plan',
            'billing_interval': 'monthly',
            'billing_interval_count': 1,
        })
        start = date(2026, 1, 31)
        next_date = plan.calculate_next_billing_date(start_date=start)
        self.assertEqual(next_date, date(2026, 2, 28), f'Expected 2026-02-28, got {next_date}')

    def test_14_february_leap_year_handling(self):
        """February Leap-Year: 2024-01-31 + 1 month -> 2024-02-29 (2024 is a leap year)."""
        plan = self.SubscriptionPlan.create({
            'name': 'Leap Feb Plan',
            'billing_interval': 'monthly',
            'billing_interval_count': 1,
        })
        start = date(2024, 1, 31)
        next_date = plan.calculate_next_billing_date(start_date=start)
        self.assertEqual(next_date, date(2024, 2, 29), f'Expected 2024-02-29, got {next_date}')

    def test_15_yearly_leap_day_handling(self):
        """Yearly Leap-Day: 2024-02-29 + 1 year -> 2025-02-28 (boundary adjustment)."""
        plan = self.SubscriptionPlan.create({
            'name': 'Leap Year Plan',
            'billing_interval': 'yearly',
            'billing_interval_count': 1,
        })
        start = date(2024, 2, 29)
        next_date = plan.calculate_next_billing_date(start_date=start)
        self.assertEqual(next_date, date(2025, 2, 28), f'Expected 2025-02-28, got {next_date}')

    def test_16_multiple_billing_intervals(self):
        """Quarterly (3 months): 2026-01-31 + 3 months -> 2026-04-30."""
        plan = self.SubscriptionPlan.create({
            'name': 'Quarterly Plan',
            'billing_interval': 'monthly',
            'billing_interval_count': 3,
        })
        start = date(2026, 1, 31)
        next_date = plan.calculate_next_billing_date(start_date=start)
        self.assertEqual(next_date, date(2026, 4, 30), f'Expected 2026-04-30, got {next_date}')

    # =========================================================================
    # PRICING, VARIANTS & MINIMUM QUANTITY (tests 17–22)
    # =========================================================================

    def test_17_plan_product_base_pricing(self):
        """Plan associated with base product inherits ₹2,000 price."""
        variant = self.base_template.product_variant_ids[0]
        plan = self.SubscriptionPlan.create({
            'name': 'Base Plan',
            'product_id': variant.id,
            'billing_interval': 'monthly',
        })
        calc = plan.calculate_plan_price(quantity=1)
        self.assertEqual(calc['unit_price'], 2000.0)
        self.assertEqual(calc['total_amount'], 2000.0)

    def test_18_plan_variant_pricing_2000_plus_560(self):
        """Plan with Odoo variant calculates ₹2,000 + ₹560 = ₹2,560."""
        plan = self.SubscriptionPlan.create({
            'name': 'Odoo Variant Plan',
            'product_id': self.odoo_variant.id,
            'billing_interval': 'monthly',
        })
        calc = plan.calculate_plan_price(quantity=1)
        self.assertAlmostEqual(calc['unit_price'], 2560.0, places=2)
        self.assertAlmostEqual(calc['total_amount'], 2560.0, places=2)

    def test_19_no_duplicate_variant_surcharge(self):
        """Critical: Variant surcharge of ₹560 is never applied twice."""
        plan = self.SubscriptionPlan.create({
            'name': 'Surcharge Double Application Guard',
            'product_id': self.odoo_variant.id,
            'billing_interval': 'monthly',
        })
        calc = plan.calculate_plan_price(variant=self.odoo_variant, quantity=1)
        self.assertAlmostEqual(
            calc['unit_price'], 2560.0, places=2,
            msg=f'Expected ₹2,560.00; got {calc["unit_price"]}. Surcharge double-applied!'
        )
        self.assertAlmostEqual(
            calc['total_amount'], 2560.0, places=2,
            msg=f'Total amount expected ₹2,560.00; got {calc["total_amount"]}.'
        )

    def test_20_minimum_quantity_calculation(self):
        """Price calculation multiplies unit price by quantity correctly."""
        plan = self.SubscriptionPlan.create({
            'name': 'Multi-Qty Plan',
            'product_id': self.odoo_variant.id,
            'billing_interval': 'monthly',
            'minimum_quantity': 2.0,
        })
        # 2 units * ₹2,560 = ₹5,120
        calc = plan.calculate_plan_price(quantity=2.0)
        self.assertAlmostEqual(calc['total_amount'], 5120.0, places=2)

    def test_21_quantity_below_minimum_rejected(self):
        """Requesting quantity below configured minimum raises ValidationError."""
        plan = self.SubscriptionPlan.create({
            'name': 'Enforce Min Qty Plan',
            'product_id': self.odoo_variant.id,
            'billing_interval': 'monthly',
            'minimum_quantity': 5.0,
        })
        with self.assertRaises(ValidationError):
            plan.calculate_plan_price(quantity=4.0)

    def test_22_uom_fractional_quantity_validation(self):
        """Discrete Unit UoM rejects invalid fractional quantities (e.g. 1.5)."""
        plan = self.SubscriptionPlan.create({
            'name': 'UoM Precision Plan',
            'product_id': self.odoo_variant.id,
            'billing_interval': 'monthly',
            'minimum_quantity': 1.0,
        })
        with self.assertRaises(ValidationError):
            plan.calculate_plan_price(quantity=1.5)

    # =========================================================================
    # PLAN AVAILABILITY DATES & SAFEGUARDS (tests 23–28)
    # =========================================================================

    def test_23_plan_before_start_date_rejected(self):
        """Plan checked before availability start date raises UserError."""
        plan = self.SubscriptionPlan.create({
            'name': 'Future Available Plan',
            'billing_interval': 'monthly',
            'availability_start_date': date(2027, 1, 1),
            'availability_end_date': date(2027, 12, 31),
        })
        with self.assertRaises(UserError):
            plan.check_availability(target_date=date(2026, 12, 1))

    def test_24_plan_within_availability_accepted(self):
        """Plan checked within availability window returns True."""
        plan = self.SubscriptionPlan.create({
            'name': 'Active Window Plan',
            'billing_interval': 'monthly',
            'availability_start_date': date(2026, 1, 1),
            'availability_end_date': date(2026, 12, 31),
        })
        self.assertTrue(plan.check_availability(target_date=date(2026, 6, 15)))

    def test_25_plan_after_expiry_rejected(self):
        """Plan checked after availability end date raises UserError."""
        plan = self.SubscriptionPlan.create({
            'name': 'Expired Plan',
            'billing_interval': 'monthly',
            'availability_start_date': date(2025, 1, 1),
            'availability_end_date': date(2025, 12, 31),
        })
        with self.assertRaises(UserError):
            plan.check_availability(target_date=date(2026, 1, 1))

    def test_26_archived_plan_rejected(self):
        """Archived plan raises UserError on availability check."""
        plan = self.SubscriptionPlan.create({
            'name': 'To Be Archived Plan',
            'billing_interval': 'monthly',
        })
        plan.write({'active': False})
        with self.assertRaises(UserError):
            plan.check_availability()

    def test_27_archived_product_rejected(self):
        """Plan referencing an archived product raises UserError on availability check."""
        prod = self.ProductTemplate.create({
            'name': 'Product To Archive',
            'type': 'service',
            'list_price': 500.0,
        }).product_variant_ids[0]

        plan = self.SubscriptionPlan.create({
            'name': 'Plan With Dying Product',
            'product_id': prod.id,
            'billing_interval': 'monthly',
        })
        # Archive product
        prod.product_tmpl_id.write({'active': False})

        with self.assertRaises(UserError):
            plan.check_availability()

    def test_28_invalid_date_ranges_rejected(self):
        """Setting start date after end date raises ValidationError."""
        with self.assertRaises(ValidationError):
            self.SubscriptionPlan.create({
                'name': 'Backwards Date Plan',
                'billing_interval': 'monthly',
                'availability_start_date': date(2026, 12, 31),
                'availability_end_date': date(2026, 1, 1),
            })

    # =========================================================================
    # LIFECYCLE CONFIGURATION (tests 29–32)
    # =========================================================================

    def test_29_lifecycle_auto_close_configuration(self):
        """auto_close boolean can be configured on the plan."""
        plan = self.SubscriptionPlan.create({
            'name': 'Auto Close Plan',
            'billing_interval': 'monthly',
            'auto_close': True,
        })
        self.assertTrue(plan.auto_close)
        plan.write({'auto_close': False})
        self.assertFalse(plan.auto_close)

    def test_30_lifecycle_early_closure_enabled_and_disabled(self):
        """allow_early_closure allows early closure when True, raises UserError when False."""
        plan = self.SubscriptionPlan.create({
            'name': 'Early Closure Plan',
            'billing_interval': 'monthly',
            'allow_early_closure': True,
        })
        self.assertTrue(plan.validate_early_closure())

        plan.write({'allow_early_closure': False})
        with self.assertRaises(UserError):
            plan.validate_early_closure()

    def test_31_lifecycle_pause_enabled_and_disabled(self):
        """allow_pause allows pause when True, raises UserError when False."""
        plan = self.SubscriptionPlan.create({
            'name': 'Pause Test Plan',
            'billing_interval': 'monthly',
            'allow_pause': True,
        })
        self.assertTrue(plan.validate_pause())

        plan.write({'allow_pause': False})
        with self.assertRaises(UserError):
            plan.validate_pause()

    def test_32_lifecycle_renewal_enabled_and_disabled(self):
        """allow_renewal allows renewal when True, raises UserError when False."""
        plan = self.SubscriptionPlan.create({
            'name': 'Renewal Test Plan',
            'billing_interval': 'monthly',
            'allow_renewal': True,
        })
        self.assertTrue(plan.validate_renewal())

        plan.write({'allow_renewal': False})
        with self.assertRaises(UserError):
            plan.validate_renewal()

    # =========================================================================
    # ROLE-BASED ACCESS CONTROL (tests 33–36)
    # =========================================================================

    def test_33_admin_can_create_and_update_plans(self):
        """Admin user can create and update subscription plans."""
        plan = self.SubscriptionPlan.with_user(self.admin_user).create({
            'name': 'Admin Created Subscription Plan',
            'billing_interval': 'monthly',
            'list_price': 1500.0,
        })
        self.assertTrue(plan.id)
        plan.with_user(self.admin_user).write({'list_price': 1800.0})
        self.assertEqual(plan.list_price, 1800.0)

    def test_34_staff_can_read_plans(self):
        """Staff user can search and read subscription plans."""
        plan = self.SubscriptionPlan.create({
            'name': 'Staff Readable Plan',
            'billing_interval': 'monthly',
            'list_price': 750.0,
        })
        found = self.SubscriptionPlan.with_user(self.staff_user).search(
            [('name', '=', 'Staff Readable Plan')]
        )
        self.assertTrue(found)
        self.assertEqual(found[0].list_price, 750.0)

    def test_35_staff_cannot_modify_plans(self):
        """Staff user attempting to create or modify a plan raises AccessError."""
        # Attempt to create
        with self.assertRaises(AccessError):
            self.SubscriptionPlan.with_user(self.staff_user).create({
                'name': 'Illegal Staff Plan',
                'billing_interval': 'monthly',
                'list_price': 500.0,
            })

        # Attempt to modify
        plan = self.SubscriptionPlan.create({
            'name': 'Immutable For Staff Plan',
            'billing_interval': 'monthly',
            'list_price': 900.0,
        })
        with self.assertRaises(AccessError):
            plan.with_user(self.staff_user).write({'list_price': 1200.0})

    def test_36_customer_cannot_administer_plans(self):
        """Customer user has no access to search, read, create, or modify plans."""
        self.SubscriptionPlan.create({
            'name': 'Secret Enterprise Plan',
            'billing_interval': 'monthly',
            'list_price': 9999.0,
        })
        with self.assertRaises(AccessError):
            self.SubscriptionPlan.with_user(self.customer_user).search([])

        with self.assertRaises(AccessError):
            self.SubscriptionPlan.with_user(self.customer_user).create({
                'name': 'Customer Rogue Plan',
                'billing_interval': 'monthly',
            })

    # =========================================================================
    # AUDIT LOGGING (tests 37–41)
    # =========================================================================

    def test_37_audit_plan_creation_recorded(self):
        """Creating a plan logs a plan_created security audit event."""
        before = self.SecurityAudit.search_count([('event_type', '=', 'plan_created')])
        self.SubscriptionPlan.create({
            'name': 'Audit Plan Creation',
            'billing_interval': 'monthly',
            'list_price': 1200.0,
        })
        after = self.SecurityAudit.search_count([('event_type', '=', 'plan_created')])
        self.assertGreater(after, before)

    def test_38_audit_plan_changes_recorded(self):
        """Updating plan description logs a plan_updated security audit event."""
        plan = self.SubscriptionPlan.create({
            'name': 'Audit Plan Update',
            'billing_interval': 'monthly',
            'list_price': 1200.0,
        })
        before = self.SecurityAudit.search_count([('event_type', '=', 'plan_updated')])
        plan.write({'description': 'Updated plan description.'})
        after = self.SecurityAudit.search_count([('event_type', '=', 'plan_updated')])
        self.assertGreater(after, before)

    def test_39_audit_price_changes_recorded(self):
        """Changing plan price logs a plan_price_modified security audit event."""
        plan = self.SubscriptionPlan.create({
            'name': 'Audit Plan Price Change',
            'billing_interval': 'monthly',
            'list_price': 1000.0,
        })
        before = self.SecurityAudit.search_count([('event_type', '=', 'plan_price_modified')])
        plan.write({'list_price': 1300.0})
        after = self.SecurityAudit.search_count([('event_type', '=', 'plan_price_modified')])
        self.assertGreater(after, before)

    def test_40_audit_policy_changes_recorded(self):
        """Changing lifecycle policies logs a plan_policy_modified event."""
        plan = self.SubscriptionPlan.create({
            'name': 'Audit Policy Change Plan',
            'billing_interval': 'monthly',
            'allow_pause': True,
        })
        before = self.SecurityAudit.search_count([('event_type', '=', 'plan_policy_modified')])
        plan.write({'allow_pause': False})
        after = self.SecurityAudit.search_count([('event_type', '=', 'plan_policy_modified')])
        self.assertGreater(after, before)

    def test_41_audit_archival_recorded(self):
        """Archiving a plan logs a plan_archived security audit event."""
        plan = self.SubscriptionPlan.create({
            'name': 'Audit Archival Plan',
            'billing_interval': 'monthly',
            'list_price': 500.0,
        })
        before = self.SecurityAudit.search_count([('event_type', '=', 'plan_archived')])
        plan.write({'active': False})
        after = self.SecurityAudit.search_count([('event_type', '=', 'plan_archived')])
        self.assertGreater(after, before)

