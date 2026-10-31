# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.tests.test_frontend_experience
#
# Automated Test Suite for Phase 12: Premium Frontend, Complete Product Experience & Visual System
#
# COVERS:
# 1. Marketing Landing Page & Cinematic Video Integration (/ and /brightloop)
# 2. Palomar Hero Video (hf_20260820_010308_b1636845-4c15-4ab6-b0c9-9a29bfb0c6e3.mp4)
# 3. Driftbar Footer Video (4d01c727-d9c5-47c8-a778-35a451ffd39f.mp4)
# 4. Living Green Ambient Canvas (#ambient-canvas) & ThreeUI sylva integration
# 5. Authentication UI Pages (/auth/login, /auth/register, /auth/reset-password)
# 6. Real-time Password Policy Validation UI & Registration Backend Engine
# 7. Authenticated SaaS Console Shell (/app) & Customer Portal Shell (/app/portal)
# 8. Authentication REST API (/api/v1/auth/login, register, reset-password, me, logout)
# 9. App REST API for Admin/Staff (/api/v1/app/subscriptions, catalog, quotations, invoices, payments, actions)
# 10. Static Asset Delivery (CSS theme design tokens, landing JS, app client JS)
# =============================================================================

import json
import logging
from odoo.tests.common import HttpCase
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


class TestFrontendExperience(HttpCase):
    """
    Automated HTTP test suite verifying the Phase 12 frontend experience,
    routes, visual tokens, video assets, authentication flows, and app APIs.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.User = cls.env['res.users'].sudo()
        cls.Partner = cls.env['res.partner'].sudo()
        cls.Subscription = cls.env['brightloop.subscription'].sudo()
        cls.SubscriptionPlan = cls.env['brightloop.subscription.plan'].sudo()
        cls.Product = cls.env['product.product'].sudo()
        cls.company = cls.env.company

        # Staff user with group_brightloop_staff
        cls.staff_user = cls.User.create({
            'name': 'Brightloop Staff Lead',
            'login': 'staff_frontend@brightloop.test',
            'email': 'staff_frontend@brightloop.test',
            'group_ids': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('brightloop_core.group_brightloop_staff').id,
            ])],
            'company_id': cls.company.id,
            'company_ids': [(6, 0, [cls.company.id])],
        })
        cls.staff_user.password = 'StaffPass123!@#'

        # Ensure a test subscription plan exists
        cls.product_service = cls.Product.create({
            'name': 'Cloud Platform Enterprise',
            'type': 'service',
            'list_price': 450.0,
        })

        cls.test_plan = cls.SubscriptionPlan.create({
            'name': 'Enterprise Monthly Front',
            'billing_interval': 'monthly',
            'billing_interval_count': 1,
            'list_price': 450.0,
            'currency_id': cls.company.currency_id.id,
            'product_id': cls.product_service.id,
            'allow_pause': True,
            'allow_early_closure': True,
        })

        # Test customer partner and subscription
        cls.customer_partner = cls.Partner.create({
            'name': 'Frontend Test Corp',
            'email': 'customer_front@test.com',
            'customer_rank': 1,
            'company_id': cls.company.id,
        })

        cls.test_subscription = cls.Subscription.create({
            'name': 'SUB-FRONT-001',
            'customer_id': cls.customer_partner.id,
            'subscription_plan_id': cls.test_plan.id,
            'recurring_amount': 450.0,
            'currency_id': cls.company.currency_id.id,
            'company_id': cls.company.id,
            'state': 'active',
            'start_date': '2026-01-01',
            'next_billing_date': '2026-02-01',
        })

    # =========================================================================
    # 1. PUBLIC MARKETING WEBSITE & CINEMATIC ASSETS
    # =========================================================================

    def test_01_landing_page_palomar_hero_video(self):
        """Landing page returns HTTP 200 and embeds the Palomar cinematic hero video."""
        res = self.url_open('/')
        self.assertEqual(res.status_code, 200)
        content = res.text

        # Verify Palomar Video asset
        self.assertIn('hf_20260820_010308_b1636845-4c15-4ab6-b0c9-9a29bfb0c6e3.mp4', content)
        self.assertIn('<video', content)
        self.assertIn('id="hero-video"', content)

        # Verify Core SaaS branding & headline
        self.assertIn('Brightloop', content)
        self.assertIn('Subscription Intelligence', content)

    def test_02_landing_page_driftbar_footer_video(self):
        """Landing page embeds the Driftbar atmospheric footer video and poster fallback."""
        res = self.url_open('/brightloop')
        self.assertEqual(res.status_code, 200)
        content = res.text

        # Verify Driftbar Video asset
        self.assertIn('4d01c727-d9c5-47c8-a778-35a451ffd39f.mp4', content)
        self.assertIn('id="footer-video"', content)
        self.assertIn('driftbar-footer', content)

    def test_03_landing_page_living_green_particle_canvas(self):
        """Landing page renders the ambient living-green particle canvas element."""
        res = self.url_open('/')
        self.assertEqual(res.status_code, 200)
        content = res.text

        # Verify Living Green canvas
        self.assertIn('<canvas id="ambient-canvas"></canvas>', content)
        self.assertIn('brightloop_landing.js', content)

    # =========================================================================
    # 2. AUTHENTICATION PAGES (LOGIN, REGISTER, RESET)
    # =========================================================================

    def test_04_auth_login_page_renders(self):
        """Auth login page returns HTTP 200 with credentials form and redirect handler."""
        res = self.url_open('/auth/login')
        self.assertEqual(res.status_code, 200)
        content = res.text

        self.assertIn('id="login-form"', content)
        self.assertIn('id="login-email"', content)
        self.assertIn('id="login-password"', content)
        self.assertIn('Sign In', content)

    def test_05_auth_register_page_password_policy_checklist(self):
        """Auth register page returns HTTP 200 and renders real-time password policy checklist."""
        res = self.url_open('/auth/register')
        self.assertEqual(res.status_code, 200)
        content = res.text

        self.assertIn('id="register-form"', content)
        self.assertIn('rule-len', content)
        self.assertIn('rule-upper', content)
        self.assertIn('rule-lower', content)
        self.assertIn('rule-special', content)

    def test_06_auth_reset_password_page_renders(self):
        """Auth reset password page returns HTTP 200 with recovery instructions."""
        res = self.url_open('/auth/reset-password')
        self.assertEqual(res.status_code, 200)
        content = res.text

        self.assertIn('id="reset-form"', content)
        self.assertIn('id="reset-email"', content)
        self.assertIn('Send Reset Link', content)

    # =========================================================================
    # 3. AUTHENTICATED APPLICATION SHELLS
    # =========================================================================

    def test_07_app_shell_and_portal_shell_structure(self):
        """SaaS application shell (/app) and portal shell (/app/portal) return HTTP 200 and include layout."""
        res_app = self.url_open('/app')
        self.assertEqual(res_app.status_code, 200)
        self.assertIn('id="brightloop-app"', res_app.text)
        self.assertIn('brightloop_app.js', res_app.text)
        self.assertIn('tab-overview', res_app.text)
        self.assertIn('tab-subscriptions', res_app.text)

        res_portal = self.url_open('/app/portal')
        self.assertEqual(res_portal.status_code, 200)
        self.assertIn('tab-portal', res_portal.text)

    # =========================================================================
    # 4. AUTHENTICATION REST API
    # =========================================================================

    def test_08_api_auth_me_anonymous(self):
        """Unauthenticated caller to /api/v1/auth/me receives anonymous status."""
        res = self.url_open('/api/v1/auth/me')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.text)
        self.assertEqual(data.get('status'), 'anonymous')
        self.assertFalse(data.get('authenticated'))

    def test_09_api_auth_register_weak_password_rejected(self):
        """Customer registration rejects passwords violating enterprise policy (>8, uppercase, lowercase, special)."""
        payload = {
            'name': 'Test Weak Corp',
            'email': 'weak@example.com',
            'password': 'simplepassword',  # No uppercase, no special char
        }
        res = self.url_open('/api/v1/auth/register', data=json.dumps(payload), headers={'Content-Type': 'application/json'})
        self.assertEqual(res.status_code, 400)
        data = json.loads(res.text)
        self.assertEqual(data.get('status'), 'error')

    def test_10_api_auth_register_success(self):
        """Customer registration creates a customer user and partner with valid password."""
        unique_email = 'customer_new_2026@brightloop.test'
        payload = {
            'name': 'New Enterprise Client',
            'email': unique_email,
            'password': 'Secur3!P@ssword2026',
        }
        res = self.url_open('/api/v1/auth/register', data=json.dumps(payload), headers={'Content-Type': 'application/json'})
        self.assertEqual(res.status_code, 201)
        data = json.loads(res.text)
        self.assertEqual(data.get('status'), 'success')
        self.assertEqual(data.get('data', {}).get('email'), unique_email)

        # Verify user in database has customer group
        created_user = self.User.search([('login', '=', unique_email)])
        self.assertTrue(created_user.exists())
        self.assertTrue(created_user.has_group('brightloop_core.group_brightloop_customer'))

    def test_11_api_auth_login_invalid_password(self):
        """Login attempt with wrong password returns 401 Unauthorized."""
        payload = {
            'login': 'staff_frontend@brightloop.test',
            'password': 'WrongPassword123!',
        }
        res = self.url_open('/api/v1/auth/login', data=json.dumps(payload), headers={'Content-Type': 'application/json'})
        self.assertEqual(res.status_code, 401)
        data = json.loads(res.text)
        self.assertEqual(data.get('status'), 'error')

    def test_12_api_auth_login_success(self):
        """Login attempt with valid credentials returns 200, sets session, and returns user identity."""
        payload = {
            'login': 'staff_frontend@brightloop.test',
            'password': 'StaffPass123!@#',
        }
        res = self.url_open('/api/v1/auth/login', data=json.dumps(payload), headers={'Content-Type': 'application/json'})
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.text)
        self.assertEqual(data.get('status'), 'success')
        self.assertEqual(data.get('user', {}).get('role'), 'staff')

        # Check me endpoint is now authenticated
        res_me = self.url_open('/api/v1/auth/me')
        self.assertEqual(res_me.status_code, 200)
        me_data = json.loads(res_me.text)
        self.assertTrue(me_data.get('authenticated'))
        self.assertEqual(me_data.get('user', {}).get('email'), 'staff_frontend@brightloop.test')

    def test_13_api_auth_logout(self):
        """Logout endpoint terminates session."""
        res = self.url_open('/api/v1/auth/logout')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.text)
        self.assertEqual(data.get('status'), 'success')

        # Session should now be anonymous
        res_me = self.url_open('/api/v1/auth/me')
        me_data = json.loads(res_me.text)
        self.assertFalse(me_data.get('authenticated'))

    def test_14_api_auth_reset_password_endpoint(self):
        """Password reset request endpoint returns success without user enumeration leakage."""
        payload = {'email': 'staff_frontend@brightloop.test'}
        res = self.url_open('/api/v1/auth/reset-password', data=json.dumps(payload), headers={'Content-Type': 'application/json'})
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.text)
        self.assertEqual(data.get('status'), 'success')

    # =========================================================================
    # 5. APP REST API FOR STAFF & ADMIN
    # =========================================================================

    def test_15_api_app_subscriptions_unauthorized_rejection(self):
        """Anonymous access to /api/v1/app/subscriptions is rejected with 403."""
        # Ensure logged out
        self.url_open('/api/v1/auth/logout')
        res = self.url_open('/api/v1/app/subscriptions')
        self.assertEqual(res.status_code, 403)

    def test_16_api_app_authenticated_staff_data(self):
        """Staff user can retrieve subscriptions, catalog, quotations, invoices, and payments."""
        # Login as staff
        login_res = self.url_open('/api/v1/auth/login', data=json.dumps({
            'login': 'staff_frontend@brightloop.test',
            'password': 'StaffPass123!@#',
        }), headers={'Content-Type': 'application/json'})
        self.assertEqual(login_res.status_code, 200)

        # 1. Subscriptions list
        subs_res = self.url_open('/api/v1/app/subscriptions')
        self.assertEqual(subs_res.status_code, 200)
        subs_data = json.loads(subs_res.text)
        self.assertEqual(subs_data.get('status'), 'success')
        self.assertGreaterEqual(subs_data.get('data', {}).get('total', 0), 1)

        # 2. Catalog
        cat_res = self.url_open('/api/v1/app/catalog')
        self.assertEqual(cat_res.status_code, 200)
        cat_data = json.loads(cat_res.text)
        self.assertEqual(cat_data.get('status'), 'success')
        self.assertIn('plans', cat_data.get('data', {}))

        # 3. Quotations
        quot_res = self.url_open('/api/v1/app/quotations')
        self.assertEqual(quot_res.status_code, 200)

        # 4. Invoices
        inv_res = self.url_open('/api/v1/app/invoices')
        self.assertEqual(inv_res.status_code, 200)

        # 5. Payments
        pay_res = self.url_open('/api/v1/app/payments')
        self.assertEqual(pay_res.status_code, 200)

    def test_17_api_app_subscription_lifecycle_actions(self):
        """Staff user can execute lifecycle operations (pause, resume) via /api/v1/app/subscriptions/<id>/action."""
        # Login as staff
        self.url_open('/api/v1/auth/login', data=json.dumps({
            'login': 'staff_frontend@brightloop.test',
            'password': 'StaffPass123!@#',
        }), headers={'Content-Type': 'application/json'})

        # Pause subscription
        pause_res = self.url_open(f'/api/v1/app/subscriptions/{self.test_subscription.id}/action', data=json.dumps({
            'action': 'pause',
            'reason': 'Staff maintenance test',
        }), headers={'Content-Type': 'application/json'})
        self.assertEqual(pause_res.status_code, 200)
        pause_data = json.loads(pause_res.text)
        self.assertEqual(pause_data.get('status'), 'success')
        self.assertEqual(pause_data.get('data', {}).get('state'), 'paused')

        # Resume subscription
        resume_res = self.url_open(f'/api/v1/app/subscriptions/{self.test_subscription.id}/action', data=json.dumps({
            'action': 'resume',
        }), headers={'Content-Type': 'application/json'})
        self.assertEqual(resume_res.status_code, 200)
        resume_data = json.loads(resume_res.text)
        self.assertEqual(resume_data.get('status'), 'success')
        self.assertEqual(resume_data.get('data', {}).get('state'), 'active')

    # =========================================================================
    # 6. STATIC ASSET SERVING
    # =========================================================================

    def test_18_theme_css_serves_design_tokens(self):
        """Theme stylesheet /brightloop_core/static/src/css/brightloop_theme.css serves CSS tokens."""
        res = self.url_open('/brightloop_core/static/src/css/brightloop_theme.css')
        self.assertEqual(res.status_code, 200)
        content = res.text
        self.assertIn('--forest-950', content)
        self.assertIn('--cream-50', content)
        self.assertIn('--champagne', content)

    def test_19_javascript_assets_serve_successfully(self):
        """Landing and App JavaScript bundles serve with 200 OK."""
        res_landing = self.url_open('/brightloop_core/static/src/js/brightloop_landing.js')
        self.assertEqual(res_landing.status_code, 200)
        self.assertIn('ambient-canvas', res_landing.text)

        res_app = self.url_open('/brightloop_core/static/src/js/brightloop_app.js')
        self.assertEqual(res_app.status_code, 200)
        self.assertIn('BrightloopApp', res_app.text)

    def test_20_capability_card_illustrations_render(self):
        """Landing page includes all 4 capability card SVG illustrations with 200 OK."""
        res_landing = self.url_open('/')
        self.assertEqual(res_landing.status_code, 200)
        content = res_landing.text

        # Verify all 4 illustrations are referenced in HTML
        svg_assets = [
            'plan_engine.svg',
            'payment_reconciliation.svg',
            'financial_analytics.svg',
            'customer_portal.svg',
        ]
        for asset in svg_assets:
            self.assertIn(asset, content)
            res_svg = self.url_open(f'/brightloop_core/static/src/img/{asset}')
            self.assertEqual(res_svg.status_code, 200)
            self.assertIn('<svg', res_svg.text)
