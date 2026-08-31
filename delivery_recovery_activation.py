"""Activate Telegram localization before covered startup lifecycle sends."""

from __future__ import annotations

from functools import wraps
from typing import Any

from .runtime import RuntimeState, install_on_adapter


_STATE_ATTR = "_hermes_telegram_delivery_recovery_localization_state"
_WRAPPED_ATTR = "_hermes_telegram_delivery_recovery_localization_wrapped"


def install_delivery_recovery_localization(state: RuntimeState) -> dict[str, str]:
    """Wrap covered startup sends without changing lifecycle behavior."""
    from gateway.run import GatewayRunner

    setattr(GatewayRunner, _STATE_ATTR, state)
    statuses: dict[str, str] = {}
    for method_name in (
        "_send_restart_notification",
        "_redeliver_pending_obligations",
    ):
        original = getattr(GatewayRunner, method_name, None)
        if not callable(original):
            statuses[method_name] = "method_missing"
            continue
        if getattr(original, _WRAPPED_ATTR, False):
            statuses[method_name] = "already_installed"
            continue

        @wraps(original)
        async def wrapped(
            self: Any,
            *args: Any,
            _original: Any = original,
            _method_name: str = method_name,
            **kwargs: Any,
        ) -> Any:
            current_state = getattr(type(self), _STATE_ATTR, state)
            try:
                for platform, adapter in getattr(self, "adapters", {}).items():
                    platform_name = str(
                        getattr(platform, "value", str(platform))
                    ).lower()
                    if platform_name == "telegram":
                        install_on_adapter(adapter, current_state)
            except Exception as exc:
                try:
                    current_state.reporter.emit(
                        {
                            "event": "startup_localization",
                            "method": _method_name,
                            "status": "activation_failed",
                            "error_type": type(exc).__name__,
                        }
                    )
                except Exception:
                    pass
            return await _original(self, *args, **kwargs)

        setattr(wrapped, _WRAPPED_ATTR, True)
        setattr(GatewayRunner, method_name, wrapped)
        statuses[method_name] = "installed"
    return statuses
