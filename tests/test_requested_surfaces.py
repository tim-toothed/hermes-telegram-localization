import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from translator import Catalog


class RequestedSurfaceCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.from_yaml(ROOT / "rules" / "ru.yaml")

    def assert_translation(self, source: str, expected: str, boundary: str = "telegram.format_message"):
        result = self.catalog.translate(source, boundary=boundary)
        self.assertEqual("translated", result.status, result)
        self.assertEqual(expected, result.text)

    def test_codex_compaction_autoraise_preserves_model_numbers_and_command(self):
        source = (
            "ℹ️ Codex model gpt-5.6-luna has a 272K context window; raising the "
            "compaction trigger from 50% to 85% so more of it is used before summarizing.\n"
            "   Restore the old trigger: hermes config set compression.codex_gpt55_autoraise false"
        )
        expected = (
            "ℹ️ Модель Codex gpt-5.6-luna имеет окно контекста 272K; порог сжатия "
            "повышен с 50% до 85%, чтобы использовать больше контекста до создания сводки.\n"
            "   Вернуть прежний порог: hermes config set compression.codex_gpt55_autoraise false"
        )
        self.assert_translation(source, expected)

    def test_daily_session_reset_preserves_dynamic_time_and_commands(self):
        source = (
            "◐ Session automatically reset (daily schedule at 04:00). Conversation history cleared.\n"
            "Use /resume to continue a previous session, or just keep chatting to start fresh.\n"
            "Adjust reset behavior in config.yaml under session_reset."
        )
        expected = (
            "◐ Сеанс автоматически сброшен (ежедневно в 04:00). История диалога очищена.\n"
            "Используйте /resume, чтобы продолжить предыдущий сеанс, или просто начните новый диалог.\n"
            "Настройте сброс в config.yaml в разделе session_reset."
        )
        self.assert_translation(source, expected)

    def test_context_threshold_preserves_token_counts_and_commands(self):
        source = (
            "⚠ Context is over the compression threshold (190,123 / 204,000 tokens), but "
            "automatic compression was already attempted this turn. Send /new to start fresh "
            "or /compress to retry manually."
        )
        expected = (
            "⚠ Контекст превышает порог сжатия (190,123 / 204,000 токенов), но автоматическое "
            "сжатие уже выполнялось в этом запросе. Отправьте /new, чтобы начать новый сеанс, "
            "или /compress, чтобы повторить сжатие вручную."
        )
        self.assert_translation(source, expected)

    def test_compression_success_preserves_all_dynamic_values(self):
        self.assert_translation(
            "✓ Compressed: 176 → 73 messages\nApprox request size: 123,456 tokens (estimated)",
            "✓ Сжато: 176 → 73 сообщений\nПримерный размер запроса: 123,456 токенов (estimated)",
        )

    def test_compression_in_progress_preserves_holder_verbatim(self):
        holder = "pid=3384, tid=140331, agent=Agent@7f24, nonce=f8a6d2"
        self.assert_translation(
            "⚠️ Compression already in progress for this session.\n"
            f"The current compression holder is still active ({holder}). Use `/compress --cancel` only if it is genuinely stuck.",
            "⚠️ Сжатие для этого сеанса уже выполняется.\n"
            f"Текущий владелец блокировки сжатия всё ещё активен ({holder}). Используйте `/compress --cancel`, только если процесс действительно завис.",
        )

    def test_compaction_start(self):
        self.assert_translation(
            "Compacting context — summarizing earlier conversation so I can continue...",
            "Сжимаю контекст — создаю сводку предыдущей части диалога, чтобы продолжить...",
        )

    def test_fallback_status(self):
        self.assert_translation(
            "⚠️ Provider unreachable — switching to fallback provider...",
            "⚠️ Провайдер недоступен — переключаюсь на резервного провайдера...",
        )

    def test_busy_model_switch_preserves_stop(self):
        self.assert_translation(
            "Agent is running — wait or /stop first, then switch models.",
            "Агент выполняет запрос — дождитесь завершения или сначала используйте /stop, затем переключите модель.",
        )

    def test_model_endpoint_existing_rule_is_single_russian_variant(self):
        self.assert_translation(
            "⚠️ **The model server is not responding.** Check the configured endpoint or try again later. The request was not completed.",
            "⚠️ **Сервер модели не отвечает.** Проверьте настроенный endpoint или попробуйте позже. Запрос не выполнен.",
        )

    def test_current_codex_autoraise_surface(self):
        self.assert_translation(
            "ℹ Codex gpt-5.6-luna caps context at 272K, so auto-compaction was raised "
            "to 85% (from 50%) to use more of the window before summarizing.\n"
            "  Opt back out: hermes config set compression.codex_gpt55_autoraise false",
            "ℹ Codex gpt-5.6-luna ограничивает контекст до 272K, поэтому порог автоматического "
            "сжатия повышен до 85% (с 50%), чтобы использовать больше окна до создания сводки.\n"
            "  Отключить автоповышение: hermes config set compression.codex_gpt55_autoraise false",
        )

    def test_current_daily_reset_surface(self):
        self.assert_translation(
            "◐ Session automatically reset (daily schedule at 4:00). Conversation history cleared.\n"
            "Use /resume to browse and restore a previous session.\n"
            "Adjust reset timing in config.yaml under session_reset.",
            "◐ Сеанс автоматически сброшен (ежедневно в 4:00). История диалога очищена.\n"
            "Используйте /resume, чтобы найти и восстановить предыдущий сеанс.\n"
            "Настройте время сброса в config.yaml в разделе session_reset.",
        )

    def test_current_threshold_blocked_surface(self):
        self.assert_translation(
            "⚠ Context is over the compression threshold (~190,123 tokens >= 180,000) but "
            "compression is currently blocked (cooldown:30s). The model may stop responding. "
            "Run /new to start a fresh session or /compress to retry immediately.",
            "⚠ Контекст превышает порог сжатия (~190,123 токенов >= 180,000), но сжатие сейчас "
            "заблокировано (cooldown:30s). Модель может перестать отвечать. Используйте /new для "
            "нового сеанса или /compress, чтобы немедленно повторить сжатие.",
        )

    def test_current_compression_result_is_segmented_without_value_loss(self):
        self.assert_translation(
            "🗜️ Compressed: 176 → 73 messages\nApprox request size: ~210,000 → ~123,456 tokens",
            "🗜️ Сжато: 176 → 73 сообщений\nПримерный размер запроса: ~210,000 → ~123,456 токенов",
        )

    def test_current_compression_holder_is_verbatim(self):
        holder = "pid=3384, tid=140331, agent=Agent@7f24, nonce=f8a6d2"
        self.assert_translation(
            f"⏳ Compression already in progress for this session (holder: {holder}). Please wait for it to finish.",
            f"⏳ Сжатие для этого сеанса уже выполняется (holder: {holder}). Дождитесь его завершения.",
        )

    def test_current_compaction_start_and_heartbeat(self):
        self.assert_translation(
            "🗜️ Compacting context — summarizing earlier conversation so I can continue...",
            "🗜️ Сжимаю контекст — создаю сводку предыдущей части диалога, чтобы продолжить...",
        )
        self.assert_translation(
            "🗜️ Compacting context — still summarizing earlier conversation so I can continue...",
            "🗜️ Сжимаю контекст — всё ещё создаю сводку предыдущей части диалога, чтобы продолжить...",
        )

    def test_current_fallback_preserves_models_providers_and_reason(self):
        self.assert_translation(
            "⚠️ Model fallback: gpt-5.6-luna via openai-codex unavailable (server error); "
            "using claude-opus-4-1 via anthropic.",
            "⚠️ Резервная модель: gpt-5.6-luna через openai-codex недоступна (server error); "
            "используется claude-opus-4-1 через anthropic.",
        )

    def test_current_endpoint_surface(self):
        self.assert_translation(
            "⚠️ The model server is not responding — it looks like the configured model endpoint is not running or is unreachable.",
            "⚠️ Сервер модели не отвечает — похоже, настроенная конечная точка модели не запущена или недоступна.",
        )


if __name__ == "__main__":
    unittest.main()
