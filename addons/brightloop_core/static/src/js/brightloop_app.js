/**
 * ============================================================================
 * Brightloop Subscription Intelligence — Production Application Client
 * Phase 12: Premium Frontend, Complete Product Experience & Visual System
 * ============================================================================
 * Handles:
 * - Session bootstrap & role-based routing (Admin, Staff, Customer Portal)
 * - Data fetching for Overview, Subscriptions, Catalog, Invoices, Payments, Analytics
 * - Real-time SVG chart rendering (Revenue Area Trend, Aging Bar, Status Donut)
 * - Subscription lifecycle action modals (Pause, Resume, Renew, Close)
 * - Customer self-service profile management and PDF invoice downloads
 * - Honest empty states, loading indicators, toast notifications
 */

(function () {
    'use strict';

    // State management
    const state = {
        user: null,
        currentTab: 'overview',
        overviewData: null,
        subscriptions: [],
        catalog: null,
        quotations: [],
        invoices: [],
        payments: [],
        analytics: null,
        portal: null,
        loading: false,
    };

    // DOM Elements Cache
    let elements = {};

    function init() {
        cacheElements();
        bindEvents();
        bootstrapSession();
    }

    function cacheElements() {
        elements = {
            appShell: document.getElementById('brightloop-app'),
            userName: document.getElementById('user-name-display'),
            userRole: document.getElementById('user-role-badge'),
            userInitial: document.getElementById('user-initial-display'),
            navLinks: document.querySelectorAll('[data-nav-tab]'),
            tabPanes: document.querySelectorAll('.tab-pane'),
            logoutBtn: document.getElementById('logout-btn'),
            refreshBtn: document.getElementById('refresh-btn'),
            toastContainer: document.getElementById('toast-container'),
            modalOverlay: document.getElementById('modal-overlay'),
            modalTitle: document.getElementById('modal-title'),
            modalBody: document.getElementById('modal-body'),
            modalConfirmBtn: document.getElementById('modal-confirm-btn'),
            modalCancelBtn: document.getElementById('modal-cancel-btn'),
            mobileMenuToggle: document.getElementById('mobile-menu-toggle'),
            sidebar: document.getElementById('app-sidebar'),
        };
    }

    function bindEvents() {
        // Tab switching
        document.addEventListener('click', (e) => {
            const tabBtn = e.target.closest('[data-nav-tab]');
            if (tabBtn) {
                e.preventDefault();
                const targetTab = tabBtn.getAttribute('data-nav-tab');
                switchTab(targetTab);
                if (elements.sidebar && elements.sidebar.classList.contains('mobile-open')) {
                    elements.sidebar.classList.remove('mobile-open');
                }
            }
        });

        // Hash change navigation
        window.addEventListener('hashchange', () => {
            const hash = window.location.hash.replace('#', '');
            if (hash && hash !== state.currentTab) {
                switchTab(hash);
            }
        });

        // Logout
        if (elements.logoutBtn) {
            elements.logoutBtn.addEventListener('click', handleLogout);
        }

        // Refresh
        if (elements.refreshBtn) {
            elements.refreshBtn.addEventListener('click', () => {
                loadCurrentTabData(true);
            });
        }

        // Mobile sidebar toggle
        if (elements.mobileMenuToggle && elements.sidebar) {
            elements.mobileMenuToggle.addEventListener('click', () => {
                elements.sidebar.classList.toggle('mobile-open');
            });
        }

        // Modal backdrop close
        if (elements.modalOverlay) {
            elements.modalOverlay.addEventListener('click', (e) => {
                if (e.target === elements.modalOverlay) {
                    closeModal();
                }
            });
        }

        if (elements.modalCancelBtn) {
            elements.modalCancelBtn.addEventListener('click', closeModal);
        }
    }

    // =========================================================================
    // SESSION BOOTSTRAP
    // =========================================================================

    async function bootstrapSession() {
        try {
            showLoading(true);
            const res = await fetch('/api/v1/auth/me', { credentials: 'same-origin' });
            const data = await res.json();

            if (!data.authenticated || !data.user) {
                window.location.href = '/auth/login?redirect=' + encodeURIComponent(window.location.pathname + window.location.hash);
                return;
            }

            state.user = data.user;
            renderUserIdentity();

            // Set initial tab based on role and URL hash
            const isPortalMode = window.location.pathname.includes('/portal') || state.user.role === 'customer';
            const hash = window.location.hash.replace('#', '');

            if (state.user.role === 'customer' || isPortalMode) {
                // Customer Portal mode
                document.body.classList.add('portal-view');
                // Hide staff-only tabs
                document.querySelectorAll('.staff-only').forEach(el => el.style.display = 'none');
                switchTab('portal');
            } else {
                // Admin / Staff mode
                document.querySelectorAll('.customer-only').forEach(el => el.style.display = 'none');
                const initialTab = ['overview', 'subscriptions', 'catalog', 'quotations', 'invoices', 'payments', 'analytics'].includes(hash) ? hash : 'overview';
                switchTab(initialTab);
            }
        } catch (err) {
            console.error('Session bootstrap failed:', err);
            showToast('Session check failed. Please refresh.', 'error');
        } finally {
            showLoading(false);
        }
    }

    function renderUserIdentity() {
        if (!state.user) return;
        if (elements.userName) elements.userName.textContent = state.user.name;
        if (elements.userInitial) elements.userInitial.textContent = (state.user.name || 'U').charAt(0).toUpperCase();
        if (elements.userRole) {
            elements.userRole.textContent = state.user.role.toUpperCase();
            elements.userRole.className = `role-badge role-${state.user.role}`;
        }
    }

    // =========================================================================
    // TAB ROUTING & LOADING
    // =========================================================================

    function switchTab(tabId) {
        state.currentTab = tabId;
        window.location.hash = tabId;

        // Update active nav styling
        document.querySelectorAll('[data-nav-tab]').forEach(btn => {
            if (btn.getAttribute('data-nav-tab') === tabId) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        // Show matching pane
        document.querySelectorAll('.tab-pane').forEach(pane => {
            if (pane.id === `tab-${tabId}`) {
                pane.classList.add('active');
            } else {
                pane.classList.remove('active');
            }
        });

        loadCurrentTabData();
    }

    function loadCurrentTabData(force = false) {
        switch (state.currentTab) {
            case 'overview':
                loadOverviewData(force);
                break;
            case 'subscriptions':
                loadSubscriptionsData(force);
                break;
            case 'catalog':
                loadCatalogData(force);
                break;
            case 'quotations':
                loadQuotationsData(force);
                break;
            case 'invoices':
                loadInvoicesData(force);
                break;
            case 'payments':
                loadPaymentsData(force);
                break;
            case 'analytics':
                loadAnalyticsData(force);
                break;
            case 'portal':
                loadPortalData(force);
                break;
        }
    }

    // =========================================================================
    // 1. OVERVIEW TAB
    // =========================================================================

    async function loadOverviewData(force = false) {
        const container = document.getElementById('tab-overview');
        if (!container) return;

        try {
            renderOverviewSkeleton();

            // Parallel fetch of real KPIs, MRR, Subscriptions breakdown, and Invoices
            const [kpisRes, revenueRes, subsRes, invoicesRes] = await Promise.all([
                fetch('/api/v1/analytics/kpis', { credentials: 'same-origin' }).then(r => r.json()),
                fetch('/api/v1/analytics/revenue?months=6', { credentials: 'same-origin' }).then(r => r.json()),
                fetch('/api/v1/analytics/subscriptions', { credentials: 'same-origin' }).then(r => r.json()),
                fetch('/api/v1/app/invoices?limit=5', { credentials: 'same-origin' }).then(r => r.json()),
            ]);

            state.overviewData = {
                kpis: kpisRes.data || {},
                revenue: revenueRes.data || {},
                subscriptions: subsRes.data || {},
                invoices: (invoicesRes.data && invoicesRes.data.invoices) || [],
            };

            renderOverview(state.overviewData);
        } catch (err) {
            console.error('Failed to load overview data:', err);
            container.innerHTML = renderErrorState('Failed to load live overview metrics.', () => loadOverviewData(true));
        }
    }

    function renderOverview(data) {
        const container = document.getElementById('tab-overview');
        if (!container) return;

        const kpis = data.kpis || {};
        const currencySymbol = kpis.currency_symbol || '$';
        const mrr = formatMoney(kpis.mrr || 0, currencySymbol);
        const arr = formatMoney(kpis.arr || 0, currencySymbol);
        const revenue = formatMoney(kpis.total_revenue || 0, currencySymbol);
        const activeSubs = kpis.active_subscriptions || 0;
        const totalSubs = kpis.total_subscriptions || 0;
        const collectionRate = (kpis.collection_rate !== undefined ? kpis.collection_rate : 100).toFixed(1) + '%';
        const churnRate = (kpis.churn_rate !== undefined ? kpis.churn_rate : 0).toFixed(1) + '%';

        // Monthly revenue trend points
        const monthlyTrend = (data.revenue && data.revenue.monthly_trend) || [];
        const svgChart = renderRevenueTrendChart(monthlyTrend, currencySymbol);

        // Subscriptions breakdown
        const subBreakdown = data.subscriptions.breakdown || {};
        const activeCount = subBreakdown.active || activeSubs;
        const pausedCount = subBreakdown.paused || 0;
        const closedCount = subBreakdown.closed || 0;

        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Executive Finance Overview</h1>
                    <p class="page-subtitle">Real-time subscription intelligence, recurring revenue, and cashflow analytics.</p>
                </div>
                <div class="header-actions">
                    <span class="live-pill"><span class="pulse-dot"></span> Live Odoo Accounting</span>
                </div>
            </div>

            <!-- KPI Metric Cards Grid -->
            <div class="kpi-grid">
                <div class="card kpi-card">
                    <div class="kpi-label">Monthly Recurring Revenue (MRR)</div>
                    <div class="kpi-value">${mrr}</div>
                    <div class="kpi-subtext positive">Normalized across active recurring contracts</div>
                </div>
                <div class="card kpi-card">
                    <div class="kpi-label">Annual Run Rate (ARR)</div>
                    <div class="kpi-value">${arr}</div>
                    <div class="kpi-subtext">MRR × 12 projection</div>
                </div>
                <div class="card kpi-card">
                    <div class="kpi-label">Active Subscriptions</div>
                    <div class="kpi-value">${activeSubs} <span class="kpi-denom">/ ${totalSubs}</span></div>
                    <div class="kpi-subtext">${churnRate} churn rate</div>
                </div>
                <div class="card kpi-card">
                    <div class="kpi-label">Total Invoiced Revenue</div>
                    <div class="kpi-value">${revenue}</div>
                    <div class="kpi-subtext positive">${collectionRate} collection rate</div>
                </div>
            </div>

            <!-- Analytics Visual System Grid -->
            <div class="analytics-row">
                <!-- Revenue Area Chart -->
                <div class="card chart-card">
                    <div class="card-header">
                        <div>
                            <h3 class="card-title">Recurring Revenue Growth Trend</h3>
                            <p class="card-subtitle">Historical posted revenue trajectory over trailing 6 months</p>
                        </div>
                    </div>
                    <div class="chart-container">
                        ${svgChart}
                    </div>
                </div>

                <!-- Subscriptions Breakdown -->
                <div class="card breakdown-card">
                    <div class="card-header">
                        <div>
                            <h3 class="card-title">Portfolio State</h3>
                            <p class="card-subtitle">Active vs Paused vs Terminated</p>
                        </div>
                    </div>
                    <div class="breakdown-body">
                        <div class="breakdown-stat">
                            <div class="stat-left"><span class="status-indicator active"></span> Active Contracts</div>
                            <div class="stat-right"><strong>${activeCount}</strong></div>
                        </div>
                        <div class="progress-bar-bg"><div class="progress-bar-fill fill-active" style="width: ${totalSubs ? (activeCount/totalSubs*100) : 0}%"></div></div>

                        <div class="breakdown-stat">
                            <div class="stat-left"><span class="status-indicator paused"></span> Paused Contracts</div>
                            <div class="stat-right"><strong>${pausedCount}</strong></div>
                        </div>
                        <div class="progress-bar-bg"><div class="progress-bar-fill fill-paused" style="width: ${totalSubs ? (pausedCount/totalSubs*100) : 0}%"></div></div>

                        <div class="breakdown-stat">
                            <div class="stat-left"><span class="status-indicator closed"></span> Closed / Terminated</div>
                            <div class="stat-right"><strong>${closedCount}</strong></div>
                        </div>
                        <div class="progress-bar-bg"><div class="progress-bar-fill fill-closed" style="width: ${totalSubs ? (closedCount/totalSubs*100) : 0}%"></div></div>

                        <div class="breakdown-total">
                            <span>Total Contracts Tracked</span>
                            <span><strong>${totalSubs}</strong></span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Recent Invoices Table -->
            <div class="card mt-6">
                <div class="card-header">
                    <div>
                        <h3 class="card-title">Recent Invoices</h3>
                        <p class="card-subtitle">Latest accounts receivable billing entries</p>
                    </div>
                    <button class="btn btn-secondary btn-sm" onclick="window.BrightloopApp.switchTab('invoices')">View All Invoices</button>
                </div>
                ${renderOverviewInvoicesTable(data.invoices, currencySymbol)}
            </div>
        `;
    }

    function renderRevenueTrendChart(points, symbol) {
        if (!points || points.length === 0) {
            return `
                <div class="chart-empty-state">
                    <div class="empty-icon">📈</div>
                    <p>No historical revenue data recorded in this period.</p>
                </div>
            `;
        }

        const width = 640;
        const height = 220;
        const padding = 35;

        const maxVal = Math.max(...points.map(p => p.amount || 0), 100);
        const minVal = 0;

        const xStep = (width - padding * 2) / Math.max(points.length - 1, 1);

        const coords = points.map((p, i) => {
            const x = padding + i * xStep;
            const y = height - padding - ((p.amount || 0) / maxVal) * (height - padding * 2);
            return { x, y, amount: p.amount || 0, label: p.month || '' };
        });

        const linePath = coords.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(' ');
        const areaPath = `${linePath} L ${coords[coords.length - 1].x.toFixed(1)} ${height - padding} L ${coords[0].x.toFixed(1)} ${height - padding} Z`;

        const dots = coords.map(c => `
            <circle cx="${c.x.toFixed(1)}" cy="${c.y.toFixed(1)}" r="4" class="chart-dot">
                <title>${c.label}: ${formatMoney(c.amount, symbol)}</title>
            </circle>
        `).join('');

        const xLabels = coords.map(c => `
            <text x="${c.x.toFixed(1)}" y="${height - 10}" text-anchor="middle" class="chart-axis-label">${c.label}</text>
        `).join('');

        return `
            <svg viewBox="0 0 ${width} ${height}" class="interactive-svg-chart" preserveAspectRatio="none">
                <defs>
                    <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="#2D7A4F" stop-opacity="0.38"/>
                        <stop offset="100%" stop-color="#2D7A4F" stop-opacity="0.0"/>
                    </linearGradient>
                </defs>
                <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" class="chart-grid-line"/>
                <path d="${areaPath}" fill="url(#chartGradient)"/>
                <path d="${linePath}" fill="none" stroke="#2D7A4F" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                ${dots}
                ${xLabels}
            </svg>
        `;
    }

    function renderOverviewInvoicesTable(invoices, symbol) {
        if (!invoices || invoices.length === 0) {
            return `
                <div class="empty-state p-6">
                    <p class="text-muted">No invoices generated yet.</p>
                </div>
            `;
        }

        return `
            <div class="table-responsive">
                <table class="table">
                    <thead>
                        <tr>
                            <th>Number</th>
                            <th>Customer</th>
                            <th>Date</th>
                            <th>Total</th>
                            <th>Residual Balance</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${invoices.map(inv => `
                            <tr>
                                <td><strong>${escapeHtml(inv.name)}</strong></td>
                                <td>${escapeHtml(inv.partner_name || '—')}</td>
                                <td>${inv.invoice_date || '—'}</td>
                                <td>${formatMoney(inv.amount_total, symbol)}</td>
                                <td>${formatMoney(inv.amount_residual, symbol)}</td>
                                <td>${renderPaymentBadge(inv.payment_state)}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    // =========================================================================
    // 2. SUBSCRIPTIONS TAB
    // =========================================================================

    async function loadSubscriptionsData(force = false) {
        const container = document.getElementById('tab-subscriptions');
        if (!container) return;

        try {
            container.innerHTML = renderTableSkeleton('Subscriptions');
            const res = await fetch('/api/v1/app/subscriptions?limit=50', { credentials: 'same-origin' });
            const result = await res.json();

            if (result.status !== 'success') {
                throw new Error(result.message || 'Failed to fetch subscriptions');
            }

            state.subscriptions = (result.data && result.data.subscriptions) || [];
            renderSubscriptions(state.subscriptions);
        } catch (err) {
            console.error('Failed to load subscriptions:', err);
            container.innerHTML = renderErrorState('Failed to load subscriptions.', () => loadSubscriptionsData(true));
        }
    }

    function renderSubscriptions(subscriptions) {
        const container = document.getElementById('tab-subscriptions');
        if (!container) return;

        if (!subscriptions || subscriptions.length === 0) {
            container.innerHTML = `
                <div class="page-header">
                    <div>
                        <h1 class="page-title">Subscription Contracts</h1>
                        <p class="page-subtitle">Manage customer recurring contracts and lifecycle actions.</p>
                    </div>
                </div>
                <div class="card empty-state">
                    <div class="empty-icon">📋</div>
                    <h3>No Subscription Contracts Found</h3>
                    <p>There are no active or historical subscription contracts currently recorded in the database.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Subscription Contracts</h1>
                    <p class="page-subtitle">Active, paused, and closed customer contracts with full lifecycle controls.</p>
                </div>
                <div class="header-actions">
                    <div class="filter-group">
                        <button class="btn btn-filter active" data-sub-filter="all">All (${subscriptions.length})</button>
                        <button class="btn btn-filter" data-sub-filter="active">Active</button>
                        <button class="btn btn-filter" data-sub-filter="paused">Paused</button>
                        <button class="btn btn-filter" data-sub-filter="closed">Closed</button>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="table-responsive">
                    <table class="table" id="subscriptions-table">
                        <thead>
                            <tr>
                                <th>Contract</th>
                                <th>Customer</th>
                                <th>Plan</th>
                                <th>Recurring Amount</th>
                                <th>Next Billing</th>
                                <th>Status</th>
                                <th class="text-right">Lifecycle Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${subscriptions.map(sub => `
                                <tr data-state="${sub.state}">
                                    <td>
                                        <strong>${escapeHtml(sub.name)}</strong>
                                        <div class="text-xs text-muted">ID: ${sub.id}</div>
                                    </td>
                                    <td>
                                        <div>${escapeHtml(sub.customer_name)}</div>
                                        <div class="text-xs text-muted">${escapeHtml(sub.customer_email || '')}</div>
                                    </td>
                                    <td><span class="badge badge-plan">${escapeHtml(sub.plan_name)}</span></td>
                                    <td><strong>${formatMoney(sub.recurring_amount, sub.currency_symbol || '$')}</strong></td>
                                    <td>${sub.next_billing_date || '—'}</td>
                                    <td>${renderSubscriptionBadge(sub.state)}</td>
                                    <td class="text-right">
                                        ${renderSubscriptionActionButtons(sub)}
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;

        // Bind filter buttons
        container.querySelectorAll('[data-sub-filter]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const filter = e.target.getAttribute('data-sub-filter');
                container.querySelectorAll('[data-sub-filter]').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');

                const rows = container.querySelectorAll('#subscriptions-table tbody tr');
                rows.forEach(r => {
                    if (filter === 'all' || r.getAttribute('data-state') === filter) {
                        r.style.display = '';
                    } else {
                        r.style.display = 'none';
                    }
                });
            });
        });

        // Bind action buttons
        container.querySelectorAll('[data-sub-action]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const subId = parseInt(btn.getAttribute('data-sub-id'), 10);
                const action = btn.getAttribute('data-sub-action');
                const subName = btn.getAttribute('data-sub-name');
                openSubscriptionActionModal(subId, subName, action);
            });
        });
    }

    function renderSubscriptionActionButtons(sub) {
        let buttons = [];
        if (sub.state === 'active') {
            if (sub.allow_pause) {
                buttons.push(`<button class="btn btn-outline btn-xs" data-sub-action="pause" data-sub-id="${sub.id}" data-sub-name="${escapeHtml(sub.name)}">Pause</button>`);
            }
            if (sub.allow_close) {
                buttons.push(`<button class="btn btn-outline btn-xs btn-danger" data-sub-action="close" data-sub-id="${sub.id}" data-sub-name="${escapeHtml(sub.name)}">Close</button>`);
            }
        } else if (sub.state === 'paused') {
            buttons.push(`<button class="btn btn-primary btn-xs" data-sub-action="resume" data-sub-id="${sub.id}" data-sub-name="${escapeHtml(sub.name)}">Resume</button>`);
            if (sub.allow_close) {
                buttons.push(`<button class="btn btn-outline btn-xs btn-danger" data-sub-action="close" data-sub-id="${sub.id}" data-sub-name="${escapeHtml(sub.name)}">Close</button>`);
            }
        } else if (sub.state === 'closed') {
            buttons.push(`<button class="btn btn-outline btn-xs" data-sub-action="renew" data-sub-id="${sub.id}" data-sub-name="${escapeHtml(sub.name)}">Renew</button>`);
        } else if (sub.state === 'draft') {
            buttons.push(`<button class="btn btn-primary btn-xs" data-sub-action="confirm" data-sub-id="${sub.id}" data-sub-name="${escapeHtml(sub.name)}">Confirm</button>`);
        } else if (sub.state === 'confirmed') {
            buttons.push(`<button class="btn btn-primary btn-xs" data-sub-action="activate" data-sub-id="${sub.id}" data-sub-name="${escapeHtml(sub.name)}">Activate</button>`);
        }

        return buttons.join(' ') || '<span class="text-muted text-xs">—</span>';
    }

    function openSubscriptionActionModal(subId, subName, action) {
        const actionLabels = {
            pause: 'Pause Subscription',
            resume: 'Resume Subscription',
            renew: 'Renew Subscription Contract',
            close: 'Terminate / Close Subscription Early',
            confirm: 'Confirm Subscription Contract',
            activate: 'Activate Subscription Contract',
        };

        const needsReason = action === 'pause' || action === 'close';
        const title = actionLabels[action] || action;

        let content = `
            <p>Are you sure you want to <strong>${action.toUpperCase()}</strong> subscription <strong>${escapeHtml(subName)}</strong>?</p>
        `;

        if (needsReason) {
            content += `
                <div class="form-group mt-4">
                    <label class="form-label">Reason / Notes ${action === 'close' ? '(Required)' : '(Optional)'}</label>
                    <textarea id="modal-reason-input" class="form-control" rows="3" placeholder="Enter reason for this action..."></textarea>
                </div>
            `;
        }

        openModal(title, content, async () => {
            const reasonInput = document.getElementById('modal-reason-input');
            const reason = reasonInput ? reasonInput.value.trim() : null;

            if (action === 'close' && !reason) {
                showToast('A reason is required to close early.', 'warning');
                return;
            }

            try {
                showLoading(true);
                const res = await fetch(`/api/v1/app/subscriptions/${subId}/action`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    body: JSON.stringify({ action, reason }),
                });
                const data = await res.json();

                if (data.status === 'success') {
                    showToast(data.message || `Subscription ${action} succeeded.`, 'success');
                    closeModal();
                    loadSubscriptionsData(true);
                } else {
                    showToast(data.message || `Action failed: ${data.status}`, 'error');
                }
            } catch (err) {
                console.error(`Action ${action} failed:`, err);
                showToast('Network error while processing request.', 'error');
            } finally {
                showLoading(false);
            }
        });
    }

    // =========================================================================
    // 3. CATALOG TAB (PRODUCTS & PLANS)
    // =========================================================================

    async function loadCatalogData(force = false) {
        const container = document.getElementById('tab-catalog');
        if (!container) return;

        try {
            container.innerHTML = renderTableSkeleton('Catalog');
            const res = await fetch('/api/v1/app/catalog', { credentials: 'same-origin' });
            const result = await res.json();

            if (result.status !== 'success') {
                throw new Error(result.message || 'Failed to fetch catalog');
            }

            state.catalog = result.data || { plans: [], products: [] };
            renderCatalog(state.catalog);
        } catch (err) {
            console.error('Failed to load catalog:', err);
            container.innerHTML = renderErrorState('Failed to load products and plans.', () => loadCatalogData(true));
        }
    }

    function renderCatalog(catalog) {
        const container = document.getElementById('tab-catalog');
        if (!container) return;

        const plans = catalog.plans || [];
        const products = catalog.products || [];

        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Products & Subscription Plans</h1>
                    <p class="page-subtitle">Catalog configurations, billing recurrence frequencies, and lifecycle policies.</p>
                </div>
            </div>

            <!-- Subscription Plans Grid -->
            <h3 class="section-title">Subscription Plans</h3>
            <div class="plans-grid">
                ${plans.length === 0 ? '<p class="text-muted">No subscription plans configured.</p>' : plans.map(p => `
                    <div class="card plan-card">
                        <div class="plan-header">
                            <h4 class="plan-title">${escapeHtml(p.name)}</h4>
                            <span class="badge ${p.active ? 'badge-active' : 'badge-closed'}">${p.active ? 'Active' : 'Inactive'}</span>
                        </div>
                        <div class="plan-price">
                            ${formatMoney(p.list_price, p.currency_symbol || '$')}
                            <span class="plan-interval">/ ${p.billing_interval_count > 1 ? p.billing_interval_count + ' ' : ''}${p.billing_interval}</span>
                        </div>
                        <ul class="plan-features">
                            <li><span>Pause Policy:</span> <strong>${p.allow_pause ? 'Allowed' : 'Disallowed'}</strong></li>
                            <li><span>Early Closure:</span> <strong>${p.allow_early_closure ? 'Allowed' : 'Disallowed'}</strong></li>
                            <li><span>Auto Close:</span> <strong>${p.auto_close ? 'Enabled' : 'Disabled'}</strong></li>
                        </ul>
                    </div>
                `).join('')}
            </div>

            <!-- Products Table -->
            <h3 class="section-title mt-8">Products & Services</h3>
            <div class="card">
                <div class="table-responsive">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Product Name</th>
                                <th>Internal Code</th>
                                <th>Type</th>
                                <th>Sales Price</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${products.length === 0 ? '<tr><td colspan="4" class="text-muted p-4">No products found.</td></tr>' : products.map(prod => `
                                <tr>
                                    <td><strong>${escapeHtml(prod.name)}</strong></td>
                                    <td>${escapeHtml(prod.default_code || '—')}</td>
                                    <td><span class="badge badge-outline">${prod.type}</span></td>
                                    <td><strong>${formatMoney(prod.list_price, prod.currency_symbol || '$')}</strong></td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    // =========================================================================
    // 4. QUOTATIONS TAB
    // =========================================================================

    async function loadQuotationsData(force = false) {
        const container = document.getElementById('tab-quotations');
        if (!container) return;

        try {
            container.innerHTML = renderTableSkeleton('Quotations');
            const res = await fetch('/api/v1/app/quotations?limit=50', { credentials: 'same-origin' });
            const result = await res.json();

            if (result.status !== 'success') {
                throw new Error(result.message || 'Failed to fetch quotations');
            }

            state.quotations = (result.data && result.data.quotations) || [];
            renderQuotations(state.quotations);
        } catch (err) {
            console.error('Failed to load quotations:', err);
            container.innerHTML = renderErrorState('Failed to load quotations.', () => loadQuotationsData(true));
        }
    }

    function renderQuotations(quotations) {
        const container = document.getElementById('tab-quotations');
        if (!container) return;

        if (!quotations || quotations.length === 0) {
            container.innerHTML = `
                <div class="page-header">
                    <div>
                        <h1 class="page-title">Sales Quotations & Orders</h1>
                        <p class="page-subtitle">Track sales pipelines and subscription conversion quotations.</p>
                    </div>
                </div>
                <div class="card empty-state">
                    <div class="empty-icon">📝</div>
                    <h3>No Quotations Found</h3>
                    <p>There are no sales quotations or orders recorded in the current company.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Sales Quotations & Orders</h1>
                    <p class="page-subtitle">Pipeline quotations, sales orders, and subscription conversion records.</p>
                </div>
            </div>

            <div class="card">
                <div class="table-responsive">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Quotation #</th>
                                <th>Customer</th>
                                <th>Order Date</th>
                                <th>Total Amount</th>
                                <th>Order Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${quotations.map(q => `
                                <tr>
                                    <td><strong>${escapeHtml(q.name)}</strong></td>
                                    <td>${escapeHtml(q.partner_name || '—')}</td>
                                    <td>${q.date_order ? q.date_order.substring(0, 10) : '—'}</td>
                                    <td><strong>${formatMoney(q.amount_total, q.currency_symbol || '$')}</strong></td>
                                    <td>${renderSaleOrderBadge(q.state)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    // =========================================================================
    // 5. INVOICES TAB
    // =========================================================================

    async function loadInvoicesData(force = false) {
        const container = document.getElementById('tab-invoices');
        if (!container) return;

        try {
            container.innerHTML = renderTableSkeleton('Invoices');
            const res = await fetch('/api/v1/app/invoices?limit=50', { credentials: 'same-origin' });
            const result = await res.json();

            if (result.status !== 'success') {
                throw new Error(result.message || 'Failed to fetch invoices');
            }

            state.invoices = (result.data && result.data.invoices) || [];
            renderInvoices(state.invoices);
        } catch (err) {
            console.error('Failed to load invoices:', err);
            container.innerHTML = renderErrorState('Failed to load invoices.', () => loadInvoicesData(true));
        }
    }

    function renderInvoices(invoices) {
        const container = document.getElementById('tab-invoices');
        if (!container) return;

        if (!invoices || invoices.length === 0) {
            container.innerHTML = `
                <div class="page-header">
                    <div>
                        <h1 class="page-title">Invoices & Billing History</h1>
                        <p class="page-subtitle">Customer accounts receivable entries, payments, and PDF copies.</p>
                    </div>
                </div>
                <div class="card empty-state">
                    <div class="empty-icon">🧾</div>
                    <h3>No Invoices Found</h3>
                    <p>There are no posted invoices in the current fiscal ledger.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Invoices & Billing History</h1>
                    <p class="page-subtitle">Real posted invoices, residual balances, and downloadable tax receipts.</p>
                </div>
            </div>

            <div class="card">
                <div class="table-responsive">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Invoice #</th>
                                <th>Customer</th>
                                <th>Invoice Date</th>
                                <th>Due Date</th>
                                <th>Total</th>
                                <th>Residual Balance</th>
                                <th>Payment State</th>
                                <th class="text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${invoices.map(inv => `
                                <tr>
                                    <td><strong>${escapeHtml(inv.name)}</strong></td>
                                    <td>${escapeHtml(inv.partner_name || '—')}</td>
                                    <td>${inv.invoice_date || '—'}</td>
                                    <td>${inv.invoice_date_due || '—'}</td>
                                    <td><strong>${formatMoney(inv.amount_total, inv.currency_symbol || '$')}</strong></td>
                                    <td>${formatMoney(inv.amount_residual, inv.currency_symbol || '$')}</td>
                                    <td>${renderPaymentBadge(inv.payment_state)}</td>
                                    <td class="text-right">
                                        <a href="/api/v1/portal/invoices/${inv.id}/pdf" target="_blank" class="btn btn-outline btn-xs" download>
                                            📄 PDF
                                        </a>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    // =========================================================================
    // 6. PAYMENTS TAB
    // =========================================================================

    async function loadPaymentsData(force = false) {
        const container = document.getElementById('tab-payments');
        if (!container) return;

        try {
            container.innerHTML = renderTableSkeleton('Payments');
            const res = await fetch('/api/v1/app/payments?limit=50', { credentials: 'same-origin' });
            const result = await res.json();

            if (result.status !== 'success') {
                throw new Error(result.message || 'Failed to fetch payments');
            }

            state.payments = (result.data && result.data.payments) || [];
            renderPayments(state.payments);
        } catch (err) {
            console.error('Failed to load payments:', err);
            container.innerHTML = renderErrorState('Failed to load payments.', () => loadPaymentsData(true));
        }
    }

    function renderPayments(payments) {
        const container = document.getElementById('tab-payments');
        if (!container) return;

        if (!payments || payments.length === 0) {
            container.innerHTML = `
                <div class="page-header">
                    <div>
                        <h1 class="page-title">Payments & Reconciliations</h1>
                        <p class="page-subtitle">Track inbound settlements, bank deposits, and invoice matches.</p>
                    </div>
                </div>
                <div class="card empty-state">
                    <div class="empty-icon">💳</div>
                    <h3>No Payments Recorded</h3>
                    <p>There are no customer payments registered in the system yet.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Payments & Reconciliations</h1>
                    <p class="page-subtitle">Inbound settlements, journal allocations, and accounting ledger postings.</p>
                </div>
            </div>

            <div class="card">
                <div class="table-responsive">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Payment Ref</th>
                                <th>Customer</th>
                                <th>Payment Date</th>
                                <th>Journal</th>
                                <th>Amount</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${payments.map(p => `
                                <tr>
                                    <td><strong>${escapeHtml(p.name)}</strong></td>
                                    <td>${escapeHtml(p.partner_name || '—')}</td>
                                    <td>${p.date || '—'}</td>
                                    <td><span class="badge badge-outline">${escapeHtml(p.journal_name || 'Bank')}</span></td>
                                    <td><strong class="text-success">${formatMoney(p.amount, p.currency_symbol || '$')}</strong></td>
                                    <td><span class="badge ${p.state === 'posted' ? 'badge-active' : 'badge-draft'}">${p.state}</span></td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    // =========================================================================
    // 7. FINANCIAL ANALYTICS DEEP DIVE
    // =========================================================================

    async function loadAnalyticsData(force = false) {
        const container = document.getElementById('tab-analytics');
        if (!container) return;

        try {
            renderOverviewSkeleton();

            const [mrrRes, agingRes, customersRes, compareRes] = await Promise.all([
                fetch('/api/v1/analytics/mrr', { credentials: 'same-origin' }).then(r => r.json()),
                fetch('/api/v1/analytics/aging', { credentials: 'same-origin' }).then(r => r.json()),
                fetch('/api/v1/analytics/customers', { credentials: 'same-origin' }).then(r => r.json()),
                fetch('/api/v1/analytics/compare', { credentials: 'same-origin' }).then(r => r.json()),
            ]);

            state.analytics = {
                mrr: mrrRes.data || {},
                aging: agingRes.data || {},
                customers: customersRes.data || {},
                compare: compareRes.data || {},
            };

            renderAnalytics(state.analytics);
        } catch (err) {
            console.error('Failed to load analytics deep dive:', err);
            container.innerHTML = renderErrorState('Failed to load finance analytics.', () => loadAnalyticsData(true));
        }
    }

    function renderAnalytics(data) {
        const container = document.getElementById('tab-analytics');
        if (!container) return;

        const mrr = data.mrr || {};
        const aging = data.aging || {};
        const customers = data.customers || {};
        const compare = data.compare || {};
        const symbol = mrr.currency_symbol || '$';

        const agingBuckets = aging.aging_buckets || {};
        const bCurrent = agingBuckets.current || 0;
        const b1_30 = agingBuckets['1_30'] || 0;
        const b31_60 = agingBuckets['31_60'] || 0;
        const b61_90 = agingBuckets['61_90'] || 0;
        const b90_plus = agingBuckets['90_plus'] || 0;
        const agingTotal = bCurrent + b1_30 + b31_60 + b61_90 + b90_plus;

        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Financial Analytics & Aging Engine</h1>
                    <p class="page-subtitle">Multi-currency MRR distributions, AR aging risk, and cohort growth analytics.</p>
                </div>
            </div>

            <!-- Analytics Top Metrics -->
            <div class="kpi-grid">
                <div class="card kpi-card">
                    <div class="kpi-label">Active Customer Accounts</div>
                    <div class="kpi-value">${customers.active_customers_count || 0}</div>
                    <div class="kpi-subtext">Distinct paying subscriber entities</div>
                </div>
                <div class="card kpi-card">
                    <div class="kpi-label">Average Revenue Per User (ARPU)</div>
                    <div class="kpi-value">${formatMoney(customers.arpu || 0, symbol)}</div>
                    <div class="kpi-subtext">MRR / Active Customers</div>
                </div>
                <div class="card kpi-card">
                    <div class="kpi-label">Total Outstanding Receivables</div>
                    <div class="kpi-value">${formatMoney(aging.total_outstanding || 0, symbol)}</div>
                    <div class="kpi-subtext">${aging.overdue_count || 0} overdue invoices</div>
                </div>
                <div class="card kpi-card">
                    <div class="kpi-label">Month-over-Month MRR Growth</div>
                    <div class="kpi-value ${compare.growth_pct >= 0 ? 'text-success' : 'text-danger'}">
                        ${compare.growth_pct !== undefined ? (compare.growth_pct >= 0 ? '+' : '') + compare.growth_pct.toFixed(1) + '%' : '0.0%'}
                    </div>
                    <div class="kpi-subtext">Compared to prior calendar period</div>
                </div>
            </div>

            <!-- Aging Analysis Card -->
            <div class="card mt-6">
                <div class="card-header">
                    <div>
                        <h3 class="card-title">Accounts Receivable (AR) Aging Buckets</h3>
                        <p class="card-subtitle">Overdue distribution based on invoice due dates</p>
                    </div>
                </div>
                <div class="aging-grid">
                    <div class="aging-box">
                        <div class="aging-label">Current (Not Due)</div>
                        <div class="aging-value">${formatMoney(bCurrent, symbol)}</div>
                        <div class="progress-bar-bg mt-2"><div class="progress-bar-fill fill-active" style="width: ${agingTotal ? (bCurrent/agingTotal*100) : 0}%"></div></div>
                    </div>
                    <div class="aging-box">
                        <div class="aging-label">1–30 Days Overdue</div>
                        <div class="aging-value">${formatMoney(b1_30, symbol)}</div>
                        <div class="progress-bar-bg mt-2"><div class="progress-bar-fill fill-paused" style="width: ${agingTotal ? (b1_30/agingTotal*100) : 0}%"></div></div>
                    </div>
                    <div class="aging-box">
                        <div class="aging-label">31–60 Days Overdue</div>
                        <div class="aging-value">${formatMoney(b31_60, symbol)}</div>
                        <div class="progress-bar-bg mt-2"><div class="progress-bar-fill fill-paused" style="width: ${agingTotal ? (b31_60/agingTotal*100) : 0}%"></div></div>
                    </div>
                    <div class="aging-box">
                        <div class="aging-label">61–90 Days Overdue</div>
                        <div class="aging-value text-danger">${formatMoney(b61_90, symbol)}</div>
                        <div class="progress-bar-bg mt-2"><div class="progress-bar-fill fill-closed" style="width: ${agingTotal ? (b61_90/agingTotal*100) : 0}%"></div></div>
                    </div>
                    <div class="aging-box">
                        <div class="aging-label">90+ Days Overdue</div>
                        <div class="aging-value text-danger">${formatMoney(b90_plus, symbol)}</div>
                        <div class="progress-bar-bg mt-2"><div class="progress-bar-fill fill-closed" style="width: ${agingTotal ? (b90_plus/agingTotal*100) : 0}%"></div></div>
                    </div>
                </div>
            </div>
        `;
    }

    // =========================================================================
    // 8. CUSTOMER SELF-SERVICE PORTAL TAB
    // =========================================================================

    async function loadPortalData(force = false) {
        const container = document.getElementById('tab-portal');
        if (!container) return;

        try {
            renderOverviewSkeleton();

            const [profileRes, subsRes, invoicesRes, paymentsRes, timelineRes] = await Promise.all([
                fetch('/api/v1/portal/profile', { credentials: 'same-origin' }).then(r => r.json()),
                fetch('/api/v1/portal/subscriptions', { credentials: 'same-origin' }).then(r => r.json()),
                fetch('/api/v1/portal/invoices', { credentials: 'same-origin' }).then(r => r.json()),
                fetch('/api/v1/portal/payments', { credentials: 'same-origin' }).then(r => r.json()),
                fetch('/api/v1/portal/timeline', { credentials: 'same-origin' }).then(r => r.json()),
            ]);

            state.portal = {
                profile: profileRes.data || {},
                subscriptions: (subsRes.data && subsRes.data.subscriptions) || [],
                invoices: (invoicesRes.data && invoicesRes.data.invoices) || [],
                payments: (paymentsRes.data && paymentsRes.data.payments) || [],
                timeline: (timelineRes.data && timelineRes.data.timeline) || [],
            };

            renderPortal(state.portal);
        } catch (err) {
            console.error('Failed to load portal data:', err);
            container.innerHTML = renderErrorState('Failed to load customer portal.', () => loadPortalData(true));
        }
    }

    function renderPortal(portal) {
        const container = document.getElementById('tab-portal');
        if (!container) return;

        const profile = portal.profile || {};
        const subscriptions = portal.subscriptions || [];
        const invoices = portal.invoices || [];
        const payments = portal.payments || [];
        const timeline = portal.timeline || [];

        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Customer Self-Service Portal</h1>
                    <p class="page-subtitle">Manage your subscriptions, view billing statements, and update contact profile.</p>
                </div>
                <div class="header-actions">
                    <span class="badge badge-active">Account Active</span>
                </div>
            </div>

            <!-- Profile Overview & Edit Grid -->
            <div class="grid grid-cols-2 gap-6 mb-8">
                <div class="card">
                    <div class="card-header">
                        <div>
                            <h3 class="card-title">Billing & Account Profile</h3>
                            <p class="card-subtitle">Keep your direct contact details current</p>
                        </div>
                    </div>
                    <form id="portal-profile-form">
                        <div class="form-group mb-4">
                            <label class="form-label">Company / Account Name</label>
                            <input type="text" class="form-control" value="${escapeHtml(profile.name || '')}" disabled>
                        </div>
                        <div class="form-group mb-4">
                            <label class="form-label">Primary Email Address</label>
                            <input type="email" class="form-control" value="${escapeHtml(profile.email || '')}" disabled>
                            <span class="text-xs text-muted">Contact support to modify primary email.</span>
                        </div>
                        <div class="grid grid-cols-2 gap-4 mb-4">
                            <div class="form-group">
                                <label class="form-label">Phone</label>
                                <input type="text" id="profile-phone" class="form-control" value="${escapeHtml(profile.phone || '')}">
                            </div>
                            <div class="form-group">
                                <label class="form-label">Mobile</label>
                                <input type="text" id="profile-mobile" class="form-control" value="${escapeHtml(profile.mobile || '')}">
                            </div>
                        </div>
                        <div class="form-group mb-4">
                            <label class="form-label">Billing Address</label>
                            <input type="text" id="profile-street" class="form-control" value="${escapeHtml(profile.street || '')}">
                        </div>
                        <button type="submit" class="btn btn-primary btn-sm">Update Contact Details</button>
                    </form>
                </div>

                <!-- Account Summary -->
                <div class="card">
                    <div class="card-header">
                        <div>
                            <h3 class="card-title">Contract Summary</h3>
                            <p class="card-subtitle">Snapshot of current active subscriptions</p>
                        </div>
                    </div>
                    <div class="p-4">
                        <div class="breakdown-stat">
                            <span>Active Subscriptions:</span>
                            <strong>${subscriptions.filter(s => s.state === 'active').length}</strong>
                        </div>
                        <div class="breakdown-stat">
                            <span>Open Invoices:</span>
                            <strong>${invoices.filter(i => i.payment_state !== 'paid').length}</strong>
                        </div>
                        <div class="breakdown-stat">
                            <span>Total Historical Payments:</span>
                            <strong>${payments.length}</strong>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Subscriptions List -->
            <div class="card mb-8">
                <div class="card-header">
                    <div>
                        <h3 class="card-title">My Subscriptions</h3>
                        <p class="card-subtitle">Active and past subscription services</p>
                    </div>
                </div>
                <div class="table-responsive">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Plan</th>
                                <th>Recurring Amount</th>
                                <th>Next Billing</th>
                                <th>Status</th>
                                <th class="text-right">Self-Service Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${subscriptions.length === 0 ? '<tr><td colspan="5" class="text-muted p-4">No subscriptions linked to this customer account.</td></tr>' : subscriptions.map(sub => `
                                <tr>
                                    <td>
                                        <strong>${escapeHtml(sub.name)}</strong>
                                        <div class="text-xs text-muted">${escapeHtml(sub.plan_name || '')}</div>
                                    </td>
                                    <td><strong>${formatMoney(sub.recurring_amount, sub.currency_symbol || '$')}</strong></td>
                                    <td>${sub.next_billing_date || '—'}</td>
                                    <td>${renderSubscriptionBadge(sub.state)}</td>
                                    <td class="text-right">
                                        ${renderPortalSubscriptionActions(sub)}
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Invoices & Tax Receipts -->
            <div class="card mb-8">
                <div class="card-header">
                    <div>
                        <h3 class="card-title">Invoices & Statements</h3>
                        <p class="card-subtitle">Download official accounting receipts for tax reporting</p>
                    </div>
                </div>
                <div class="table-responsive">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Invoice #</th>
                                <th>Date</th>
                                <th>Total</th>
                                <th>Residual</th>
                                <th>Status</th>
                                <th class="text-right">Receipt</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${invoices.length === 0 ? '<tr><td colspan="6" class="text-muted p-4">No billing statements found.</td></tr>' : invoices.map(inv => `
                                <tr>
                                    <td><strong>${escapeHtml(inv.name)}</strong></td>
                                    <td>${inv.invoice_date || '—'}</td>
                                    <td>${formatMoney(inv.amount_total, inv.currency_symbol || '$')}</td>
                                    <td>${formatMoney(inv.amount_residual, inv.currency_symbol || '$')}</td>
                                    <td>${renderPaymentBadge(inv.payment_state)}</td>
                                    <td class="text-right">
                                        <a href="/api/v1/portal/invoices/${inv.id}/pdf" target="_blank" class="btn btn-outline btn-xs" download>
                                            📄 Download PDF
                                        </a>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Activity Timeline -->
            <div class="card">
                <div class="card-header">
                    <div>
                        <h3 class="card-title">Account Activity History</h3>
                        <p class="card-subtitle">Timeline of contract lifecycle, billing, and payment events</p>
                    </div>
                </div>
                <div class="timeline-container p-6">
                    ${timeline.length === 0 ? '<p class="text-muted">No timeline activity logged.</p>' : timeline.map(event => `
                        <div class="timeline-item">
                            <div class="timeline-dot"></div>
                            <div class="timeline-content">
                                <div class="timeline-title"><strong>${escapeHtml(event.title || event.event_type || 'Event')}</strong></div>
                                <div class="timeline-description text-sm text-muted">${escapeHtml(event.description || '')}</div>
                                <div class="timeline-date text-xs text-muted">${event.date || ''}</div>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;

        // Bind Profile form
        const profileForm = document.getElementById('portal-profile-form');
        if (profileForm) {
            profileForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const phone = document.getElementById('profile-phone').value.trim();
                const mobile = document.getElementById('profile-mobile').value.trim();
                const street = document.getElementById('profile-street').value.trim();

                try {
                    showLoading(true);
                    const res = await fetch('/api/v1/portal/profile', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'same-origin',
                        body: JSON.stringify({ phone, mobile, street }),
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        showToast('Profile updated successfully.', 'success');
                    } else {
                        showToast(data.message || 'Update failed.', 'error');
                    }
                } catch (err) {
                    console.error('Profile update failed:', err);
                    showToast('Failed to update profile.', 'error');
                } finally {
                    showLoading(false);
                }
            });
        }

        // Bind Customer Sub actions
        container.querySelectorAll('[data-portal-action]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const subId = parseInt(btn.getAttribute('data-sub-id'), 10);
                const action = btn.getAttribute('data-portal-action');
                handleCustomerSubAction(subId, action);
            });
        });
    }

    function renderPortalSubscriptionActions(sub) {
        let buttons = [];
        if (sub.state === 'active') {
            if (sub.allow_pause) {
                buttons.push(`<button class="btn btn-outline btn-xs" data-portal-action="pause" data-sub-id="${sub.id}">Pause</button>`);
            }
            if (sub.allow_close) {
                buttons.push(`<button class="btn btn-outline btn-xs btn-danger" data-portal-action="close" data-sub-id="${sub.id}">Cancel Plan</button>`);
            }
        } else if (sub.state === 'paused') {
            buttons.push(`<button class="btn btn-primary btn-xs" data-portal-action="resume" data-sub-id="${sub.id}">Resume</button>`);
        } else if (sub.state === 'closed') {
            buttons.push(`<button class="btn btn-outline btn-xs" data-portal-action="renew" data-sub-id="${sub.id}">Renew</button>`);
        }
        return buttons.join(' ') || '<span class="text-muted text-xs">—</span>';
    }

    async function handleCustomerSubAction(subId, action) {
        if (!confirm(`Are you sure you want to ${action} this subscription?`)) return;

        try {
            showLoading(true);
            const endpoint = `/api/v1/portal/subscriptions/${subId}/${action}`;
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({}),
            });
            const data = await res.json();

            if (data.status === 'success') {
                showToast(`Subscription ${action} completed successfully.`, 'success');
                loadPortalData(true);
            } else {
                showToast(data.message || `Action failed.`, 'error');
            }
        } catch (err) {
            console.error(`Portal action ${action} failed:`, err);
            showToast('Network error while processing request.', 'error');
        } finally {
            showLoading(false);
        }
    }

    // =========================================================================
    // UI HELPERS, MODALS & TOASTS
    // =========================================================================

    function openModal(title, contentHtml, onConfirm) {
        if (!elements.modalOverlay) return;
        if (elements.modalTitle) elements.modalTitle.textContent = title;
        if (elements.modalBody) elements.modalBody.innerHTML = contentHtml;

        elements.modalOverlay.classList.remove('hidden');

        // Replace confirm button to clean past listeners
        const newConfirmBtn = elements.modalConfirmBtn.cloneNode(true);
        elements.modalConfirmBtn.parentNode.replaceChild(newConfirmBtn, elements.modalConfirmBtn);
        elements.modalConfirmBtn = newConfirmBtn;

        elements.modalConfirmBtn.addEventListener('click', onConfirm);
    }

    function closeModal() {
        if (elements.modalOverlay) {
            elements.modalOverlay.classList.add('hidden');
        }
    }

    function showToast(message, type = 'info') {
        if (!elements.toastContainer) {
            alert(message);
            return;
        }

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <span class="toast-message">${escapeHtml(message)}</span>
            <button class="toast-close">&times;</button>
        `;

        toast.querySelector('.toast-close').addEventListener('click', () => toast.remove());
        elements.toastContainer.appendChild(toast);

        setTimeout(() => {
            if (toast.parentNode) {
                toast.classList.add('fade-out');
                setTimeout(() => toast.remove(), 300);
            }
        }, 4000);
    }

    function showLoading(show) {
        state.loading = show;
        const spinner = document.getElementById('global-loading-spinner');
        if (spinner) {
            spinner.style.display = show ? 'flex' : 'none';
        }
    }

    async function handleLogout() {
        try {
            await fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'same-origin' });
        } finally {
            window.location.href = '/auth/login';
        }
    }

    function renderSubscriptionBadge(state) {
        const badges = {
            active: '<span class="badge badge-active">Active</span>',
            paused: '<span class="badge badge-paused">Paused</span>',
            closed: '<span class="badge badge-closed">Closed</span>',
            draft: '<span class="badge badge-draft">Draft</span>',
            confirmed: '<span class="badge badge-outline">Confirmed</span>',
        };
        return badges[state] || `<span class="badge">${state}</span>`;
    }

    function renderPaymentBadge(state) {
        const badges = {
            paid: '<span class="badge badge-active">Paid</span>',
            not_paid: '<span class="badge badge-closed">Not Paid</span>',
            partial: '<span class="badge badge-paused">Partial</span>',
            in_payment: '<span class="badge badge-outline">In Payment</span>',
        };
        return badges[state] || `<span class="badge">${state || '—'}</span>`;
    }

    function renderSaleOrderBadge(state) {
        const badges = {
            draft: '<span class="badge badge-draft">Quotation</span>',
            sent: '<span class="badge badge-outline">Quotation Sent</span>',
            sale: '<span class="badge badge-active">Sales Order</span>',
            cancel: '<span class="badge badge-closed">Cancelled</span>',
        };
        return badges[state] || `<span class="badge">${state}</span>`;
    }

    function formatMoney(amount, symbol = '$') {
        const num = parseFloat(amount || 0);
        return symbol + num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function renderOverviewSkeleton() {
        return `
            <div class="skeleton-grid">
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
            </div>
        `;
    }

    function renderTableSkeleton(name) {
        return `
            <div class="page-header">
                <div>
                    <h1 class="page-title">${name}</h1>
                    <p class="page-subtitle">Loading records...</p>
                </div>
            </div>
            <div class="card p-6">
                <div class="skeleton-line mb-4"></div>
                <div class="skeleton-line mb-4"></div>
                <div class="skeleton-line mb-4"></div>
                <div class="skeleton-line"></div>
            </div>
        `;
    }

    function renderErrorState(message, retryFn) {
        return `
            <div class="card empty-state">
                <div class="empty-icon text-danger">⚠️</div>
                <h3>Unable to Load Data</h3>
                <p class="text-muted mb-4">${escapeHtml(message)}</p>
                <button class="btn btn-primary btn-sm" id="retry-btn">Retry</button>
            </div>
        `;
    }

    // Expose public API on window for onclick hooks
    window.BrightloopApp = {
        switchTab,
        refresh: () => loadCurrentTabData(true),
    };

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();

