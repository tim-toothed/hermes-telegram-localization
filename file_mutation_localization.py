"""Fail-open localization for Hermes-owned file-mutation verifier footers."""

from __future__ import annotations

import re

_HEADER = re.compile(
    r"⚠️ File-mutation verifier: (?P<count>\d+) file(?:\(s\)|s?) (?:were NOT modified|edit\(s\) FAILED) "
    r"this turn despite any wording above that may suggest otherwise\. "
    r"Run `git status` or `read_file` to confirm(?: what actually landed)?\."
)

_EXACT_ERRORS = {
    "No edit was applied because old_string and new_string are identical. Provide the existing text to replace in old_string and the changed replacement text in new_string.":
        "Изменение не применено: `old_string` и `new_string` совпадают. Передайте в `old_string` существующий текст, который нужно заменить, а в `new_string` — изменённый текст для замены.",
    "Could not find a match for old_string in the file":
        "В файле не найдено совпадение с `old_string`.",
    "old_string and new_string required":
        "Необходимо передать `old_string` и `new_string`.",
    "Patch contains no changes (only context lines were provided)":
        "Патч не содержит изменений: переданы только строки контекста.",
}

_PREFIX_ERRORS = (
    (re.compile(r"^Found (?P<count>\d+) matches for old_string\. Provide more context to make it unique, or use replace_all=True\. Matches:"),
     lambda m: f"Для `old_string` найдено совпадений: {m['count']}. Добавьте больше контекста, чтобы получить одно совпадение, или используйте `replace_all=True`. Совпадения:"),
    (re.compile(r"^Could not find match for old_string in (?P<path>.+)$"),
     lambda m: f"В файле {m['path']} не найдено совпадение с `old_string`."),
    (re.compile(r"^Patch validation failed \(no files were modified\):"),
     lambda _m: "Проверка патча завершилась ошибкой, файлы не изменены:"),
    (re.compile(r"^Post-write verification failed: could not re-read (?P<path>.+)$"),
     lambda m: f"Проверка после записи завершилась ошибкой: не удалось повторно прочитать {m['path']}."),
    (re.compile(r"^Failed to write changes: (?P<detail>.+)$"),
     lambda m: f"Не удалось записать изменения: {m['detail']}"),
    (re.compile(r"^(?P<path>.+) was modified since you last read it on disk \(external edit or unrecorded writer\)\. Re-read the file before writing\.$"),
     lambda m: f"Файл {m['path']} изменился после последнего чтения. Перечитайте его перед записью."),
    (re.compile(r"^(?P<path>.+) was last read with offset/limit pagination \(partial view\)\. Read the remaining pages, or use patch, before overwriting it\.$"),
     lambda m: f"Файл {m['path']} был прочитан частично с `offset`/`limit`. Перед перезаписью прочитайте оставшиеся страницы или используйте `patch`."),
    (re.compile(r"^(?P<path>.+) was not read by this agent\. Read the file first so you can write an informed edit\.$"),
     lambda m: f"Агент не читал файл {m['path']}. Сначала прочитайте файл."),
    (re.compile(r"^old_string is only whitespace — provide non-blank text to match\. Set it to the exact existing text the replacement should replace \(read the file first if unsure\)\. Do not re-send this call unchanged\.$"),
     lambda _m: "`old_string` содержит только пробелы. Передайте точный непустой текст, который нужно заменить; при необходимости сначала прочитайте файл. Не повторяйте вызов без изменений."),
)


def _translate_error(error: str) -> str:
    exact = _EXACT_ERRORS.get(error)
    if exact is not None:
        return exact
    for pattern, render in _PREFIX_ERRORS:
        match = pattern.match(error)
        if match:
            translated = render(match)
            return translated + error[match.end():]
    return error


def translate_file_mutation_footer(text: str) -> str:
    """Translate only recognized verifier structure and known Hermes errors."""
    header = _HEADER.search(text)
    if header is None:
        return text
    count = header["count"]
    translated_header = (
        f"⚠️ Проверка изменения файлов: за этот ход не изменено файлов: {count}, "
        "хотя текст выше может утверждать обратное. Попросите REDD проверить результат и объяснить причину."
    )
    result = text[:header.start()] + translated_header + text[header.end():]
    lines = result.splitlines()
    for index, line in enumerate(lines):
        marker = " — ["
        if marker not in line:
            continue
        prefix, separator, rest = line.partition(marker)
        tool, closing, error = rest.partition("] ")
        if not closing:
            continue
        lines[index] = prefix + separator + tool + closing + _translate_error(error)
    return "\n".join(lines)
