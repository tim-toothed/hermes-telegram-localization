"""Install translation boundaries on the live Telegram adapter instance."""

from __future__ import annotations

import inspect
import sys
from collections import Counter
from contextvars import ContextVar
from typing import Any, Callable

from .account_usage_localization import translate_account_usage_envelope
from .background_review_localization import translate_background_review_notification
from .delivery_recovery_localization import translate_delivery_recovery_notice
from .model_switch_localization import translate_model_switch_card
from .runtime_status_localization import translate_runtime_status
from .translator import Catalog, TranslationResult


def _safe_transform(transform: Callable[[str], str], text: str) -> str:
    """Run a pure envelope recognizer without ever blocking delivery."""
    try:
        return transform(text)
    except Exception:
        return text


class RuntimeState:
    def __init__(self, catalog: Catalog, reporter: Any) -> None:
        self.catalog = catalog
        self.reporter = reporter
        self.counters: Counter[str] = Counter()
        self.boundaries: dict[str, str] = {}
        self.adapter_class = ""
        self._suppress_translation: ContextVar[bool] = ContextVar(
            "hermes_telegram_localization_suppress", default=False
        )
        self._command_dispatch: ContextVar[bool] = ContextVar(
            "hermes_telegram_localization_command_dispatch", default=False
        )
        self._delivery_cycle: ContextVar[dict[str, Any] | None] = ContextVar(
            "hermes_telegram_localization_delivery_cycle", default=None
        )
        self._runtime_status_message_ids: dict[tuple[str, str], None] = {}

    def begin_delivery_cycle(self) -> None:
        """Start narrow duplicate tracking for one incoming gateway event."""
        self._delivery_cycle.set({"generation": 0, "provider_results": {}})

    def provider_surface(self, text: Any) -> tuple[bool, bool]:
        """Return ``(provider_failure, fallback_transition)`` for exact catalog surfaces."""
        if not isinstance(text, str):
            return False, False
        translated = self.catalog.translate(text, boundary="telegram.transport")
        rule_id = translated.rule_id or ""
        family = translated.family or ""
        provider_failure = (
            rule_id.startswith("gateway.provider_error.")
            or family.startswith("gateway.provider_error")
        )
        fallback_transition = (
            rule_id.startswith("requested.provider.fallback")
            or "switching to fallback provider..." in text
        )
        return provider_failure, fallback_transition

    def provider_result(self) -> tuple[bool, Any]:
        cycle = self._delivery_cycle.get()
        if cycle is None:
            return False, None
        key = (cycle["generation"], "provider_failure")
        results = cycle["provider_results"]
        return key in results, results.get(key)

    def record_provider_result(self, result: Any) -> None:
        cycle = self._delivery_cycle.get()
        if cycle is None:
            return
        cycle["provider_results"][(cycle["generation"], "provider_failure")] = result

    def advance_provider_generation(self) -> None:
        cycle = self._delivery_cycle.get()
        if cycle is not None:
            cycle["generation"] += 1

    def translate_provider_failure(self, text: str) -> str:
        body, marker, details = text.partition("\n\nProvider said: ")
        card = self.catalog.translate(body, boundary="telegram.provider_failure")
        if not marker and card.rule_id != "telegram.provider_023.codex_app_server":
            return text
        if card.status != "translated" or not (card.rule_id or "").startswith("telegram.provider_023."):
            return text
        if not marker:
            return card.text
        raw, separator, last = details.rpartition("\n\n")
        reset = self.catalog.translate(last, boundary="telegram.provider_reset")
        has_reset = bool(separator and reset.rule_id == "telegram.provider_023.reset_at")
        detail = raw if has_reset else details
        localized = self.catalog.translate(detail, boundary="telegram.codex_detail")
        if localized.rule_id in {"telegram.provider_023.codex_limit", "telegram.provider_023.codex_limit_retry"}:
            detail = localized.text
        return card.text + "\n\nОтвет провайдера: " + detail + (separator + reset.text if has_reset else "")

    def translate_final_system_surface(self, text: Any) -> tuple[Any, bool]:
        """Translate only recognized Hermes-owned fragments inside a final reply."""
        if not isinstance(text, str):
            return text, False
        cron = self.catalog.translate(text, boundary="telegram.transport")
        if (
            cron.status == "translated"
            and cron.rule_id == "locale.cron.delivery.wrapper"
        ):
            return cron.text, True
        marker = "⚠️ File-mutation verifier:"
        replacement = "⚠️ Проверка изменения файла:"
        if text.startswith(marker):
            return replacement + text[len(marker):], True
        footer_marker = "\n\n" + marker
        if footer_marker in text:
            head, tail = text.rsplit(footer_marker, 1)
            return head + "\n\n" + replacement + tail, True
        head, separator, tail = text.rpartition("\n\n")
        notice = self.catalog.translate(tail, boundary="telegram.final_turn_notice")
        if notice.status == "translated" and (notice.rule_id or "").startswith("telegram.turn_notice."):
            if separator:
                body = self.catalog.translate(head, boundary="telegram.final_turn_notice")
                if body.status == "translated" and (body.rule_id or "").startswith("telegram.turn_notice.truncated"):
                    head = body.text
                else:
                    head = self.translate_provider_failure(head)
            return head + separator + notice.text, True
        provider_card = self.translate_provider_failure(text)
        if provider_card != text:
            return provider_card, True
        provider_failure, _fallback = self.provider_surface(text)
        if not provider_failure:
            return text, False
        translated = self.catalog.translate(text, boundary="telegram.transport")
        return translated.text, translated.status == "translated"

    def translate(self, text: Any, boundary: str) -> Any:
        if self._suppress_translation.get():
            return text
        if not isinstance(text, str) or not text:
            return text
        try:
            # Telegram approval cards reach the adapter already formatted as HTML.
            if boundary in ("TelegramAdapter._send_message_with_thread_fallback", "TelegramAdapter.format_message"):
                labels = ("Why it was flagged: ", "Почему помечена: ", "Reason: ", "Причина: ")
                markers = (prefix + label for prefix in ("</pre>\n\n", "\n```\n", "\n```\n\n") for label in labels)
                for marker in markers:
                    head, separator, tail = text.rpartition(marker)
                    if not separator:
                        continue
                    reason, newline, rest = tail.partition("\n")
                    localized = self.catalog.translate(reason, boundary="telegram.approval_reason")
                    if localized.status == "translated" and (localized.rule_id or "").startswith("telegram.approval."):
                        return head + separator + localized.text + newline + rest
            translated_background = translate_background_review_notification(text)
            translated_recovery = translate_delivery_recovery_notice(text)
            translated_model_card = translate_model_switch_card(text)
            translated_runtime_status = translate_runtime_status(text)
            translated_account_usage = translate_account_usage_envelope(text)
            if translated_account_usage != text:
                # The account parser removes ambiguous English account lines first;
                # then the catalog can safely localize the surrounding /usage card.
                segmented = self.catalog.translate(
                    translated_account_usage, boundary=boundary
                )
                result = TranslationResult(
                    text=(
                        segmented.text
                        if segmented.status == "translated"
                        else translated_account_usage
                    ),
                    status="translated",
                    rule_id=(
                        "account_usage.structured+" + str(segmented.rule_id)
                        if segmented.status == "translated"
                        else "account_usage.structured"
                    ),
                    source_file="agent/account_usage.py,gateway/slash_commands.py",
                    family="account_usage",
                    variables={},
                )
            elif translated_background != text:
                result = TranslationResult(
                    text=translated_background,
                    status="translated",
                    rule_id="background_review.notification",
                    source_file="agent/background_review.py",
                    family="background_review",
                    variables={},
                )
            elif translated_recovery != text:
                result = TranslationResult(
                    text=translated_recovery,
                    status="translated",
                    rule_id="delivery_recovery.notice",
                    source_file="gateway/delivery_ledger.py",
                    family="delivery_recovery",
                    variables={},
                )
            elif translated_model_card != text:
                result = TranslationResult(
                    text=translated_model_card,
                    status="translated",
                    rule_id="telegram.model_switch.card",
                    source_file="gateway/slash_commands.py",
                    family="telegram.model_picker",
                    variables={},
                )
            elif translated_runtime_status != text:
                result = TranslationResult(
                    text=translated_runtime_status,
                    status="translated",
                    rule_id="runtime_status.structured",
                    source_file="gateway/run.py",
                    family="runtime_status",
                    variables={},
                )
            else:
                result = self.catalog.translate(text, boundary=boundary)
            self.counters[result.status] += 1
        except Exception as exc:
            self.counters["wrapper_error"] += 1
            try:
                self.reporter.emit(
                    {
                        "event": "translation",
                        "status": "wrapper_error",
                        "boundary": boundary,
                        "error_type": type(exc).__name__,
                    }
                )
            except Exception:
                pass
            return text

        try:
            self.reporter.emit(
                {
                    "event": "translation",
                    "status": result.status,
                    "boundary": boundary,
                    "rule_id": result.rule_id,
                    "source_file": result.source_file,
                    "family": result.family,
                    "variable_names": sorted((result.variables or {}).keys()),
                },
                input_text=text,
                output_text=result.text,
            )
        except Exception:
            self.counters["reporter_error"] += 1
        return result.text

    def summary(self) -> str:
        boundaries = ", ".join(
            f"{name}={status}" for name, status in sorted(self.boundaries.items())
        ) or "не установлены"
        return (
            "Плагин локализации загружен.\n"
            f"Telegram adapter: {self.adapter_class or 'ещё не активирован'}\n"
            f"Границы: {boundaries}\n"
            f"Переведено: {self.counters['translated']}\n"
            f"Неоднозначно: {self.counters['ambiguous']}\n"
            f"Пропущено без изменений: {self.counters['passthrough']}\n"
            f"Правил: {self.catalog.rule_count}"
        )


_COMPACTION_STATUS_TEXTS = frozenset({
    "🗜️ Compacting context — summarizing earlier conversation so I can continue...",
    "🗜️ Compacting context — still summarizing earlier conversation so I can continue...",
    "✓ Context compaction complete — continuing turn...",
})


def _install_compaction_status_entry(adapter: Any, state: RuntimeState) -> None:
    """Translate known system statuses before rich send/edit bypasses formatting."""
    boundary = "TelegramAdapter.send_or_update_status.compaction_entry"
    original = getattr(adapter, "send_or_update_status", None)
    if not callable(original):
        state.boundaries[boundary] = "method_missing"
        return
    signature = inspect.signature(original)

    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            bound = signature.bind_partial(*args, **kwargs)
            content = bound.arguments.get("content")
            if isinstance(content, str) and content in _COMPACTION_STATUS_TEXTS:
                translated = state.translate(content, boundary)
                if translated != content:
                    bound.arguments["content"] = translated
                    args, kwargs = bound.args, bound.kwargs
        except Exception:
            # Localization must never block delivery or alter the original call.
            pass
        return await original(*args, **kwargs)

    setattr(adapter, "send_or_update_status", wrapped)
    state.boundaries[boundary] = "installed"


def _install_final_reply_guards(adapter: Any, state: RuntimeState) -> None:
    """Do not translate model-authored final replies that share adapter boundaries."""
    for method_name in ("send", "edit_message"):
        boundary = f"TelegramAdapter.{method_name}.final_reply_guard"
        original = getattr(adapter, method_name, None)
        if not callable(original):
            state.boundaries[boundary] = "method_missing"
            continue
        signature = inspect.signature(original)

        async def guarded(
            *args: Any,
            _original: Any = original,
            _signature: Any = signature,
            _method_name: str = method_name,
            **kwargs: Any,
        ) -> Any:
            bound = None
            try:
                bound = _signature.bind_partial(*args, **kwargs)
                metadata = bound.arguments.get("metadata")
            except Exception:
                metadata = kwargs.get("metadata")

            suppress_final_reply = bool(
                isinstance(metadata, dict)
                and metadata.get("notify") is True
                and not state._command_dispatch.get()
            )
            content = bound.arguments.get("content") if bound is not None else None
            provider_failure, fallback_transition = state.provider_surface(content)
            final_system_translated = False
            if provider_failure:
                already_sent, previous_result = state.provider_result()
                if already_sent:
                    return previous_result
            if suppress_final_reply and bound is not None:
                translated, final_system_translated = (
                    state.translate_final_system_surface(content)
                )
                if final_system_translated:
                    bound.arguments["content"] = translated

            recovery_translated = False
            runtime_status_translated = False
            runtime_status_send = False
            is_stream_preview = bool(
                isinstance(metadata, dict)
                and metadata.get("expect_edits") is True
            )
            if bound is not None and _method_name == "send" and not suppress_final_reply:
                content = bound.arguments.get("content")
                if isinstance(content, str):
                    runtime_status_send = bool(
                        not is_stream_preview
                        and _safe_transform(translate_runtime_status, content) != content
                    )
                    if not is_stream_preview:
                        progress = state.catalog.translate(content, boundary="telegram.provider_progress")
                        if progress.status == "translated":
                            bound.arguments["content"] = progress.text
                    candidate = _safe_transform(
                        translate_delivery_recovery_notice, content
                    )
                    if candidate != content:
                        translated = state.translate(
                            content, "TelegramAdapter.send.delivery_recovery_entry"
                        )
                        if translated != content:
                            bound.arguments["content"] = translated
                            recovery_translated = True

            # Heartbeat refreshes use raw edit_message(finalize=False). Translate
            # only IDs previously returned by a recognized non-model heartbeat send.
            if (
                bound is not None
                and _method_name == "edit_message"
                and bound.arguments.get("finalize", False) is False
            ):
                status_key = (
                    str(bound.arguments.get("chat_id")),
                    str(bound.arguments.get("message_id")),
                )
                content = bound.arguments.get("content")
                if (
                    status_key in state._runtime_status_message_ids
                    and isinstance(content, str)
                ):
                    candidate = _safe_transform(translate_runtime_status, content)
                    if candidate != content:
                        translated = state.translate(
                            content, "TelegramAdapter.edit_message.runtime_status_entry"
                        )
                        if translated != content:
                            bound.arguments["content"] = translated
                            runtime_status_translated = True

            # Entry translators already returned their final localized envelope;
            # suppress downstream reprocessing while preserving model-reply guards.
            token = state._suppress_translation.set(
                suppress_final_reply
                or final_system_translated
                or recovery_translated
                or runtime_status_translated
            )
            try:
                if bound is not None and (
                    final_system_translated
                    or recovery_translated
                    or runtime_status_translated
                ):
                    result = await _original(*bound.args, **bound.kwargs)
                else:
                    result = await _original(*args, **kwargs)
                if provider_failure:
                    state.record_provider_result(result)
                if fallback_transition:
                    state.advance_provider_generation()
                if (
                    runtime_status_send
                    and getattr(result, "success", False)
                    and getattr(result, "message_id", None) is not None
                    and bound is not None
                ):
                    status_key = (
                        str(bound.arguments.get("chat_id")),
                        str(result.message_id),
                    )
                    if len(state._runtime_status_message_ids) >= 1024:
                        state._runtime_status_message_ids.pop(
                            next(iter(state._runtime_status_message_ids))
                        )
                    state._runtime_status_message_ids[status_key] = None
                return result
            finally:
                state._suppress_translation.reset(token)

        setattr(adapter, method_name, guarded)
        state.boundaries[boundary] = "installed"
        if method_name == "send":
            state.boundaries[
                "TelegramAdapter.send.delivery_recovery_entry"
            ] = "installed"
        elif method_name == "edit_message":
            state.boundaries[
                "TelegramAdapter.edit_message.runtime_status_entry"
            ] = "installed"


def _install_format_boundary(adapter: Any, state: RuntimeState) -> None:
    name = "TelegramAdapter.format_message"
    original = getattr(adapter, "format_message", None)
    if not callable(original):
        state.boundaries[name] = "method_missing"
        return

    def wrapped(content: str, *args: Any, **kwargs: Any) -> Any:
        translated = state.translate(content, name)
        return original(translated, *args, **kwargs)

    setattr(adapter, "format_message", wrapped)
    state.boundaries[name] = "installed"


def _install_transport_boundary(adapter: Any, state: RuntimeState) -> None:
    name = "TelegramAdapter._send_message_with_thread_fallback"
    original = getattr(adapter, "_send_message_with_thread_fallback", None)
    if not callable(original):
        state.boundaries[name] = "method_missing"
        return

    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        call_kwargs = dict(kwargs)
        for field in ("text", "caption"):
            if field in call_kwargs:
                call_kwargs[field] = state.translate(
                    call_kwargs[field], f"{name}.{field}"
                )
        return await original(*args, **call_kwargs)

    setattr(adapter, "_send_message_with_thread_fallback", wrapped)
    state.boundaries[name] = "installed"


def _install_button_boundary(adapter: Any, state: RuntimeState) -> None:
    name = "telegram.InlineKeyboardButton"
    module = sys.modules.get(adapter.__class__.__module__)
    original = getattr(module, "InlineKeyboardButton", None) if module else None
    if not callable(original):
        state.boundaries[name] = "method_missing"
        return
    if getattr(module, "_hermes_telegram_localization_button_wrapped", False):
        state.boundaries[name] = "already_installed"
        return

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        call_args = list(args)
        call_kwargs = dict(kwargs)
        if call_args and isinstance(call_args[0], str):
            call_args[0] = state.translate(call_args[0], name)
        elif isinstance(call_kwargs.get("text"), str):
            call_kwargs["text"] = state.translate(call_kwargs["text"], name)
        return original(*call_args, **call_kwargs)

    setattr(module, "InlineKeyboardButton", wrapped)
    setattr(module, "_hermes_telegram_localization_button_wrapped", True)
    state.boundaries[name] = "installed"


def _install_callback_boundaries(adapter: Any, state: RuntimeState) -> None:
    """Translate callback popups/edits only after the live adapter is available."""
    try:
        from telegram import CallbackQuery
    except Exception:
        state.boundaries["telegram.CallbackQuery"] = "class_missing"
        return

    setattr(CallbackQuery, "_hermes_telegram_localization_state", state)
    for method_name, text_position in (("answer", 0), ("edit_message_text", 0)):
        boundary = f"telegram.CallbackQuery.{method_name}"
        original = getattr(CallbackQuery, method_name, None)
        if not callable(original):
            state.boundaries[boundary] = "method_missing"
            continue
        if getattr(original, "_hermes_telegram_localization_wrapped", False):
            state.boundaries[boundary] = "already_installed"
            continue

        async def wrapped(
            self: Any,
            *args: Any,
            _original: Any = original,
            _boundary: str = boundary,
            _text_position: int = text_position,
            **kwargs: Any,
        ) -> Any:
            current_state = getattr(
                type(self), "_hermes_telegram_localization_state", state
            )
            call_args = list(args)
            call_kwargs = dict(kwargs)
            if len(call_args) > _text_position and isinstance(
                call_args[_text_position], str
            ):
                call_args[_text_position] = current_state.translate(
                    call_args[_text_position], _boundary
                )
            elif isinstance(call_kwargs.get("text"), str):
                call_kwargs["text"] = current_state.translate(
                    call_kwargs["text"], _boundary
                )
            return await _original(self, *call_args, **call_kwargs)

        setattr(wrapped, "_hermes_telegram_localization_wrapped", True)
        setattr(CallbackQuery, method_name, wrapped)
        state.boundaries[boundary] = "installed"


def install_on_adapter(adapter: Any, state: RuntimeState) -> bool:
    if getattr(adapter, "_hermes_telegram_localization_installed", False):
        return False
    setattr(adapter, "_hermes_telegram_localization_installed", True)
    state.adapter_class = (
        f"{adapter.__class__.__module__}.{adapter.__class__.__qualname__}"
    )
    _install_final_reply_guards(adapter, state)
    _install_compaction_status_entry(adapter, state)
    _install_format_boundary(adapter, state)
    _install_transport_boundary(adapter, state)
    _install_button_boundary(adapter, state)
    _install_callback_boundaries(adapter, state)
    state.reporter.emit(
        {
            "event": "adapter_install",
            "status": "installed",
            "adapter_class": state.adapter_class,
            "boundaries": dict(state.boundaries),
            "rule_count": state.catalog.rule_count,
        }
    )
    return True


def activate_from_gateway_event(
    *, event: Any, gateway: Any, state: RuntimeState
) -> None:
    source = getattr(event, "source", None)
    try:
        is_command = bool(event.is_command())
    except Exception:
        is_command = str(getattr(event, "text", "") or "").lstrip().startswith("/")
    state._command_dispatch.set(is_command)
    platform = getattr(getattr(source, "platform", None), "value", "")
    if str(platform).lower() != "telegram":
        return
    state.begin_delivery_cycle()
    adapter_for_source: Callable[..., Any] | None = None
    boundary = "GatewayRunner._delivery_adapter_for"
    for method_name in ("_delivery_adapter_for", "_adapter_for_source"):
        candidate = getattr(gateway, method_name, None)
        if callable(candidate):
            adapter_for_source = candidate
            boundary = f"GatewayRunner.{method_name}"
            break
    if adapter_for_source is None:
        state.boundaries[boundary] = "method_missing"
        return
    adapter = adapter_for_source(source)
    if adapter is None:
        state.boundaries[boundary] = "adapter_missing"
        return
    state.boundaries.pop("GatewayRunner._adapter_for_source", None)
    state.boundaries[boundary] = "installed"
    install_on_adapter(adapter, state)
