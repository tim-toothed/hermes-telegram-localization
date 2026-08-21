# Hermes Telegram Russian Localization

Standalone runtime plugin that translates Hermes system UI in Telegram without modifying Hermes core files.

## Install

```bash
hermes plugins install tim-toothed/hermes-telegram-localization --enable
```

After enabling the plugin, restart the Gateway normally. The Telegram adapter is discovered from the live `GatewayRunner` and wrapped in memory on the first inbound Telegram event.

Check plugin state:

```bash
hermes localization status
```

In Telegram:

```text
/localization
```

Update from GitHub:

```bash
hermes plugins update procvetaev-localization
```

## Compatibility

- Windows: full offline TelegramAdapter acceptance passed against Hermes 0.20.0.
- Linux: plugin import, catalog loading, and translation smoke passed on Linux/Python 3.12. The runtime contains no OS-specific paths or APIs.
- macOS: supported by the same platform-neutral runtime, but not yet exercised in this release.

The plugin does not translate early restart/startup/update notifications or the optional Telegram profile status indicator. Callback popups and callback message edits are covered through narrow live Telegram callback boundaries installed after adapter activation; callback data and command IDs remain unchanged.

During normal plugin registration, before Telegram connects, the plugin wraps `hermes_cli.commands.telegram_menu_commands()`. The wrapper applies Russian descriptions to every known command and then removes entries listed in `HIDDEN_TELEGRAM_COMMANDS` from the `/` menu. Hidden commands retain Russian descriptions for future re-enabling; their handlers, `/help` entries, and manual invocation remain unchanged. Unknown future plugin commands fail open with their original descriptions.

## Acceptance tests

Run with the Python interpreter from the active Hermes installation:

```bash
python tests/run_acceptance.py
```

The suite performs no Telegram network calls. It exercises the real installed TelegramAdapter, `/new` and command-approval cards, buttons and outcomes, then samples representative notifications from every catalog source file.

## Design

- `plugin.yaml` and `register(ctx)` use the normal Hermes standalone plugin loader.
- During plugin registration, a fail-open menu wrapper localizes known command descriptions and applies a display-only filter before adapter connection; it does not modify command dispatch.
- Background self-improvement summaries are translated structurally when Hermes emits them, including `Memory updated`, profile updates, bounded skill create/update/full-rewrite messages, and single-action file-patch counts. Names, paths, counts, and dynamic previews remain literal. Mixed summaries containing a file patch fail open because the upstream delimiter is not escaped; attended Telegram verification is pending.
- Long-running heartbeat and busy-input details are translated structurally, including elapsed time, iterations, known built-in tool activity, provider waits/retries, and context compression. Unknown plugin/MCP tool identifiers remain literal. D2 runtime verification is pending because the stand is offline.
- Callback popups and callback edits are translated at narrow live Telegram callback boundaries. Model/provider identifiers remain literal, and model-switch confirmation cards are translated structurally.
- Cron deliveries use a compact `⏰ <task name>` header without job IDs or management boilerplate.
- A narrow shutdown wrapper activates localization on the still-connected Telegram adapter before Hermes emits shutdown notices; startup/restart notifications remain a separate uncovered lifecycle.
- `pre_gateway_dispatch` obtains the real adapter instance through `GatewayRunner._adapter_for_source()` before message dispatch.
- Translation boundaries cover Telegram Markdown formatting, control-message transport, and inline-button labels.
- Known unique rules are translated; unknown or ambiguous text passes through unchanged.
- Final LLM replies marked with `metadata.notify=true` are excluded from translation.
- Button-only labels are restricted with `boundaries` and cannot match normal message text.
- Callback data, command IDs, model names, provider names, and other machine fields are never changed.
- Runtime events are written to `$HERMES_HOME/plugin-data/procvetaev-localization/reports/localization.jsonl` without message bodies or secrets.

## Rules

`rules/ru.yaml` contains one rule model for literals and placeholder templates:

```yaml
groups:
  agent.chat_completion_helpers.py:
    source_file: agent/chat_completion_helpers.py
    rules:
      - id: provider_progress.no_response_reconnecting
        family: provider_progress
        from: "⚠ no response from provider in {seconds}s — reconnecting..."
        to: "⚠ Провайдер не отвечает {seconds} с — переподключаюсь…"
        placeholders:
          seconds: "[0-9]+"
```

Rules are grouped by the Hermes source module that emits them. Optional `boundaries` narrow ambiguous labels to a specific runtime surface.

## Runtime report outcomes

- `translated`
- `passthrough` (counter only; message body is not logged)
- `ambiguous`
- `method_missing`
- `adapter_missing`
- `wrapper_error`

The plugin is fail-open: translation or reporting failures do not block Telegram delivery.

The current covered, partial, and blocked Telegram surfaces are tracked in [`docs/LOCALIZATION_SURFACE_INVENTORY.md`](docs/LOCALIZATION_SURFACE_INVENTORY.md).
