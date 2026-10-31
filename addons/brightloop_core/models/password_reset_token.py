# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.password_reset_token
#
# Cryptographically Secure Password Reset Token Model
#
# PHASE 2 SCOPE
# -------------
# Manages single-use, hashed, expiring tokens for customer/staff password resets.
#
# SECURITY ARCHITECTURE
# ---------------------
# - Tokens are generated using the OS CSPRNG (secrets.token_urlsafe).
# - Only SHA-256 hashes of tokens are stored in the database. Plaintext tokens
#   are NEVER stored in the database or written to log files.
# - Enforces single-use consumption.
# - Enforces time-based expiration (default: 1 hour).
# - Rate limiting prevents automated flooding/abuse per user.
# - Tokens are invalidated immediately after consumption.
# =============================================================================

import hashlib
import logging
import secrets
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

TOKEN_EXPIRATION_HOURS = 1
RATE_LIMIT_WINDOW_MINUTES = 15
RATE_LIMIT_MAX_REQUESTS = 3


class BrightloopPasswordResetToken(models.Model):
    """
    Manages hashed password reset tokens.
    """
    _name = 'brightloop.password.reset.token'
    _description = 'Brightloop Password Reset Token'
    _order = 'create_date desc'

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
        required=True,
        ondelete='cascade',
        index=True,
        readonly=True,
    )

    token_hash = fields.Char(
        string='Token Hash (SHA-256)',
        required=True,
        index=True,
        readonly=True,
        help='Cryptographic SHA-256 digest of the plaintext reset token.',
    )

    expiration_date = fields.Datetime(
        string='Expires At (UTC)',
        required=True,
        readonly=True,
        index=True,
    )

    used = fields.Boolean(
        string='Used',
        default=False,
        readonly=True,
        index=True,
    )

    used_date = fields.Datetime(
        string='Used At (UTC)',
        readonly=True,
    )

    request_ip = fields.Char(
        string='Request IP',
        readonly=True,
    )

    # =========================================================================
    # TOKEN GENERATION & MANAGEMENT
    # =========================================================================

    @api.model
    def _hash_token(self, token: str) -> str:
        """Compute SHA-256 hash of a plaintext token."""
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    @api.model
    def create_token_for_user(self, user, ip_address=None) -> str:
        """
        Generate a cryptographically secure reset token for a user.

        :param user: res.users record
        :param ip_address: Optional client IP address
        :return: Plaintext token string (to send via email or return to caller)
        :raises UserError: If rate limit is exceeded
        """
        now = fields.Datetime.now()
        rate_window = now - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)

        # Rate limiting: check recent requests
        recent_count = self.sudo().search_count([
            ('user_id', '=', user.id),
            ('create_date', '>=', rate_window),
        ])
        if recent_count >= RATE_LIMIT_MAX_REQUESTS:
            self.env['brightloop.security.audit'].log_event(
                event_type='unauthorized_access',
                summary='Rate limit exceeded for password reset request',
                details=f'User {user.login} exceeded reset limit ({RATE_LIMIT_MAX_REQUESTS} requests in {RATE_LIMIT_WINDOW_MINUTES}m)',
                target_user_id=user.id,
                ip_address=ip_address,
            )
            raise UserError('Too many password reset requests. Please wait a few minutes before trying again.')

        # Invalidate existing active tokens for this user
        self.sudo().search([
            ('user_id', '=', user.id),
            ('used', '=', False),
        ]).write({'used': True, 'used_date': now})

        # Generate CSPRNG token (32 bytes = 256 bits of entropy)
        raw_token = secrets.token_urlsafe(32)
        token_hash = self._hash_token(raw_token)
        expiration = now + timedelta(hours=TOKEN_EXPIRATION_HOURS)

        # Store ONLY the hash in database
        self.sudo().create({
            'user_id': user.id,
            'token_hash': token_hash,
            'expiration_date': expiration,
            'request_ip': ip_address or False,
        })

        # Audit log (never includes raw_token)
        self.env['brightloop.security.audit'].log_event(
            event_type='password_reset_request',
            summary='Password reset token requested',
            details=f'Reset token issued for user {user.login}. Expires in {TOKEN_EXPIRATION_HOURS} hour(s).',
            target_user_id=user.id,
            ip_address=ip_address,
        )

        # Send email via template
        template = self.env.ref('brightloop_core.mail_template_password_reset', raise_if_not_found=False)
        if template:
            try:
                template.sudo().with_context(
                    token=raw_token,
                    request_time=now.strftime('%Y-%m-%d %H:%M:%S UTC'),
                ).send_mail(user.id, force_send=False)
            except Exception as e:
                _logger.warning('Failed to enqueue reset email for user %s: %s', user.login, e)

        return raw_token

    @api.model
    def validate_token(self, token: str):
        """
        Validate a plaintext token without consuming it.

        :param token: Plaintext token string
        :return: Matching brightloop.password.reset.token record
        :raises UserError: If token is invalid, expired, or already used
        """
        if not token or not isinstance(token, str):
            raise UserError('Invalid password reset token format.')

        token_hash = self._hash_token(token)
        record = self.sudo().search([
            ('token_hash', '=', token_hash),
        ], limit=1)

        if not record:
            raise UserError('Invalid or unrecognized password reset token.')

        if record.used:
            self.env['brightloop.security.audit'].log_event(
                event_type='unauthorized_access',
                summary='Attempted reuse of consumed password reset token',
                details=f'Token for user {record.user_id.login} was already consumed on {record.used_date}',
                target_user_id=record.user_id.id,
            )
            raise UserError('This password reset token has already been used.')

        if fields.Datetime.now() > record.expiration_date:
            self.env['brightloop.security.audit'].log_event(
                event_type='unauthorized_access',
                summary='Attempted use of expired password reset token',
                details=f'Token for user {record.user_id.login} expired on {record.expiration_date}',
                target_user_id=record.user_id.id,
            )
            raise UserError('This password reset token has expired.')

        return record

    @api.model
    def consume_token_and_reset_password(self, token: str, new_password: str) -> bool:
        """
        Validate token, enforce password policy, set new password, and invalidate token.

        :param token: Plaintext token string
        :param new_password: New password string
        :return: True on success
        :raises UserError / ValidationError: If token or password fails validation
        """
        record = self.validate_token(token)
        user = record.user_id

        # Enforce password policy
        user._validate_password_policy(new_password)

        # Mark token as used immediately
        record.write({
            'used': True,
            'used_date': fields.Datetime.now(),
        })

        # Update user password securely via Odoo's crypt context
        user.sudo().write({'password': new_password})

        # Invalidate any other tokens for this user
        self.sudo().search([
            ('user_id', '=', user.id),
            ('id', '!=', record.id),
            ('used', '=', False),
        ]).write({'used': True, 'used_date': fields.Datetime.now()})

        # Audit log
        self.env['brightloop.security.audit'].log_event(
            event_type='password_reset_success',
            summary='Password successfully reset via token',
            details=f'Password reset completed for user {user.login}.',
            target_user_id=user.id,
        )

        return True
