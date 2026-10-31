# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.tests.test_registration
#
# Automated Tests for Customer Registration & Password Policy Enforcement
# =============================================================================

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestCustomerRegistration(TransactionCase):
    """
    Test suite for customer registration, email normalization, uniqueness,
    password policy, and role assignment restrictions.
    """

    def setUp(self):
        super().setUp()
        self.Users = self.env['res.users']
        self.customer_group = self.env.ref('brightloop_core.group_brightloop_customer')
        self.portal_group = self.env.ref('base.group_portal')
        self.staff_group = self.env.ref('brightloop_core.group_brightloop_staff')
        self.admin_group = self.env.ref('brightloop_core.group_brightloop_admin')

    def test_01_valid_customer_registration(self):
        """Valid customer registration must succeed with correct groups and partner."""
        email = 'valid.customer@brightloop.io'
        user = self.Users.register_customer(
            name='Alice Valid',
            email=email,
            password='Password123!',
        )
        self.assertTrue(user, 'User must be created.')
        self.assertEqual(user.login, email)
        self.assertEqual(user.email, email)
        self.assertTrue(user.partner_id, 'Partner must be created and linked.')
        self.assertEqual(user.partner_id.name, 'Alice Valid')
        self.assertEqual(user.partner_id.email, email)

        # Must have Customer and Portal groups
        self.assertIn(self.customer_group, user.all_group_ids, 'Must belong to Brightloop Customer group.')
        self.assertIn(self.portal_group, user.all_group_ids, 'Must belong to Portal group.')

        # Must NOT have privileged groups
        self.assertNotIn(self.staff_group, user.all_group_ids, 'Customer must NOT have Staff role.')
        self.assertNotIn(self.admin_group, user.all_group_ids, 'Customer must NOT have Admin role.')

    def test_02_missing_email_rejected(self):
        """Registration without email must raise ValidationError."""
        with self.assertRaises(ValidationError):
            self.Users.register_customer(
                name='No Email User',
                email='',
                password='Password123!',
            )

        with self.assertRaises(ValidationError):
            self.Users.register_customer(
                name='None Email User',
                email=None,
                password='Password123!',
            )

    def test_03_duplicate_email_rejected(self):
        """Registering with an already existing email must raise ValidationError."""
        email = 'duplicate.test@brightloop.io'
        self.Users.register_customer(
            name='First Registration',
            email=email,
            password='Password123!',
        )

        with self.assertRaises(ValidationError):
            self.Users.register_customer(
                name='Second Registration',
                email=email,
                password='AnotherPassword123!',
            )

    def test_04_case_insensitive_duplicate_email_rejected(self):
        """Email uniqueness check must be strictly case-insensitive."""
        self.Users.register_customer(
            name='Case Test',
            email='casetest@brightloop.io',
            password='Password123!',
        )

        with self.assertRaises(ValidationError):
            self.Users.register_customer(
                name='Case Duplicate',
                email='CASETEST@BRIGHTLOOP.IO',
                password='Password456@',
            )

        with self.assertRaises(ValidationError):
            self.Users.register_customer(
                name='Mixed Case Duplicate',
                email='CaseTest@BrightLoop.io',
                password='Password789#',
            )

    def test_05_password_length_policy(self):
        """Password with 8 or fewer characters must be rejected (must be > 8 characters)."""
        # 8 characters exactly (1 upper, 1 lower, 1 digit, 1 special) -> must fail!
        with self.assertRaises(ValidationError):
            self.Users.register_customer(
                name='Short Pass',
                email='shortpass@brightloop.io',
                password='Pass12!a',  # len = 8
            )

        # 9 characters -> must succeed!
        user = self.Users.register_customer(
            name='Valid Length Pass',
            email='validlen@brightloop.io',
            password='Pass12!ab',  # len = 9
        )
        self.assertTrue(user)

    def test_06_password_missing_uppercase(self):
        """Password missing uppercase letter must be rejected."""
        with self.assertRaises(ValidationError):
            self.Users.register_customer(
                name='No Upper',
                email='noupper@brightloop.io',
                password='password123!',
            )

    def test_07_password_missing_lowercase(self):
        """Password missing lowercase letter must be rejected."""
        with self.assertRaises(ValidationError):
            self.Users.register_customer(
                name='No Lower',
                email='nolower@brightloop.io',
                password='PASSWORD123!',
            )

    def test_08_password_missing_special_character(self):
        """Password missing special character must be rejected."""
        with self.assertRaises(ValidationError):
            self.Users.register_customer(
                name='No Special',
                email='nospecial@brightloop.io',
                password='Password12345',
            )
