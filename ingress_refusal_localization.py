"""Fail-open localization for Hermes messaging-admission refusals."""

from __future__ import annotations

import re

_REFUSAL = re.compile(
    r"^⚠️ Hermes refused this message \((?P<reason>[^)]+)\), so it was not saved "
    r"or answered\. Ask the operator to check gateway\.log\.$"
)

_MEDIA_FIELDS = frozenset(
    {
        "media_urls",
        "media_types",
        "media_text_inlined",
        "media_types_length",
        "media_text_inlined_length",
        "media_filenames",
        "media_filenames_length",
    }
)
_MESSAGE_FIELDS = frozenset(
    {
        "text",
        "auto_skill",
        "channel_prompt",
        "channel_context",
        "reply_expected",
    }
)


def translate_ingress_refusal(text: str) -> str:
    """Translate only the finite user-visible v0.23 admission refusal envelope."""
    match = _REFUSAL.fullmatch(text)
    if match is None:
        return text
    reason = match["reason"]
    field = reason.removeprefix("invalid_params: ")
    if field in _MEDIA_FIELDS:
        detail = "из-за ошибки обработки вложения"
    elif field in _MESSAGE_FIELDS:
        detail = "из-за ошибки обработки сообщения"
    elif reason == "invalid_params":
        detail = "из-за некорректных данных сообщения"
    else:
        return text
    return (
        f"⚠️ Сообщение отклонено {detail} и не было сохранено или обработано. "
        "Отправьте его ещё раз. Если ошибка повторится, "
        "[напишите в поддержку REDD](https://t.me/PROCVESUP)."
    )
