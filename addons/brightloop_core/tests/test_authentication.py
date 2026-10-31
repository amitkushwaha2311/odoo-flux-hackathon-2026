# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.tests.test_authentication
#
# Automated Tests for Authentication, Credential Verification & Session Security
# =============================================================================

from odoo.exceptions import AccessDenied
from odoo.tests.common import TransactionCase


class TestAuthentication(TransactionCase):
    """
    Test suite for credential verification, email-based login, case-insensitive
    matching, and access denial for invalid passwords.
    """

    def setUp(self):
        super().setUp()
        self.AuthService = self.env['brightloop.auth.service']
        self.email = 'auth.tester@brightloop.io'
        self.password = 'SecureAuthPass2026!'
        self.user = self.env['res.users'].register_customer(
            name='Auth Tester',
            email=self.email,
            password=self.password,
        )

    def test_01_valid_authentication(self):
        """Valid credentials must return the authenticated user record."""
        auth_user = self.AuthService.authenticate_credentials(self.email, self.password)
        self.assertEqual(auth_user.id, self.user.id)

    def test_02_case_insensitive_email_login(self):
        """Login email comparison must be case-insensitive."""
        upper_email = 'AUTH.TESTER@BRIGHTLOOP.IO'
        auth_user = self.AuthService.authenticate_credentials(upper_email, self.password)
        self.assertEqual(auth_user.id, self.user.id)

        mixed_email = 'Auth.Tester@BrightLoop.io'
        auth_user2 = self.AuthService.authenticate_credentials(mixed_email, self.password)
        self.assertEqual(auth_user2.id, self.user.id)

    def test_03_invalid_password_rejected(self):
        """Invalid password must raise AccessDenied."""
        with self.assertRaises(AccessDenied):
            self.AuthService.authenticate_credentials(self.email, 'WrongPassword123!')

    def test_04_unknown_email_rejected(self):
        """Non-existent email must raise AccessDenied."""
        with self.assertRaises(AccessDenied):
            self.AuthService.authenticate_credentials('unknown.user@brightloop.io', self.password)

    def test_05_empty_credentials_rejected(self):
        """Empty login or password must raise AccessDenied."""
        with self.assertRaises(AccessDenied):
            self.AuthService.authenticate_credentials('', self.password)

        with self.assertRaises(AccessDenied):
            self.AuthService.authenticate_credentials(self.email, '')
