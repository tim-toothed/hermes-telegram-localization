"""PROCVETAEV Russian localization for Hermes Telegram runtime."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .cron_delivery import install_cron_delivery_wrapper
from .delivery_recovery_activation import install_delivery_recovery_localization
from .menu_filter import HIDDEN_TELEGRAM_COMMANDS, install_telegram_menu_filter
from .reporter import JsonlReporter
from .runtime import (
    RuntimeState,
    activate_from_gateway_event,
)
from .shutdown_localization import install_shutdown_localization
from .translator import Catalog


_PLUGIN_DIR = Path(__file__).resolve().parent
_STATE: RuntimeState | None = None


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except Exception:
        import os

        configured = os.getenv("HERMES_HOME")
        return Path(configured) if configured else Path.home() / ".hermes"


def _status_command(_raw_args: str = "") -> str:
    if _STATE is None:
        return "Плагин локализации не инициализирован."
    return _STATE.summary()


def _setup_cli(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action",
        nargs="?",
        choices=("status",),
        default="status",
        help="Show plugin load and Telegram boundary status",
    )
    parser.set_defaults(func=_cli_handler)


def _cli_handler(_args: argparse.Namespace) -> int:
    if _STATE is None:
        print("Плагин локализации не загружен.")
        return 1
    print(_STATE.summary())
    print(f"Отчёт: {_STATE.reporter.path}")
    return 0


def register(ctx: Any) -> None:
    global _STATE
    catalog = Catalog.from_yaml(_PLUGIN_DIR / "rules" / "ru.yaml")
    report_path = (
        _hermes_home()
        / "plugin-data"
        / "procvetaev-localization"
        / "reports"
        / "localization.jsonl"
    )
    reporter = JsonlReporter(report_path)
    _STATE = RuntimeState(catalog, reporter)
    reporter.emit(
        {
            "event": "plugin_register",
            "status": "loaded",
            "profile": getattr(ctx, "profile_name", "default"),
            "rule_count": catalog.rule_count,
            "report_path": str(report_path),
        }
    )
    try:
        menu_filter_status = install_telegram_menu_filter()
    except Exception as exc:
        menu_filter_status = "install_failed"
        reporter.emit(
            {
                "event": "telegram_menu_filter",
                "status": menu_filter_status,
                "error_type": type(exc).__name__,
            }
        )
    else:
        reporter.emit(
            {
                "event": "telegram_menu_filter",
                "status": menu_filter_status,
                "hidden_command_count": len(HIDDEN_TELEGRAM_COMMANDS),
            }
        )
    _STATE.boundaries["hermes_cli.commands.telegram_menu_commands"] = (
        menu_filter_status
    )

    try:
        shutdown_status = install_shutdown_localization(_STATE)
    except Exception as exc:
        shutdown_status = "install_failed"
        reporter.emit(
            {
                "event": "shutdown_localization",
                "status": shutdown_status,
                "error_type": type(exc).__name__,
            }
        )
    else:
        reporter.emit(
            {
                "event": "shutdown_localization",
                "status": shutdown_status,
            }
        )
    _STATE.boundaries[
        "GatewayRunner._notify_active_sessions_of_shutdown"
    ] = shutdown_status

    try:
        cron_delivery_status = install_cron_delivery_wrapper(_STATE)
    except Exception as exc:
        cron_delivery_status = "install_failed"
        reporter.emit(
            {
                "event": "cron_delivery",
                "status": cron_delivery_status,
                "error_type": type(exc).__name__,
            }
        )
    else:
        reporter.emit(
            {
                "event": "cron_delivery",
                "status": cron_delivery_status,
            }
        )
    _STATE.boundaries["cron.scheduler._deliver_result"] = cron_delivery_status

    try:
        delivery_recovery_status = install_delivery_recovery_localization(_STATE)
    except Exception as exc:
        delivery_recovery_status = "install_failed"
        reporter.emit(
            {
                "event": "delivery_recovery_localization",
                "status": delivery_recovery_status,
                "error_type": type(exc).__name__,
            }
        )
    else:
        reporter.emit(
            {
                "event": "delivery_recovery_localization",
                "status": delivery_recovery_status,
            }
        )
    _STATE.boundaries[
        "GatewayRunner._redeliver_pending_obligations"
    ] = delivery_recovery_status

    def on_pre_gateway_dispatch(**kwargs: Any) -> None:
        if _STATE is None:
            return None
        activate_from_gateway_event(
            event=kwargs.get("event"),
            gateway=kwargs.get("gateway"),
            state=_STATE,
        )
        return None

    ctx.register_hook("pre_gateway_dispatch", on_pre_gateway_dispatch)
    ctx.register_command(
        name="localization",
        handler=_status_command,
        description="Состояние русской локализации Telegram",
    )
    ctx.register_cli_command(
        name="localization",
        help="Inspect Telegram localization plugin status",
        setup_fn=_setup_cli,
        handler_fn=_cli_handler,
        description="Show plugin load state, installed runtime boundaries, counters, and report path.",
    )
