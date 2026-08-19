"""Append-only JSONL runtime report without recording message bodies."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class JsonlReporter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def emit(
        self,
        event: Mapping[str, Any],
        *,
        input_text: str | None = None,
        output_text: str | None = None,
    ) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **dict(event),
        }
        if input_text is not None:
            payload["input_sha256"] = hashlib.sha256(
                input_text.encode("utf-8")
            ).hexdigest()
            payload["input_chars"] = len(input_text)
        if output_text is not None:
            payload["output_chars"] = len(output_text)
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
