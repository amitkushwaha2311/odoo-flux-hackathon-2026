# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.tests.test_password_reset
#
# Automated Tests for Password Reset Workflow & Cryptographic Token Security
# =============================================================================

from datetime import timedelta
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestPasswordReset(TransactionCase):
    """
    Test suite for password reset token generation, secure hashing, single-use
    consumption, expiration, rate limiting, and email enumeration defense.
    """

    def setUp(self):
        super().setUp()
        self.AuthService = self.env['brightloop.auth.service']
        self.TokenModel = self.env['brightloop.password.reset.token']
        self.email = 'reset.tester@brightloop.io'
        self.original_password = 'OriginalPass123!'
        self.user = self.env['res.users'].register_customer(
            name='Reset Tester',
            email=self.email,
            password=self.original_password,
        )

    def test_01_valid_password_reset_flow(self):
        """End-to-end password reset flow must succeed and allow login with new password."""
        # 1. Generate token
        raw_token = self.TokenModel.create_token_for_user(self.user)
        self.assertTrue(raw_token, 'A plaintext token must be returned.')

        # Database must store ONLY hash, not raw_token
        stored_record = self.TokenModel.search([('user_id', '=', self.user.id), ('used', '=', False)], limit=1)
        self.assertTrue(stored_record)
        self.assertNotEqual(stored_record.token_hash, raw_token, 'Database must never store raw token.')
        self.assertEqual(stored_record.token_hash, self.TokenModel._hash_token(raw_token))

        # 2. Reset password using token
        new_password = 'BrandNewPassword2026!'
        success = self.AuthService.confirm_password_reset(raw_token, new_password)
        self.assertTrue(success)

        # 3. Old password must be invalid now
        with self.assertRaises(Exception):
            self.AuthService.authenticate_credentials(self.email, self.original_password)

        # 4. New password must authenticate successfully
        authenticated_user = self.AuthService.authenticate_credentials(self.email, new_password)
        self.assertEqual(authenticated_user.id, self.user.id)

    def test_02_reused_token_rejected(self):
        """A consumed token cannot be reused for a second reset (single-use enforcement)."""
        raw_token = self.TokenModel.create_token_for_user(self.user)
        self.AuthService.confirm_password_reset(raw_token, 'FirstChangePass123!')

        # Attempt to reuse the same token
        with self.assertRaises(UserError):
            self.AuthService.confirm_password_reset(raw_token, 'SecondChangePass123!')

    def test_03_expired_token_rejected(self):
        """An expired token must be rejected."""
        raw_token = self.TokenModel.create_token_for_user(self.user)
        token_record = self.TokenModel.search([('user_id', '=', self.user.id), ('used', '=', False)], limit=1)

        # Artificially set expiration to the past
        past_time = fields.Datetime.now() - timedelta(hours=2)
        token_record.sudo().write({'expiration_date': past_time})

        with self.assertRaises(UserError):
            self.AuthService.confirm_password_reset(raw_token, 'ExpiredResetPass123!')

    def test_04_invalid_token_rejected(self):
        """Bogus, malformed, or empty tokens must be rejected."""
        with self.assertRaises(UserError):
            self.AuthService.confirm_password_reset('completely_fake_token_value_123', 'SomePassword123!')

        with self.assertRaises(UserError):
            self.AuthService.confirm_password_reset('', 'SomePassword123!')

    def test_05_anti_enumeration_identical_response(self):
        """
        Requesting reset for an existing vs non-existing email must return
        an identical response message to prevent email enumeration attacks.
        """
        resp_existing = self.AuthService.request_password_reset(self.email)
        resp_non_existing = self.AuthService.request_password_reset('does.not.exist@brightloop.io')

        self.assertEqual(resp_existing['success'], True)
        self.assertEqual(resp_non_existing['success'], True)
        self.assertEqual(resp_existing['message'], resp_non_existing['message'])

    def test_06_rate_limiting_enforced(self):
        """Requesting more than MAX_REQUESTS within the time window must be rejected."""
        # 1st request -> ok
        self.TokenModel.create_token_for_user(self.user)
        # 2nd request -> ok
        self.TokenModel.create_token_for_user(self.user)
        # 3rd request -> ok
        self.TokenModel.create_token_for_user(self.user)

        # 4th request -> must exceed rate limit!
        with self.assertRaises(UserError):
            self.TokenModel.create_token_for_user(self.user)

