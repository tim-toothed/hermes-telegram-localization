# Telegram localization surface inventory

Scope: Hermes Telegram user interface outside model output, tool output, logs, and approval UX.

## Covered by plugin 0.3.9

| Surface | Runtime path | Coverage |
|---|---|---|
| Normal messages and edits | live `TelegramAdapter.format_message`, `send`, `edit_message`, `_send_message_with_thread_fallback` | Catalog translation after the first inbound Telegram event; final model replies remain excluded. |
| Inline button labels | live Telegram adapter module `InlineKeyboardButton` | Known static labels are translated after live adapter activation. Callback data and command IDs remain unchanged. |
| Telegram command menu | `hermes_cli.commands.telegram_menu_commands()` → adapter `set_my_commands` | Known descriptions are localized and configured commands are hidden for default/private/group scopes. |
| Forum-chat command menu | lazy forum registration in the Telegram adapter | Uses the same wrapped command generator, preserving filtering and Russian descriptions. |
| Callback popup text | live `CallbackQuery.answer` | Known popup labels are translated after adapter activation. Real model-picker popup verified on D2. |
| Callback message edits and plain-text fallback | live `CallbackQuery.edit_message_text` plus `TelegramAdapter.format_message` | Known callback UI is translated; callback data remains unchanged. |
| Model-switch confirmation card | `gateway/slash_commands.py` result card | Structured translator localizes labels and known capabilities while preserving model/provider values. Final D2 card verification is pending. |
| Cron delivery | `cron.scheduler._deliver_result` | Real D2 delivery verified with `⏰ <task name>`, separator, and literal payload; job ID and management footer are omitted. |
| Gateway shutdown notification | `GatewayRunner._notify_active_sessions_of_shutdown` | Real D2 graceful shutdown verified; localization activates before the notice is sent. |
| Long-running heartbeat and busy activity | `gateway/run.py` activity heartbeat and busy acknowledgements | Structured translator localizes elapsed time, iterations, known built-in tools, provider waits/retries, and context compression. Unknown plugin/MCP tool IDs fail open unchanged. D2 verification is pending because the stand is offline. |
| Context compaction completion | `agent/conversation_compression.py` `status_callback("compacted", ...)` → live `TelegramAdapter.format_message` | Exact terminal edge is translated to `✅ Сжатие контекста завершено — продолжаю текущий запрос...`; telemetry confirms the English source reached this boundary as passthrough before 0.3.8. |
| Account usage blocks in `/usage` | `agent/account_usage.py` → `gateway/slash_commands.py` → Telegram formatter | Structured line translator recognizes both `Account limits` and `Nous credits`, localizes known labels, balances, percentages, reset windows, and fixes the known pending-detail italic marker while preserving provider values, timestamps, URLs, and unknown lines. |
| Repeated long-running heartbeat edits | `gateway/run.py` → `TelegramAdapter.edit_message(finalize=False)` | Runtime-status translation runs at edit entry only for a full known heartbeat envelope; model-authored edits remain guarded. |

## Implemented but awaiting live notification

| Surface | Coverage | Pending evidence |
|---|---|---|
| Background self-improvement review | A fail-open wrapper translates each producer action independently and returns a new localized list only when every action is recognized; otherwise it returns the original list unchanged. It registers the exact serialized localized envelope in a bounded thread-safe set; the outbound boundary then replaces only the fixed English prefix and preserves the registered payload verbatim. Mixed file-patch summaries need no parsing of the unescaped delimiter, and identical serialized payloads have one deterministic target. Unknown actions and dynamic previews remain unchanged. | Attended Telegram emission after plugin update and Gateway restart. |
| Delivery-ledger recovered reply | Startup wrapper activates the live Telegram adapter boundary before recovery replay; only the fixed marker is translated and stored reply content remains literal. | Attended recovery after an actual interrupted delivery and Gateway restart. |
| Chat-specific restart completion | For a native Telegram adapter, the startup wrapper activates the live adapter boundary before `_send_restart_notification`; the fixed success sentence is translated exactly. Relay-routed Telegram startup delivery remains unchanged. | Attended `/restart` after plugin update. |

## Confirmed gaps and deferred surfaces

| Status | Surface | Reason |
|---|---|---|
| BLOCKED | Home-channel “Gateway online” notification | Same startup-order gap. |
| BLOCKED | Post-update completion notification after restart | Same startup-order gap; captured update output must remain literal. |
| BLOCKED | Relay-routed Telegram startup lifecycle delivery | Relay delivery bypasses the native Telegram adapter boundaries owned by this plugin. |
| OUT OF SCOPE | Optional Bot profile status indicator | Direct Bot API profile mutation; intentionally excluded from this release. |
| DEFERRED | Language-specific BotCommand menus | Current PROCVETAEV bots intentionally publish one Russian command list. |

## Explicit exclusions

- Approval cards, approval reasons, and approval callbacks are a separate deferred work block.
- Suggestions, tips, and parallel-chat instructions are deferred.
- Model prose, tool output, logs, tracebacks, callback data, command IDs, model IDs, provider IDs, and user-authored previews are not localization targets.
- Direct command execution policy is unrelated to menu visibility and localization.
