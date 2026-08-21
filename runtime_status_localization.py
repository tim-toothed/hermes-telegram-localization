"""Structured localization for long-running Gateway activity statuses."""

from __future__ import annotations

import re
from collections.abc import Callable


_TOOL_ACTIONS = {
    "web_search": "ищу в интернете",
    "web_extract": "читаю страницу",
    "browser_navigate": "открываю страницу",
    "browser_click": "нажимаю",
    "browser_type": "ввожу текст",
    "read_file": "читаю файл",
    "write_file": "записываю файл",
    "patch": "редактирую файл",
    "search_files": "ищу в файлах",
    "terminal": "выполняю команду",
    "execute_code": "выполняю код",
    "image_generate": "создаю изображение",
    "video_generate": "создаю видео",
    "text_to_speech": "озвучиваю текст",
    "vision_analyze": "анализирую изображение",
    "session_search": "ищу в истории диалогов",
    "skill_view": "изучаю навык",
    "skills_list": "получаю список навыков",
    "skill_manage": "обновляю навык",
    "delegate_task": "передаю задачу агенту",
    "cronjob": "управляю расписанием",
    "clarify": "задаю вопрос",
    "memory": "обновляю память",
    "todo": "обновляю список задач",
}

_TOOL_NOUNS = {
    "web_search": "поиск в интернете",
    "web_extract": "чтение страницы",
    "browser_navigate": "открытие страницы",
    "browser_click": "нажатие",
    "browser_type": "ввод текста",
    "read_file": "чтение файла",
    "write_file": "запись файла",
    "patch": "редактирование файла",
    "search_files": "поиск в файлах",
    "terminal": "команда",
    "execute_code": "выполнение кода",
    "image_generate": "создание изображения",
    "video_generate": "создание видео",
    "text_to_speech": "озвучивание текста",
    "vision_analyze": "анализ изображения",
    "session_search": "поиск в истории диалогов",
    "skill_view": "изучение навыка",
    "skills_list": "получение списка навыков",
    "skill_manage": "обновление навыка",
    "delegate_task": "задача субагента",
    "cronjob": "расписание",
    "clarify": "уточняющий вопрос",
    "memory": "обновление памяти",
    "todo": "обновление списка задач",
}

_EXACT_ACTIVITY = {
    "waiting for non-streaming API response": "ожидаю ответ провайдера",
    "waiting for provider response (streaming)": "ожидаю потоковый ответ провайдера",
    "receiving stream response": "получаю ответ провайдера",
    "context compression started": "начинаю сжатие контекста",
    "context compression in progress": "сжимаю контекст",
    "context compression completed": "сжатие контекста завершено",
    "context compression cancelled": "сжатие контекста отменено",
    "context compression failed": "сжатие контекста завершилось ошибкой",
    "session hygiene compression timed out": "сжатие истории сессии превысило время ожидания",
    "session hygiene compression aborted": "сжатие истории сессии прервано",
}

_TECHNICAL_ID = r"[A-Za-z_][A-Za-z0-9_.:-]*"
_TOOL_LIST = rf"{_TECHNICAL_ID}(?:, {_TECHNICAL_ID})*"
_SECONDS = r"[0-9]+(?:\.[0-9])?"
_TECHNICAL_ID_RE = re.compile(rf"^{_TECHNICAL_ID}$")
_TOOL_LIST_RE = re.compile(rf"^{_TOOL_LIST}$")
_HEARTBEAT = re.compile(
    r"^⏳ Working — (?P<minutes>[0-9]+) min(?: — (?P<detail>.*))?$"
)


def _match(pattern: str, text: str, render: Callable[[re.Match[str]], str]) -> str | None:
    match = re.fullmatch(pattern, text)
    return render(match) if match else None


def _known_tool_list(value: str) -> str | None:
    if not _TOOL_LIST_RE.fullmatch(value):
        return None
    tools = value.split(", ")
    if any(tool not in _TOOL_NOUNS for tool in tools):
        return None
    return ", ".join(_TOOL_NOUNS[tool] for tool in tools)


def translate_activity_description(value: str) -> str:
    """Translate the bounded activity protocol; preserve unknown values literally."""
    exact = _EXACT_ACTIVITY.get(value)
    if exact is not None:
        return exact
    if _TECHNICAL_ID_RE.fullmatch(value):
        return _TOOL_ACTIONS.get(value, value)
    if ", " in value:
        tools = _known_tool_list(value)
        if tools is not None:
            return f"параллельно выполняю: {tools}"

    def known_tool_action(match: re.Match[str]) -> str:
        tool = match["tool"]
        return _TOOL_ACTIONS.get(tool, match.string)

    def known_tool_completion(match: re.Match[str]) -> str:
        tool = match["tool"]
        if tool not in _TOOL_NOUNS:
            return match.string
        suffix = " (ошибка)" if match.groupdict().get("error") else ""
        return f"завершено: {_TOOL_NOUNS[tool]} ({match['s']} с){suffix}"

    def known_concurrent_tools(match: re.Match[str]) -> str:
        tools = _known_tool_list(match["tools"])
        if tools is None:
            return match.string
        return f"параллельно выполняю инструменты ({match['count']}): {tools}"

    def known_running_tools(match: re.Match[str]) -> str:
        tools = _known_tool_list(match["tools"])
        if tools is None:
            return match.string
        return f"параллельные инструменты работают {match['s']} с; осталось {match['count']}: {tools}"

    patterns: tuple[tuple[str, Callable[[re.Match[str]], str]], ...] = (
        (r"starting API call #(?P<n>[0-9]+)", lambda m: f"запускаю запрос к модели №{m['n']}"),
        (r"API call #(?P<n>[0-9]+) completed", lambda m: f"запрос к модели №{m['n']} завершён"),
        (r"tool results posted, continuing iteration #(?P<n>[0-9]+)", lambda m: f"результаты инструментов отправлены модели; продолжаю итерацию №{m['n']}"),
        (r"API error recovery \(attempt (?P<a>[0-9]+)/(?P<m>[0-9]+)\)", lambda m: f"восстанавливаюсь после ошибки API (попытка {m['a']}/{m['m']})"),
        (r"(?:retry|error retry|empty response retry) backoff \((?P<a>[0-9]+)/(?P<m>[0-9]+)\), (?P<s>[0-9]+)s remaining", lambda m: f"ожидание перед повтором ({m['a']}/{m['m']}), осталось {m['s']} с"),
        (r"stream retry (?P<a>[0-9]+)/(?P<m>[0-9]+) after (?P<error>[^\r\n]+)", lambda m: f"повтор потока {m['a']}/{m['m']} после {m['error']}"),
        (rf"executing tool: (?P<tool>{_TECHNICAL_ID})", known_tool_action),
        (rf"executing (?P<count>[0-9]+) tools concurrently: (?P<tools>{_TOOL_LIST})", known_concurrent_tools),
        (rf"tool completed: (?P<tool>{_TECHNICAL_ID}) \((?P<s>{_SECONDS})s\)(?P<error> \(error\))?", known_tool_completion),
        (rf"sequential tool running \((?P<s>{_SECONDS})s\): (?P<tool>{_TECHNICAL_ID})", lambda m: f"инструмент работает {m['s']} с: {_TOOL_NOUNS[m['tool']]}" if m["tool"] in _TOOL_NOUNS else m.string),
        (rf"concurrent tools running \((?P<s>{_SECONDS})s, (?P<count>[0-9]+) remaining: (?P<tools>{_TOOL_LIST})\)", known_running_tools),
        (r"waiting for stream response \((?P<s>[0-9]+)s, no chunks yet\)", lambda m: f"ожидаю потоковый ответ ({m['s']} с, данных пока нет)"),
        (r"stale stream detected after (?P<s>[0-9]+)s, reconnecting", lambda m: f"поток не отвечает {m['s']} с; переподключаюсь"),
        (r"stale non-streaming call killed after (?P<s>[0-9]+)s", lambda m: f"зависший запрос без потока остановлен через {m['s']} с"),
        (r"codex stream killed after (?P<s>[0-9]+)s with no first byte", lambda m: f"поток Codex остановлен через {m['s']} с без первого байта"),
        (r"codex stream killed after (?P<s>[0-9]+)s with no SSE events", lambda m: f"поток Codex остановлен через {m['s']} с без SSE-событий"),
    )
    for pattern, render in patterns:
        translated = _match(pattern, value, render)
        if translated is not None:
            return translated
    return value


def _translate_status_detail(detail: str) -> str:
    """Translate heartbeat iteration and exact current-tool/activity formats."""
    iteration = re.fullmatch(
        r"iteration (?P<c>[0-9]+)/(?P<m>[0-9]+), (?P<activity>[^\r\n]+)",
        detail,
    )
    if iteration:
        activity = translate_activity_description(iteration["activity"])
        return f"итерация {iteration['c']}/{iteration['m']}, {activity}"
    only_iteration = re.fullmatch(r"iteration (?P<c>[0-9]+)/(?P<m>[0-9]+)", detail)
    if only_iteration:
        return f"итерация {only_iteration['c']}/{only_iteration['m']}"
    return translate_activity_description(detail)


def _translate_busy_detail(detail: str) -> str:
    if not detail:
        return ""
    inner = detail[2:-1]
    match = re.fullmatch(
        rf"(?:(?P<elapsed>[0-9]+) min elapsed(?:, )?)?"
        rf"(?:(?:iteration (?P<c>[0-9]+)/(?P<m>[0-9]+))(?:, )?)?"
        rf"(?:running: (?P<tools>{_TOOL_LIST}))?",
        inner,
    )
    if match is None or not any(match.groupdict().values()):
        return detail
    translated: list[str] = []
    if match["elapsed"]:
        translated.append(f"прошло {match['elapsed']} мин")
    if match["c"]:
        translated.append(f"итерация {match['c']}/{match['m']}")
    if match["tools"]:
        tools = _known_tool_list(match["tools"])
        if tools is None:
            translated.append(f"running: {match['tools']}")
        elif ", " in match["tools"]:
            translated.append(f"инструменты: {tools}")
        else:
            translated.append(_TOOL_ACTIONS[match["tools"]])
    return f" ({', '.join(translated)})"


_BUSY_DETAIL = rf" \((?:[0-9]+ min elapsed(?:, iteration [0-9]+/[0-9]+)?(?:, running: {_TOOL_LIST})?|iteration [0-9]+/[0-9]+(?:, running: {_TOOL_LIST})?|running: {_TOOL_LIST})\)"
_BUSY_PATTERNS: tuple[tuple[str, str], ...] = (
    (rf"⏩ Steered into current run(?P<detail>{_BUSY_DETAIL})?\. Your message arrives after the next tool call\.", "⏩ Сообщение передано в текущую работу{detail}. Оно будет учтено после следующего вызова инструмента."),
    (rf"↪ Redirected current run(?P<detail>{_BUSY_DETAIL})?\. I'll adjust using your correction\.", "↪ Уточнение принято{detail}. Продолжаю работу с его учётом."),
    (rf"⏳ Subagent working(?P<detail>{_BUSY_DETAIL})? — your message is queued for when it finishes \(use /stop to cancel everything\)\.", "⏳ Субагент работает{detail} — сообщение поставлено в очередь до его завершения (`/stop` отменит всю работу)."),
    (rf"⏳ Compressing context(?P<detail>{_BUSY_DETAIL})? — your message is queued for when it finishes \(use /stop to cancel everything\)\.", "⏳ Сжимаю контекст{detail} — сообщение поставлено в очередь до завершения (`/stop` отменит всю работу)."),
    (rf"⏳ Queued for the next turn(?P<detail>{_BUSY_DETAIL})?\. I'll respond once the current task finishes\.", "⏳ Сообщение поставлено в очередь на следующий ход{detail}. Отвечу после завершения текущей задачи."),
    (rf"⚡ Interrupting current task(?P<detail>{_BUSY_DETAIL})?\. I'll respond to your message shortly\.", "⚡ Прерываю текущую задачу{detail}. Скоро отвечу на сообщение."),
)


def translate_runtime_status(text: str) -> str:
    """Translate known heartbeat/busy envelopes and fail open for all other text."""
    heartbeat = _HEARTBEAT.fullmatch(text)
    if heartbeat:
        suffix = ""
        if heartbeat["detail"]:
            suffix = " — " + _translate_status_detail(heartbeat["detail"])
        return f"⏳ Работаю — {heartbeat['minutes']} мин{suffix}"

    first, separator, remainder = text.partition("\n\n")
    for pattern, template in _BUSY_PATTERNS:
        match = re.fullmatch(pattern, first)
        if match:
            translated = template.format(
                detail=_translate_busy_detail(match.groupdict().get("detail") or "")
            )
            return translated + (separator + remainder if separator else "")
    return text
