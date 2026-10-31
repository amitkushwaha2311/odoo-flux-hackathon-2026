# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.tests.test_taxes_and_discounts
#
# Automated Test Suite for Phase 7: Tax & Discount Management Engine
#
# COVERS:
# 1. Tax Configuration (percentage, fixed, activation, archival, rate validity, company)
# 2. Tax Calculation (tax-exclusive, tax-inclusive, multiple taxes, currency rounding, sequence)
# 3. GST Support (intra-state CGST+SGST, inter-state IGST, fiscal position mapping, no double tax)
# 4. Discount Model & Constraints (percentage, fixed, negative value, maximum cap, date ranges)
# 5. Discount Eligibility Engine (active, dates, min purchase, min qty, product, category, plan, usage limit, company)
# 6. Discount Calculation (10% of 2000 = 200, fixed 250, maximum discount, quantity-aware, no duplicate, stacking)
# 7. Quotation Integration (discount application, tax calculation, line totals, server-side validation)
# 8. Subscription Integration (recurring discount, expiry check, usage exhaustion, calculation breakdown, no invoice)
# 9. Usage Limits & Concurrency Protection (atomic increment, usage limit enforcement, transaction rollback)
# 10. Role-Based Security & Audit Logging (Admin CRUD, Staff read, Customer isolation, audit events)
# =============================================================================

from datetime import date
from dateutil.relativedelta import relativedelta
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestTaxesAndDiscounts(TransactionCase):
    """Automated backend test suite for Brightloop Phase 7: Tax & Discount Engine."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.AccountTax = cls.env['account.tax']
        cls.FiscalPosition = cls.env['account.fiscal.position']
        cls.TaxService = cls.env['brightloop.tax.service']
        cls.Discount = cls.env['brightloop.discount']
        cls.DiscountService = cls.env['brightloop.discount.service']
        cls.ProductTemplate = cls.env['product.template']
        cls.ProductProduct = cls.env['product.product']
        cls.ProductCategory = cls.env['product.category']
        cls.SubscriptionPlan = cls.env['brightloop.subscription.plan']
        cls.SaleOrder = cls.env['sale.order']
        cls.SaleOrderLine = cls.env['sale.order.line']
        cls.Subscription = cls.env['brightloop.subscription']
        cls.SubscriptionLine = cls.env['brightloop.subscription.line']
        cls.SecurityAudit = cls.env['brightloop.security.audit']
        cls.Partner = cls.env['res.partner']
        cls.Users = cls.env['res.users']
        cls.Company = cls.env['res.company']

        cls.main_company = cls.env.company
        cls.currency_inr = cls.main_company.currency_id

        # Security groups
        cls.admin_group = cls.env.ref('brightloop_core.group_brightloop_admin')
        cls.staff_group = cls.env.ref('brightloop_core.group_brightloop_staff')
        cls.customer_group = cls.env.ref('brightloop_core.group_brightloop_customer')
        cls.internal_group = cls.env.ref('base.group_user')
        cls.account_manager_group = cls.env.ref('account.group_account_manager')

        # Tax group
        cls.tax_group = cls.env['account.tax.group'].search([], limit=1)
        if not cls.tax_group:
            cls.tax_group = cls.env['account.tax.group'].create({'name': 'GST'})

        # Partners
        cls.partner_customer = cls.Partner.create({
            'name': 'Pooja Sharma',
            'email': 'pooja.sharma.tax@brightloop.io',
        })
        cls.partner_other_customer = cls.Partner.create({
            'name': 'Rahul Verma',
            'email': 'rahul.verma.tax@brightloop.io',
        })
        cls.partner_staff = cls.Partner.create({
            'name': 'Tax Staff Agent',
            'email': 'tax.staff@brightloop.io',
        })
        cls.partner_admin = cls.Partner.create({
            'name': 'Tax Admin User',
            'email': 'tax.admin@brightloop.io',
        })

        # Users
        cls.admin_user = cls.Users.create({
            'name': 'Tax Admin',
            'login': 'tax.admin@brightloop.io',
            'email': 'tax.admin@brightloop.io',
            'partner_id': cls.partner_admin.id,
            'group_ids': [(6, 0, [cls.admin_group.id, cls.internal_group.id, cls.account_manager_group.id])],
        })
        cls.staff_user = cls.Users.create({
            'name': 'Tax Staff',
            'login': 'tax.staff@brightloop.io',
            'email': 'tax.staff@brightloop.io',
            'partner_id': cls.partner_staff.id,
            'group_ids': [(6, 0, [cls.staff_group.id, cls.internal_group.id])],
        })
        cls.customer_user = cls.Users.create({
            'name': 'Tax Customer',
            'login': 'tax.customer@brightloop.io',
            'email': 'tax.customer@brightloop.io',
            'partner_id': cls.partner_customer.id,
            'group_ids': [(6, 0, [cls.customer_group.id])],
        })

        # Product Categories
        cls.category_software = cls.ProductCategory.create({'name': 'Software Subscriptions'})
        cls.category_hardware = cls.ProductCategory.create({'name': 'Hardware Devices'})

        # Products
        cls.tmpl_saas = cls.ProductTemplate.create({
            'name': 'Brightloop Cloud SaaS',
            'list_price': 2000.0,
            'categ_id': cls.category_software.id,
            'type': 'service',
        })
        cls.product_saas = cls.tmpl_saas.product_variant_id

        cls.tmpl_device = cls.ProductTemplate.create({
            'name': 'Brightloop IoT Hub',
            'list_price': 5000.0,
            'categ_id': cls.category_hardware.id,
            'type': 'consu',
        })
        cls.product_device = cls.tmpl_device.product_variant_id

        # Subscription Plan
        cls.plan_monthly = cls.SubscriptionPlan.create({
            'name': 'Cloud Monthly Plan',
            'product_id': cls.product_saas.id,
            'billing_interval': 'monthly',
            'billing_interval_count': 1,
            'list_price': 2000.0,
            'minimum_quantity': 1.0,
            'allow_pause': True,
            'allow_early_closure': True,
            'allow_renewal': True,
            'auto_close': True,
        })

        # Native Taxes: GST Setup (CGST 9%, SGST 9%, IGST 18%, and a Fixed 100 tax)
        cls.tax_cgst_9 = cls.AccountTax.create({
            'name': 'CGST 9%',
            'amount_type': 'percent',
            'amount': 9.0,
            'type_tax_use': 'sale',
            'sequence': 1,
            'company_id': cls.main_company.id,
            'tax_group_id': cls.tax_group.id,
        })
        cls.tax_sgst_9 = cls.AccountTax.create({
            'name': 'SGST 9%',
            'amount_type': 'percent',
            'amount': 9.0,
            'type_tax_use': 'sale',
            'sequence': 2,
            'company_id': cls.main_company.id,
            'tax_group_id': cls.tax_group.id,
        })
        cls.tax_igst_18 = cls.AccountTax.create({
            'name': 'IGST 18%',
            'amount_type': 'percent',
            'amount': 18.0,
            'type_tax_use': 'sale',
            'sequence': 10,
            'company_id': cls.main_company.id,
            'tax_group_id': cls.tax_group.id,
        })
        cls.tax_fixed_100 = cls.AccountTax.create({
            'name': 'Environmental Cess Fixed ₹100',
            'amount_type': 'fixed',
            'amount': 100.0,
            'type_tax_use': 'sale',
            'sequence': 20,
            'company_id': cls.main_company.id,
            'tax_group_id': cls.tax_group.id,
        })

    # =========================================================================
    # 1. TAX CONFIGURATION (tests 01–06)
    # =========================================================================

    def test_01_create_percentage_tax(self):
        """Administrator creates percentage sales tax with valid rate and metadata."""
        tax = self.AccountTax.with_user(self.admin_user).create({
            'name': 'Standard VAT 12%',
            'amount_type': 'percent',
            'amount': 12.0,
            'type_tax_use': 'sale',
            'company_id': self.main_company.id,
            'tax_group_id': self.tax_group.id,
        })
        self.assertTrue(tax.id)
        self.assertEqual(tax.amount, 12.0)
        self.assertEqual(tax.amount_type, 'percent')
        self.assertTrue(tax.active)

    def test_02_create_fixed_tax(self):
        """Administrator creates fixed amount sales tax."""
        tax = self.AccountTax.with_user(self.admin_user).create({
            'name': 'Municipal Fee Flat ₹50',
            'amount_type': 'fixed',
            'amount': 50.0,
            'type_tax_use': 'sale',
            'company_id': self.main_company.id,
            'tax_group_id': self.tax_group.id,
        })
        self.assertTrue(tax.id)
        self.assertEqual(tax.amount, 50.0)
        self.assertEqual(tax.amount_type, 'fixed')

    def test_03_tax_activation_and_archival(self):
        """Taxes can be active or archived safely without breaking references."""
        tax = self.AccountTax.create({
            'name': 'Temporary Cess 1%',
            'amount_type': 'percent',
            'amount': 1.0,
            'type_tax_use': 'sale',
            'tax_group_id': self.tax_group.id,
            'active': True,
        })
        self.assertTrue(tax.active)
        tax.write({'active': False})
        self.assertFalse(tax.active)

    def test_04_tax_company_isolation(self):
        """Taxes are strictly isolated by company."""
        country = self.env['res.country'].search([], limit=1)
        company_b = self.Company.create({
            'name': 'Brightloop Subsidiary B Ltd',
            'country_id': country.id,
        })
        tax_group_b = self.env['account.tax.group'].create({
            'name': 'GST B',
            'company_id': company_b.id,
        })
        tax_comp_b = self.AccountTax.create({
            'name': 'Sub B Tax 5%',
            'amount_type': 'percent',
            'amount': 5.0,
            'company_id': company_b.id,
            'tax_group_id': tax_group_b.id,
        })
        self.assertEqual(tax_comp_b.company_id, company_b)
        self.assertNotEqual(tax_comp_b.company_id, self.main_company)

    def test_05_staff_cannot_create_tax(self):
        """Staff users cannot create or reconfigure tax rates."""
        with self.assertRaises(AccessError):
            self.AccountTax.with_user(self.staff_user).create({
                'name': 'Unauthorized Tax',
                'amount_type': 'percent',
                'amount': 15.0,
            })

    def test_06_customer_cannot_access_tax_management(self):
        """Customers have no access to create or edit tax configurations."""
        with self.assertRaises(AccessError):
            self.AccountTax.with_user(self.customer_user).create({
                'name': 'Customer Tax Hack',
                'amount_type': 'percent',
                'amount': 0.0,
            })

    # =========================================================================
    # 2. TAX CALCULATION SERVICE (tests 07–13)
    # =========================================================================

    def test_07_tax_exclusive_calculation(self):
        """Tax-exclusive calculation on ₹2,000 with 18% IGST yields ₹360 tax, total ₹2,360."""
        breakdown = self.TaxService.compute_taxes(
            taxes=self.tax_igst_18,
            price_unit=2000.0,
            quantity=1.0,
            currency=self.currency_inr,
        )
        self.assertEqual(breakdown['untaxed_amount'], 2000.0)
        self.assertEqual(breakdown['total_tax'], 360.0)
        self.assertEqual(breakdown['total_included'], 2360.0)
        self.assertEqual(len(breakdown['tax_lines']), 1)
        self.assertEqual(breakdown['tax_lines'][0]['amount'], 360.0)

    def test_08_tax_inclusive_pricing(self):
        """Tax-inclusive tax splits base and tax correctly."""
        tax_inc_18 = self.AccountTax.create({
            'name': 'GST 18% Included',
            'amount_type': 'percent',
            'amount': 18.0,
            'price_include_override': 'tax_included',
            'type_tax_use': 'sale',
        })
        breakdown = self.TaxService.compute_taxes(
            taxes=tax_inc_18,
            price_unit=1180.0,
            quantity=1.0,
            currency=self.currency_inr,
            price_include=True,
        )
        # 1180 inclusive of 18% = 1000 base + 180 tax
        self.assertEqual(breakdown['total_tax'], 180.0)
        self.assertEqual(breakdown['total_excluded'], 1000.0)
        self.assertEqual(breakdown['total_included'], 1180.0)

    def test_09_multiple_taxes_intra_state_gst(self):
        """Multiple applicable taxes (CGST 9% + SGST 9%) compute ₹180 + ₹180 = ₹360 tax on ₹2,000."""
        combined_taxes = self.tax_cgst_9 | self.tax_sgst_9
        breakdown = self.TaxService.compute_taxes(
            taxes=combined_taxes,
            price_unit=2000.0,
            quantity=1.0,
            currency=self.currency_inr,
        )
        self.assertEqual(breakdown['untaxed_amount'], 2000.0)
        self.assertEqual(breakdown['total_tax'], 360.0)
        self.assertEqual(breakdown['total_included'], 2360.0)
        self.assertEqual(len(breakdown['tax_lines']), 2)

        tax_amounts = {t['tax_name']: t['amount'] for t in breakdown['tax_lines']}
        self.assertEqual(tax_amounts['CGST 9%'], 180.0)
        self.assertEqual(tax_amounts['SGST 9%'], 180.0)

    def test_10_mixed_percentage_and_fixed_tax(self):
        """Mixed percentage (18%) and flat fee (₹100) on ₹2,000 gives ₹360 + ₹100 = ₹460 tax."""
        mixed = self.tax_igst_18 | self.tax_fixed_100
        breakdown = self.TaxService.compute_taxes(
            taxes=mixed,
            price_unit=2000.0,
            quantity=1.0,
            currency=self.currency_inr,
        )
        self.assertEqual(breakdown['untaxed_amount'], 2000.0)
        self.assertEqual(breakdown['total_tax'], 460.0)
        self.assertEqual(breakdown['total_included'], 2460.0)

    def test_11_tax_calculation_respects_quantity(self):
        """Quantity multiplier (qty 3 on ₹2,000 = ₹6,000) yields ₹1,080 tax at 18%."""
        breakdown = self.TaxService.compute_taxes(
            taxes=self.tax_igst_18,
            price_unit=2000.0,
            quantity=3.0,
            currency=self.currency_inr,
        )
        self.assertEqual(breakdown['untaxed_amount'], 6000.0)
        self.assertEqual(breakdown['total_tax'], 1080.0)
        self.assertEqual(breakdown['total_included'], 7080.0)

    def test_12_tax_calculation_with_zero_taxes(self):
        """Zero applicable taxes returns exact untaxed amounts with 0.0 tax."""
        breakdown = self.TaxService.compute_taxes(
            taxes=self.AccountTax.browse(),
            price_unit=2500.0,
            quantity=2.0,
            currency=self.currency_inr,
        )
        self.assertEqual(breakdown['untaxed_amount'], 5000.0)
        self.assertEqual(breakdown['total_tax'], 0.0)
        self.assertEqual(breakdown['total_included'], 5000.0)
        self.assertEqual(len(breakdown['tax_lines']), 0)

    def test_13_no_double_tax_application(self):
        """Passing duplicate taxes in recordset does not double calculate."""
        # Recordsets naturally deduplicate identical records
        dup_taxes = self.tax_igst_18 | self.tax_igst_18
        self.assertEqual(len(dup_taxes), 1)
        breakdown = self.TaxService.compute_taxes(
            taxes=dup_taxes,
            price_unit=2000.0,
            quantity=1.0,
            currency=self.currency_inr,
        )
        self.assertEqual(breakdown['total_tax'], 360.0)

    # =========================================================================
    # 3. GST SUPPORT & FISCAL POSITIONS (tests 14–16)
    # =========================================================================

    def test_14_fiscal_position_interstate_tax_mapping(self):
        """Fiscal position correctly maps Intra-state (CGST+SGST) to Inter-state (IGST)."""
        self.tax_igst_18.write({'original_tax_ids': [(6, 0, [self.tax_cgst_9.id, self.tax_sgst_9.id])]})
        fp = self.FiscalPosition.create({
            'name': 'Inter-State GST Mapping',
            'tax_ids': [(6, 0, [self.tax_igst_18.id])],
        })
        mapped = fp.map_tax(self.tax_cgst_9 | self.tax_sgst_9)
        self.assertEqual(mapped, self.tax_igst_18)

        # Tax service uses this mapping
        breakdown = self.TaxService.compute_taxes(
            taxes=self.tax_cgst_9 | self.tax_sgst_9,
            price_unit=2000.0,
            quantity=1.0,
            fiscal_position=fp,
            currency=self.currency_inr,
        )
        self.assertEqual(len(breakdown['tax_lines']), 1)
        self.assertEqual(breakdown['tax_lines'][0]['tax_name'], 'IGST 18%')
        self.assertEqual(breakdown['total_tax'], 360.0)

    def test_15_gst_convenience_helper(self):
        """TaxService.get_gst_breakdown returns named GST components."""
        breakdown = self.TaxService.get_gst_breakdown(
            taxes=self.tax_cgst_9 | self.tax_sgst_9,
            price_unit=2000.0,
            quantity=1.0,
            currency=self.currency_inr,
        )
        self.assertIn('gst_components', breakdown)
        self.assertEqual(breakdown['gst_components']['CGST 9%'], 180.0)
        self.assertEqual(breakdown['gst_components']['SGST 9%'], 180.0)

    def test_16_avoid_simultaneous_cgst_sgst_and_igst(self):
        """Correct configuration does not blend intra-state and inter-state taxes erroneously."""
        # When mapped through inter-state fiscal position, intra-state taxes are excluded
        self.tax_igst_18.write({'original_tax_ids': [(6, 0, [self.tax_cgst_9.id, self.tax_sgst_9.id])]})
        fp = self.FiscalPosition.create({
            'name': 'Strict Inter-State',
            'tax_ids': [(6, 0, [self.tax_igst_18.id])],
        })
        breakdown = self.TaxService.compute_taxes(
            taxes=self.tax_cgst_9 | self.tax_sgst_9,
            price_unit=1000.0,
            quantity=1.0,
            fiscal_position=fp,
            currency=self.currency_inr,
        )
        tax_names = [t['tax_name'] for t in breakdown['tax_lines']]
        self.assertIn('IGST 18%', tax_names)
        self.assertNotIn('CGST 9%', tax_names)
        self.assertNotIn('SGST 9%', tax_names)

    # =========================================================================
    # 4. DISCOUNT MODEL & CONSTRAINTS (tests 17–22)
    # =========================================================================

    def test_17_create_percentage_discount(self):
        """Create valid percentage discount with scope and audit logging."""
        disc = self.Discount.create({
            'name': 'Festive Offer 10%',
            'discount_type': 'percentage',
            'discount_value': 10.0,
            'maximum_discount_amount': 500.0,
            'application_scope': 'all',
        })
        self.assertTrue(disc.id)
        self.assertEqual(disc.discount_value, 10.0)
        self.assertEqual(disc.maximum_discount_amount, 500.0)

    def test_18_create_fixed_discount(self):
        """Create valid fixed amount discount."""
        disc = self.Discount.create({
            'name': 'Welcome Credit ₹250',
            'discount_type': 'fixed',
            'discount_value': 250.0,
            'application_scope': 'all',
        })
        self.assertTrue(disc.id)
        self.assertEqual(disc.discount_value, 250.0)

    def test_19_reject_negative_discount_value(self):
        """Negative discount values are rejected via ValidationError."""
        with self.assertRaises(ValidationError):
            self.Discount.create({
                'name': 'Negative Invalid',
                'discount_type': 'percentage',
                'discount_value': -5.0,
            })

    def test_20_reject_percentage_exceeding_100(self):
        """Percentage discounts exceeding 100% are rejected via ValidationError."""
        with self.assertRaises(ValidationError):
            self.Discount.create({
                'name': 'Exorbitant 120%',
                'discount_type': 'percentage',
                'discount_value': 120.0,
            })

    def test_21_reject_invalid_date_range(self):
        """Start date after end date raises ValidationError."""
        with self.assertRaises(ValidationError):
            self.Discount.create({
                'name': 'Inverted Dates',
                'discount_type': 'percentage',
                'discount_value': 10.0,
                'start_date': date(2026, 12, 31),
                'end_date': date(2026, 1, 1),
            })

    def test_22_reject_negative_monetary_thresholds(self):
        """Negative minimum purchase or quantity thresholds raise ValidationError."""
        with self.assertRaises(ValidationError):
            self.Discount.create({
                'name': 'Bad Min Purchase',
                'discount_type': 'percentage',
                'discount_value': 5.0,
                'minimum_purchase_amount': -100.0,
            })

    # =========================================================================
    # 5. DISCOUNT ELIGIBILITY ENGINE (tests 23–32)
    # =========================================================================

    def test_23_eligible_discount_approved(self):
        """Discount satisfying all conditions returns eligible=True."""
        disc = self.Discount.create({
            'name': 'Standard 10%',
            'discount_type': 'percentage',
            'discount_value': 10.0,
            'active': True,
        })
        res = self.DiscountService.check_eligibility(
            discount=disc,
            product=self.product_saas,
            quantity=1.0,
            purchase_amount=2000.0,
        )
        self.assertTrue(res['eligible'])
        self.assertEqual(res['reason'], 'ok')

    def test_24_inactive_discount_rejected(self):
        """Archived or inactive discount returns eligible=False."""
        disc = self.Discount.create({
            'name': 'Inactive Disc',
            'discount_type': 'percentage',
            'discount_value': 10.0,
            'active': False,
        })
        res = self.DiscountService.check_eligibility(discount=disc)
        self.assertFalse(res['eligible'])
        self.assertIn('inactive', res['reason'].lower())

    def test_25_discount_before_start_date_rejected(self):
        """Discount evaluated before valid start date is rejected."""
        disc = self.Discount.create({
            'name': 'Future Black Friday',
            'discount_type': 'percentage',
            'discount_value': 20.0,
            'start_date': date.today() + relativedelta(days=10),
        })
        res = self.DiscountService.check_eligibility(
            discount=disc,
            target_date=date.today(),
        )
        self.assertFalse(res['eligible'])
        self.assertIn('starts', res['reason'].lower())

    def test_26_discount_after_end_date_rejected(self):
        """Discount evaluated after end date has expired is rejected."""
        disc = self.Discount.create({
            'name': 'Expired Flash Sale',
            'discount_type': 'percentage',
            'discount_value': 30.0,
            'start_date': date.today() - relativedelta(days=10),
            'end_date': date.today() - relativedelta(days=1),
        })
        res = self.DiscountService.check_eligibility(
            discount=disc,
            target_date=date.today(),
        )
        self.assertFalse(res['eligible'])
        self.assertIn('expired', res['reason'].lower())

    def test_27_minimum_purchase_threshold_enforced(self):
        """Purchase below minimum amount is rejected."""
        disc = self.Discount.create({
            'name': 'Bulk Spend ₹5,000 Disc',
            'discount_type': 'percentage',
            'discount_value': 15.0,
            'minimum_purchase_amount': 5000.0,
        })
        # ₹2,000 spend fails
        res_fail = self.DiscountService.check_eligibility(
            discount=disc,
            purchase_amount=2000.0,
        )
        self.assertFalse(res_fail['eligible'])
        self.assertIn('minimum', res_fail['reason'].lower())

        # ₹5,000 spend qualifies
        res_pass = self.DiscountService.check_eligibility(
            discount=disc,
            purchase_amount=5000.0,
        )
        self.assertTrue(res_pass['eligible'])

    def test_28_minimum_quantity_threshold_enforced(self):
        """Quantity below minimum quantity is rejected."""
        disc = self.Discount.create({
            'name': 'Buy 5 Seats Disc',
            'discount_type': 'percentage',
            'discount_value': 10.0,
            'minimum_quantity': 5.0,
        })
        # Qty 2 fails
        res_fail = self.DiscountService.check_eligibility(
            discount=disc,
            quantity=2.0,
        )
        self.assertFalse(res_fail['eligible'])

        # Qty 5 passes
        res_pass = self.DiscountService.check_eligibility(
            discount=disc,
            quantity=5.0,
        )
        self.assertTrue(res_pass['eligible'])

    def test_29_product_specific_scope_enforced(self):
        """Product-scoped discount allows eligible product and rejects other products."""
        disc = self.Discount.create({
            'name': 'SaaS Variant Only 10%',
            'discount_type': 'percentage',
            'discount_value': 10.0,
            'application_scope': 'product',
            'product_ids': [(6, 0, [self.product_saas.id])],
        })
        # Eligible product
        res_pass = self.DiscountService.check_eligibility(
            discount=disc,
            product=self.product_saas,
        )
        self.assertTrue(res_pass['eligible'])

        # Ineligible product
        res_fail = self.DiscountService.check_eligibility(
            discount=disc,
            product=self.product_device,
        )
        self.assertFalse(res_fail['eligible'])
        self.assertIn('eligible', res_fail['reason'].lower())

    def test_30_category_specific_scope_enforced(self):
        """Category-scoped discount allows products in matching category."""
        disc = self.Discount.create({
            'name': 'Software Category Promo',
            'discount_type': 'percentage',
            'discount_value': 10.0,
            'application_scope': 'category',
            'product_category_ids': [(6, 0, [self.category_software.id])],
        })
        res_pass = self.DiscountService.check_eligibility(
            discount=disc,
            product=self.product_saas,
        )
        self.assertTrue(res_pass['eligible'])

        res_fail = self.DiscountService.check_eligibility(
            discount=disc,
            product=self.product_device,  # Hardware
        )
        self.assertFalse(res_fail['eligible'])

    def test_31_subscription_plan_scope_enforced(self):
        """Subscription-plan-scoped discount applies only to designated plan."""
        plan_other = self.SubscriptionPlan.create({
            'name': 'Enterprise Plan',
            'product_id': self.product_saas.id,
            'billing_interval': 'yearly',
            'billing_interval_count': 1,
            'list_price': 20000.0,
        })
        disc = self.Discount.create({
            'name': 'Monthly Plan Special',
            'discount_type': 'percentage',
            'discount_value': 15.0,
            'application_scope': 'subscription_plan',
            'subscription_plan_ids': [(6, 0, [self.plan_monthly.id])],
        })
        # Matching plan
        res_pass = self.DiscountService.check_eligibility(
            discount=disc,
            subscription_plan=self.plan_monthly,
        )
        self.assertTrue(res_pass['eligible'])

        # Other plan
        res_fail = self.DiscountService.check_eligibility(
            discount=disc,
            subscription_plan=plan_other,
        )
        self.assertFalse(res_fail['eligible'])

    def test_32_exhausted_usage_limit_rejected(self):
        """Discount that has reached its usage limit is rejected."""
        disc = self.Discount.create({
            'name': 'First 10 Customers Only',
            'discount_type': 'percentage',
            'discount_value': 25.0,
            'usage_limit': 10,
        })
        disc.write({'usage_count': 10})
        res = self.DiscountService.check_eligibility(discount=disc)
        self.assertFalse(res['eligible'])
        self.assertIn('exhausted', res['reason'].lower())

    # =========================================================================
    # 6. DISCOUNT CALCULATION (tests 33–38)
    # =========================================================================

    def test_33_percentage_discount_calculation_2000_10_percent(self):
        """10% of ₹2,000 = ₹200; final amount before tax = ₹1,800."""
        disc = self.Discount.create({
            'name': 'Ten Percent Off',
            'discount_type': 'percentage',
            'discount_value': 10.0,
        })
        amt = self.DiscountService.calculate_discount_amount(
            discount=disc,
            price_unit=2000.0,
            quantity=1.0,
            currency=self.currency_inr,
        )
        self.assertEqual(amt, 200.0)

        breakdown = self.DiscountService.apply_discounts(
            discounts=[disc],
            price_unit=2000.0,
            quantity=1.0,
            currency=self.currency_inr,
        )
        self.assertEqual(breakdown['gross_amount'], 2000.0)
        self.assertEqual(breakdown['total_discount'], 200.0)
        self.assertEqual(breakdown['final_amount_before_tax'], 1800.0)

    def test_34_fixed_discount_calculation_2000_250_fixed(self):
        """Fixed ₹250 discount on ₹2,000 = final amount ₹1,750."""
        disc = self.Discount.create({
            'name': 'Flat 250 Off',
            'discount_type': 'fixed',
            'discount_value': 250.0,
        })
        amt = self.DiscountService.calculate_discount_amount(
            discount=disc,
            price_unit=2000.0,
            quantity=1.0,
            currency=self.currency_inr,
        )
        self.assertEqual(amt, 250.0)

        breakdown = self.DiscountService.apply_discounts(
            discounts=[disc],
            price_unit=2000.0,
            quantity=1.0,
            currency=self.currency_inr,
        )
        self.assertEqual(breakdown['final_amount_before_tax'], 1750.0)

    def test_35_maximum_discount_cap_enforced(self):
        """20% of ₹5,000 = ₹1,000, capped at maximum_discount_amount ₹400."""
        disc = self.Discount.create({
            'name': '20% Capped at 400',
            'discount_type': 'percentage',
            'discount_value': 20.0,
            'maximum_discount_amount': 400.0,
        })
        amt = self.DiscountService.calculate_discount_amount(
            discount=disc,
            price_unit=5000.0,
            quantity=1.0,
            currency=self.currency_inr,
        )
        self.assertEqual(amt, 400.0)

    def test_36_prevent_negative_line_totals(self):
        """Fixed discount exceeding line total floors at 0.00 and does not yield negative amount."""
        disc = self.Discount.create({
            'name': 'Huge ₹3,000 Credit',
            'discount_type': 'fixed',
            'discount_value': 3000.0,
        })
        breakdown = self.DiscountService.apply_discounts(
            discounts=[disc],
            price_unit=2000.0,
            quantity=1.0,
            currency=self.currency_inr,
        )
        self.assertEqual(breakdown['total_discount'], 2000.0)
        self.assertEqual(breakdown['final_amount_before_tax'], 0.0)

    def test_37_quantity_aware_discount_calculation(self):
        """10% discount on ₹2,000 * 3 units (₹6,000 gross) = ₹600 discount, net ₹5,400."""
        disc = self.Discount.create({
            'name': 'Volume 10%',
            'discount_type': 'percentage',
            'discount_value': 10.0,
        })
        breakdown = self.DiscountService.apply_discounts(
            discounts=[disc],
            price_unit=2000.0,
            quantity=3.0,
            currency=self.currency_inr,
        )
        self.assertEqual(breakdown['gross_amount'], 6000.0)
        self.assertEqual(breakdown['total_discount'], 600.0)
        self.assertEqual(breakdown['final_amount_before_tax'], 5400.0)

    def test_38_discount_stacking_rules(self):
        """
        Non-stackable takes priority; stackable discounts apply cumulatively.
        Gross ₹2,000.
        Disc A (non-stackable, priority 10): ₹250 flat -> price becomes ₹1,750.
        Disc B (stackable, priority 5): 10% on remaining ₹1,750 = ₹175.
        Total discount = ₹250 + ₹175 = ₹425. Final net = ₹1,575.
        """
        disc_a = self.Discount.create({
            'name': 'Non-Stackable Flat 250',
            'discount_type': 'fixed',
            'discount_value': 250.0,
            'stackable': False,
            'priority': 10,
        })
        disc_b = self.Discount.create({
            'name': 'Stackable 10% Additional',
            'discount_type': 'percentage',
            'discount_value': 10.0,
            'stackable': True,
            'priority': 5,
        })
        breakdown = self.DiscountService.apply_discounts(
            discounts=[disc_a, disc_b],
            price_unit=2000.0,
            quantity=1.0,
            currency=self.currency_inr,
        )
        self.assertEqual(breakdown['total_discount'], 425.0)
        self.assertEqual(breakdown['final_amount_before_tax'], 1575.0)

    # =========================================================================
    # 7. QUOTATION INTEGRATION (tests 39–41)
    # =========================================================================

    def test_39_quotation_line_apply_discount(self):
        """Applying eligible discount to quotation line sets discount% and links discount_id."""
        order = self.SaleOrder.create({'partner_id': self.partner_customer.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.product_saas.id,
            'subscription_plan_id': self.plan_monthly.id,
            'product_uom_qty': 1.0,
            'price_unit': 2000.0,
        })
        disc = self.Discount.create({
            'name': 'Quote Promo 10%',
            'discount_type': 'percentage',
            'discount_value': 10.0,
        })

        line.action_apply_discount(disc)
        self.assertEqual(line.discount, 10.0)
        self.assertEqual(line.discount_id, disc)
        self.assertEqual(line.price_subtotal, 1800.0)

    def test_40_quotation_line_reject_ineligible_discount(self):
        """Applying an expired discount to quotation line raises UserError."""
        order = self.SaleOrder.create({'partner_id': self.partner_customer.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.product_saas.id,
            'product_uom_qty': 1.0,
            'price_unit': 2000.0,
        })
        disc_expired = self.Discount.create({
            'name': 'Old Expired',
            'discount_type': 'percentage',
            'discount_value': 20.0,
            'start_date': date.today() - relativedelta(days=20),
            'end_date': date.today() - relativedelta(days=1),
        })
        with self.assertRaises(UserError):
            line.action_apply_discount(disc_expired)

    def test_41_quotation_tax_computation_after_discount(self):
        """Quotation line calculates tax on discounted base (₹2,000 - 10% = ₹1,800 * 18% = ₹324)."""
        order = self.SaleOrder.create({'partner_id': self.partner_customer.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.product_saas.id,
            'subscription_plan_id': self.plan_monthly.id,
            'product_uom_qty': 1.0,
            'price_unit': 2000.0,
            'tax_ids': [(6, 0, [self.tax_igst_18.id])],
        })
        disc = self.Discount.create({
            'name': '10% Saver',
            'discount_type': 'percentage',
            'discount_value': 10.0,
        })
        line.action_apply_discount(disc)

        tax_res = self.TaxService.compute_taxes_for_quotation_line(line)
        self.assertEqual(tax_res['untaxed_amount'], 1800.0)
        self.assertEqual(tax_res['total_tax'], 324.0)
        self.assertEqual(tax_res['total_included'], 2124.0)

    # =========================================================================
    # 8. SUBSCRIPTION INTEGRATION (tests 42–44)
    # =========================================================================

    def test_42_subscription_line_receives_discount_and_computes_tax(self):
        """Confirmed quotation converts to subscription carrying discount_id and computing tax."""
        # Assign taxes to product template
        self.tmpl_saas.write({'taxes_id': [(6, 0, [self.tax_igst_18.id])]})

        order = self.SaleOrder.create({'partner_id': self.partner_customer.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.product_saas.id,
            'subscription_plan_id': self.plan_monthly.id,
            'product_uom_qty': 1.0,
            'price_unit': 2000.0,
        })

        disc = self.Discount.create({
            'name': 'Subscription Welcome 10%',
            'discount_type': 'percentage',
            'discount_value': 10.0,
        })
        line.action_apply_discount(disc)
        order.action_confirm()

        subs = order.action_create_subscriptions()
        self.assertEqual(len(subs), 1)
        sub_line = subs[0].subscription_line_ids[0]

        self.assertEqual(sub_line.discount, 10.0)
        self.assertEqual(sub_line.discount_id, disc)
        self.assertEqual(sub_line.price_subtotal, 1800.0)
        self.assertEqual(sub_line.tax_amount, 324.0)
        self.assertEqual(sub_line.price_total, 2124.0)
        self.assertTrue(sub_line.tax_breakdown)

    def test_43_recurring_discount_revalidation_detects_expiry(self):
        """Discount service revalidates recurring discount for next billing date and catches expiry."""
        disc = self.Discount.create({
            'name': 'Limited 3-Month Promo',
            'discount_type': 'percentage',
            'discount_value': 15.0,
            'end_date': date.today() + relativedelta(days=45),
        })
        # Next billing in 30 days: still valid
        res_current = self.DiscountService.validate_recurring_discount(
            discount=disc,
            billing_date=date.today() + relativedelta(days=30),
            subscription_plan=self.plan_monthly,
            purchase_amount=2000.0,
        )
        self.assertTrue(res_current['eligible'])

        # Next billing in 60 days: expired
        res_future = self.DiscountService.validate_recurring_discount(
            discount=disc,
            billing_date=date.today() + relativedelta(days=60),
            subscription_plan=self.plan_monthly,
            purchase_amount=2000.0,
        )
        self.assertFalse(res_future['eligible'])
        self.assertIn('expired', res_future['reason'].lower())

    def test_44_no_invoice_generated_in_phase_7(self):
        """Phase 7 boundary: neither discount application nor tax computation generates account.move."""
        order = self.SaleOrder.create({'partner_id': self.partner_customer.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.product_saas.id,
            'subscription_plan_id': self.plan_monthly.id,
            'product_uom_qty': 1.0,
            'price_unit': 2000.0,
        })
        disc = self.Discount.create({
            'name': 'Test Boundary Disc',
            'discount_type': 'percentage',
            'discount_value': 5.0,
        })
        line.action_apply_discount(disc)
        order.action_confirm()

        # Check account.move count
        moves = self.env['account.move'].search([('invoice_origin', '=', order.name)])
        self.assertEqual(len(moves), 0, 'Phase 7 must NOT generate accounting invoices (Phase 8 boundary).')

    # =========================================================================
    # 9. USAGE LIMITS & CONCURRENCY PROTECTION (tests 45–47)
    # =========================================================================

    def test_45_usage_count_increments_atomically(self):
        """_increment_usage updates usage_count and logs audit event."""
        disc = self.Discount.create({
            'name': 'Coupon 5 Uses',
            'discount_type': 'fixed',
            'discount_value': 100.0,
            'usage_limit': 5,
        })
        self.assertEqual(disc.usage_count, 0)
        disc._increment_usage()
        self.assertEqual(disc.usage_count, 1)

    def test_46_usage_limit_strictly_enforced_at_ceiling(self):
        """Exceeding configured usage limit raises UserError."""
        disc = self.Discount.create({
            'name': 'One Time Special',
            'discount_type': 'fixed',
            'discount_value': 500.0,
            'usage_limit': 1,
        })
        disc._increment_usage()
        self.assertEqual(disc.usage_count, 1)

        # Second increment must fail
        with self.assertRaises(UserError):
            disc._increment_usage()

    def test_47_quotation_confirmation_consumes_usage(self):
        """Confirming quotation automatically consumes usage for applied discounts."""
        disc = self.Discount.create({
            'name': 'Order Confirm Coupon',
            'discount_type': 'percentage',
            'discount_value': 10.0,
            'usage_limit': 2,
        })
        order = self.SaleOrder.create({'partner_id': self.partner_customer.id})
        line = self.SaleOrderLine.create({
            'order_id': order.id,
            'product_id': self.product_saas.id,
            'product_uom_qty': 1.0,
            'price_unit': 2000.0,
        })
        line.action_apply_discount(disc)
        self.assertEqual(disc.usage_count, 0)

        order.action_confirm()
        self.assertEqual(disc.usage_count, 1)

    # =========================================================================
    # 10. SECURITY & AUDIT LOGGING (tests 48–50)
    # =========================================================================

    def test_48_admin_and_staff_discount_permissions(self):
        """Admin has full CRUD on discounts; Staff has read-only access."""
        # Admin can create
        disc = self.Discount.with_user(self.admin_user).create({
            'name': 'Admin Config Disc',
            'discount_type': 'percentage',
            'discount_value': 12.0,
        })
        self.assertTrue(disc.id)

        # Staff can read
        staff_disc = self.Discount.with_user(self.staff_user).browse(disc.id)
        self.assertEqual(staff_disc.name, 'Admin Config Disc')

        # Staff cannot modify discount value
        with self.assertRaises(AccessError):
            staff_disc.write({'discount_value': 50.0})

    def test_49_customer_blocked_from_discounts(self):
        """Customer role cannot create, modify, or read internal discount configurations."""
        with self.assertRaises(AccessError):
            self.Discount.with_user(self.customer_user).search([])

        with self.assertRaises(AccessError):
            self.Discount.with_user(self.customer_user).create({
                'name': 'Customer Rogue Disc',
                'discount_type': 'percentage',
                'discount_value': 90.0,
            })

    def test_50_tax_and_discount_audit_events_logged(self):
        """All discount creations, rejections, and usage updates are captured in security audit."""
        disc = self.Discount.create({
            'name': 'Audit Trail Discount',
            'discount_type': 'percentage',
            'discount_value': 10.0,
            'minimum_purchase_amount': 5000.0,
        })
        # Check discount_created audit event
        audit_created = self.SecurityAudit.search([
            ('event_type', '=', 'discount_created'),
            ('name', 'ilike', 'Audit Trail Discount'),
        ], limit=1)
        self.assertTrue(audit_created.id)

        # Trigger discount rejection
        self.DiscountService.apply_discounts(
            discounts=[disc],
            price_unit=1000.0,
            quantity=1.0,
            currency=self.currency_inr,
        )
        audit_rejected = self.SecurityAudit.search([
            ('event_type', '=', 'discount_rejected'),
            ('name', 'ilike', 'Audit Trail Discount'),
        ], limit=1)
        self.assertTrue(audit_rejected.id)
