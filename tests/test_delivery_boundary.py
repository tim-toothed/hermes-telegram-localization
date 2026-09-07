import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "loc_delivery_test_pkg",
    ROOT / "__init__.py",
    submodule_search_locations=[str(ROOT)],
)
pkg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pkg
spec.loader.exec_module(pkg)
from loc_delivery_test_pkg.cron_delivery import install_cron_delivery_wrapper
from loc_delivery_test_pkg.runtime import RuntimeState, install_on_adapter
from loc_delivery_test_pkg.translator import Catalog
ENDPOINT_ERROR = (
    "⚠️ **The model server is not responding.** Check the configured endpoint or "
    "try again later. The request was not completed."
)
FALLBACK = "⚠️ Provider unreachable — switching to fallback provider..."
CURRENT_FALLBACK = (
    "⚠️ Model fallback: gpt-5.6-luna via openai-codex unavailable (server error); "
    "using claude-opus-4-1 via anthropic."
)
CURRENT_ENDPOINT_ERROR = (
    "⚠️ The model server is not responding — it looks like the configured model endpoint "
    "is not running or is unreachable."
)
RETRY_EXHAUSTED = (
    "⚠️ The model provider failed after retries. I kept raw provider details out of chat; "
    "check gateway logs for diagnostics."
)
CRON_FAILURE = "⚠️ Cron 'Inventory check' failed: Script exited with code 1 stdout: API returned 503"


def cron_envelope(content):
    return (
        "Cronjob Response: Inventory check\n"
        "(job_id: cron-test-42)\n"
        "-------------\n\n"
        f"{content}\n\n"
        'To stop or manage this job, send me a new message '
        '(e.g. "stop reminder Inventory check").'
    )


class Reporter:
    def emit(self, *_args, **_kwargs):
        return None


class Adapter:
    def __init__(self):
        self.sent = []

    def format_message(self, content, **_kwargs):
        return content

    async def send(self, chat_id, content, metadata=None, **kwargs):
        rendered = self.format_message(content)
        result = SimpleNamespace(success=True, message_id=len(self.sent) + 1)
        self.sent.append((str(chat_id), rendered, dict(metadata or {}), kwargs))
        return result

    async def edit_message(self, chat_id, message_id, content, metadata=None, **kwargs):
        rendered = self.format_message(content)
        result = SimpleNamespace(success=True, message_id=message_id)
        self.sent.append((str(chat_id), rendered, dict(metadata or {}), kwargs))
        return result


class DeliveryBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def make_runtime(self):
        state = RuntimeState(Catalog.from_yaml(ROOT / "rules" / "ru.yaml"), Reporter())
        adapter = Adapter()
        install_on_adapter(adapter, state)
        state.begin_delivery_cycle()
        return state, adapter

    async def test_same_provider_error_is_delivered_once_in_one_cycle(self):
        _state, adapter = self.make_runtime()
        first = await adapter.send("42", ENDPOINT_ERROR, metadata={})
        second = await adapter.send("42", ENDPOINT_ERROR, metadata={"notify": True})
        self.assertEqual(first.message_id, second.message_id)
        self.assertEqual(1, len(adapter.sent))
        self.assertEqual(
            "⚠️ **Сервер модели не отвечает.** Проверьте настроенный endpoint или попробуйте позже. Запрос не выполнен.",
            adapter.sent[0][1],
        )

    async def test_endpoint_error_sent_three_times_is_delivered_once(self):
        _state, adapter = self.make_runtime()
        first = await adapter.send("42", ENDPOINT_ERROR, metadata={})
        second = await adapter.send("42", ENDPOINT_ERROR, metadata={})
        third = await adapter.send("42", ENDPOINT_ERROR, metadata={"notify": True})
        self.assertEqual(first.message_id, second.message_id)
        self.assertEqual(first.message_id, third.message_id)
        self.assertEqual(1, len(adapter.sent))

    async def test_retry_exhaustion_russian_and_english_pair_becomes_one_russian(self):
        _state, adapter = self.make_runtime()
        await adapter.send("42", RETRY_EXHAUSTED, metadata={})
        await adapter.send("42", RETRY_EXHAUSTED, metadata={"notify": True})
        self.assertEqual(1, len(adapter.sent))
        self.assertIn("Провайдер модели не ответил", adapter.sent[0][1])
        self.assertNotIn("failed after retries", adapter.sent[0][1])

    async def test_fallback_transition_keeps_same_error_from_next_provider(self):
        _state, adapter = self.make_runtime()
        await adapter.send("42", ENDPOINT_ERROR, metadata={})
        await adapter.send("42", FALLBACK, metadata={})
        await adapter.send("42", ENDPOINT_ERROR, metadata={"notify": True})
        self.assertEqual(3, len(adapter.sent))
        self.assertIn("резервного провайдера", adapter.sent[1][1])
        self.assertNotIn("The model server", adapter.sent[2][1])

    async def test_current_fallback_transition_starts_a_new_provider_generation(self):
        _state, adapter = self.make_runtime()
        await adapter.send("42", CURRENT_ENDPOINT_ERROR, metadata={})
        await adapter.send("42", CURRENT_FALLBACK, metadata={})
        await adapter.send("42", CURRENT_ENDPOINT_ERROR, metadata={"notify": True})
        self.assertEqual(3, len(adapter.sent))
        self.assertIn("gpt-5.6-luna", adapter.sent[1][1])
        self.assertIn("openai-codex", adapter.sent[1][1])
        self.assertIn("claude-opus-4-1", adapter.sent[1][1])
        self.assertIn("anthropic", adapter.sent[1][1])
        self.assertNotIn("The model server", adapter.sent[2][1])

    async def test_ordinary_duplicate_messages_are_not_deduplicated(self):
        _state, adapter = self.make_runtime()
        await adapter.send("42", "same model reply", metadata={"notify": True})
        await adapter.send("42", "same model reply", metadata={"notify": True})
        self.assertEqual(2, len(adapter.sent))
        self.assertEqual("same model reply", adapter.sent[0][1])
        self.assertEqual("same model reply", adapter.sent[1][1])

    async def test_only_file_verifier_footer_label_changes_in_final_reply(self):
        _state, adapter = self.make_runtime()
        source = (
            "Keep machine ID file-mutation-verifier unchanged.\n\n"
            "⚠️ File-mutation verifier: 1 file(s) were NOT modified this turn.\n"
            "  • `C:/repo/a.py` — [patch] failed"
        )
        await adapter.send("42", source, metadata={"notify": True})
        actual = adapter.sent[0][1]
        self.assertIn("machine ID file-mutation-verifier unchanged", actual)
        self.assertIn("⚠️ Проверка изменения файла:", actual)
        self.assertNotIn("⚠️ File-mutation verifier:", actual)
        self.assertIn("[patch]", actual)

    async def test_cron_notification_translates_owned_envelope_and_known_failure(self):
        _state, adapter = self.make_runtime()
        await adapter.send("42", cron_envelope(CRON_FAILURE), metadata={"notify": True})
        actual = adapter.sent[0][1]
        self.assertIn("Ответ cron-задачи: Inventory check", actual)
        self.assertIn("(job_id: cron-test-42)", actual)
        self.assertIn("Задача Cron «Inventory check» завершилась ошибкой", actual)
        self.assertIn("Script exited with code 1 stdout: API returned 503", actual)
        self.assertIn("Чтобы остановить задачу или управлять ею", actual)
        self.assertNotIn("Cronjob Response:", actual)
        self.assertNotIn("To stop or manage this job", actual)

    async def test_cron_notification_preserves_arbitrary_report_content(self):
        _state, adapter = self.make_runtime()
        report = "Revenue report: keep this model-authored text unchanged."
        await adapter.send("42", cron_envelope(report), metadata={"notify": True})
        actual = adapter.sent[0][1]
        self.assertIn(report, actual)
        self.assertIn("Ответ cron-задачи: Inventory check", actual)

    def test_scheduler_hook_translates_known_failure_before_compact_delivery(self):
        state = RuntimeState(Catalog.from_yaml(ROOT / "rules" / "ru.yaml"), Reporter())
        delivered = []

        def original_deliver(
            job, content, adapters=None, loop=None, *, for_failure=False
        ):
            delivered.append((content, for_failure))

        scheduler = SimpleNamespace(
            _deliver_result=original_deliver,
            load_config=lambda: {"cron": {"wrap_response": True}},
        )
        previous = sys.modules.get("cron")
        sys.modules["cron"] = SimpleNamespace(scheduler=scheduler)
        try:
            self.assertEqual("installed", install_cron_delivery_wrapper(state))
            scheduler._deliver_result(
                {"id": "cron-test-42", "name": "Inventory check"},
                CRON_FAILURE,
                for_failure=True,
            )
        finally:
            if previous is None:
                sys.modules.pop("cron", None)
            else:
                sys.modules["cron"] = previous

        self.assertEqual(1, len(delivered))
        content, for_failure = delivered[0]
        self.assertTrue(for_failure)
        self.assertIn("⏰ Inventory check", content)
        self.assertIn("Задача Cron «Inventory check» завершилась ошибкой", content)
        self.assertNotIn("Cron 'Inventory check' failed", content)
        self.assertIn(
            "Script exited with code 1 stdout: API returned 503", content
        )


if __name__ == "__main__":
    unittest.main()
