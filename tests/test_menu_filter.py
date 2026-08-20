from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from menu_filter import (
    HIDDEN_TELEGRAM_COMMANDS,
    filter_menu_commands,
    install_telegram_menu_filter,
)


class _PluginContext:
    profile_name = "test"

    def register_hook(self, *_args, **_kwargs) -> None:
        return None

    def register_command(self, *_args, **_kwargs) -> None:
        return None

    def register_cli_command(self, *_args, **_kwargs) -> None:
        return None


class TelegramMenuFilterTests(unittest.TestCase):
    def test_hidden_commands_are_removed_without_changing_remaining_entries(self) -> None:
        commands = [
            ("help", "Show help"),
            ("egress", "Configure egress"),
            ("codex_runtime", "Inspect Codex runtime"),
            ("topup", "Manage provider balance"),
            ("status", "Show status"),
        ]

        filtered, removed = filter_menu_commands(commands)

        self.assertEqual(
            filtered,
            [("help", "Show help"), ("status", "Show status")],
        )
        self.assertEqual(removed, 3)

    def test_installed_wrapper_filters_real_telegram_menu_generator(self) -> None:
        import hermes_cli.commands as hermes_commands

        original = hermes_commands.telegram_menu_commands
        before, _ = original(max_commands=100)
        try:
            status = install_telegram_menu_filter()
            after, _ = hermes_commands.telegram_menu_commands(max_commands=100)
        finally:
            hermes_commands.telegram_menu_commands = original

        self.assertEqual(status, "installed")
        self.assertFalse({name for name, _ in after} & HIDDEN_TELEGRAM_COMMANDS)
        expected = [entry for entry in before if entry[0] not in HIDDEN_TELEGRAM_COMMANDS]
        self.assertEqual(after, expected)

    def test_plugin_register_installs_menu_filter_before_adapter_connect(self) -> None:
        import hermes_cli.commands as hermes_commands

        original = hermes_commands.telegram_menu_commands
        before, _ = original(max_commands=100)
        spec = importlib.util.spec_from_file_location(
            "loc_menu_register_test",
            PLUGIN_DIR / "__init__.py",
            submodule_search_locations=[str(PLUGIN_DIR)],
        )
        package = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = package
        try:
            spec.loader.exec_module(package)
            with tempfile.TemporaryDirectory() as home, patch.dict(
                os.environ, {"HERMES_HOME": home}
            ):
                package.register(_PluginContext())
                after, _ = hermes_commands.telegram_menu_commands(max_commands=100)
        finally:
            hermes_commands.telegram_menu_commands = original
            sys.modules.pop(spec.name, None)

        expected = [entry for entry in before if entry[0] not in HIDDEN_TELEGRAM_COMMANDS]
        self.assertEqual(after, expected)


if __name__ == "__main__":
    unittest.main()
