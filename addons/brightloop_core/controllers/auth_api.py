# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.controllers.auth_api
#
# Authentication & Identity REST API Controller
#
# PHASE 12 SCOPE
# --------------
# - RESTful JSON endpoints for authentication and session management.
# - /api/v1/auth/login: Authenticates credentials and sets session cookies.
# - /api/v1/auth/register: Customer self-registration using res.users.register_customer.
# - /api/v1/auth/reset-password: Password recovery request.
# - /api/v1/auth/me: Current authenticated session identity, role, and permissions.
# - /api/v1/auth/logout: Session termination.
# =============================================================================

import json
import logging
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessDenied, AccessError, UserError, ValidationError
from odoo.addons.web.controllers.session import authenticate as odoo_authenticate, logout as odoo_logout, save_session

_logger = logging.getLogger(__name__)


class BrightloopAuthApiController(http.Controller):
    """
    Authentication & Session REST API controller.
    """

    def _get_auth_service(self):
        return request.env['brightloop.auth.service']

    def _get_user_role(self, user):
        """Determine primary Brightloop role of the user."""
        if not user or user._is_public():
            return 'anonymous'
        if user._is_admin() or user.has_group('brightloop_core.group_brightloop_admin') or user.has_group('base.group_system'):
            return 'admin'
        if user.has_group('brightloop_core.group_brightloop_staff') or user.has_group('account.group_account_invoice'):
            return 'staff'
        return 'customer'

    # =========================================================================
    # 1. LOGIN ENDPOINT
    # =========================================================================

    @http.route('/api/v1/auth/login', type='http', auth='public', methods=['POST'], csrf=False)
    def api_login(self, **kw):
        """
        Authenticate user with email/login and password.
        Sets standard Odoo session cookie and returns user profile.
        """
        try:
            body = {}
            if request.httprequest.data:
                try:
                    body = json.loads(request.httprequest.data.decode('utf-8'))
                except Exception:
                    body = {}
            params = {**request.params, **body}

            login = (params.get('login') or params.get('email') or '').strip()
            password = params.get('password') or ''

            if not login or not password:
                return request.make_json_response(
                    {'status': 'error', 'message': 'Email and password are required.'},
                    status=400,
                )

            db_name = request.db or request.env.cr.dbname or 'brightloop_dev'

            # Authenticate through native Odoo session controller
            credential = {'login': login, 'password': password, 'type': 'password'}
            auth_info = odoo_authenticate(request.session, request.env, credential)
            uid = auth_info.get('uid')

            if not uid:
                return request.make_json_response(
                    {'status': 'error', 'message': 'Invalid email or password.'},
                    status=401,
                )

            request.session.db = db_name
            save_session(request, request.env)

            user = request.env['res.users'].sudo().browse(uid)
            role = self._get_user_role(user)

            return request.make_json_response({
                'status': 'success',
                'user': {
                    'id': user.id,
                    'name': user.name,
                    'email': user.email or user.login,
                    'role': role,
                    'company_id': user.company_id.id,
                    'company_name': user.company_id.name,
                    'is_admin': role == 'admin',
                    'is_staff': role in ('admin', 'staff'),
                    'is_customer': role == 'customer',
                },
            }, status=200)

        except AccessDenied as e:
            return request.make_json_response({'status': 'error', 'message': 'Invalid email or password.'}, status=401)
        except Exception as e:
            _logger.exception('Login error: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

    # =========================================================================
    # 2. CUSTOMER REGISTRATION ENDPOINT
    # =========================================================================

    @http.route('/api/v1/auth/register', type='http', auth='public', methods=['POST'], csrf=False)
    def api_register(self, **kw):
        """
        Register a new customer account using Phase 2 registration service.
        Strictly assigns Customer role (never Admin or Staff).
        """
        try:
            body = {}
            if request.httprequest.data:
                try:
                    body = json.loads(request.httprequest.data.decode('utf-8'))
                except Exception:
                    body = {}
            params = {**request.params, **body}

            name = (params.get('name') or '').strip()
            email = (params.get('email') or '').strip()
            password = params.get('password') or ''

            if not name or not email or not password:
                return request.make_json_response(
                    {'status': 'error', 'message': 'Full name, email, and password are required.'},
                    status=400,
                )

            ip = request.httprequest.remote_addr
            user = request.env['res.users'].sudo().register_customer(
                name=name,
                email=email,
                password=password,
                ip_address=ip,
            )

            # Automatically log in new customer
            db_name = request.db or request.env.cr.dbname or 'brightloop_dev'
            credential = {'login': email.lower(), 'password': password, 'type': 'password'}
            odoo_authenticate(request.session, request.env, credential)
            request.session.db = db_name
            save_session(request, request.env)

            user_info = {
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'role': 'customer',
                'company_id': user.company_id.id,
                'company_name': user.company_id.name,
            }
            return request.make_json_response({
                'status': 'success',
                'message': 'Account created successfully.',
                'data': user_info,
                'user': user_info,
            }, status=201)

        except ValidationError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Registration error: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

    # =========================================================================
    # 3. PASSWORD RESET REQUEST ENDPOINT
    # =========================================================================

    @http.route('/api/v1/auth/reset-password', type='http', auth='public', methods=['POST'], csrf=False)
    def api_reset_password(self, **kw):
        """
        Request password reset email.
        Always returns generic message to prevent email enumeration.
        """
        try:
            body = {}
            if request.httprequest.data:
                try:
                    body = json.loads(request.httprequest.data.decode('utf-8'))
                except Exception:
                    body = {}
            params = {**request.params, **body}
            email = (params.get('email') or '').strip()

            if email:
                ip = request.httprequest.remote_addr
                try:
                    self._get_auth_service().sudo().request_password_reset(email, ip_address=ip)
                except Exception as e:
                    _logger.warning('Password reset request error for %s: %s', email, e)

            return request.make_json_response({
                'status': 'success',
                'message': 'If an account associated with this email exists, password reset instructions have been dispatched.',
            }, status=200)

        except Exception as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

    # =========================================================================
    # 4. CURRENT SESSION IDENTITY (WHOAMI)
    # =========================================================================

    @http.route('/api/v1/auth/me', type='http', auth='public', methods=['GET'], csrf=False)
    def api_me(self, **kw):
        """
        Return the identity, role, and capabilities of the currently authenticated user.
        """
        user = request.env.user
        if not user or user._is_public() or user.id == request.env.ref('base.public_user', raise_if_not_found=False).id:
            return request.make_json_response({
                'status': 'anonymous',
                'authenticated': False,
                'user': None,
            }, status=200)

        role = self._get_user_role(user)
        companies = [{'id': c.id, 'name': c.name} for c in user.company_ids]

        return request.make_json_response({
            'status': 'success',
            'authenticated': True,
            'user': {
                'id': user.id,
                'name': user.name,
                'email': user.email or user.login,
                'role': role,
                'company_id': user.company_id.id,
                'company_name': user.company_id.name,
                'companies': companies,
                'is_admin': role == 'admin',
                'is_staff': role in ('admin', 'staff'),
                'is_customer': role == 'customer',
            },
        }, status=200)

    # =========================================================================
    # 5. LOGOUT ENDPOINT
    # =========================================================================

    @http.route('/api/v1/auth/logout', type='http', auth='public', methods=['POST', 'GET'], csrf=False)
    def api_logout(self, **kw):
        """
        Terminate user session.
        """
        try:
            if hasattr(request, 'session') and request.session:
                odoo_logout(request.session, keep_db=True)
            return request.make_json_response({'status': 'success', 'message': 'Logged out successfully.'}, status=200)
        except Exception as e:
            _logger.warning('Logout error: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

