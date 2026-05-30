from __future__ import annotations

from typing import Any

from .models import (
    AddonFsrsPresetConfig,
    DynamicPresetSelectionConfig,
    FsrsPresetRuleConfig,
    FsrsPresetVersion,
)

SUPPORTED_FSRS_VERSIONS: set[str] = {"seven", "six", "five", "four"}
ADR_PARAMETER_COUNT = 15


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

    adr_enabled = _optional_bool(
        raw_preset,
        "fsrs_dynamic_desired_retention_enabled",
        f"presets[{index}]",
    ) or False
    adr_params = tuple(
        _optional_float_list(
            raw_preset,
            "fsrs_dynamic_desired_retention_params",
            f"presets[{index}]",
        )
    )
    adr_weights = tuple(
        _optional_float_list(
            raw_preset,
            "fsrs_dynamic_desired_retention_weights",
            f"presets[{index}]",
        )
    )
    adr_avg_drs = tuple(
        _optional_float_list(
            raw_preset,
            "fsrs_dynamic_desired_retention_avg_drs",
            f"presets[{index}]",
        )
    )
    adr_fsrs_eq_weights = tuple(
        _optional_float_list(
            raw_preset,
            "fsrs_dynamic_desired_retention_fsrs_eq_weights",
            f"presets[{index}]",
        )
    )
    adr_fsrs_eq_drs = tuple(
        _optional_float_list(
            raw_preset,
            "fsrs_dynamic_desired_retention_fsrs_eq_drs",
            f"presets[{index}]",
        )
    )
    adr_min = _optional_float(
        raw_preset,
        "fsrs_dynamic_desired_retention_min",
        f"presets[{index}]",
    )
    adr_max = _optional_float(
        raw_preset,
        "fsrs_dynamic_desired_retention_max",
        f"presets[{index}]",
    )
    adr_review_limit = _optional_positive_int(
        raw_preset,
        "fsrs_dynamic_desired_retention_review_limit",
        f"presets[{index}]",
    )
    adr_max_cost_minutes = _optional_positive_float(
        raw_preset,
        "fsrs_dynamic_desired_retention_max_cost_perday_minutes",
        f"presets[{index}]",
    )
    _validate_dynamic_desired_retention(
        path=f"presets[{index}]",
        fsrs_version=fsrs_version,
        enabled=adr_enabled,
        params=adr_params,
        weights=adr_weights,
        avg_drs=adr_avg_drs,
        fsrs_eq_weights=adr_fsrs_eq_weights,
        fsrs_eq_drs=adr_fsrs_eq_drs,
        retention_min=adr_min,
        retention_max=adr_max,
    )

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
        fsrs_dynamic_desired_retention_enabled=adr_enabled,
        fsrs_dynamic_desired_retention_review_limit=adr_review_limit,
        fsrs_dynamic_desired_retention_max_cost_perday_minutes=adr_max_cost_minutes,
        fsrs_dynamic_desired_retention_params=adr_params,
        fsrs_dynamic_desired_retention_weights=adr_weights,
        fsrs_dynamic_desired_retention_avg_drs=adr_avg_drs,
        fsrs_dynamic_desired_retention_fsrs_eq_weights=adr_fsrs_eq_weights,
        fsrs_dynamic_desired_retention_fsrs_eq_drs=adr_fsrs_eq_drs,
        fsrs_dynamic_desired_retention_min=adr_min or 0.0,
        fsrs_dynamic_desired_retention_max=adr_max or 0.0,
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


def _optional_float_list(raw: dict[str, Any], key: str, path: str) -> list[float]:
    value = raw.get(key, [])
    if not isinstance(value, list):
        raise ConfigError(f"{path}.{key} must be a list")
    floats: list[float] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ConfigError(f"{path}.{key}[{index}] must be a number")
        floats.append(float(item))
    return floats


def _optional_float(raw: dict[str, Any], key: str, path: str) -> float | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path}.{key} must be a number")
    return float(value)


def _optional_positive_float(raw: dict[str, Any], key: str, path: str) -> float | None:
    value = _optional_float(raw, key, path)
    if value is not None and value <= 0:
        raise ConfigError(f"{path}.{key} must be positive")
    return value


def _optional_positive_int(raw: dict[str, Any], key: str, path: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{path}.{key} must be an integer")
    if value <= 0:
        raise ConfigError(f"{path}.{key} must be positive")
    return value


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


def _validate_dynamic_desired_retention(
    *,
    path: str,
    fsrs_version: str,
    enabled: bool,
    params: tuple[float, ...],
    weights: tuple[float, ...],
    avg_drs: tuple[float, ...],
    fsrs_eq_weights: tuple[float, ...],
    fsrs_eq_drs: tuple[float, ...],
    retention_min: float | None,
    retention_max: float | None,
) -> None:
    has_policy_data = bool(
        params
        or weights
        or avg_drs
        or fsrs_eq_weights
        or fsrs_eq_drs
        or retention_min
        or retention_max
    )
    if not enabled and not has_policy_data:
        return
    if fsrs_version != "seven":
        raise ConfigError(f"{path}.fsrs_dynamic_desired_retention_enabled requires FSRS-7")
    if enabled and not has_policy_data:
        return
    if len(params) != ADR_PARAMETER_COUNT:
        raise ConfigError(f"{path}.fsrs_dynamic_desired_retention_params must contain 15 numbers")
    if len(weights) != len(avg_drs) or len(weights) < 2:
        raise ConfigError(
            f"{path}.fsrs_dynamic_desired_retention_weights and "
            "fsrs_dynamic_desired_retention_avg_drs must have matching lengths of at least 2"
        )
    if any(weight < 0 for weight in weights):
        raise ConfigError(f"{path}.fsrs_dynamic_desired_retention_weights must be non-negative")
    if any(not 0 <= avg_dr <= 1 for avg_dr in avg_drs):
        raise ConfigError(
            f"{path}.fsrs_dynamic_desired_retention_avg_drs must be between 0 and 1"
        )
    if len(fsrs_eq_weights) != len(fsrs_eq_drs):
        raise ConfigError(
            f"{path}.fsrs_dynamic_desired_retention_fsrs_eq_weights and "
            "fsrs_dynamic_desired_retention_fsrs_eq_drs must have matching lengths"
        )
    if any(weight < 0 for weight in fsrs_eq_weights):
        raise ConfigError(
            f"{path}.fsrs_dynamic_desired_retention_fsrs_eq_weights must be non-negative"
        )
    if any(not 0 <= dr <= 1 for dr in fsrs_eq_drs):
        raise ConfigError(
            f"{path}.fsrs_dynamic_desired_retention_fsrs_eq_drs must be between 0 and 1"
        )
    if (
        retention_min is None
        or retention_max is None
        or not 0 < retention_min < retention_max < 1
    ):
        raise ConfigError(
            f"{path}.fsrs_dynamic_desired_retention_min/max must be valid retention bounds"
        )
