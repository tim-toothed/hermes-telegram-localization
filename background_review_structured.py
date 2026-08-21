"""Structured producer boundary for background-review summaries."""

from __future__ import annotations

from collections import OrderedDict
from functools import wraps
from threading import Lock
from typing import Any, Callable


_SOURCE_PREFIX = "💾 Self-improvement review: "
_TARGET_PREFIX = "💾 Фоновое обновление: "
_SEPARATOR = " · "
_MAX_ENTRIES = 256
_LOCK = Lock()
_LOCALIZED_ENVELOPES: OrderedDict[str, None] = OrderedDict()
_WRAPPED_ATTR = "_procvetaev_background_review_structured_wrapped"


def _remember_localized_envelope(actions: list[str]) -> None:
    unique_actions = list(dict.fromkeys(actions))
    source = _SOURCE_PREFIX + _SEPARATOR.join(unique_actions)
    with _LOCK:
        _LOCALIZED_ENVELOPES[source] = None
        _LOCALIZED_ENVELOPES.move_to_end(source)
        while len(_LOCALIZED_ENVELOPES) > _MAX_ENTRIES:
            _LOCALIZED_ENVELOPES.popitem(last=False)


def translate_registered_localized_envelope(source: str) -> str | None:
    """Translate only the prefix of an exact producer-registered envelope."""
    with _LOCK:
        if source not in _LOCALIZED_ENVELOPES:
            return None
        _LOCALIZED_ENVELOPES.move_to_end(source)
    return _TARGET_PREFIX + source[len(_SOURCE_PREFIX) :]


def install_structured_background_review_localization(
    translate_action: Callable[[str], str | None],
) -> str:
    """Localize a producer action list only when every action is recognized."""
    from agent import background_review

    original = getattr(background_review, "summarize_background_review_actions", None)
    if not callable(original):
        return "method_missing"
    if getattr(original, _WRAPPED_ATTR, False):
        return "already_installed"

    @wraps(original)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        actions = original(*args, **kwargs)
        try:
            localized = [translate_action(action) for action in actions]
            if actions and all(item is not None for item in localized):
                result = [str(item) for item in localized]
                _remember_localized_envelope(result)
                return result
        except Exception:
            pass
        return actions

    setattr(wrapped, _WRAPPED_ATTR, True)
    setattr(background_review, "summarize_background_review_actions", wrapped)
    return "installed"
