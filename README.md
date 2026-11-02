# Hermes Telegram Localization

![Hermes Telegram Localization](assets/banner.png)

Russian localization for Hermes in Telegram.

Translates system messages, buttons, command descriptions, and runtime status updates without modifying Hermes core files. Agent replies remain unchanged.

## Install

```bash
hermes plugins install tim-toothed/hermes-telegram-localization --enable
```

Restart the Gateway through your normal launcher after installation. The plugin activates its Telegram adapter wrappers on the first inbound Telegram event.

## Features

- Russian system messages, inline buttons, and command-menu descriptions.
- Localized progress updates, context-compaction notices, and callback confirmations.
- Compact cron-delivery headers.
- Unknown or ambiguous text passes through unchanged; translation failures do not block delivery.

## Check status

In Telegram:

```text
/localization
```

Or from the terminal:

```bash
hermes localization status
```

## Update

```bash
hermes plugins update hermes-telegram-localization
```

Restart the Gateway through your normal launcher to load the update.

## Other languages

Russian is the included translation catalog. To adapt the plugin to another language, fork the repository and translate the targets in `rules/ru.yaml`, preserving source patterns, placeholders, and boundary restrictions. Review the Russian-specific runtime and command-menu translations as well; changing the catalog alone does not cover every surface.

This is a starting point for another localization, not a built-in language selector or an already tested multilingual release.

## Limitations

- Restart/shutdown notifications and the optional profile status indicator are not translated.
- New or unmatched Hermes messages remain in their original language.
- Windows and Linux checks are documented in the [surface inventory](docs/LOCALIZATION_SURFACE_INVENTORY.md); macOS has not been exercised.

## Development

Run offline acceptance with the Python interpreter from the active Hermes installation:

```bash
python tests/run_acceptance.py
```

These tests do not make Telegram network calls. Live delivery requires a separate Telegram check.

## Author

[tim-toothed](https://github.com/tim-toothed)
