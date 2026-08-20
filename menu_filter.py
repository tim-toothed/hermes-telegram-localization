"""Display-only filtering for the Telegram BotCommand menu."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import wraps
from typing import Any

try:
    from .command_descriptions import localize_command_descriptions
except ImportError:  # Direct execution from the plugin checkout.
    from command_descriptions import localize_command_descriptions


HIDDEN_TELEGRAM_COMMANDS = frozenset(
    {
        "egress",
        "resume",
        "sessions",
        "update",
        "approve",
        "deny",
        "queue",
        "background",
        "platform",
        "profile",
        "kanban",
        "suggestions",
        "whoami",
        "retry",
        "undo",
        "title",
        "branch",
        "rollback",
        "pause",
        "agents",
        "heartbeat",
        "codex_runtime",
        "diff",
        "yolo",
        "approvals",
        "memory",
        "bundles",
        "learn",
        "init",
        "blueprint",
        "version",
        "topup",
    }
)


def filter_menu_commands(
    commands: Iterable[tuple[str, str]],
) -> tuple[list[tuple[str, str]], int]:
    """Remove display-only entries while preserving dispatch and descriptions."""
    source = list(commands)
    filtered = [entry for entry in source if entry[0] not in HIDDEN_TELEGRAM_COMMANDS]
    return filtered, len(source) - len(filtered)


def install_telegram_menu_filter() -> str:
    """Wrap Hermes' menu generator before Telegram registers BotCommands."""
    import hermes_cli.commands as hermes_commands

    original: Callable[..., tuple[list[tuple[str, str]], int]] = (
        hermes_commands.telegram_menu_commands
    )
    if getattr(original, "_procvetaev_menu_filter", False):
        return "already_installed"

    @wraps(original)
    def wrapped(*args: Any, **kwargs: Any) -> tuple[list[tuple[str, str]], int]:
        commands, hidden_count = original(*args, **kwargs)
        try:
            localized = localize_command_descriptions(commands)
            filtered, removed_count = filter_menu_commands(localized)
        except Exception:
            return commands, hidden_count
        return filtered, hidden_count + removed_count

    setattr(wrapped, "_procvetaev_menu_filter", True)
    hermes_commands.telegram_menu_commands = wrapped
    return "installed"
