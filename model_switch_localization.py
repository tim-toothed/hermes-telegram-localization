"""Structured localization for model-switch confirmation cards."""

from __future__ import annotations

import re


_FIRST_LINE = re.compile(r"^Model switched to (?P<model>`[^`\n]+`|[^\n]+)$")
_CAPABILITIES = {
    "reasoning": "рассуждение",
    "tools": "инструменты",
    "vision": "изображения",
    "pdf": "PDF",
    "structured output": "структурированный вывод",
    "audio": "аудио",
    "video": "видео",
}


def _translate_line(line: str) -> str | None:
    if line.startswith("Provider: "):
        return "Провайдер: " + line[len("Provider: ") :]
    match = re.fullmatch(r"Context: (?P<tokens>.+) tokens", line)
    if match:
        return f"Контекст: {match.group('tokens')} токенов"
    match = re.fullmatch(r"Max output: (?P<tokens>.+) tokens", line)
    if match:
        return f"Максимальный вывод: {match.group('tokens')} токенов"
    if line.startswith("Capabilities: "):
        values = line[len("Capabilities: ") :].split(", ")
        localized = [_CAPABILITIES.get(value.lower(), value) for value in values]
        return "Возможности: " + ", ".join(localized)
    if line == "Prompt caching: enabled":
        return "Кеширование промптов: включено"
    if line.startswith("Warning: "):
        return "Предупреждение: " + line[len("Warning: ") :]
    if line == "Saved to config.yaml (`--global`)":
        return "Сохранено в config.yaml (`--global`)"
    if line == "_(session only — add `--global` to persist)_":
        # The Telegram formatter accepts standard *italic*, not underscore italic.
        return "*Только для этой сессии — добавьте `--global`, чтобы сохранить.*"
    return None


def translate_model_switch_card(text: str) -> str:
    """Translate a fully recognized model card and preserve dynamic identifiers."""
    lines = text.splitlines()
    if not lines:
        return text
    first = _FIRST_LINE.fullmatch(lines[0])
    if first is None:
        return text

    translated = [f"Модель изменена на {first.group('model')}"]
    for line in lines[1:]:
        localized = _translate_line(line)
        if localized is None:
            return text
        translated.append(localized)
    return "\n".join(translated)
