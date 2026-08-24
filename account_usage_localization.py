"""Conservative localization for structured /usage and /context account blocks."""

from __future__ import annotations

import re


_PENDING_DETAILS = {
    "_(Detailed usage available after the first agent response)_",
    "_(Подробное использование доступно после первого ответа агента)_",
}
_PENDING_DETAIL_ITALIC = "*(Подробное использование доступно после первого ответа агента)*"
_HEADER = re.compile(
    r"^📈 (?:(?P<bold>\*\*)(?P<bold_title>Account limits|Nous credits)(?P=bold)"
    r"|(?P<plain_title>Account limits|Nous credits))$"
)
_PROVIDER_PLAN = re.compile(r"^Provider: (?P<provider>.+?) \((?P<plan>[^()]+)\)$")
_PROVIDER = re.compile(r"^Provider: (?P<provider>.+)$")
_WINDOW = re.compile(
    r"^(?P<label>[^:\n]+): (?P<remaining>[0-9][0-9.,]*)% remaining "
    r"\((?P<used>[0-9][0-9.,]*)% used\)(?P<suffix>.*)$"
)
_RESET_DAYS_HOURS = re.compile(
    r"^in (?P<days>[0-9]+)d (?P<hours>[0-9]+)h (?P<timestamp>\(.+\))$"
)
_RESET_HOURS_MINUTES = re.compile(
    r"^in (?P<hours>[0-9]+)h (?P<minutes>[0-9]+)m (?P<timestamp>\(.+\))$"
)
_RESET_MINUTES = re.compile(r"^in (?P<minutes>[0-9]+)m (?P<timestamp>\(.+\))$")
_RESET_NOW = re.compile(r"^now (?P<timestamp>\(.+\))$")
_BANKED = re.compile(
    r"^You have (?P<count>[0-9]+) resets? banked - use /usage reset to activate$"
)
_CREDITS_REMAINING = re.compile(
    r"^(?P<remaining>\$[0-9][0-9,.]*) of (?P<total>\$[0-9][0-9,.]*) left$"
)

_LABELS = {
    "Session": "Сеанс",
    "Weekly": "Неделя",
    "API key quota": "Квота API-ключа",
    "Subscription": "Подписка",
}


def _translate_reset(value: str) -> str | None:
    match = _RESET_DAYS_HOURS.fullmatch(value)
    if match:
        return (
            f"через {match['days']} д {match['hours']} ч "
            f"{match['timestamp']}"
        )
    match = _RESET_HOURS_MINUTES.fullmatch(value)
    if match:
        return (
            f"через {match['hours']} ч {match['minutes']} мин "
            f"{match['timestamp']}"
        )
    match = _RESET_MINUTES.fullmatch(value)
    if match:
        return f"через {match['minutes']} мин {match['timestamp']}"
    match = _RESET_NOW.fullmatch(value)
    if match:
        return f"сейчас {match['timestamp']}"
    if value == "unknown":
        return "в неизвестное время"
    return None


def _translate_account_line(line: str) -> str:
    match = _HEADER.fullmatch(line)
    if match:
        bold = match["bold"] or ""
        title = match["bold_title"] or match["plain_title"]
        translated_title = {
            "Account limits": "Ограничения аккаунта",
            "Nous credits": "Кредиты Nous",
        }[title]
        return f"📈 {bold}{translated_title}{bold}"

    match = _PROVIDER_PLAN.fullmatch(line)
    if match:
        return f"Провайдер: {match['provider']} ({match['plan']})"

    match = _PROVIDER.fullmatch(line)
    if match:
        return f"Провайдер: {match['provider']}"

    match = _WINDOW.fullmatch(line)
    if match:
        label = _LABELS.get(match["label"], match["label"])
        translated = (
            f"{label}: осталось {match['remaining']}% "
            f"(использовано {match['used']}%)"
        )
        suffix = match["suffix"]
        if suffix.startswith(" • resets "):
            reset = _translate_reset(suffix.removeprefix(" • resets "))
            if reset is not None:
                suffix = f" • сброс {reset}"
        elif suffix.startswith(" • "):
            credits = _CREDITS_REMAINING.fullmatch(suffix.removeprefix(" • "))
            if credits:
                suffix = (
                    f" • осталось {credits['remaining']} из {credits['total']}"
                )
        return translated + suffix

    match = _BANKED.fullmatch(line)
    if match:
        return (
            f"Накопленные сбросы: {match['count']} — "
            "используйте `/usage reset` для активации"
        )

    if line.startswith("Unavailable: "):
        return "Недоступно: " + line.removeprefix("Unavailable: ")
    if line.startswith("Credits balance: "):
        value = line.removeprefix("Credits balance: ")
        return "Баланс кредитов: " + ("без ограничений" if value == "unlimited" else value)
    for source, target in (
        ("Subscription credits: ", "Кредиты подписки: "),
        ("Top-up credits: ", "Пополненные кредиты: "),
        ("Total usable: ", "Всего доступно: "),
        ("Rollover: ", "Перенесённый остаток: "),
        ("Renews: ", "Продление: "),
        ("Top up: ", "Пополнить: "),
    ):
        if line.startswith(source):
            return target + line.removeprefix(source)
    if line == "Status: access depleted — top up to restore":
        return "Статус: доступ исчерпан — пополните баланс для восстановления"
    if line == "(or run /topup)":
        return "(или выполните `/topup`)"
    return line


def translate_account_usage_envelope(text: str) -> str:
    """Translate only recognized account-limit lines; preserve unknown data verbatim."""
    lines = text.split("\n")
    header_index = next(
        (index for index, line in enumerate(lines) if _HEADER.fullmatch(line)),
        None,
    )
    if header_index is None:
        return text

    lines = [
        _PENDING_DETAIL_ITALIC if line in _PENDING_DETAILS else line
        for line in lines
    ]

    for index in range(header_index, len(lines)):
        lines[index] = _translate_account_line(lines[index])
    return "\n".join(lines)
