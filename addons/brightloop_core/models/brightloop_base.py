# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.brightloop_base
#
# Foundation abstract mixin for all Brightloop models.
#
# PHASE 1 SCOPE
# -------------
# Establishes:
#   - Centralized logging convention
#   - Currency-aware financial helpers (stub)
#   - Timezone-aware date helpers (stub)
#   - Consistent error handling pattern
#   - Safe transaction helpers (stub)
#
# Business logic (subscriptions, billing, invoicing) is NOT implemented here.
# That belongs to Phase 3+.
# =============================================================================

import logging
from datetime import datetime, timezone

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# ---------------------------------------------------------------------------
# Module-level logger
# Convention: always use __name__ so the logger hierarchy mirrors the module
# hierarchy, making log filtering straightforward.
# ---------------------------------------------------------------------------
_logger = logging.getLogger(__name__)


class BrightloopBase(models.AbstractModel):
    """
    Abstract mixin that every Brightloop model should inherit.

    Provides a consistent foundation for:
    - Logging
    - Currency awareness
    - Timezone awareness
    - Error handling
    - Transaction safety

    Usage::

        class MyBrightloopModel(models.Model):
            _name = 'brightloop.my.model'
            _inherit = ['brightloop.base']
            _description = 'My Model'
    """

    _name = 'brightloop.base'
    _description = 'Brightloop Base Mixin'

    # -------------------------------------------------------------------------
    # Company awareness
    # Every Brightloop record belongs to a company.
    # Odoo's multi-company support is handled automatically when this field
    # is present and the model has _check_company_auto = True.
    # -------------------------------------------------------------------------
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        readonly=False,
        default=lambda self: self.env.company,
        index=True,
        help='Company that owns this record.',
    )

    # -------------------------------------------------------------------------
    # Audit timestamps
    # Odoo provides create_date / write_date automatically, but we expose
    # them here so subclasses can always reference them in views/reports.
    # -------------------------------------------------------------------------
    # (create_date, write_date, create_uid, write_uid are inherited from Model)

    # =========================================================================
    # LOGGING HELPERS
    # =========================================================================

    def _bl_log_info(self, message: str, *args) -> None:
        """Log an INFO message under the brightloop namespace."""
        _logger.info('[%s] ' + message, self._name, *args)

    def _bl_log_warning(self, message: str, *args) -> None:
        """Log a WARNING message under the brightloop namespace."""
        _logger.warning('[%s] ' + message, self._name, *args)

    def _bl_log_error(self, message: str, *args) -> None:
        """Log an ERROR message under the brightloop namespace."""
        _logger.error('[%s] ' + message, self._name, *args)

    # =========================================================================
    # ERROR HANDLING HELPERS
    # =========================================================================

    @staticmethod
    def _bl_raise_user_error(message: str) -> None:
        """
        Raise a user-visible error.

        Use this for validation failures that are the user's fault and should
        display a friendly dialog in the Odoo UI.

        :param message: Human-readable error message.
        :raises UserError: Always.
        """
        raise UserError(message)

    @staticmethod
    def _bl_raise_validation_error(message: str) -> None:
        """
        Raise a validation error (typically from @api.constrains).

        :param message: Human-readable validation message.
        :raises ValidationError: Always.
        """
        raise ValidationError(message)

    # =========================================================================
    # TIMEZONE HELPERS
    # =========================================================================

    @api.model
    def _bl_now_utc(self) -> datetime:
        """
        Return the current UTC datetime as a timezone-aware object.

        Convention: all Brightloop timestamps are stored in UTC and converted
        to the user's timezone only in the presentation layer.
        """
        return datetime.now(tz=timezone.utc)

    @api.model
    def _bl_user_timezone(self) -> str:
        """
        Return the current user's configured timezone string.

        Falls back to 'UTC' if the user has no timezone set.
        """
        return self.env.user.tz or 'UTC'

    # =========================================================================
    # CURRENCY HELPERS (stubs — expanded in Phase 3 billing module)
    # =========================================================================

    @api.model
    def _bl_company_currency(self):
        """
        Return the currency of the current company.

        Phase 1 stub — full currency conversion logic lives in the billing
        module (Phase 4).
        """
        return self.env.company.currency_id

    # =========================================================================
    # TRANSACTION SAFETY HELPERS (stubs — expanded in Phase 3+)
    # =========================================================================

    @api.model
    def _bl_ensure_single_record(self) -> None:
        """
        Assert that self is a single record (not an empty or multi-record set).

        Pattern::

            def my_action(self):
                self._bl_ensure_single_record()
                # safe to access self.id, self.name, etc.

        :raises UserError: If self is empty or contains multiple records.
        """
        self.ensure_one()

    # =========================================================================
    # INTERNAL UTILITIES
    # =========================================================================

    @api.model
    def _bl_module_name(self) -> str:
        """Return the technical name of this module for logging/reference."""
        return 'brightloop_core'
