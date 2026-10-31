# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.tests.test_products
#
# Phase 3 Automated Tests — Product & Variant Management Engine
#
# Test coverage:
#   - Product creation, validation, and lifecycle (tests 01–08)
#   - Product attribute and variant generation (tests 09–13)
#   - Pricing: base price, attribute extras, no double-counting (tests 14–20)
#   - Role-based access control (Admin/Staff/Customer) (tests 21–27)
#   - Audit event logging for product lifecycle (tests 28–31)
# =============================================================================

import logging
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class TestProducts(TransactionCase):
    """
    Phase 3 test suite: Product & Variant Management Engine.
    Uses Odoo standard product infrastructure (product.template, product.product,
    product.attribute, product.template.attribute.value).
    """

    def setUp(self):
        super().setUp()

        self.ProductTemplate = self.env['product.template']
        self.ProductAttribute = self.env['product.attribute']
        self.ProductAttributeValue = self.env['product.attribute.value']
        self.SecurityAudit = self.env['brightloop.security.audit']
        self.PricingService = self.env['brightloop.pricing.service']
        self.Users = self.env['res.users']

        self.admin_group = self.env.ref('brightloop_core.group_brightloop_admin')
        self.staff_group = self.env.ref('brightloop_core.group_brightloop_staff')
        self.customer_group = self.env.ref('brightloop_core.group_brightloop_customer')
        self.internal_group = self.env.ref('base.group_user')
        self.portal_group = self.env.ref('base.group_portal')

        # --- Admin user ---
        partner_admin = self.env['res.partner'].create({
            'name': 'Product Admin',
            'email': 'productadmin@brightloop.io',
        })
        self.admin_user = self.Users.create({
            'name': 'Product Admin',
            'login': 'productadmin@brightloop.io',
            'email': 'productadmin@brightloop.io',
            'partner_id': partner_admin.id,
            'group_ids': [(6, 0, [self.admin_group.id, self.internal_group.id])],
        })

        # --- Staff user ---
        partner_staff = self.env['res.partner'].create({
            'name': 'Product Staff',
            'email': 'productstaff@brightloop.io',
        })
        self.staff_user = self.Users.create({
            'name': 'Product Staff',
            'login': 'productstaff@brightloop.io',
            'email': 'productstaff@brightloop.io',
            'partner_id': partner_staff.id,
            'group_ids': [(6, 0, [self.staff_group.id, self.internal_group.id])],
        })

        # --- Customer user (portal) ---
        self.customer_user = self.Users.register_customer(
            name='Product Customer',
            email='productcustomer@brightloop.io',
            password='CustomerProd123!',
        )

    # =========================================================================
    # PRODUCT CREATION AND VALIDATION (tests 01–08)
    # =========================================================================

    def test_01_create_valid_product_service(self):
        """Admin can create a valid service-type product with correct fields."""
        product = self.ProductTemplate.create({
            'name': 'Brightloop SaaS Plan',
            'type': 'service',
            'list_price': 2000.0,
            'standard_price': 800.0,
            'description_sale': 'Monthly SaaS subscription service.',
        })
        self.assertTrue(product.id, 'Product was not created.')
        self.assertEqual(product.name, 'Brightloop SaaS Plan')
        self.assertEqual(product.type, 'service')
        self.assertEqual(product.list_price, 2000.0)
        self.assertEqual(product.standard_price, 800.0)
        self.assertTrue(product.active, 'Newly created product must be active by default.')

    def test_02_create_valid_product_goods(self):
        """Admin can create a valid consumable (goods) product."""
        product = self.ProductTemplate.create({
            'name': 'USB Device License',
            'type': 'consu',
            'list_price': 500.0,
            'standard_price': 150.0,
        })
        self.assertTrue(product.id)
        self.assertEqual(product.type, 'consu')
        self.assertEqual(product.list_price, 500.0)

    def test_03_missing_name_rejected(self):
        """Empty or whitespace-only product name must raise ValidationError."""
        with self.assertRaises((ValidationError, UserError)):
            self.ProductTemplate.create({
                'name': '   ',
                'type': 'service',
                'list_price': 100.0,
            })

    def test_04_negative_sales_price_rejected(self):
        """Negative sales price (list_price) must raise ValidationError."""
        with self.assertRaises(ValidationError):
            self.ProductTemplate.create({
                'name': 'Bad Price Product',
                'type': 'service',
                'list_price': -1.0,
            })

    def test_05_negative_cost_price_rejected(self):
        """Negative cost price (standard_price) must raise ValidationError."""
        with self.assertRaises(ValidationError):
            self.ProductTemplate.create({
                'name': 'Bad Cost Product',
                'type': 'service',
                'list_price': 100.0,
                'standard_price': -50.0,
            })

    def test_06_update_product_info(self):
        """Admin can update product name and description successfully."""
        product = self.ProductTemplate.create({
            'name': 'Original Name',
            'type': 'service',
            'list_price': 1000.0,
        })
        product.write({
            'name': 'Updated Name',
            'description_sale': 'Updated description for Brightloop plan.',
        })
        self.assertEqual(product.name, 'Updated Name')
        self.assertEqual(product.description_sale, 'Updated description for Brightloop plan.')

    def test_07_archive_product(self):
        """Admin can archive a product; product becomes inactive."""
        product = self.ProductTemplate.create({
            'name': 'To Be Archived',
            'type': 'service',
            'list_price': 1500.0,
        })
        self.assertTrue(product.active)
        product.write({'active': False})
        # Use sudo to bypass any active domain filtering
        archived = self.ProductTemplate.sudo().with_context(active_test=False).browse(product.id)
        self.assertFalse(archived.active, 'Product must be inactive after archival.')

    def test_08_reactivate_product(self):
        """Admin can reactivate a previously archived product."""
        product = self.ProductTemplate.create({
            'name': 'To Be Reactivated',
            'type': 'service',
            'list_price': 500.0,
        })
        product.write({'active': False})
        product.with_context(active_test=False).write({'active': True})
        reactivated = self.ProductTemplate.sudo().browse(product.id)
        self.assertTrue(reactivated.active, 'Product must be active after reactivation.')

    # =========================================================================
    # PRODUCT ATTRIBUTE AND VARIANT GENERATION (tests 09–13)
    # =========================================================================

    def test_09_create_product_attribute(self):
        """Admin can create a product attribute."""
        attr = self.ProductAttribute.create({'name': 'Edition'})
        self.assertTrue(attr.id)
        self.assertEqual(attr.name, 'Edition')

    def test_10_create_attribute_values(self):
        """Admin can create multiple values for a product attribute."""
        attr = self.ProductAttribute.create({'name': 'Edition'})
        val_standard = self.ProductAttributeValue.create({'name': 'Standard', 'attribute_id': attr.id})
        val_odoo = self.ProductAttributeValue.create({'name': 'Odoo', 'attribute_id': attr.id})
        self.assertTrue(val_standard.id)
        self.assertTrue(val_odoo.id)
        self.assertEqual(val_standard.attribute_id, attr)
        self.assertEqual(val_odoo.attribute_id, attr)

    def test_11_generate_variants(self):
        """Adding one attribute with two values to a template generates two variants."""
        attr = self.ProductAttribute.create({'name': 'Edition'})
        val_s = self.ProductAttributeValue.create({'name': 'Standard', 'attribute_id': attr.id})
        val_o = self.ProductAttributeValue.create({'name': 'Odoo', 'attribute_id': attr.id})

        product = self.ProductTemplate.create({
            'name': 'SaaS Edition Plan',
            'type': 'service',
            'list_price': 2000.0,
            'attribute_line_ids': [(0, 0, {
                'attribute_id': attr.id,
                'value_ids': [(6, 0, [val_s.id, val_o.id])],
            })],
        })

        variants = product.product_variant_ids
        self.assertEqual(len(variants), 2, f'Expected 2 variants; got {len(variants)}')

    def test_12_multiple_attribute_combinations(self):
        """Two attributes with two values each generate four variants."""
        attr_edition = self.ProductAttribute.create({'name': 'Edition'})
        val_std = self.ProductAttributeValue.create({'name': 'Standard', 'attribute_id': attr_edition.id})
        val_pro = self.ProductAttributeValue.create({'name': 'Pro', 'attribute_id': attr_edition.id})

        attr_support = self.ProductAttribute.create({'name': 'Support'})
        val_basic = self.ProductAttributeValue.create({'name': 'Basic', 'attribute_id': attr_support.id})
        val_premium = self.ProductAttributeValue.create({'name': 'Premium', 'attribute_id': attr_support.id})

        product = self.ProductTemplate.create({
            'name': 'Multi-Attribute Plan',
            'type': 'service',
            'list_price': 3000.0,
            'attribute_line_ids': [
                (0, 0, {
                    'attribute_id': attr_edition.id,
                    'value_ids': [(6, 0, [val_std.id, val_pro.id])],
                }),
                (0, 0, {
                    'attribute_id': attr_support.id,
                    'value_ids': [(6, 0, [val_basic.id, val_premium.id])],
                }),
            ],
        })

        variants = product.product_variant_ids
        self.assertEqual(len(variants), 4, f'Expected 4 variants (2×2); got {len(variants)}')

    def test_13_archived_variant_check_available_raises(self):
        """check_available_for_sale() raises UserError when the product template is archived."""
        product = self.ProductTemplate.create({
            'name': 'Archived Product Check',
            'type': 'service',
            'list_price': 1000.0,
        })
        product.write({'active': False})

        # Retrieve the product bypassing active filter
        product_inactive = self.ProductTemplate.sudo().with_context(active_test=False).browse(product.id)
        with self.assertRaises(UserError):
            product_inactive.check_available_for_sale()

    # =========================================================================
    # PRICING TESTS — BASE, EXTRAS, NO DOUBLE-COUNTING (tests 14–20)
    # =========================================================================

    def _create_edition_plan(self):
        """
        Helper: Create a 'SaaS Edition Plan' template at ₹2,000 with
        two variants — Standard (₹0 extra) and Odoo (₹560 extra).
        Returns (template, standard_variant, odoo_variant).
        """
        attr = self.ProductAttribute.create({'name': 'Edition'})
        val_std = self.ProductAttributeValue.create({'name': 'Standard', 'attribute_id': attr.id})
        val_odoo = self.ProductAttributeValue.create({'name': 'Odoo', 'attribute_id': attr.id})

        product = self.ProductTemplate.create({
            'name': 'SaaS Pricing Plan',
            'type': 'service',
            'list_price': 2000.0,
            'attribute_line_ids': [(0, 0, {
                'attribute_id': attr.id,
                'value_ids': [(6, 0, [val_std.id, val_odoo.id])],
            })],
        })

        # Set ₹560 price_extra on the "Odoo" PTAV (product.template.attribute.value)
        odoo_ptav = product.attribute_line_ids.product_template_value_ids.filtered(
            lambda ptav: ptav.name == 'Odoo'
        )
        self.assertEqual(len(odoo_ptav), 1, 'Expected exactly one PTAV named "Odoo"')
        odoo_ptav.sudo().write({'price_extra': 560.0})

        # Identify variants by their attribute values
        std_variant = product.product_variant_ids.filtered(
            lambda v: any(ptav.name == 'Standard' for ptav in v.product_template_attribute_value_ids)
        )
        odoo_variant = product.product_variant_ids.filtered(
            lambda v: any(ptav.name == 'Odoo' for ptav in v.product_template_attribute_value_ids)
        )

        self.assertEqual(len(std_variant), 1)
        self.assertEqual(len(odoo_variant), 1)
        return product, std_variant, odoo_variant

    def test_14_base_product_price(self):
        """Template list_price is set to ₹2,000."""
        product, std_variant, odoo_variant = self._create_edition_plan()
        self.assertEqual(product.list_price, 2000.0,
                         f'Expected template list_price=2000.0, got {product.list_price}')

    def test_15_standard_variant_extra_price_zero(self):
        """Standard variant has zero attribute extra; effective price equals base (₹2,000)."""
        product, std_variant, odoo_variant = self._create_edition_plan()
        std_ptav = std_variant.product_template_attribute_value_ids.filtered(
            lambda ptav: ptav.name == 'Standard'
        )
        self.assertEqual(std_ptav.price_extra, 0.0,
                         f'Standard PTAV price_extra should be 0.0, got {std_ptav.price_extra}')
        self.assertAlmostEqual(
            std_variant.lst_price, 2000.0, places=2,
            msg=f'Standard variant lst_price should be ₹2,000.00, got {std_variant.lst_price}'
        )

    def test_16_odoo_variant_extra_price_560(self):
        """Odoo variant has ₹560 extra; effective price = ₹2,000 + ₹560 = ₹2,560."""
        product, std_variant, odoo_variant = self._create_edition_plan()
        odoo_ptav = odoo_variant.product_template_attribute_value_ids.filtered(
            lambda ptav: ptav.name == 'Odoo'
        )
        self.assertEqual(odoo_ptav.price_extra, 560.0,
                         f'Odoo PTAV price_extra should be 560.0, got {odoo_ptav.price_extra}')
        self.assertAlmostEqual(
            odoo_variant.lst_price, 2560.0, places=2,
            msg=f'Odoo variant lst_price should be ₹2,560.00, got {odoo_variant.lst_price}'
        )

    def test_17_pricing_service_calculate_variant(self):
        """PricingService.calculate_variant_price(odoo_variant) returns ₹2,560.00."""
        product, std_variant, odoo_variant = self._create_edition_plan()
        price = self.PricingService.calculate_variant_price(odoo_variant)
        self.assertAlmostEqual(
            price, 2560.0, places=2,
            msg=f'PricingService should return ₹2,560.00 for Odoo variant; got {price}'
        )

    def test_18_pricing_service_breakdown(self):
        """PricingService.get_variant_price_breakdown returns a complete and correct dict."""
        product, std_variant, odoo_variant = self._create_edition_plan()
        breakdown = self.PricingService.get_variant_price_breakdown(odoo_variant)

        self.assertIn('base_price', breakdown)
        self.assertIn('attribute_extras', breakdown)
        self.assertIn('total_extra', breakdown)
        self.assertIn('effective_price', breakdown)
        self.assertIn('currency_symbol', breakdown)

        self.assertAlmostEqual(breakdown['base_price'], 2000.0, places=2,
                               msg=f'base_price should be ₹2,000.00, got {breakdown["base_price"]}')
        self.assertAlmostEqual(breakdown['total_extra'], 560.0, places=2,
                               msg=f'total_extra should be ₹560.00, got {breakdown["total_extra"]}')
        self.assertAlmostEqual(breakdown['effective_price'], 2560.0, places=2,
                               msg=f'effective_price should be ₹2,560.00, got {breakdown["effective_price"]}')
        self.assertEqual(len(breakdown['attribute_extras']), 1,
                         f'Expected 1 attribute extra in breakdown, got {len(breakdown["attribute_extras"])}')

        extra_entry = breakdown['attribute_extras'][0]
        self.assertEqual(extra_entry['value_name'], 'Odoo')
        self.assertAlmostEqual(extra_entry['price_extra'], 560.0, places=2)

    def test_19_extra_price_not_double_applied(self):
        """
        Critical: Verify ₹560 extra is applied exactly once.
        odoo_variant.lst_price must equal ₹2,560 (not ₹2,560 + ₹560 = ₹3,120).
        """
        product, std_variant, odoo_variant = self._create_edition_plan()
        effective_price = odoo_variant.lst_price
        self.assertAlmostEqual(
            effective_price, 2560.0, places=2,
            msg=(
                f'Extra price was double-applied! Expected ₹2,560.00 but got ₹{effective_price:.2f}. '
                'The ₹560 attribute extra must be applied exactly once.'
            )
        )
        # Also verify via PricingService for consistency
        service_price = self.PricingService.calculate_variant_price(odoo_variant)
        self.assertAlmostEqual(service_price, effective_price, places=2,
                               msg='PricingService price must match variant lst_price — no discrepancy.')

    def test_20_multiple_attribute_price_extras(self):
        """
        Two attributes each with a price extra: effective price = base + sum of both extras.
        base=₹3,000, extra_1=₹400, extra_2=₹200 → effective=₹3,600.
        """
        attr_edition = self.ProductAttribute.create({'name': 'Edition'})
        val_pro = self.ProductAttributeValue.create({'name': 'Pro', 'attribute_id': attr_edition.id})
        val_std2 = self.ProductAttributeValue.create({'name': 'Standard', 'attribute_id': attr_edition.id})

        attr_support = self.ProductAttribute.create({'name': 'Support'})
        val_premium = self.ProductAttributeValue.create({'name': 'Premium', 'attribute_id': attr_support.id})
        val_basic2 = self.ProductAttributeValue.create({'name': 'Basic', 'attribute_id': attr_support.id})

        product = self.ProductTemplate.create({
            'name': 'Multi Extra Plan',
            'type': 'service',
            'list_price': 3000.0,
            'attribute_line_ids': [
                (0, 0, {
                    'attribute_id': attr_edition.id,
                    'value_ids': [(6, 0, [val_pro.id, val_std2.id])],
                }),
                (0, 0, {
                    'attribute_id': attr_support.id,
                    'value_ids': [(6, 0, [val_premium.id, val_basic2.id])],
                }),
            ],
        })

        # Set price_extra on "Pro" = ₹400 and "Premium" = ₹200
        pro_ptav = product.attribute_line_ids.product_template_value_ids.filtered(
            lambda p: p.name == 'Pro'
        )
        premium_ptav = product.attribute_line_ids.product_template_value_ids.filtered(
            lambda p: p.name == 'Premium'
        )
        pro_ptav.sudo().write({'price_extra': 400.0})
        premium_ptav.sudo().write({'price_extra': 200.0})

        # Find the "Pro + Premium" variant
        target_variant = product.product_variant_ids.filtered(
            lambda v: (
                any(p.name == 'Pro' for p in v.product_template_attribute_value_ids)
                and any(p.name == 'Premium' for p in v.product_template_attribute_value_ids)
            )
        )
        self.assertEqual(len(target_variant), 1)

        # Verify effective price = ₹3,000 + ₹400 + ₹200 = ₹3,600
        price = self.PricingService.calculate_variant_price(target_variant)
        self.assertAlmostEqual(
            price, 3600.0, places=2,
            msg=f'Expected ₹3,600.00 (base ₹3,000 + Pro ₹400 + Premium ₹200), got ₹{price:.2f}'
        )

    # =========================================================================
    # ROLE-BASED ACCESS CONTROL (tests 21–27)
    # =========================================================================

    def test_21_admin_can_create_product(self):
        """Admin user can create a product successfully."""
        product = self.ProductTemplate.with_user(self.admin_user).create({
            'name': 'Admin Created Product',
            'type': 'service',
            'list_price': 1000.0,
        })
        self.assertTrue(product.id, 'Admin should be able to create a product.')

    def test_22_staff_cannot_create_product(self):
        """Staff user attempting to create a product must raise AccessError."""
        with self.assertRaises(AccessError):
            self.ProductTemplate.with_user(self.staff_user).create({
                'name': 'Staff Illegal Product',
                'type': 'service',
                'list_price': 500.0,
            })

    def test_23_customer_cannot_create_product(self):
        """Customer (portal) attempting to create a product must raise AccessError."""
        with self.assertRaises(AccessError):
            self.ProductTemplate.with_user(self.customer_user).create({
                'name': 'Customer Illegal Product',
                'type': 'service',
                'list_price': 200.0,
            })

    def test_24_staff_can_read_product(self):
        """Staff user can search and read product templates (read-only access)."""
        # Create product as admin context first
        product = self.ProductTemplate.create({
            'name': 'Readable Plan for Staff',
            'type': 'service',
            'list_price': 750.0,
        })
        # Staff reads product catalog
        results = self.ProductTemplate.with_user(self.staff_user).search(
            [('name', '=', 'Readable Plan for Staff')]
        )
        self.assertTrue(results, 'Staff should be able to read product templates.')
        self.assertEqual(results[0].name, 'Readable Plan for Staff')

    def test_25_staff_cannot_modify_price(self):
        """Staff user attempting to write list_price must raise AccessError."""
        product = self.ProductTemplate.create({
            'name': 'Price Protected Plan',
            'type': 'service',
            'list_price': 1000.0,
        })
        with self.assertRaises(AccessError):
            product.with_user(self.staff_user).write({'list_price': 1500.0})

    def test_26_customer_cannot_access_products(self):
        """Customer (portal) cannot search or read product templates."""
        self.ProductTemplate.create({
            'name': 'Hidden From Customer',
            'type': 'service',
            'list_price': 1200.0,
        })
        with self.assertRaises(AccessError):
            self.ProductTemplate.with_user(self.customer_user).search([])

    def test_27_customer_cannot_read_standard_price(self):
        """Customer cannot access the standard_price (cost) field of any product."""
        product = self.ProductTemplate.create({
            'name': 'Cost Protected Product',
            'type': 'service',
            'list_price': 1000.0,
            'standard_price': 400.0,
        })
        # standard_price field has groups="base.group_user" — portal users are excluded.
        # Attempting to read the field as customer should raise AccessError.
        with self.assertRaises(AccessError):
            self.ProductTemplate.with_user(self.customer_user).search([])

    # =========================================================================
    # AUDIT EVENT LOGGING (tests 28–31)
    # =========================================================================

    def test_28_product_creation_logged(self):
        """Creating a product must log a product_created audit event."""
        audit_count_before = self.SecurityAudit.search_count([
            ('event_type', '=', 'product_created'),
        ])
        self.ProductTemplate.create({
            'name': 'Audit Creation Test Plan',
            'type': 'service',
            'list_price': 1100.0,
        })
        audit_count_after = self.SecurityAudit.search_count([
            ('event_type', '=', 'product_created'),
        ])
        self.assertGreater(
            audit_count_after, audit_count_before,
            'A product_created audit event must be logged when a product is created.'
        )

    def test_29_product_update_logged(self):
        """Updating product details must log a product_updated audit event."""
        product = self.ProductTemplate.create({
            'name': 'Audit Update Test Plan',
            'type': 'service',
            'list_price': 900.0,
        })
        audit_count_before = self.SecurityAudit.search_count([
            ('event_type', '=', 'product_updated'),
        ])
        product.write({'name': 'Updated Audit Test Plan'})
        audit_count_after = self.SecurityAudit.search_count([
            ('event_type', '=', 'product_updated'),
        ])
        self.assertGreater(
            audit_count_after, audit_count_before,
            'A product_updated audit event must be logged when product details change.'
        )

    def test_30_price_change_logged(self):
        """Changing list_price must log a product_updated audit event."""
        product = self.ProductTemplate.create({
            'name': 'Price Change Audit Plan',
            'type': 'service',
            'list_price': 500.0,
        })
        audit_count_before = self.SecurityAudit.search_count([
            ('event_type', '=', 'product_updated'),
        ])
        product.write({'list_price': 750.0})
        audit_count_after = self.SecurityAudit.search_count([
            ('event_type', '=', 'product_updated'),
        ])
        self.assertGreater(
            audit_count_after, audit_count_before,
            'A product_updated audit event must be logged when list_price changes.'
        )

    def test_31_archive_event_logged(self):
        """Archiving a product must log a product_archived audit event."""
        product = self.ProductTemplate.create({
            'name': 'Archive Audit Plan',
            'type': 'service',
            'list_price': 300.0,
        })
        audit_count_before = self.SecurityAudit.search_count([
            ('event_type', '=', 'product_archived'),
        ])
        product.write({'active': False})
        audit_count_after = self.SecurityAudit.search_count([
            ('event_type', '=', 'product_archived'),
        ])
        self.assertGreater(
            audit_count_after, audit_count_before,
            'A product_archived audit event must be logged when a product is archived.'
        )

