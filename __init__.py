"""Hermes Telegram localization plugin entrypoint."""

from __future__ import annotations

import logging
from typing import Any

from .config import LocalizationConfig
from .cron_delivery import install_cron_delivery_wrapper
from .menu_filter import install_menu_filter
from .reporter import LocalizationReporter
from .runtime import (
    LocalizationState,
    install_background_review_wrapper,
    install_runtime_boundary_wrappers,
)

logger = logging.getLogger(__name__)

_STATE: LocalizationState | None = None


def register(ctx: Any) -> None:
    global _STATE

    config = LocalizationConfig.load(
        custom_rules_dir=getattr(ctx, "rules_dir", None),
        env_prefix="HERMES_TELEGRAM_LOCALIZATION_",
    )
    reporter = LocalizationReporter(getattr(ctx, "data_dir", None))
    _STATE = LocalizationState(config=config, reporter=reporter)

    reporter.emit(
        {
            "event": "startup",
            "locale": config.locale,
            "rule_count": len(config.rules),
            "manifest_version": "0.3.10",
        }
    )

    try:
        runtime_status = install_runtime_boundary_wrappers(_STATE)
    except Exception as exc:
        runtime_status = "error"
        logger.warning(
            "hermes-telegram-localization: runtime wrapper install failed: %s",
            exc,
            exc_info=True,
        )
    reporter.emit({"event": "boundary_wrappers", "status": runtime_status})
    _STATE.boundaries["runtime_boundary_wrappers"] = runtime_status

    try:
        menu_filter_status = install_menu_filter(_STATE)
    except Exception as exc:
        menu_filter_status = "error"
        logger.warning(
            "hermes-telegram-localization: menu filter install failed: %s",
            exc,
            exc_info=True,
        )
    reporter.emit({"event": "menu_filter", "status": menu_filter_status})
    _STATE.boundaries["TelegramPlatformAdapter._send_command_menu"] = (
        menu_filter_status
    )

    # Lifecycle sends deliberately stay untouched. A failed Telegram restart or
    # shutdown notification must never turn Gateway startup/stop into a failure.
    _STATE.boundaries[
        "GatewayRunner._notify_active_sessions_of_shutdown"
    ] = "disabled_lifecycle_safety"
    _STATE.boundaries[
        "GatewayRunner._send_restart_notification"
    ] = "disabled_lifecycle_safety"
    startup_statuses = {
        "_send_restart_notification": "disabled",
        "_redeliver_pending_obligations": "disabled",
    }
    reporter.emit({"event": "startup_localization", "boundaries": startup_statuses})
    reporter.emit({"event": "shutdown_localization", "status": "disabled"})

    try:
        cron_delivery_status = install_cron_delivery_wrapper(_STATE)
    except Exception as exc:
        cron_delivery_status = "error"
        logger.warning(
            "hermes-telegram-localization: cron delivery install failed: %s",
            exc,
            exc_info=True,
        )
    reporter.emit({"event": "cron_delivery", "status": cron_delivery_status})
    _STATE.boundaries["cron_delivery_wrapper"] = cron_delivery_status

    try:
        background_review_status = install_background_review_wrapper(_STATE)
    except Exception as exc:
        background_review_status = "error"
        logger.warning(
            "hermes-telegram-localization: background review install failed: %s",
            exc,
            exc_info=True,
        )
    reporter.emit(
        {"event": "background_review_localization", "status": background_review_status}
    )
    _STATE.boundaries[
        "background_review.summarize_background_review_actions"
    ] = background_review_status

    def on_pre_gateway_dispatch(**kwargs: Any) -> None:
        if _STATE is None:
            return None
        _STATE.reporter.emit({"event": "pre_gateway_dispatch", "kwargs": list(kwargs.keys())})
        return None

    register_hook = getattr(ctx, "register_hook", None)
    if callable(register_hook):
        register_hook("pre_gateway_dispatch", on_pre_gateway_dispatch)
