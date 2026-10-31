# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.auth_service
#
# Backend Authentication & Credential Service
#
# PHASE 2 SCOPE
# -------------
# Centralizes authentication operations:
#   - Email-based user verification
#   - Customer registration
#   - Staff user provisioning
#   - Password reset request and confirmation
#   - Email enumeration defense
# =============================================================================

import logging
from odoo import api, models
from odoo.exceptions import AccessDenied, UserError

_logger = logging.getLogger(__name__)


class BrightloopAuthService(models.AbstractModel):
    """
    Centralized service for Brightloop authentication, registration, and password recovery.
    """
    _name = 'brightloop.auth.service'
    _description = 'Brightloop Authentication Service'

    # =========================================================================
    # AUTHENTICATION
    # =========================================================================

    @api.model
    def authenticate_credentials(self, email: str, password: str, ip_address=None):
        """
        Verify credentials for a user using case-insensitive email matching.

        :param email: Login email.
        :param password: Candidate plaintext password.
        :param ip_address: Origin IP address.
        :return: Authenticated res.users record.
        :raises AccessDenied: On invalid login or password.
        """
        email = (email or '').strip().lower()
        if not email or not password:
            raise AccessDenied('Email and password are required.')

        user = self.env['res.users'].sudo().search([
            '|',
            ('login', '=ilike', email),
            ('email', '=ilike', email),
        ], limit=1)

        if not user:
            self.env['brightloop.security.audit'].log_event(
                event_type='login_failure',
                summary='Login failed: user not found',
                details=f'Attempted login with non-existent email: {email}',
                ip_address=ip_address,
            )
            raise AccessDenied('Invalid email or password.')

        self.env.cr.execute(
            "SELECT COALESCE(password, '') FROM res_users WHERE id=%s",
            [user.id]
        )
        row = self.env.cr.fetchone()
        hashed = row[0] if row else ''
        if not hashed:
            self.env['brightloop.security.audit'].log_event(
                event_type='login_failure',
                summary='Login failed: user has no password set',
                details=f'User {email} has no stored password hash',
                target_user_id=user.id,
                ip_address=ip_address,
            )
            raise AccessDenied('Invalid email or password.')

        valid, replacement = user._crypt_context().verify_and_update(password, hashed)
        if replacement is not None:
            user.sudo()._set_encrypted_password(user.id, replacement)

        if not valid:
            self.env['brightloop.security.audit'].log_event(
                event_type='login_failure',
                summary='Login failed: invalid password',
                details=f'Failed password attempt for user {email}',
                target_user_id=user.id,
                ip_address=ip_address,
            )
            raise AccessDenied('Invalid email or password.')

        return user

    # =========================================================================
    # PASSWORD RESET ORCHESTRATION
    # =========================================================================

    @api.model
    def request_password_reset(self, email: str, ip_address=None) -> dict:
        """
        Initiate a password reset request.

        ANTI-ENUMERATION:
          Returns an identical confirmation message whether or not the email exists
          in the system, preventing attackers from probing for registered emails.

        :param email: Customer or staff email.
        :param ip_address: Origin IP address.
        :return: Standard response dict.
        """
        normalized_email = (email or '').strip().lower()

        if normalized_email:
            user = self.env['res.users'].sudo().search([
                '|',
                ('login', '=ilike', normalized_email),
                ('email', '=ilike', normalized_email),
            ], limit=1)

            if user and user.active:
                # User exists: generate token and send email
                self.env['brightloop.password.reset.token'].create_token_for_user(
                    user, ip_address=ip_address
                )
            else:
                # Log enumeration probe attempt
                self.env['brightloop.security.audit'].log_event(
                    event_type='password_reset_request',
                    summary='Password reset requested for unregistered email',
                    details=f'Reset requested for non-existent email: {normalized_email}',
                    ip_address=ip_address,
                )

        return {
            'success': True,
            'message': 'If the provided email is registered with Brightloop, password reset instructions have been sent.',
        }

    @api.model
    def confirm_password_reset(self, token: str, new_password: str) -> bool:
        """
        Complete a password reset using a single-use token.

        :param token: Plaintext token received by customer.
        :param new_password: New candidate password satisfying security policy.
        :return: True on success.
        """
        return self.env['brightloop.password.reset.token'].consume_token_and_reset_password(
            token, new_password
        )
