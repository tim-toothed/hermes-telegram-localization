"""Render compact, user-facing Cron delivery notifications."""

from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
from typing import Any

from .runtime import RuntimeState


_PREWRAPPED: ContextVar[bool] = ContextVar(
    "procvetaev_cron_delivery_prewrapped", default=False
)
_STATE_ATTR = "_procvetaev_cron_delivery_state"
_DELIVER_WRAPPED_ATTR = "_procvetaev_cron_delivery_wrapped"
_CONFIG_WRAPPED_ATTR = "_procvetaev_cron_config_wrapped"


def _report(state: RuntimeState, payload: dict[str, Any]) -> None:
    try:
        state.reporter.emit(payload)
    except Exception:
        pass


def install_cron_delivery_wrapper(state: RuntimeState) -> str:
    """Keep the stock Cron header while omitting its management footer."""
    from cron import scheduler

    setattr(scheduler, _STATE_ATTR, state)
    original_deliver = getattr(scheduler, "_deliver_result", None)
    original_load_config = getattr(scheduler, "load_config", None)
    if not callable(original_deliver) or not callable(original_load_config):
        return "method_missing"

    if not getattr(original_load_config, _CONFIG_WRAPPED_ATTR, False):
        @wraps(original_load_config)
        def load_config_wrapped(*args: Any, **kwargs: Any) -> Any:
            config = original_load_config(*args, **kwargs)
            if not _PREWRAPPED.get() or not isinstance(config, dict):
                return config
            adjusted = dict(config)
            cron_config = dict(adjusted.get("cron", {}) or {})
            cron_config["wrap_response"] = False
            adjusted["cron"] = cron_config
            return adjusted

        setattr(load_config_wrapped, _CONFIG_WRAPPED_ATTR, True)
        setattr(scheduler, "load_config", load_config_wrapped)

    if getattr(original_deliver, _DELIVER_WRAPPED_ATTR, False):
        return "already_installed"

    @wraps(original_deliver)
    def deliver_wrapped(
        job: dict,
        content: str,
        adapters: Any = None,
        loop: Any = None,
    ) -> Any:
        current_state = getattr(scheduler, _STATE_ATTR, state)
        try:
            config = original_load_config()
            cron_config = config.get("cron", {}) if isinstance(config, dict) else {}
            if not isinstance(cron_config, dict):
                cron_config = {}
            wrap_response = cron_config.get("wrap_response", True)
            if not wrap_response:
                return original_deliver(job, content, adapters=adapters, loop=loop)

            task_name = job.get("name", job.get("id", ""))
            wrapped_content = (
                f"⏰ {task_name}\n"
                f"-------------\n\n"
                f"{content}"
            )
            _report(
                current_state,
                {
                    "event": "cron_delivery",
                    "status": "management_footer_removed",
                },
            )
        except Exception as exc:
            _report(
                current_state,
                {
                    "event": "cron_delivery",
                    "status": "wrapper_failed",
                    "error_type": type(exc).__name__,
                },
            )
            return original_deliver(job, content, adapters=adapters, loop=loop)

        token = _PREWRAPPED.set(True)
        try:
            return original_deliver(
                job, wrapped_content, adapters=adapters, loop=loop
            )
        finally:
            _PREWRAPPED.reset(token)

    setattr(deliver_wrapped, _DELIVER_WRAPPED_ATTR, True)
    setattr(scheduler, "_deliver_result", deliver_wrapped)
    return "installed"
