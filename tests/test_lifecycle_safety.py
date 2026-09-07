import builtins
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class PluginContext:
    profile_name = "test"

    def register_hook(self, *_args, **_kwargs):
        return None

    def register_command(self, *_args, **_kwargs):
        return None

    def register_cli_command(self, *_args, **_kwargs):
        return None


class LifecycleSafetyTests(unittest.TestCase):
    def test_register_never_imports_gateway_run_and_reports_lifecycle_disabled(self):
        package_name = "loc_lifecycle_safety_test"
        spec = importlib.util.spec_from_file_location(
            package_name,
            ROOT / "__init__.py",
            submodule_search_locations=[str(ROOT)],
        )
        package = importlib.util.module_from_spec(spec)
        sys.modules[package_name] = package
        original_import = builtins.__import__
        attempted = []

        def guarded_import(name, *args, **kwargs):
            if name == "gateway.run":
                attempted.append(name)
                raise AssertionError("plugin register must not import gateway.run")
            return original_import(name, *args, **kwargs)

        try:
            spec.loader.exec_module(package)
            with tempfile.TemporaryDirectory() as home, patch.dict(
                os.environ, {"HERMES_HOME": home}
            ), patch("builtins.__import__", side_effect=guarded_import):
                package.register(PluginContext())
            self.assertEqual([], attempted)
            self.assertEqual(
                "disabled_lifecycle_safety",
                package._STATE.boundaries[
                    "GatewayRunner._send_restart_notification"
                ],
            )
            self.assertEqual(
                "disabled_lifecycle_safety",
                package._STATE.boundaries[
                    "GatewayRunner._notify_active_sessions_of_shutdown"
                ],
            )
        finally:
            sys.modules.pop(package_name, None)


if __name__ == "__main__":
    unittest.main()
