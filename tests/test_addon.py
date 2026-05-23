from __future__ import annotations

import logging
from types import SimpleNamespace

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
