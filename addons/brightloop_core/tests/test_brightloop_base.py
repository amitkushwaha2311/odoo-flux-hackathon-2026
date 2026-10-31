# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.tests.test_brightloop_base
#
# Tests for the BrightloopBase abstract mixin.
# These run inside the Odoo test framework via:
#
#   docker compose exec odoo odoo -d brightloop_dev \
#       --test-enable --test-tags brightloop_core \
#       -i brightloop_core --stop-after-init
# =============================================================================

import logging
from datetime import timezone

from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class TestBrightloopBase(TransactionCase):
    """
    Phase 1 tests for the BrightloopBase abstract mixin.

    Validates that the foundation mixin is importable, that its helpers
    return correct types, and that the module loads cleanly.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Use res.company as a concrete model to exercise the mixin helpers.
        # brightloop.base is abstract and cannot be instantiated directly.
        cls.company = cls.env.company

    def test_module_loads(self):
        """The brightloop_core module must be installed and loadable."""
        module = self.env['ir.module.module'].search(
            [('name', '=', 'brightloop_core'), ('state', '=', 'installed')],
            limit=1,
        )
        self.assertTrue(
            module,
            "brightloop_core must be in 'installed' state",
        )

    def test_company_currency_returns_currency(self):
        """_bl_company_currency() must return a res.currency record."""
        # Access via a company record (which does NOT inherit brightloop.base,
        # but we can call the method directly via the abstract model).
        abstract = self.env['brightloop.base']
        currency = abstract._bl_company_currency()
        self.assertTrue(
            currency,
            "_bl_company_currency() must return a non-empty currency record",
        )
        self.assertEqual(
            currency._name,
            'res.currency',
            "_bl_company_currency() must return a res.currency record",
        )

    def test_now_utc_is_timezone_aware(self):
        """_bl_now_utc() must return a UTC-aware datetime."""
        abstract = self.env['brightloop.base']
        now = abstract._bl_now_utc()
        self.assertIsNotNone(now.tzinfo, "_bl_now_utc() must be timezone-aware")
        self.assertEqual(
            now.tzinfo,
            timezone.utc,
            "_bl_now_utc() must return UTC timezone",
        )

    def test_user_timezone_returns_string(self):
        """_bl_user_timezone() must return a non-empty string."""
        abstract = self.env['brightloop.base']
        tz = abstract._bl_user_timezone()
        self.assertIsInstance(tz, str, "_bl_user_timezone() must return a string")
        self.assertTrue(len(tz) > 0, "_bl_user_timezone() must not be empty")

    def test_module_name_returns_string(self):
        """_bl_module_name() must return 'brightloop_core'."""
        abstract = self.env['brightloop.base']
        name = abstract._bl_module_name()
        self.assertEqual(name, 'brightloop_core')
