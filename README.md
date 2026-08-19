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

The plugin currently cannot translate three early or unsupported surfaces safely: the Gateway restart notification sent before adapter activation, callback popups, and Telegram command-menu descriptions. These remain English rather than using unsafe global monkey-patches.

## Acceptance tests

Run with the Python interpreter from the active Hermes installation:

```bash
python tests/run_acceptance.py
```

The suite performs no Telegram network calls. It exercises the real installed TelegramAdapter, `/new` and command-approval cards, buttons and outcomes, then samples representative notifications from every catalog source file.

## Design

- `plugin.yaml` and `register(ctx)` use the normal Hermes standalone plugin loader.
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
