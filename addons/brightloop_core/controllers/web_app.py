# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.controllers.web_app
#
# Brightloop Web Application & Public Experience Controller
#
# PHASE 12 SCOPE
# --------------
# - / and /brightloop: Public Marketing Experience with Palomar Hero Video,
#   Prisma feature cards, ThreeUI living green canvas, and Driftbar footer.
# - /auth/login: Modern login experience with session authentication.
# - /auth/register: Customer registration with real-time password policy validation.
# - /auth/reset-password: Password recovery request.
# - /app: Production SaaS Management Application Shell for Admin & Staff.
# - /app/portal: Customer Self-Service Portal Shell.
# =============================================================================

import html
from odoo import http
from odoo.http import request


class BrightloopWebAppController(http.Controller):
    """
    HTTP Controller serving Brightloop Public and Authenticated Web Interfaces.
    """

    # =========================================================================
    # 1. PUBLIC MARKETING WEBSITE
    # =========================================================================

    @http.route(['/', '/brightloop'], type='http', auth='public', methods=['GET'], csrf=False)
    def landing_page(self, **kw):
        """Serve the world-class Brightloop SaaS marketing landing page."""
        html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brightloop — Subscription Intelligence & Recurring Revenue Architecture</title>
    <link rel="stylesheet" href="/brightloop_core/static/src/css/brightloop_theme.css">
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='45' fill='%23C6A66B'/><path d='M30 50 Q50 25 70 50 Q50 75 30 50' stroke='%2311120F' stroke-width='8' fill='none'/></svg>">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
</head>
<body class="landing-body">
    <!-- 3D Geometric Brand Intro Screen Overlay -->
    <div class="brand-intro-overlay" id="brand-intro-overlay">
        <canvas id="brand-intro-canvas"></canvas>
        <div class="intro-brand-container">
            <h1 class="intro-wordmark" id="intro-wordmark">BRIGHTLOOP</h1>
            <p class="intro-subtext" id="intro-subtext">Subscription Intelligence Architecture</p>
        </div>
        <button type="button" class="skip-intro-btn" id="skip-intro-btn">Skip Intro &rarr;</button>
    </div>

    <!-- Living Green Ambient Particle Canvas -->
    <canvas id="ambient-canvas"></canvas>

    <!-- Glassmorphic Global Header -->
    <header class="landing-header" id="navbar">
        <div class="nav-container">
            <a href="/" class="brand-logo">
                <span class="brand-icon"></span>
                <span class="brand-name">Brightloop</span>
            </a>
            <nav class="nav-menu">
                <a href="#features" class="nav-link">Platform</a>
                <a href="#architecture" class="nav-link">Architecture</a>
                <a href="#showcase" class="nav-link">Intelligence</a>
                <a href="#portal" class="nav-link">Self-Service</a>
            </nav>
            <div class="nav-actions">
                <a href="/auth/login" class="btn btn-ghost btn-sm">Sign In</a>
                <a href="/app" class="btn btn-primary btn-sm">Launch Console</a>
            </div>
        </div>
    </header>

    <!-- Hero Section with Palomar Video -->
    <main>
        <section class="hero-section">
            <div class="hero-bg-video-container">
                <video id="hero-video" class="hero-video" autoplay loop muted playsinline poster="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20261014_121838_c97d0940-f430-4304-8573-4f47ee44f447.png">
                    <source src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260820_010308_b1636845-4c15-4ab6-b0c9-9a29bfb0c6e3.mp4" type="video/mp4">
                </video>
                <div class="hero-overlay"></div>
            </div>

            <div class="hero-content">
                <div class="hero-badge">
                    <span class="pulse-dot"></span> Brightloop Enterprise v2026.1
                </div>
                <h1 class="hero-title">
                    Intelligence Behind Every<br>
                    <span class="editorial-gold">Recurring Revenue.</span>
                </h1>
                <p class="hero-subtitle">
                    Unify subscriptions, recurring billing, payment reconciliation and financial intelligence in one powerful platform.
                </p>
                <div class="hero-cta-group">
                    <a href="/app" class="btn btn-primary btn-lg">Launch Platform Console</a>
                    <a href="/auth/register" class="btn btn-secondary btn-lg">Create Customer Account</a>
                </div>
            </div>
        </section>

        <!-- Prisma Feature Cards Section -->
        <section class="section" id="features">
            <div class="section-header text-center">
                <span class="badge badge-outline mb-2">Core Capabilities</span>
                <h2 class="section-title">Built for Complex Subscription Realities</h2>
                <p class="section-subtitle">Every module integrates directly into double-entry accounting ledgers without fragile glue code.</p>
            </div>

            <div class="features-grid">
                <div class="card feature-card">
                    <div class="feature-card-media">
                        <img src="/brightloop_core/static/src/img/plan_engine.svg" alt="Multi-Frequency Plan Engine" class="feature-illustration" loading="lazy">
                    </div>
                    <div class="feature-card-body">
                        <div class="feature-tag">Lifecycle Architecture</div>
                        <h3 class="feature-title">Multi-Frequency Plan Engine</h3>
                        <p class="feature-desc">Native support for Daily, Weekly, Monthly, Quarterly, and Annual billing intervals with strict calendar normalization and leap-year compliance.</p>
                    </div>
                </div>
                <div class="card feature-card">
                    <div class="feature-card-media">
                        <img src="/brightloop_core/static/src/img/payment_reconciliation.svg" alt="Zero-Loss Payment Reconciliation" class="feature-illustration" loading="lazy">
                    </div>
                    <div class="feature-card-body">
                        <div class="feature-tag">Orchestration &amp; Journals</div>
                        <h3 class="feature-title">Zero-Loss Payment Reconciliation</h3>
                        <p class="feature-desc">Automated partial settlements, multi-invoice allocations, and idempotent payment orchestration directly into bank journals.</p>
                    </div>
                </div>
                <div class="card feature-card">
                    <div class="feature-card-media">
                        <img src="/brightloop_core/static/src/img/financial_analytics.svg" alt="Financial Analytics &amp; MRR" class="feature-illustration" loading="lazy">
                    </div>
                    <div class="feature-card-body">
                        <div class="feature-tag">Intelligence &amp; Cohorts</div>
                        <h3 class="feature-title">Financial Analytics &amp; MRR</h3>
                        <p class="feature-desc">Live MRR, ARR, AR aging buckets, and cohort revenue trends powered by strict database aggregation without external analytics SaaS.</p>
                    </div>
                </div>
                <div class="card feature-card">
                    <div class="feature-card-media">
                        <img src="/brightloop_core/static/src/img/customer_portal.svg" alt="Customer Self-Service Portal" class="feature-illustration" loading="lazy">
                    </div>
                    <div class="feature-card-body">
                        <div class="feature-tag">Customer Experience</div>
                        <h3 class="feature-title">Customer Self-Service Portal</h3>
                        <p class="feature-desc">Multi-tenant customer portal isolated strictly to commercial partner entities with real-time lifecycle actions and PDF receipt downloads.</p>
                    </div>
                </div>
            </div>
        </section>

        <!-- Interactive Architecture Showcase -->
        <section class="section bg-surface" id="architecture">
            <div class="section-header text-center">
                <span class="badge badge-outline mb-2">Technical Foundations</span>
                <h2 class="section-title">Production Odoo 20 Architecture</h2>
                <p class="section-subtitle">Enterprise-grade security, autonomous audit logging, and high-performance SQL indexing.</p>
            </div>

            <div class="showcase-tabs">
                <div class="tabs-header">
                    <button class="tab-trigger active" data-tab-target="showcase-lifecycle">Lifecycle State Machine</button>
                    <button class="tab-trigger" data-tab-target="showcase-billing">Recurring Billing Engine</button>
                    <button class="tab-trigger" data-tab-target="showcase-security">Security & Audit Isolation</button>
                </div>

                <div class="tab-content-panel active" id="showcase-lifecycle">
                    <div class="card p-6">
                        <h4>Strict State Transitions: Draft &rarr; Confirmed &rarr; Active &harr; Paused &rarr; Closed</h4>
                        <p class="text-muted mt-2">Explicit pause and early-closure policies configured per subscription plan prevent unexpected churn while keeping financial forecasting accurate.</p>
                    </div>
                </div>

                <div class="tab-content-panel" id="showcase-billing">
                    <div class="card p-6">
                        <h4>Automated Period Invoicing & Idempotent Generation</h4>
                        <p class="text-muted mt-2">Scheduled cron jobs calculate exact period start and end dates, generate balanced account moves, and advance next billing timestamps atomically.</p>
                    </div>
                </div>

                <div class="tab-content-panel" id="showcase-security">
                    <div class="card p-6">
                        <h4>Multi-Company & Partner Scoped Security Rules</h4>
                        <p class="text-muted mt-2">Row-level security enforcement through Odoo ir.rule, autonomous transaction-safe audit logging, and OWASP-compliant API authentication.</p>
                    </div>
                </div>
            </div>
        </section>

        <!-- Driftbar Atmospheric Footer -->
        <footer class="driftbar-footer">
            <div class="driftbar-video-container">
                <video id="footer-video" class="driftbar-video" autoplay loop muted playsinline poster="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20261014_121838_c97d0940-f430-4304-8573-4f47ee44f447.png">
                    <source src="https://d2ol7oe51mr4n9.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/4d01c727-d9c5-47c8-a778-35a451ffd39f.mp4" type="video/mp4">
                </video>
                <div class="driftbar-overlay"></div>
            </div>

            <div class="driftbar-content">
                <div class="footer-cta text-center">
                    <h2 class="cta-title">Ready for Intelligent Subscriptions?</h2>
                    <p class="cta-subtitle">Deploy Brightloop on Odoo 20 and unify your recurring revenue operations today.</p>
                    <div class="mt-6">
                        <a href="/app" class="btn btn-primary btn-lg">Open Management Console</a>
                        <a href="/auth/register" class="btn btn-secondary btn-lg">Customer Sign Up</a>
                    </div>
                </div>

                <div class="oversized-footer-wordmark">BRIGHTLOOP</div>

                <div class="footer-bottom">
                    <div class="brand-logo">
                        <span class="brand-icon"></span>
                        <span class="brand-name">Brightloop</span>
                    </div>
                    <p class="copyright text-xs text-muted">&copy; 2026 Brightloop Subscription Intelligence. Built on Odoo 20 Community Edition.</p>
                </div>
            </div>
        </footer>
    </main>

    <script src="/brightloop_core/static/src/js/brightloop_landing.js"></script>
</body>
</html>
"""
        return request.make_response(html_content, headers=[('Content-Type', 'text/html; charset=utf-8')])

    # =========================================================================
    # 2. AUTHENTICATION SCREENS (LOGIN, REGISTER, RESET)
    # =========================================================================

    @http.route('/auth/login', type='http', auth='public', methods=['GET'], csrf=False)
    def auth_login(self, **kw):
        """Serve the modern Brightloop Login page."""
        redirect_url = kw.get('redirect', '/app')
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign In — Brightloop</title>
    <link rel="stylesheet" href="/brightloop_core/static/src/css/brightloop_theme.css">
</head>
<body class="auth-body">
    <div class="auth-card card">
        <div class="auth-header text-center">
            <a href="/" class="brand-logo inline-flex mb-4">
                <span class="brand-icon"></span>
                <span class="brand-name">Brightloop</span>
            </a>
            <h2 class="card-title">Welcome Back</h2>
            <p class="card-subtitle">Sign in to your subscription intelligence console</p>
        </div>

        <div id="auth-alert" class="alert alert-danger hidden mb-4"></div>

        <form id="login-form">
            <input type="hidden" id="redirect-url" value="{redirect_url}">
            <div class="form-group mb-4">
                <label class="form-label" for="login-email">Email or Username</label>
                <input type="text" id="login-email" class="form-control" placeholder="admin@example.com" required autocomplete="username">
            </div>

            <div class="form-group mb-4">
                <div class="flex-between">
                    <label class="form-label" for="login-password">Password</label>
                    <a href="/auth/reset-password" class="text-xs text-brand">Forgot Password?</a>
                </div>
                <input type="password" id="login-password" class="form-control" placeholder="••••••••" required autocomplete="current-password">
            </div>

            <button type="submit" id="login-submit-btn" class="btn btn-primary btn-block">Sign In</button>
        </form>

        <div class="auth-footer text-center mt-6">
            <span class="text-sm text-muted">Don't have an account?</span>
            <a href="/auth/register" class="text-sm text-brand font-medium">Create Customer Account</a>
        </div>
    </div>

    <script>
        document.getElementById('login-form').addEventListener('submit', async (e) => {{
            e.preventDefault();
            const alertBox = document.getElementById('auth-alert');
            const submitBtn = document.getElementById('login-submit-btn');
            const login = document.getElementById('login-email').value.trim();
            const password = document.getElementById('login-password').value;
            const redirectUrl = document.getElementById('redirect-url').value || '/app';

            alertBox.classList.add('hidden');
            submitBtn.disabled = true;
            submitBtn.textContent = 'Authenticating...';

            try {{
                const res = await fetch('/api/v1/auth/login', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    credentials: 'same-origin',
                    body: JSON.stringify({{ login, password }}),
                }});
                const data = await res.json();

                if (data.status === 'success') {{
                    const target = data.user && data.user.role === 'customer' ? '/app/portal' : redirectUrl;
                    window.location.href = target;
                }} else {{
                    alertBox.textContent = data.message || 'Invalid email or password.';
                    alertBox.classList.remove('hidden');
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Sign In';
                }}
            }} catch (err) {{
                alertBox.textContent = 'A network error occurred. Please try again.';
                alertBox.classList.remove('hidden');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Sign In';
            }}
        }});
    </script>
</body>
</html>
"""
        return request.make_response(html_content, headers=[('Content-Type', 'text/html; charset=utf-8')])

    @http.route('/auth/register', type='http', auth='public', methods=['GET'], csrf=False)
    def auth_register(self, **kw):
        """Serve the customer registration page with real-time password policy validation."""
        html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Customer Registration — Brightloop</title>
    <link rel="stylesheet" href="/brightloop_core/static/src/css/brightloop_theme.css">
</head>
<body class="auth-body">
    <div class="auth-card card">
        <div class="auth-header text-center">
            <a href="/" class="brand-logo inline-flex mb-4">
                <span class="brand-icon"></span>
                <span class="brand-name">Brightloop</span>
            </a>
            <h2 class="card-title">Create Customer Account</h2>
            <p class="card-subtitle">Access your self-service subscription & billing portal</p>
        </div>

        <div id="register-alert" class="alert alert-danger hidden mb-4"></div>
        <div id="register-success" class="alert alert-success hidden mb-4"></div>

        <form id="register-form">
            <div class="form-group mb-4">
                <label class="form-label" for="reg-name">Full Name / Company</label>
                <input type="text" id="reg-name" class="form-control" placeholder="Acme Corporation" required>
            </div>

            <div class="form-group mb-4">
                <label class="form-label" for="reg-email">Email Address</label>
                <input type="email" id="reg-email" class="form-control" placeholder="billing@acme.com" required>
            </div>

            <div class="form-group mb-4">
                <label class="form-label" for="reg-password">Password</label>
                <input type="password" id="reg-password" class="form-control" placeholder="••••••••••••" required>
                <!-- Real-Time Password Policy Checklist -->
                <div class="password-policy-checklist mt-2">
                    <div id="rule-len" class="policy-rule"><span class="policy-bullet">✗</span> At least 8 characters</div>
                    <div id="rule-upper" class="policy-rule"><span class="policy-bullet">✗</span> At least 1 uppercase letter</div>
                    <div id="rule-lower" class="policy-rule"><span class="policy-bullet">✗</span> At least 1 lowercase letter</div>
                    <div id="rule-special" class="policy-rule"><span class="policy-bullet">✗</span> At least 1 special character (!@#$%^&*)</div>
                </div>
            </div>

            <button type="submit" id="reg-submit-btn" class="btn btn-primary btn-block">Complete Registration</button>
        </form>

        <div class="auth-footer text-center mt-6">
            <span class="text-sm text-muted">Already registered?</span>
            <a href="/auth/login" class="text-sm text-brand font-medium">Sign In</a>
        </div>
    </div>

    <script>
        const pwdInput = document.getElementById('reg-password');
        const ruleLen = document.getElementById('rule-len');
        const ruleUpper = document.getElementById('rule-upper');
        const ruleLower = document.getElementById('rule-lower');
        const ruleSpecial = document.getElementById('rule-special');

        pwdInput.addEventListener('input', () => {
            const val = pwdInput.value;
            validateRule(ruleLen, val.length >= 8);
            validateRule(ruleUpper, /[A-Z]/.test(val));
            validateRule(ruleLower, /[a-z]/.test(val));
            validateRule(ruleSpecial, /[!@#$%^&*(),.?":{}|<>]/.test(val));
        });

        function validateRule(el, isValid) {
            if (isValid) {
                el.classList.add('valid');
                el.querySelector('.policy-bullet').textContent = '✓';
            } else {
                el.classList.remove('valid');
                el.querySelector('.policy-bullet').textContent = '✗';
            }
        }

        document.getElementById('register-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const alertBox = document.getElementById('register-alert');
            const successBox = document.getElementById('register-success');
            const submitBtn = document.getElementById('reg-submit-btn');

            const name = document.getElementById('reg-name').value.trim();
            const email = document.getElementById('reg-email').value.trim();
            const password = pwdInput.value;

            alertBox.classList.add('hidden');
            successBox.classList.add('hidden');
            submitBtn.disabled = true;
            submitBtn.textContent = 'Registering Account...';

            try {
                const res = await fetch('/api/v1/auth/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    body: JSON.stringify({ name, email, password }),
                });
                const data = await res.json();

                if (data.status === 'success') {
                    successBox.textContent = 'Registration successful! Signing you in...';
                    successBox.classList.remove('hidden');

                    // Automatically authenticate
                    await fetch('/api/v1/auth/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'same-origin',
                        body: JSON.stringify({ login: email, password }),
                    });
                    window.location.href = '/app/portal';
                } else {
                    alertBox.textContent = data.message || 'Registration failed.';
                    alertBox.classList.remove('hidden');
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Complete Registration';
                }
            } catch (err) {
                alertBox.textContent = 'Network error occurred. Please try again.';
                alertBox.classList.remove('hidden');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Complete Registration';
            }
        });
    </script>
</body>
</html>
"""
        return request.make_response(html_content, headers=[('Content-Type', 'text/html; charset=utf-8')])

    @http.route('/auth/reset-password', type='http', auth='public', methods=['GET'], csrf=False)
    def auth_reset_password(self, **kw):
        """Serve the password reset request page."""
        html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset Password — Brightloop</title>
    <link rel="stylesheet" href="/brightloop_core/static/src/css/brightloop_theme.css">
</head>
<body class="auth-body">
    <div class="auth-card card">
        <div class="auth-header text-center">
            <a href="/" class="brand-logo inline-flex mb-4">
                <span class="brand-icon"></span>
                <span class="brand-name">Brightloop</span>
            </a>
            <h2 class="card-title">Reset Password</h2>
            <p class="card-subtitle">Enter your registered email address to receive recovery instructions</p>
        </div>

        <div id="reset-alert" class="alert alert-danger hidden mb-4"></div>
        <div id="reset-success" class="alert alert-success hidden mb-4"></div>

        <form id="reset-form">
            <div class="form-group mb-4">
                <label class="form-label" for="reset-email">Email Address</label>
                <input type="email" id="reset-email" class="form-control" placeholder="user@example.com" required>
            </div>

            <button type="submit" id="reset-submit-btn" class="btn btn-primary btn-block">Send Reset Link</button>
        </form>

        <div class="auth-footer text-center mt-6">
            <a href="/auth/login" class="text-sm text-brand font-medium">&larr; Back to Sign In</a>
        </div>
    </div>

    <script>
        document.getElementById('reset-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const alertBox = document.getElementById('reset-alert');
            const successBox = document.getElementById('reset-success');
            const submitBtn = document.getElementById('reset-submit-btn');
            const email = document.getElementById('reset-email').value.trim();

            alertBox.classList.add('hidden');
            successBox.classList.add('hidden');
            submitBtn.disabled = true;
            submitBtn.textContent = 'Submitting Request...';

            try {
                const res = await fetch('/api/v1/auth/reset-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    body: JSON.stringify({ email }),
                });
                const data = await res.json();

                successBox.textContent = data.message || 'If an account exists, reset instructions have been dispatched.';
                successBox.classList.remove('hidden');
                document.getElementById('reset-email').value = '';
                submitBtn.disabled = false;
                submitBtn.textContent = 'Send Reset Link';
            } catch (err) {
                alertBox.textContent = 'Request failed. Please try again.';
                alertBox.classList.remove('hidden');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Send Reset Link';
            }
        });
    </script>
</body>
</html>
"""
        return request.make_response(html_content, headers=[('Content-Type', 'text/html; charset=utf-8')])

    # =========================================================================
    # 3. AUTHENTICATED APPLICATION SHELLS (/app and /app/portal)
    # =========================================================================

    @http.route(['/app', '/app/portal'], type='http', auth='public', methods=['GET'], csrf=False)
    def app_shell(self, **kw):
        """
        Serve the unified authenticated SaaS application & customer portal.
        Renders role-specific navigation and active tabs directly on the server
        to completely eliminate client-side layout flashing, delayed hiding,
        and unauthorized navigation flickering on page refresh.
        """
        user = request.env.user
        is_authenticated = bool(
            user and not user._is_public() and user.id != request.env.ref('base.public_user', raise_if_not_found=False).id
        )

        role = 'anonymous'
        if is_authenticated:
            if user._is_admin() or user.has_group('brightloop_core.group_brightloop_admin') or user.has_group('base.group_system'):
                role = 'admin'
            elif user.has_group('brightloop_core.group_brightloop_staff') or user.has_group('account.group_account_invoice'):
                role = 'staff'
            else:
                role = 'customer'

        path = request.httprequest.path
        is_portal_mode = (path == '/app/portal') or (role == 'customer')

        if is_portal_mode:
            body_classes = "app-body portal-view role-customer"
        elif is_authenticated:
            body_classes = f"app-body role-{role}"
        else:
            body_classes = "app-body role-anonymous"

        if is_authenticated:
            user_name = html.escape(user.name or 'User')
            user_initial = html.escape((user.name or 'U')[:1].upper())
            user_role = role.upper()
            role_badge_class = f"role-badge role-{role}"
        else:
            user_name = "Authenticating..."
            user_initial = "..."
            user_role = "SESSION"
            role_badge_class = "role-badge"

        # Server-render role-specific navigation to prevent flash of unauthorized tabs
        if role == 'customer':
            sidebar_nav_html = """
                <div class="nav-section-title customer-only">Self-Service</div>
                <button class="nav-item customer-only active" data-nav-tab="portal">
                    <span class="nav-icon">👤</span> My Subscriptions &amp; Billing
                </button>
            """
        elif role in ('admin', 'staff'):
            if is_portal_mode:
                sidebar_nav_html = """
                    <div class="nav-section-title staff-only">Finance &amp; Operations</div>
                    <button class="nav-item staff-only" data-nav-tab="overview">
                        <span class="nav-icon">📊</span> Overview
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="subscriptions">
                        <span class="nav-icon">🔄</span> Subscriptions
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="catalog">
                        <span class="nav-icon">📦</span> Products &amp; Plans
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="quotations">
                        <span class="nav-icon">📝</span> Quotations &amp; Sales
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="invoices">
                        <span class="nav-icon">🧾</span> Invoices &amp; Billing
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="payments">
                        <span class="nav-icon">💳</span> Payments &amp; Cashflow
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="analytics">
                        <span class="nav-icon">📈</span> Finance Analytics
                    </button>
                    <div class="nav-section-title customer-only">Self-Service</div>
                    <button class="nav-item customer-only active" data-nav-tab="portal">
                        <span class="nav-icon">👤</span> My Subscriptions &amp; Billing
                    </button>
                """
            else:
                sidebar_nav_html = """
                    <div class="nav-section-title staff-only">Finance &amp; Operations</div>
                    <button class="nav-item staff-only active" data-nav-tab="overview">
                        <span class="nav-icon">📊</span> Overview
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="subscriptions">
                        <span class="nav-icon">🔄</span> Subscriptions
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="catalog">
                        <span class="nav-icon">📦</span> Products &amp; Plans
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="quotations">
                        <span class="nav-icon">📝</span> Quotations &amp; Sales
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="invoices">
                        <span class="nav-icon">🧾</span> Invoices &amp; Billing
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="payments">
                        <span class="nav-icon">💳</span> Payments &amp; Cashflow
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="analytics">
                        <span class="nav-icon">📈</span> Finance Analytics
                    </button>
                    <div class="nav-section-title staff-only">Self-Service</div>
                    <button class="nav-item staff-only" data-nav-tab="portal">
                        <span class="nav-icon">👤</span> Customer Portal View
                    </button>
                """
        else:
            # Anonymous caller before JS session bootstrap / redirect
            if is_portal_mode:
                sidebar_nav_html = """
                    <div class="nav-section-title customer-only">Self-Service</div>
                    <button class="nav-item customer-only active" data-nav-tab="portal">
                        <span class="nav-icon">👤</span> My Subscriptions &amp; Billing
                    </button>
                """
            else:
                sidebar_nav_html = """
                    <div class="nav-section-title staff-only">Finance &amp; Operations</div>
                    <button class="nav-item staff-only active" data-nav-tab="overview">
                        <span class="nav-icon">📊</span> Overview
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="subscriptions">
                        <span class="nav-icon">🔄</span> Subscriptions
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="catalog">
                        <span class="nav-icon">📦</span> Products &amp; Plans
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="quotations">
                        <span class="nav-icon">📝</span> Quotations &amp; Sales
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="invoices">
                        <span class="nav-icon">🧾</span> Invoices &amp; Billing
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="payments">
                        <span class="nav-icon">💳</span> Payments &amp; Cashflow
                    </button>
                    <button class="nav-item staff-only" data-nav-tab="analytics">
                        <span class="nav-icon">📈</span> Finance Analytics
                    </button>
                """

        overview_active_class = "active" if not is_portal_mode else ""
        portal_active_class = "active" if is_portal_mode else ""

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brightloop — Subscription Intelligence Console</title>
    <link rel="stylesheet" href="/brightloop_core/static/src/css/brightloop_theme.css">
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='45' fill='%23C6A66B'/><path d='M30 50 Q50 25 70 50 Q50 75 30 50' stroke='%2311120F' stroke-width='8' fill='none'/></svg>">
</head>
<body class="{body_classes}">
    <div id="brightloop-app" class="app-layout">
        <!-- Sidebar Navigation -->
        <aside class="app-sidebar" id="app-sidebar">
            <div class="sidebar-header">
                <a href="/app" class="brand-logo">
                    <span class="brand-icon"></span>
                    <span class="brand-name">Brightloop</span>
                </a>
            </div>

            <nav class="sidebar-nav">
                {sidebar_nav_html}
            </nav>

            <div class="sidebar-footer">
                <div class="user-profile-badge">
                    <div class="user-avatar" id="user-initial-display">{user_initial}</div>
                    <div class="user-info">
                        <div class="user-name" id="user-name-display">{user_name}</div>
                        <span id="user-role-badge" class="{role_badge_class}">{user_role}</span>
                    </div>
                </div>
                <button class="btn btn-outline btn-xs btn-block mt-3" id="logout-btn">Sign Out</button>
            </div>
        </aside>

        <!-- Main Content Workspace -->
        <main class="app-main">
            <!-- App Topbar -->
            <header class="app-topbar">
                <div class="topbar-left">
                    <button class="mobile-toggle" id="mobile-menu-toggle">&#9776;</button>
                    <span class="badge badge-brand">Brightloop Enterprise v2026.1</span>
                </div>
                <div class="topbar-right">
                    <button class="btn btn-secondary btn-sm" id="refresh-btn">⟳ Refresh</button>
                </div>
            </header>

            <!-- Workspace Panes -->
            <div class="app-workspace">
                <div id="tab-overview" class="tab-pane {overview_active_class} staff-only"></div>
                <div id="tab-subscriptions" class="tab-pane staff-only"></div>
                <div id="tab-catalog" class="tab-pane staff-only"></div>
                <div id="tab-quotations" class="tab-pane staff-only"></div>
                <div id="tab-invoices" class="tab-pane staff-only"></div>
                <div id="tab-payments" class="tab-pane staff-only"></div>
                <div id="tab-analytics" class="tab-pane staff-only"></div>
                <div id="tab-portal" class="tab-pane {portal_active_class}"></div>
            </div>
        </main>
    </div>

    <!-- Global Modal Dialog Overlay -->
    <div id="modal-overlay" class="modal-overlay hidden">
        <div class="modal-dialog card">
            <div class="modal-header">
                <h3 id="modal-title" class="modal-title">Confirm Action</h3>
            </div>
            <div id="modal-body" class="modal-body"></div>
            <div class="modal-footer">
                <button id="modal-cancel-btn" class="btn btn-secondary btn-sm">Cancel</button>
                <button id="modal-confirm-btn" class="btn btn-primary btn-sm">Confirm</button>
            </div>
        </div>
    </div>

    <!-- Global Toast Notification Container -->
    <div id="toast-container" class="toast-container"></div>

    <!-- Global Loading Spinner -->
    <div id="global-loading-spinner" class="global-loading-spinner" style="display: none;">
        <div class="spinner"></div>
    </div>

    <script src="/brightloop_core/static/src/js/brightloop_app.js"></script>
</body>
</html>
"""
        return request.make_response(html_content, headers=[('Content-Type', 'text/html; charset=utf-8')])

