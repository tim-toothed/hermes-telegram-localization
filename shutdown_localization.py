"""Activate Telegram localization before Gateway shutdown notices are sent."""

from __future__ import annotations

from functools import wraps
from typing import Any

from .runtime import RuntimeState, install_on_adapter


_STATE_ATTR = "_procvetaev_shutdown_localization_state"
_WRAPPED_ATTR = "_procvetaev_shutdown_localization_wrapped"


def install_shutdown_localization(state: RuntimeState) -> str:
    """Wrap the narrow shutdown-notification boundary, preserving fail-open stop."""
    from gateway.run import GatewayRunner

    setattr(GatewayRunner, _STATE_ATTR, state)
    original = getattr(GatewayRunner, "_notify_active_sessions_of_shutdown", None)
    if not callable(original):
        return "method_missing"
    if getattr(original, _WRAPPED_ATTR, False):
        return "already_installed"

    @wraps(original)
    async def wrapped(runner: Any, *args: Any, **kwargs: Any) -> Any:
        current_state = getattr(type(runner), _STATE_ATTR, state)
        installed = 0
        try:
            adapters = getattr(runner, "adapters", {}) or {}
            for platform, adapter in list(adapters.items()):
                platform_name = str(getattr(platform, "value", platform)).lower()
                if platform_name == "telegram" and install_on_adapter(adapter, current_state):
                    installed += 1
            current_state.reporter.emit(
                {
                    "event": "shutdown_localization",
                    "status": "activated",
                    "installed_adapter_count": installed,
                }
            )
        except Exception as exc:
            current_state.reporter.emit(
                {
                    "event": "shutdown_localization",
                    "status": "activation_failed",
                    "error_type": type(exc).__name__,
                }
            )
        return await original(runner, *args, **kwargs)

    setattr(wrapped, _WRAPPED_ATTR, True)
    setattr(GatewayRunner, "_notify_active_sessions_of_shutdown", wrapped)
    return "installed"
