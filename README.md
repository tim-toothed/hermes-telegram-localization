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
