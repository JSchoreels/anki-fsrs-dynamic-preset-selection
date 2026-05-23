from __future__ import annotations

from typing import Any

from .models import (
    AddonFsrsPresetConfig,
    DynamicPresetSelectionConfig,
    FsrsPresetRuleConfig,
    FsrsPresetVersion,
)

SUPPORTED_FSRS_VERSIONS: set[str] = {"seven", "six", "five", "four"}


class ConfigError(ValueError):
    pass


def load_config(raw_config: dict[str, Any] | None) -> DynamicPresetSelectionConfig:
    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, dict):
        raise ConfigError("config must be an object")

    presets = _load_presets(raw_config.get("presets", []))
    rules = _load_rules(raw_config.get("rules", []))
    preset_ids = {preset.id for preset in presets}
    for index, rule in enumerate(rules):
        if rule.preset_id not in preset_ids:
            raise ConfigError(f"rules[{index}].preset_id references an unknown preset")

    return DynamicPresetSelectionConfig(
        presets=tuple(presets),
        rules=tuple(rules),
    )


def _load_presets(raw_presets: Any) -> list[AddonFsrsPresetConfig]:
    if not isinstance(raw_presets, list):
        raise ConfigError("presets must be a list")

    return [_load_preset(raw_preset, index) for index, raw_preset in enumerate(raw_presets)]


def _load_preset(raw_preset: Any, index: int) -> AddonFsrsPresetConfig:
    if not isinstance(raw_preset, dict):
        raise ConfigError(f"presets[{index}] must be an object")

    preset_id = _required_string(raw_preset, "id", f"presets[{index}]")
    if not preset_id.startswith("addon:"):
        raise ConfigError(f"presets[{index}].id must start with addon:")

    fsrs_version = _required_string(raw_preset, "fsrs_version", f"presets[{index}]")
    if fsrs_version not in SUPPORTED_FSRS_VERSIONS:
        raise ConfigError(f"presets[{index}].fsrs_version is not supported")

    return AddonFsrsPresetConfig(
        id=preset_id,
        name=_required_string(raw_preset, "name", f"presets[{index}]"),
        fsrs_version=fsrs_version,  # type: ignore[arg-type]
        params=tuple(_required_float_list(raw_preset, "params", f"presets[{index}]")),
        desired_retention=_required_retention(raw_preset, "desired_retention", f"presets[{index}]"),
        historical_retention=_required_retention(raw_preset, "historical_retention", f"presets[{index}]"),
        ignore_revlogs_before_date=_optional_string(
            raw_preset,
            "ignore_revlogs_before_date",
            f"presets[{index}]",
        ),
        deck=_optional_string(raw_preset, "deck", f"presets[{index}]"),
        search=_optional_string(raw_preset, "search", f"presets[{index}]"),
        first_grade=_optional_first_grade(raw_preset, f"presets[{index}]"),
        include_same_day_reviews=_optional_bool(
            raw_preset,
            "include_same_day_reviews",
            f"presets[{index}]",
        ),
    )


def _load_rules(raw_rules: Any) -> list[FsrsPresetRuleConfig]:
    if not isinstance(raw_rules, list):
        raise ConfigError("rules must be a list")

    return [_load_rule(raw_rule, index) for index, raw_rule in enumerate(raw_rules)]


def _load_rule(raw_rule: Any, index: int) -> FsrsPresetRuleConfig:
    if not isinstance(raw_rule, dict):
        raise ConfigError(f"rules[{index}] must be an object")

    return FsrsPresetRuleConfig(
        search=_required_string(raw_rule, "search", f"rules[{index}]"),
        preset_id=_required_string(raw_rule, "preset_id", f"rules[{index}]"),
    )


def _required_string(raw: dict[str, Any], key: str, path: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path}.{key} must be a non-empty string")
    return value.strip()


def _optional_string(raw: dict[str, Any], key: str, path: str) -> str:
    value = raw.get(key, "")
    if not isinstance(value, str):
        raise ConfigError(f"{path}.{key} must be a string")
    return value.strip()


def _required_float_list(raw: dict[str, Any], key: str, path: str) -> list[float]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise ConfigError(f"{path}.{key} must be a list")
    floats: list[float] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ConfigError(f"{path}.{key}[{index}] must be a number")
        floats.append(float(item))
    return floats


def _required_retention(raw: dict[str, Any], key: str, path: str) -> float:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path}.{key} must be a number")
    normalized = float(value)
    if not 0 < normalized <= 1:
        raise ConfigError(f"{path}.{key} must be greater than 0 and at most 1")
    return normalized


def _optional_first_grade(raw: dict[str, Any], path: str) -> int | None:
    value = raw.get("first_grade")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{path}.first_grade must be 1, 2, 3, or 4")
    if value not in {1, 2, 3, 4}:
        raise ConfigError(f"{path}.first_grade must be 1, 2, 3, or 4")
    return value


def _optional_bool(raw: dict[str, Any], key: str, path: str) -> bool | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ConfigError(f"{path}.{key} must be a boolean")
    return value
