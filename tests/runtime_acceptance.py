import asyncio
import importlib.util
import json
import html
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

PLUGIN = Path(__file__).resolve().parents[1]
REPORT = Path(tempfile.gettempdir()) / "procvetaev-localization-acceptance.jsonl"

# Load the deployed plugin package without registering global hooks.
spec = importlib.util.spec_from_file_location(
    "loc_acceptance_pkg", PLUGIN / "__init__.py",
    submodule_search_locations=[str(PLUGIN)],
)
pkg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pkg
spec.loader.exec_module(pkg)
from loc_acceptance_pkg.reporter import JsonlReporter
from loc_acceptance_pkg.runtime import RuntimeState, install_on_adapter
from loc_acceptance_pkg.translator import Catalog

# Load the real bundled Telegram platform and construct its real adapter.
from hermes_cli.plugins import discover_plugins
discover_plugins(force=True)
from gateway.config import Platform, load_gateway_config
from gateway.platform_registry import platform_registry
cfg = load_gateway_config()
adapter = platform_registry.create_adapter("telegram", cfg.platforms[Platform.TELEGRAM])
if adapter is None:
    raise RuntimeError("Telegram adapter factory returned None")

state = RuntimeState(Catalog.from_yaml(PLUGIN / "rules" / "ru.yaml"), JsonlReporter(REPORT))
adapter._bot = object()  # methods only check truthiness; no network calls
captured = []

async def capture_transport(**kwargs):
    captured.append(kwargs)
    return SimpleNamespace(message_id=100 + len(captured))

# Capture is installed first, then the real plugin wraps it. This exercises
# format + transport localization while preventing Telegram network calls.
adapter._send_message_with_thread_fallback = capture_transport
install_on_adapter(adapter, state)

def button_texts(markup):
    if markup is None:
        return []
    return [button.text for row in markup.inline_keyboard for button in row]

def normalize_transport(text):
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\\([_\-*\[\]()~`>#+=|{}.!])", r"\1", text)
    return text

def result(name, passed, actual, expected=None, note=None):
    return {
        "name": name,
        "status": "PASS" if passed else "FAIL",
        "actual": actual,
        "expected": expected,
        "note": note,
    }

async def main():
    results = []
    slash_source = (
        "⚠️ **Confirm /new**\n\n"
        "This starts a fresh session and discards the current conversation history.\n\n"
        "Choose:\n"
        "• **Approve Once** — proceed this time only\n"
        "• **Always Approve** — proceed and silence this prompt permanently\n"
        "• **Cancel** — keep current conversation\n\n"
        "_Text fallback: reply `/approve`, `/always`, or `/cancel`._"
    )
    await adapter.send_slash_confirm(
        chat_id="0", title="/new", message=slash_source,
        session_key="acceptance", confirm_id="new-1", metadata={},
    )
    slash = captured[-1]
    slash_text = slash.get("text", "")
    slash_buttons = button_texts(slash.get("reply_markup"))
    forbidden = [
        "Confirm /new", "This starts a fresh session", "Choose:",
        "Approve Once", "Always Approve", "Cancel", "Text fallback:",
    ]
    results.append(result(
        "slash_confirm_new_text",
        not any(x in slash_text for x in forbidden), slash_text,
        "Полностью русский текст карточки /new",
    ))
    results.append(result(
        "slash_confirm_new_buttons",
        slash_buttons == ["✅ Подтвердить один раз", "🔒 Подтверждать всегда", "❌ Отмена"],
        slash_buttons,
        ["✅ Подтвердить один раз", "🔒 Подтверждать всегда", "❌ Отмена"],
    ))

    await adapter.send_exec_approval(
        chat_id="0",
        command="python - <<'PY'\nprint('LOCALIZATION_APPROVAL_SMOKE')\nPY",
        session_key="acceptance",
        description="dangerous command",
        metadata={},
        allow_permanent=True,
        allow_session=True,
        smart_denied=False,
    )
    approval = captured[-1]
    approval_text = approval.get("text", "")
    approval_buttons = button_texts(approval.get("reply_markup"))
    approval_forbidden = [
        "Command Approval", "Allow Once", "Session", "Always", "Deny",
        "dangerous command",
    ]
    results.append(result(
        "exec_approval_text",
        not any(x in approval_text for x in approval_forbidden), approval_text,
        "Русская карточка approval; код команды сохранён",
    ))
    results.append(result(
        "exec_approval_buttons",
        approval_buttons == ["✅ Разрешить один раз", "✅ До конца сеанса", "✅ Разрешать всегда", "❌ Отклонить"],
        approval_buttons,
        ["✅ Разрешить один раз", "✅ До конца сеанса", "✅ Разрешать всегда", "❌ Отклонить"],
    ))

    literals = [
        (
            "new_cancelled_outcome",
            "🟡 /new cancelled. Conversation unchanged.",
            "🟡 Команда /new отменена. Диалог не изменён.",
        ),
        (
            "approval_denied_outcome",
            "❌ Denied by Timur",
            "❌ Отклонено. Пользователь: Timur",
        ),
        (
            "unknown_command_warning",
            "Unknown command `/xyz`. Type /commands to see what's available, or resend without the leading slash to send as a regular message.",
            "Неизвестная команда `/xyz`.",
        ),
        (
            "provider_auth_warning",
            "⚠️ Provider authentication failed. Check the configured credentials; raw provider details are in the gateway logs.",
            "Ошибка аутентификации у провайдера",
        ),
    ]
    for name, source, expected_fragment in literals:
        actual = adapter.format_message(source)
        normalized = normalize_transport(actual)
        results.append(result(name, expected_fragment in normalized, actual, expected_fragment))

    # These surfaces currently have catalog rules but no safe live boundary
    # after the early global wrappers were removed.
    results.append({
        "name": "callback_popup_boundary",
        "status": "BLOCKED",
        "actual": state.boundaries.get("telegram.CallbackQuery.answer"),
        "expected": "supported outgoing callback hook",
        "note": "Нет безопасного adapter-level hook; ранняя глобальная подмена ломала Telegram startup.",
    })
    results.append({
        "name": "command_menu_boundary",
        "status": "BLOCKED",
        "actual": state.boundaries.get("telegram.BotCommand.description"),
        "expected": "supported command-menu hook",
        "note": "Нет безопасного adapter-level hook.",
    })
    results.append({
        "name": "restart_notification_before_adapter_activation",
        "status": "BLOCKED",
        "actual": "plugin_register precedes adapter_install; restart notice is earlier",
        "expected": "startup outgoing-message hook",
        "note": "Каталожное правило есть, но adapter wrapper ещё не активирован.",
    })

    summary = {s: sum(1 for r in results if r["status"] == s) for s in ("PASS", "FAIL", "BLOCKED")}
    payload = {
        "adapter_class": adapter.__class__.__module__ + "." + adapter.__class__.__qualname__,
        "rule_count": state.catalog.rule_count,
        "network_calls": 0,
        "summary": summary,
        "results": results,
    }
    (Path(tempfile.gettempdir()) / "procvetaev-localization-acceptance-result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=True))

asyncio.run(main())
