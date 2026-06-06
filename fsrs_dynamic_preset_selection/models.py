from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

FsrsPresetVersion = Literal["seven", "six", "five", "four"]


@dataclass(frozen=True)
class AddonFsrsPresetConfig:
    id: str
    name: str
    fsrs_version: FsrsPresetVersion
    params: tuple[float, ...]
    desired_retention: float
    historical_retention: float
    ignore_revlogs_before_date: str = ""
    deck: str = ""
    search: str = ""
    first_grade: int | None = None
    include_same_day_reviews: bool | None = None
    fsrs_dynamic_desired_retention_enabled: bool = False
    fsrs_dynamic_desired_retention_review_limit: int | None = None
    fsrs_dynamic_desired_retention_max_cost_perday_minutes: float | None = None
    fsrs_dynamic_desired_retention_params: tuple[float, ...] = ()
    fsrs_dynamic_desired_retention_weights: tuple[float, ...] = ()
    fsrs_dynamic_desired_retention_avg_drs: tuple[float, ...] = ()
    fsrs_dynamic_desired_retention_fsrs_eq_weights: tuple[float, ...] = ()
    fsrs_dynamic_desired_retention_fsrs_eq_drs: tuple[float, ...] = ()
    fsrs_dynamic_desired_retention_min: float = 0.0
    fsrs_dynamic_desired_retention_max: float = 0.0
    fsrs_dynamic_desired_retention_clamp: bool = False

    def to_overlay_dict(self) -> dict[str, object]:
        overlay = {
            "id": self.id,
            "name": self.name,
            "fsrs_version": self.fsrs_version,
            "params": list(self.params),
            "desired_retention": self.desired_retention,
            "historical_retention": self.historical_retention,
            "ignore_revlogs_before_date": self.ignore_revlogs_before_date,
        }
        if (
            self.fsrs_dynamic_desired_retention_enabled
            and self.has_dynamic_desired_retention_policy()
        ):
            overlay.update(
                {
                    "fsrs_dynamic_desired_retention_enabled": True,
                    "fsrs_dynamic_desired_retention_params": list(
                        self.fsrs_dynamic_desired_retention_params
                    ),
                    "fsrs_dynamic_desired_retention_weights": list(
                        self.fsrs_dynamic_desired_retention_weights
                    ),
                    "fsrs_dynamic_desired_retention_avg_drs": list(
                        self.fsrs_dynamic_desired_retention_avg_drs
                    ),
                    "fsrs_dynamic_desired_retention_fsrs_eq_weights": list(
                        self.fsrs_dynamic_desired_retention_fsrs_eq_weights
                    ),
                    "fsrs_dynamic_desired_retention_fsrs_eq_drs": list(
                        self.fsrs_dynamic_desired_retention_fsrs_eq_drs
                    ),
                    "fsrs_dynamic_desired_retention_min": self.fsrs_dynamic_desired_retention_min,
                    "fsrs_dynamic_desired_retention_max": self.fsrs_dynamic_desired_retention_max,
                    "fsrs_dynamic_desired_retention_clamp": self.fsrs_dynamic_desired_retention_clamp,
                }
            )
        return overlay

    def has_dynamic_desired_retention_policy(self) -> bool:
        return (
            len(self.fsrs_dynamic_desired_retention_params) == 15
            and len(self.fsrs_dynamic_desired_retention_weights)
            == len(self.fsrs_dynamic_desired_retention_avg_drs)
            and len(self.fsrs_dynamic_desired_retention_weights) >= 2
            and 0
            < self.fsrs_dynamic_desired_retention_min
            < self.fsrs_dynamic_desired_retention_max
            < 1
            and (
                not self.fsrs_dynamic_desired_retention_fsrs_eq_weights
                or len(self.fsrs_dynamic_desired_retention_fsrs_eq_weights)
                == len(self.fsrs_dynamic_desired_retention_fsrs_eq_drs)
            )
        )

    def dynamic_desired_retention_range(self) -> tuple[float, float] | None:
        if not self.fsrs_dynamic_desired_retention_avg_drs:
            return None
        return (
            min(self.fsrs_dynamic_desired_retention_avg_drs),
            max(self.fsrs_dynamic_desired_retention_avg_drs),
        )

    def fsrs_equivalent_desired_retention_range(self) -> tuple[float, float] | None:
        if not self.fsrs_dynamic_desired_retention_fsrs_eq_drs:
            return None
        return (
            min(self.fsrs_dynamic_desired_retention_fsrs_eq_drs),
            max(self.fsrs_dynamic_desired_retention_fsrs_eq_drs),
        )

    def to_rule_dict(self) -> dict[str, str] | None:
        search = preset_search(self.deck, self.search, self.first_grade)
        if not search:
            return None
        return {
            "search": search,
            "preset_id": self.id,
        }


@dataclass(frozen=True)
class FsrsPresetRuleConfig:
    search: str
    preset_id: str

    def to_overlay_dict(self) -> dict[str, str]:
        return {
            "search": self.search,
            "preset_id": self.preset_id,
        }


@dataclass(frozen=True)
class DynamicPresetSelectionConfig:
    presets: tuple[AddonFsrsPresetConfig, ...]
    rules: tuple[FsrsPresetRuleConfig, ...]

    def to_overlay_dict(self) -> dict[str, object]:
        deck_rules = [
            rule
            for preset in self.presets
            if (rule := preset.to_rule_dict()) is not None
        ]
        return {
            "presets": [preset.to_overlay_dict() for preset in self.presets],
            "rules": deck_rules + [rule.to_overlay_dict() for rule in self.rules],
        }


def deck_search(deck_name: str) -> str:
    escaped = (
        deck_name.replace("\\", "\\\\")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace('"', '\\"')
    )
    return f'deck:"{escaped}"'


def preset_search(deck_name: str, search: str, first_grade: int | None = None) -> str:
    terms = []
    if deck_name:
        terms.append(deck_search(deck_name))
    if first_grade is not None:
        terms.append(f"firstgrade:{first_grade}")
    if search.strip():
        terms.append(search.strip())
    return " ".join(terms)


def preset_id_from_name(name: str, first_grade: int | None = None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    preset_id = f"addon:fsrs-dynamic-preset-selection:{slug or 'preset'}"
    if first_grade is not None:
        preset_id += f":firstgrade-{first_grade}"
    return preset_id
