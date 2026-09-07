import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import yaml

PLUGIN = Path(__file__).resolve().parents[1]
RESULT = Path(tempfile.gettempdir()) / "hermes-telegram-localization-stratified-result.json"

spec = importlib.util.spec_from_file_location("loc_stratified_pkg", PLUGIN / "__init__.py", submodule_search_locations=[str(PLUGIN)])
pkg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pkg
spec.loader.exec_module(pkg)
from loc_stratified_pkg.reporter import JsonlReporter
from loc_stratified_pkg.runtime import RuntimeState, install_on_adapter
from loc_stratified_pkg.translator import Catalog
from loc_stratified_pkg.menu_filter import HIDDEN_TELEGRAM_COMMANDS, install_telegram_menu_filter, telegram_commands_module

from hermes_cli.plugins import discover_plugins
discover_plugins(force=True)
from gateway.config import Platform, load_gateway_config
from gateway.platform_registry import platform_registry
cfg = load_gateway_config()
adapter = platform_registry.create_adapter("telegram", cfg.platforms[Platform.TELEGRAM])
if adapter is None:
    raise RuntimeError("Telegram adapter factory returned None")
original_format = adapter.format_message

async def no_network_transport(**kwargs):
    raise AssertionError("stratified smoke must not call Telegram transport")
adapter._send_message_with_thread_fallback = no_network_transport
state = RuntimeState(Catalog.from_yaml(PLUGIN / "rules" / "ru.yaml"), JsonlReporter(Path(tempfile.gettempdir()) / "hermes-telegram-localization-stratified.jsonl"))
install_on_adapter(adapter, state)

raw = yaml.safe_load((PLUGIN / "rules" / "ru.yaml").read_text(encoding="utf-8"))
rules = {}
rule_files = {}
for group in raw["groups"].values():
    for rule in group.get("rules", []):
        rules[rule["id"]] = rule
        rule_files[rule["id"]] = group["source_file"]

SAMPLES = [
    ("account_usage.title_account_limits", {}),
    ("account_usage.label_api_key_quota", {}),
    ("provider_progress.aborting_call", {}),
    ("compression.compaction_complete", {}),
    ("tool_progress.verbs.session_search", {}),
    ("tool_progress.verbs.vision_analyze", {}),
    ("runtime_warning.cron_no_fallback", {}),
    ("runtime_warning.cron_drift_consumed", {}),
    ("runtime_warning.delivery_message", {}),
    ("runtime_warning.delivery_audio", {}),
    ("gateway.provider_error.auth", {}),
    ("runtime_warning.context_too_large", {}),
    ("runtime_warning.session_stall", {"minutes": "12"}),
    ("hardcoded.slash.platform.1595", {}),
    ("hardcoded.slash.skills.3865", {}),
    ("gateway.debug.privacy_notice", {}),
    ("runtime_warning.model_cost_threshold", {}),
    ("runtime_warning.model_cost_banner", {}),
    ("runtime_warning.model_data_contributor", {}),
    ("runtime_warning.model_expensive_title", {}),
    ("runtime_warning.model_selection_title", {}),
    ("locale.gateway.reload_mcp.confirm_prompt", {}),
    ("locale.runtime_warning.preference_save_failed", {}),
    ("runtime_warning.telegram_question_expired_html", {}),
    ("runtime_warning.telegram_prompt_expired", {}),
    ("provider_progress.codex_silent_rejection", {"model": "gpt-5.4-codex"}),
    ("requested.compression.codex_autoraise", {
        "model": "gpt-5.6-luna", "context_window": "272K",
        "old_percent": "50", "new_percent": "85",
    }),
    ("requested.compression.success", {
        "before_messages": "176", "after_messages": "73",
        "token_count": "123,456", "suffix": " (estimated)",
    }),
    ("requested.provider.fallback_unreachable", {}),
    ("requested.session.daily_reset.current", {
        "reset_time": "4:00", "session_info": "",
    }),
]

results = []
covered_files = set()
for rule_id, values in SAMPLES:
    rule = rules[rule_id]
    source = str(rule["from"]).format_map(values)
    target = str(rule["to"]).format_map(values)
    actual = adapter.format_message(source)
    expected = original_format(target)
    source_file = rule_files[rule_id]
    covered_files.add(source_file)
    results.append({
        "name": rule_id,
        "source_file": source_file,
        "status": "PASS" if actual == expected else "FAIL",
        "actual": actual,
        "expected": expected,
    })

hermes_commands = telegram_commands_module()
original_menu_generator = hermes_commands.telegram_menu_commands
try:
    menu_filter_status = install_telegram_menu_filter()
    menu_commands, _ = hermes_commands.telegram_menu_commands(max_commands=100)
finally:
    hermes_commands.telegram_menu_commands = original_menu_generator
menu_names = {name for name, _ in menu_commands}
menu_descriptions = {description for _, description in menu_commands}
menu_ok = (
    menu_filter_status in {"installed", "already_installed"}
    and not (menu_names & HIDDEN_TELEGRAM_COMMANDS)
    and "Показать доступные команды" in menu_descriptions
)
results.append({
    "name": "telegram_command_menu_descriptions",
    "source_file": "hermes_cli/commands.py",
    "status": "PASS" if menu_ok else "FAIL",
    "actual": {
        "install_status": menu_filter_status,
        "hidden_commands_present": sorted(menu_names & HIDDEN_TELEGRAM_COMMANDS),
        "russian_help_present": "Показать доступные команды" in menu_descriptions,
    },
    "expected": "new module wrapped, Russian descriptions present, hidden commands absent",
})
covered_files.add("hermes_cli/commands.py")
all_files = {group["source_file"] for group in raw["groups"].values()}
missing_files = sorted(all_files - covered_files)
for source_file in missing_files:
    results.append({
        "name": "source_file_coverage_missing",
        "source_file": source_file,
        "status": "FAIL",
        "actual": "no representative sample",
        "expected": "at least one representative sample",
    })

summary = {status: sum(r["status"] == status for r in results) for status in ("PASS", "FAIL", "BLOCKED")}
by_file = {}
for source_file in sorted(all_files):
    rows = [r for r in results if r["source_file"] == source_file]
    by_file[source_file] = {
        "PASS": sum(r["status"] == "PASS" for r in rows),
        "FAIL": sum(r["status"] == "FAIL" for r in rows),
        "BLOCKED": sum(r["status"] == "BLOCKED" for r in rows),
        "samples": [r["name"] for r in rows],
    }
payload = {
    "adapter_class": adapter.__class__.__module__ + "." + adapter.__class__.__qualname__,
    "rule_count": state.catalog.rule_count,
    "source_files_total": len(all_files),
    "source_files_covered": len(covered_files),
    "network_calls": 0,
    "summary": summary,
    "by_file": by_file,
    "results": results,
}
RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=True))
