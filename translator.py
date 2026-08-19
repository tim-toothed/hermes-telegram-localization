"""Runtime translation catalog for Hermes Telegram output."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any, Mapping, Pattern

import yaml


@dataclass(frozen=True)
class TranslationResult:
    text: str
    status: str
    rule_id: str | None = None
    source_file: str | None = None
    family: str | None = None
    variables: Mapping[str, str] | None = None


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    source_file: str
    family: str
    source: str
    target: str
    pattern: Pattern[str] | None = None
    boundaries: tuple[str, ...] = ()


def _field_names(template: str) -> list[str]:
    names: list[str] = []
    for _literal, name, _format_spec, _conversion in Formatter().parse(template):
        if name:
            if not name.isidentifier():
                raise ValueError(f"Invalid placeholder name {name!r}")
            names.append(name)
    return names


def _compile_template(
    source: str, placeholder_patterns: Mapping[str, str]
) -> Pattern[str] | None:
    fields = _field_names(source)
    if not fields:
        return None
    parts: list[str] = []
    seen: set[str] = set()
    for literal, name, _format_spec, _conversion in Formatter().parse(source):
        parts.append(re.escape(literal))
        if name:
            if name in seen:
                parts.append(f"(?P={name})")
                continue
            seen.add(name)
            constraint = placeholder_patterns.get(name, ".+?")
            parts.append(f"(?P<{name}>{constraint})")
    return re.compile("^" + "".join(parts) + "$", re.DOTALL)


class Catalog:
    def __init__(self, rules: list[_Rule]) -> None:
        self.rule_count = len(rules)
        self._literal_rules: dict[str, list[_Rule]] = {}
        self._template_rules: list[_Rule] = []
        for rule in rules:
            if rule.pattern is None:
                self._literal_rules.setdefault(rule.source, []).append(rule)
            else:
                self._template_rules.append(rule)

    @classmethod
    def from_yaml(cls, path: Path) -> "Catalog":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("Localization catalog root must be a mapping")
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Catalog":
        rules: list[_Rule] = []
        groups = data.get("groups", {})
        if not isinstance(groups, dict):
            raise ValueError("groups must be a mapping")
        seen_ids: set[str] = set()
        for group_name, group in groups.items():
            if not isinstance(group, dict):
                raise ValueError(f"Group {group_name!r} must be a mapping")
            source_file = str(group["source_file"])
            for item in group.get("rules", []):
                rule_id = str(item["id"])
                if rule_id in seen_ids:
                    raise ValueError(f"Duplicate rule id: {rule_id}")
                seen_ids.add(rule_id)
                source = str(item["from"])
                target = str(item["to"])
                source_fields = set(_field_names(source))
                target_fields = set(_field_names(target))
                if target_fields - source_fields:
                    missing = ", ".join(sorted(target_fields - source_fields))
                    raise ValueError(
                        f"Rule {rule_id} target uses unknown placeholders: {missing}"
                    )
                placeholders = {
                    str(name): str(pattern)
                    for name, pattern in item.get("placeholders", {}).items()
                }
                rules.append(
                    _Rule(
                        rule_id=rule_id,
                        source_file=source_file,
                        family=str(item.get("family", "")),
                        source=source,
                        target=target,
                        pattern=_compile_template(source, placeholders),
                        boundaries=tuple(str(value) for value in item.get("boundaries", [])),
                    )
                )
        return cls(rules)

    @staticmethod
    def _translated(rule: _Rule, variables: Mapping[str, str]) -> TranslationResult:
        return TranslationResult(
            text=rule.target.format_map(dict(variables)),
            status="translated",
            rule_id=rule.rule_id,
            source_file=rule.source_file,
            family=rule.family,
            variables=dict(variables),
        )

    def translate(self, text: str, boundary: str | None = None) -> TranslationResult:
        def allowed(rule: _Rule) -> bool:
            return not rule.boundaries or boundary in rule.boundaries

        matches: list[tuple[_Rule, Mapping[str, str]]] = [
            (rule, {})
            for rule in self._literal_rules.get(text, [])
            if allowed(rule)
        ]
        for rule in self._template_rules:
            if not allowed(rule):
                continue
            assert rule.pattern is not None
            match = rule.pattern.fullmatch(text)
            if match is not None:
                matches.append((rule, match.groupdict()))
        if not matches:
            return TranslationResult(text=text, status="passthrough", variables={})
        if len(matches) > 1:
            return TranslationResult(
                text=text,
                status="ambiguous",
                rule_id=",".join(rule.rule_id for rule, _ in matches),
                variables={},
            )
        rule, variables = matches[0]
        return self._translated(rule, variables)
