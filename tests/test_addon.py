from __future__ import annotations

import logging
import sys
from types import ModuleType, SimpleNamespace

import fsrs_dynamic_preset_selection.addon as addon_module
from fsrs_dynamic_preset_selection.addon import (
    FsrsDynamicPresetSelectionAddon,
    matched_dynamic_preset_for_card,
)
from fsrs_dynamic_preset_selection.config import load_config


class FakeCollection:
    def __init__(self, matching_searches: set[str]) -> None:
        self.matching_searches = matching_searches
        self.searched: list[str] = []

    def build_search_string(self, *nodes: str, joiner: str = "AND") -> str:
        return f" {joiner} ".join(nodes)

    def find_cards(self, search: str, order: bool = False) -> list[int]:
        self.searched.append(search)
        return [123] if search in self.matching_searches else []


class FakeCard:
    id = 123


def _config():
    return load_config(
        {
            "presets": [
                {
                    "id": "addon:test:first",
                    "name": "First",
                    "fsrs_version": "seven",
                    "params": [1.0] * 35,
                    "desired_retention": 0.9,
                    "historical_retention": 0.8,
                    "deck": "Japanese",
                },
                {
                    "id": "addon:test:second",
                    "name": "Second",
                    "fsrs_version": "seven",
                    "params": [2.0] * 35,
                    "desired_retention": 0.85,
                    "historical_retention": 0.75,
                },
            ],
            "rules": [
                {
                    "search": "tag:second",
                    "preset_id": "addon:test:second",
                }
            ],
        }
    )


def _config_with_dynamic_dr_policy():
    return load_config(
        {
            "presets": [
                {
                    "id": "addon:test:first",
                    "name": "First",
                    "fsrs_version": "seven",
                    "params": [1.0] * 35,
                    "desired_retention": 0.9,
                    "historical_retention": 0.8,
                    "deck": "Japanese",
                    "fsrs_dynamic_desired_retention_enabled": True,
                    "fsrs_dynamic_desired_retention_params": [0.0] * 15,
                    "fsrs_dynamic_desired_retention_weights": [0.0, 15.0],
                    "fsrs_dynamic_desired_retention_avg_drs": [0.9, 0.8],
                    "fsrs_dynamic_desired_retention_fsrs_eq_weights": [0.0, 15.0],
                    "fsrs_dynamic_desired_retention_fsrs_eq_drs": [0.91, 0.81],
                    "fsrs_dynamic_desired_retention_min": 0.3,
                    "fsrs_dynamic_desired_retention_max": 0.995,
                },
            ],
            "rules": [],
        }
    )


def test_matched_dynamic_preset_for_card_uses_first_matching_rule() -> None:
    collection = FakeCollection(
        {
            'deck:"Japanese" AND cid:123',
            "tag:second AND cid:123",
        }
    )

    match = matched_dynamic_preset_for_card(
        config=_config(),
        collection=collection,
        card_id=123,
        logger=logging.getLogger("test"),
    )

    assert match is not None
    preset, search = match
    assert preset.name == "First"
    assert search == 'deck:"Japanese"'
    assert collection.searched == ['deck:"Japanese" AND cid:123']


def test_addon_adds_dynamic_dr_supported_ranges_to_card_info(monkeypatch) -> None:
    collection = FakeCollection({'deck:"Japanese" AND cid:123'})
    addon = FsrsDynamicPresetSelectionAddon(
        module="test",
        logger=logging.getLogger("test"),
    )
    addon._config = _config_with_dynamic_dr_policy()
    rows = []

    monkeypatch.setattr(
        addon_module,
        "mw",
        SimpleNamespace(col=collection),
    )

    addon.add_card_info_rows(rows, FakeCard())

    assert [(row.label, row.value) for row in rows] == [
        ("Dynamic FSRS Preset", "First"),
        ("Dynamic FSRS Preset Match", 'deck:"Japanese"'),
        ("Supported ADR Range", "80.00% - 90.00%"),
        ("FSRS Equivalent DR Supported", "81.00% - 91.00%"),
    ]


def test_addon_adds_dynamic_fsrs_preset_card_info_rows(monkeypatch) -> None:
    collection = FakeCollection({'deck:"Japanese" AND cid:123'})
    addon = FsrsDynamicPresetSelectionAddon(
        module="test",
        logger=logging.getLogger("test"),
    )
    addon._config = _config()
    rows = []

    monkeypatch.setattr(
        addon_module,
        "mw",
        SimpleNamespace(col=collection),
    )

    addon.add_card_info_rows(rows, FakeCard())

    assert [(row.label, row.value) for row in rows] == [
        ("Dynamic FSRS Preset", "First"),
        ("Dynamic FSRS Preset Match", 'deck:"Japanese"'),
    ]


def test_addon_adds_dynamic_adr_card_info_row(monkeypatch) -> None:
    class DynamicAdrScheduler:
        def __init__(self) -> None:
            self.calls = []

        def get_scheduling_states(
            self,
            card_id: int,
            desired_retention_override: float | None = None,
        ) -> object:
            self.calls.append((card_id, desired_retention_override))
            return SimpleNamespace(
                dynamic_desired_retentions=[0.7, 0.8, 0.9, 0.95],
            )

    class DynamicAdrCollection(FakeCollection):
        def __init__(self) -> None:
            super().__init__({'deck:"Japanese" AND cid:123'})
            self.sched = DynamicAdrScheduler()

    collection = DynamicAdrCollection()
    addon = FsrsDynamicPresetSelectionAddon(
        module="test",
        logger=logging.getLogger("test"),
    )
    addon._config = _config()
    rows = []

    monkeypatch.setattr(
        addon_module,
        "mw",
        SimpleNamespace(col=collection),
    )

    addon.add_card_info_rows(rows, FakeCard())

    assert [(row.label, row.value) for row in rows] == [
        ("Dynamic FSRS Preset", "First"),
        ("Dynamic FSRS Preset Match", 'deck:"Japanese"'),
        (
            "Effective Dynamic DR Scheduling",
            "90.00% -> Again 70.00%, Hard 80.00%, Good 90.00%, Easy 95.00%",
        ),
    ]
    assert collection.sched.calls == [(123, 0.9)]


def test_addon_adds_fixed_dr_card_info_row_for_dynamic_dr_without_mapping(
    monkeypatch,
) -> None:
    class FixedDrScheduler:
        def get_scheduling_states(
            self,
            card_id: int,
            desired_retention_override: float | None = None,
        ) -> object:
            return SimpleNamespace(
                dynamic_desired_retention_enabled=True,
                dynamic_desired_retentions=[],
            )

    class FixedDrCollection(FakeCollection):
        def __init__(self) -> None:
            super().__init__({'deck:"Japanese" AND cid:123'})
            self.sched = FixedDrScheduler()

    addon = FsrsDynamicPresetSelectionAddon(
        module="test",
        logger=logging.getLogger("test"),
    )
    addon._config = _config()
    rows = []

    monkeypatch.setattr(
        addon_module,
        "mw",
        SimpleNamespace(col=FixedDrCollection()),
    )

    addon.add_card_info_rows(rows, FakeCard())

    assert [(row.label, row.value) for row in rows] == [
        ("Dynamic FSRS Preset", "First"),
        ("Dynamic FSRS Preset Match", 'deck:"Japanese"'),
        ("Effective Dynamic DR Scheduling", "90.00% -> fixed FSRS DR"),
    ]


def test_addon_uses_effective_dynamic_dr_for_dynamic_adr_card_info_row(
    monkeypatch,
) -> None:
    dynamic_dr_module = ModuleType("dynamic_desired_retention")
    dynamic_dr_calls = []

    def effective_desired_retention(
        *,
        collection: object,
        card: object,
        current_desired_retention: float | None,
        answer_grade: str | None = None,
    ) -> float:
        dynamic_dr_calls.append(
            (getattr(card, "id", None), current_desired_retention, answer_grade)
        )
        return 0.64

    dynamic_dr_module.effective_desired_retention = effective_desired_retention
    monkeypatch.setitem(sys.modules, "dynamic_desired_retention", dynamic_dr_module)

    class DynamicAdrScheduler:
        def __init__(self) -> None:
            self.calls = []

        def get_scheduling_states(
            self,
            card_id: int,
            desired_retention_override: float | None = None,
        ) -> object:
            self.calls.append((card_id, desired_retention_override))
            return SimpleNamespace(
                dynamic_desired_retentions=[0.62, 0.64, 0.66, 0.68],
            )

    class DynamicAdrCollection(FakeCollection):
        def __init__(self) -> None:
            super().__init__({'deck:"Japanese" AND cid:123'})
            self.sched = DynamicAdrScheduler()

    collection = DynamicAdrCollection()
    addon = FsrsDynamicPresetSelectionAddon(
        module="test",
        logger=logging.getLogger("test"),
    )
    addon._config = _config()
    rows = []

    monkeypatch.setattr(
        addon_module,
        "mw",
        SimpleNamespace(col=collection),
    )

    addon.add_card_info_rows(rows, FakeCard())

    assert dynamic_dr_calls == [(123, 0.9, None)]
    assert collection.sched.calls == [(123, 0.64)]
    assert [(row.label, row.value) for row in rows] == [
        ("Dynamic FSRS Preset", "First"),
        ("Dynamic FSRS Preset Match", 'deck:"Japanese"'),
        (
            "Effective Dynamic DR Scheduling",
            "64.00% -> Again 62.00%, Hard 64.00%, Good 66.00%, Easy 68.00%",
        ),
    ]
