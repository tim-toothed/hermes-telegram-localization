"""Structured translation for delivery-ledger recovery notices."""

from __future__ import annotations


_SOURCE_PREFIX = (
    "♻️ Recovered reply — the gateway restarted during delivery, "
    "so this may be a duplicate:\n\n"
)
_TARGET_PREFIX = (
    "♻️ Ответ восстановлен после перезапуска — возможно, "
    "это сообщение уже приходило:\n\n"
)


def translate_delivery_recovery_notice(text: str) -> str:
    """Translate only the fixed recovery prefix; preserve reply content literally."""
    if not text.startswith(_SOURCE_PREFIX):
        return text
    return _TARGET_PREFIX + text[len(_SOURCE_PREFIX) :]
