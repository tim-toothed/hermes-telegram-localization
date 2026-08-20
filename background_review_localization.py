"""Structured translation for background self-improvement notifications."""

from __future__ import annotations

import re


_SOURCE_PREFIX = "💾 Self-improvement review: "
_TARGET_PREFIX = "💾 Проверка самообучения: "
_SEPARATOR = " · "
_EXACT_ACTIONS = {
    "Memory updated": "Память обновлена",
    "Memory updated.": "Память обновлена.",
    "User profile updated": "Профиль пользователя обновлён",
    "User profile updated.": "Профиль пользователя обновлён.",
}
_SKILL_ACTIONS = {
    "patched": "изменён",
    "created": "создан",
    "rewritten": "переписан",
    "updated": "обновлён",
    "deleted": "удалён",
}
_SKILL_PATTERN = re.compile(
    r"^(?P<icon>📝 )?Skill '(?P<name>[^' ·]+)' "
    r"(?P<action>patched|created|rewritten|updated|deleted)(?P<punct>[.!]?)$"
)


def _translate_known_action(action: str) -> str | None:
    exact = _EXACT_ACTIONS.get(action)
    if exact is not None:
        return exact

    match = _SKILL_PATTERN.fullmatch(action)
    if match is None:
        return None
    icon = match.group("icon") or ""
    return (
        f"{icon}Skill '{match.group('name')}' "
        f"{_SKILL_ACTIONS[match.group('action')]}{match.group('punct')}"
    )


def translate_background_review_notification(text: str) -> str:
    """Translate only a fully recognized system envelope; otherwise fail open."""
    if not text.startswith(_SOURCE_PREFIX):
        return text

    actions = text[len(_SOURCE_PREFIX) :].split(_SEPARATOR)
    translated: list[str] = []
    for action in actions:
        localized = _translate_known_action(action)
        if localized is None:
            return text
        translated.append(localized)
    return _TARGET_PREFIX + _SEPARATOR.join(translated)
