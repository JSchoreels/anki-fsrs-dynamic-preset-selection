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

    def to_overlay_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "fsrs_version": self.fsrs_version,
            "params": list(self.params),
            "desired_retention": self.desired_retention,
            "historical_retention": self.historical_retention,
            "ignore_revlogs_before_date": self.ignore_revlogs_before_date,
        }

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
