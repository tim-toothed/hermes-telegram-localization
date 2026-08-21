"""Structured translation for background self-improvement notifications."""

from __future__ import annotations

import re


_SOURCE_PREFIX = "💾 Self-improvement review: "
_TARGET_PREFIX = "💾 Фоновое обновление: "
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
    r"^(?P<icon>📝 )?Skill '(?P<name>[a-z0-9][a-z0-9._-]*)' "
    r"(?P<action>patched|created|rewritten|updated|deleted)(?P<punct>[.!]?)$"
)
_FULL_REWRITE_PATTERN = re.compile(
    r"^Skill '(?P<name>[a-z0-9][a-z0-9._-]*)' updated \(full rewrite\)\.$"
)
_PATCHED_SKILL_FILE_PATTERN = re.compile(
    r"^Patched (?P<path>[^\r\n]+?) in skill "
    r"'(?P<name>[a-z0-9][a-z0-9._-]*)' \((?P<count>[1-9][0-9]*) "
    r"(?P<noun>replacement|replacements)\)\.$"
)
_ALLOWED_SKILL_FILE_ROOTS = {"references", "templates", "scripts", "assets"}


def _is_valid_skill_file_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return False
    if parts[-1] == "SKILL.md" and len(parts) in {1, 2}:
        return True
    return len(parts) >= 2 and parts[0] in _ALLOWED_SKILL_FILE_ROOTS


def _translate_known_action(action: str) -> str | None:
    exact = _EXACT_ACTIONS.get(action)
    if exact is not None:
        return exact

    if action == "Skill updated":
        return "Навык обновлён"

    full_rewrite = _FULL_REWRITE_PATTERN.fullmatch(action)
    if full_rewrite is not None:
        return f"Навык '{full_rewrite.group('name')}' полностью переписан."

    patched_file = _PATCHED_SKILL_FILE_PATTERN.fullmatch(action)
    if patched_file is not None:
        path = patched_file.group("path")
        count = int(patched_file.group("count"))
        noun = patched_file.group("noun")
        if not _is_valid_skill_file_path(path):
            return None
        if (count == 1) != (noun == "replacement"):
            return None
        return (
            f"Изменён файл {path} в навыке "
            f"'{patched_file.group('name')}' (замен: {count})."
        )

    match = _SKILL_PATTERN.fullmatch(action)
    if match is None:
        return None
    icon = match.group("icon") or ""
    return (
        f"{icon}Навык '{match.group('name')}' "
        f"{_SKILL_ACTIONS[match.group('action')]}{match.group('punct')}"
    )


def translate_background_review_notification(text: str) -> str:
    """Translate only a fully recognized system envelope; otherwise fail open."""
    if not text.startswith(_SOURCE_PREFIX):
        return text

    actions = text[len(_SOURCE_PREFIX) :].split(_SEPARATOR)
    # The producer does not escape its action separator inside file paths.
    # A mixed summary containing a file-patch action is therefore ambiguous:
    # the same bytes can represent either multiple actions or one legal path.
    # Translate single file-patch notices only; fail open for mixed summaries.
    if len(actions) > 1 and any(
        _PATCHED_SKILL_FILE_PATTERN.fullmatch(action) is not None
        for action in actions
    ):
        return text

    translated: list[str] = []
    for action in actions:
        localized = _translate_known_action(action)
        if localized is None:
            return text
        translated.append(localized)
    return _TARGET_PREFIX + _SEPARATOR.join(translated)
