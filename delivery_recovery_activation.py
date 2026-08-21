"""Activate Telegram localization before delivery-ledger recovery replay."""

from __future__ import annotations

from functools import wraps
from typing import Any

from .runtime import RuntimeState, install_on_adapter


_STATE_ATTR = "_procvetaev_delivery_recovery_localization_state"
_WRAPPED_ATTR = "_procvetaev_delivery_recovery_localization_wrapped"


def install_delivery_recovery_localization(state: RuntimeState) -> str:
    """Wrap startup replay activation without changing ledger behavior."""
    from gateway.run import GatewayRunner

    setattr(GatewayRunner, _STATE_ATTR, state)
    original = getattr(GatewayRunner, "_redeliver_pending_obligations", None)
    if not callable(original):
        return "method_missing"
    if getattr(original, _WRAPPED_ATTR, False):
        return "already_installed"

    @wraps(original)
    async def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        current_state = getattr(type(self), _STATE_ATTR, state)
        try:
            for platform, adapter in getattr(self, "adapters", {}).items():
                platform_name = str(getattr(platform, "value", str(platform))).lower()
                if platform_name == "telegram":
                    install_on_adapter(adapter, current_state)
        except Exception as exc:
            try:
                current_state.reporter.emit(
                    {
                        "event": "delivery_recovery_localization",
                        "status": "activation_failed",
                        "error_type": type(exc).__name__,
                    }
                )
            except Exception:
                pass
        return await original(self, *args, **kwargs)

    setattr(wrapped, _WRAPPED_ATTR, True)
    setattr(GatewayRunner, "_redeliver_pending_obligations", wrapped)
    return "installed"
