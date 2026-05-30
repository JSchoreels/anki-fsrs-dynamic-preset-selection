from __future__ import annotations

import sys
from types import ModuleType

from fsrs_dynamic_preset_selection.config import load_config
from fsrs_dynamic_preset_selection.gateway import (
    AnkiFsrsPresetGateway,
    count_cards,
    count_cards_by_preset,
    deck_unselected_counts,
    optimize_preset,
    optimize_presets_batch,
    OptimizePresetResult,
)
import fsrs_dynamic_preset_selection.gateway as gateway
from fsrs_dynamic_preset_selection.models import AddonFsrsPresetConfig


class FakeFsrsPresetOverlay:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = data

    @staticmethod
    def from_dict(data: dict[str, object]) -> "FakeFsrsPresetOverlay":
        return FakeFsrsPresetOverlay(data)


class FakeCollection:
    def __init__(self) -> None:
        self.overlay: FakeFsrsPresetOverlay | None = None

    def set_fsrs_preset_overlay(self, overlay: FakeFsrsPresetOverlay) -> None:
        self.overlay = overlay


def test_gateway_uses_typed_collection_setter(monkeypatch):
    anki_module = ModuleType("anki")
    collection_module = ModuleType("anki.collection")
    collection_module.FsrsPresetOverlay = FakeFsrsPresetOverlay
    monkeypatch.setitem(sys.modules, "anki", anki_module)
    monkeypatch.setitem(sys.modules, "anki.collection", collection_module)
    collection = FakeCollection()
    config = load_config(
        {
            "presets": [
                {
                    "id": "addon:test:medical",
                    "name": "Medical",
                    "fsrs_version": "six",
                    "params": [1.0],
                    "desired_retention": 0.9,
                    "historical_retention": 0.8,
                }
            ],
            "rules": [
                {
                    "search": "tag:medical",
                    "preset_id": "addon:test:medical",
                }
            ],
        }
    )

    AnkiFsrsPresetGateway(collection).apply(config)

    assert collection.overlay is not None
    assert collection.overlay.data["rules"] == [
        {"search": "tag:medical", "preset_id": "addon:test:medical"}
    ]


class FakeBackend:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None
        self.batch_kwargs: dict[str, object] | None = None

    def compute_fsrs_params(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        response = {"params": [1.0, 2.0, 3.0], "fsrs_items": 42}
        if kwargs.get("dynamic_desired_retention_enabled"):
            response.update(
                {
                    "fsrs_dynamic_desired_retention_params": [0.0] * 15,
                    "fsrs_dynamic_desired_retention_weights": [0.0, 15.0],
                    "fsrs_dynamic_desired_retention_avg_drs": [0.9, 0.8],
                    "fsrs_dynamic_desired_retention_fsrs_eq_weights": [0.0, 15.0],
                    "fsrs_dynamic_desired_retention_fsrs_eq_drs": [0.91, 0.81],
                    "fsrs_dynamic_desired_retention_min": 0.3,
                    "fsrs_dynamic_desired_retention_max": 0.995,
                }
            )
        return response

    def compute_fsrs_params_batch(self, **kwargs: object) -> object:
        self.batch_kwargs = kwargs
        return {
            "items": [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "params": [float(index), float(index + 1)],
                    "fsrs_items": index + 10,
                }
                for index, item in enumerate(kwargs["items"])
            ]
        }


class FakeOptimizerDecks:
    def by_name(self, name: str) -> dict[str, object] | None:
        if name == "Medical":
            return {"id": 1, "name": "Medical"}
        return None

    def config_dict_for_deck_id(self, deck_id: int) -> dict[str, object]:
        assert deck_id == 1
        return {
            "lapse": {"delays": [10, 60]},
            "fsrs7IncludeSameDayOptimize": False,
        }


class FakeOptimizerDecksSameDayOn:
    def by_name(self, name: str) -> dict[str, object] | None:
        if name == "Medical":
            return {"id": 1, "name": "Medical"}
        return None

    def config_dict_for_deck_id(self, deck_id: int) -> dict[str, object]:
        assert deck_id == 1
        return {
            "lapse": {"delays": [10, 60]},
            "fsrs7IncludeSameDayOptimize": True,
        }


class FakeCollectionWithBackend:
    decks = FakeOptimizerDecks()

    def __init__(self) -> None:
        self._backend = FakeBackend()


class FakeCollectionWithSameDayOnBackend:
    decks = FakeOptimizerDecksSameDayOn()

    def __init__(self) -> None:
        self._backend = FakeBackend()


def test_optimize_preset_uses_generated_search_and_version():
    collection = FakeCollectionWithBackend()
    preset = AddonFsrsPresetConfig(
        id="addon:test:medical",
        name="Medical",
        fsrs_version="seven",
        params=(0.1, 0.2),
        desired_retention=0.9,
        historical_retention=0.8,
        deck="Medical",
        search="tag:extra",
        first_grade=1,
    )

    result = optimize_preset(collection, preset)

    assert result.fsrs_items == 42
    assert result.params == (1.0, 2.0, 3.0)
    assert collection._backend.kwargs == {
        "search": 'deck:"Medical" firstgrade:1 tag:extra',
        "ignore_revlogs_before_ms": 0,
        "current_params": (0.1, 0.2),
        "num_of_relearning_steps": 2,
        "health_check": False,
        "include_same_day_reviews": False,
        "fsrs_version": 7,
        "dynamic_desired_retention_enabled": False,
    }


def test_optimize_preset_uses_effective_ordered_rule_slice():
    collection = FakeCollectionWithBackend()
    preset = AddonFsrsPresetConfig(
        id="addon:test:hard",
        name="Hard",
        fsrs_version="seven",
        params=(0.1, 0.2),
        desired_retention=0.9,
        historical_retention=0.8,
        deck="Medical",
        first_grade=2,
    )

    optimize_preset(
        collection,
        preset,
        [
            {"search": 'deck:"Medical" firstgrade:1', "preset_id": "addon:test:again"},
            {"search": 'deck:"Medical" firstgrade:2', "preset_id": "addon:test:hard"},
        ],
    )

    assert collection._backend.kwargs is not None
    assert collection._backend.kwargs["search"] == (
        '(deck:"Medical" firstgrade:2) -(deck:"Medical" firstgrade:1)'
    )


def test_optimize_preset_uses_preset_same_day_flag_before_deck_flag():
    collection = FakeCollectionWithBackend()
    preset = AddonFsrsPresetConfig(
        id="addon:test:medical",
        name="Medical",
        fsrs_version="seven",
        params=(0.1, 0.2),
        desired_retention=0.9,
        historical_retention=0.8,
        deck="Medical",
        include_same_day_reviews=True,
    )

    optimize_preset(collection, preset)

    assert collection._backend.kwargs is not None
    assert collection._backend.kwargs["include_same_day_reviews"] is True


def test_optimize_preset_requests_dynamic_dr_and_reads_policy():
    collection = FakeCollectionWithBackend()
    preset = AddonFsrsPresetConfig(
        id="addon:test:medical",
        name="Medical",
        fsrs_version="seven",
        params=(0.1, 0.2),
        desired_retention=0.9,
        historical_retention=0.8,
        deck="Medical",
        fsrs_dynamic_desired_retention_enabled=True,
        fsrs_dynamic_desired_retention_review_limit=123,
        fsrs_dynamic_desired_retention_max_cost_perday_minutes=45.0,
    )

    result = optimize_preset(collection, preset)

    assert collection._backend.kwargs is not None
    assert collection._backend.kwargs["dynamic_desired_retention_enabled"] is True
    assert collection._backend.kwargs["dynamic_desired_retention_review_limit"] == 123
    assert (
        collection._backend.kwargs[
            "dynamic_desired_retention_max_cost_perday_minutes"
        ]
        == 45.0
    )
    assert result.fsrs_dynamic_desired_retention_params == (0.0,) * 15
    assert result.fsrs_dynamic_desired_retention_weights == (0.0, 15.0)
    assert result.fsrs_dynamic_desired_retention_avg_drs == (0.9, 0.8)
    assert result.fsrs_dynamic_desired_retention_fsrs_eq_weights == (0.0, 15.0)
    assert result.fsrs_dynamic_desired_retention_fsrs_eq_drs == (0.91, 0.81)
    assert result.fsrs_dynamic_desired_retention_min == 0.3
    assert result.fsrs_dynamic_desired_retention_max == 0.995


def test_optimize_preset_respects_preset_same_day_disabled_before_deck_flag():
    collection = FakeCollectionWithSameDayOnBackend()
    preset = AddonFsrsPresetConfig(
        id="addon:test:medical",
        name="Medical",
        fsrs_version="seven",
        params=(0.1, 0.2),
        desired_retention=0.9,
        historical_retention=0.8,
        deck="Medical",
        include_same_day_reviews=False,
    )

    optimize_preset(collection, preset)

    assert collection._backend.kwargs is not None
    assert collection._backend.kwargs["include_same_day_reviews"] is False


def test_optimize_presets_batch_uses_single_backend_call():
    collection = FakeCollectionWithBackend()
    presets = [
        AddonFsrsPresetConfig(
            id="addon:test:again",
            name="Again",
            fsrs_version="seven",
            params=(0.1, 0.2),
            desired_retention=0.9,
            historical_retention=0.8,
            deck="Medical",
            first_grade=1,
        ),
        AddonFsrsPresetConfig(
            id="addon:test:hard",
            name="Hard",
            fsrs_version="seven",
            params=(0.3, 0.4),
            desired_retention=0.9,
            historical_retention=0.8,
            deck="Medical",
            first_grade=2,
            include_same_day_reviews=True,
        ),
    ]

    results = optimize_presets_batch(collection, presets)

    assert results == [
        OptimizePresetResult(fsrs_items=10, params=(0.0, 1.0)),
        OptimizePresetResult(fsrs_items=11, params=(1.0, 2.0)),
    ]
    assert collection._backend.kwargs is None
    assert collection._backend.batch_kwargs == {
        "items": [
            {
                "id": "addon:test:again",
                "name": "Again",
                "search": 'deck:"Medical" firstgrade:1',
                "ignore_revlogs_before_ms": 0,
                "current_params": (0.1, 0.2),
                "num_of_relearning_steps": 2,
                "include_same_day_reviews": False,
                "fsrs_version": 7,
                "dynamic_desired_retention_enabled": False,
            },
            {
                "id": "addon:test:hard",
                "name": "Hard",
                "search": 'deck:"Medical" firstgrade:2',
                "ignore_revlogs_before_ms": 0,
                "current_params": (0.3, 0.4),
                "num_of_relearning_steps": 2,
                "include_same_day_reviews": True,
                "fsrs_version": 7,
                "dynamic_desired_retention_enabled": False,
            },
        ]
    }


def test_optimize_presets_batch_uses_effective_ordered_rule_slices():
    collection = FakeCollectionWithBackend()
    presets = [
        AddonFsrsPresetConfig(
            id="addon:test:again",
            name="Again",
            fsrs_version="seven",
            params=(0.1, 0.2),
            desired_retention=0.9,
            historical_retention=0.8,
            deck="Medical",
            first_grade=1,
        ),
        AddonFsrsPresetConfig(
            id="addon:test:hard",
            name="Hard",
            fsrs_version="seven",
            params=(0.3, 0.4),
            desired_retention=0.9,
            historical_retention=0.8,
            deck="Medical",
            first_grade=2,
        ),
    ]
    ordered_rules = [
        {"search": 'deck:"Medical" firstgrade:1', "preset_id": "addon:test:again"},
        {"search": 'deck:"Medical" firstgrade:2', "preset_id": "addon:test:hard"},
    ]

    optimize_presets_batch(collection, presets, ordered_rules)

    assert collection._backend.batch_kwargs is not None
    assert collection._backend.batch_kwargs["items"][0]["search"] == (
        '(deck:"Medical" firstgrade:1)'
    )
    assert collection._backend.batch_kwargs["items"][1]["search"] == (
        '(deck:"Medical" firstgrade:2) -(deck:"Medical" firstgrade:1)'
    )


class FakeComputeFsrsParamsRequest:
    last_request = None

    def __init__(self) -> None:
        self.search = ""
        self.ignore_revlogs_before_ms = 0
        self.current_params: list[float] = []
        self.num_of_relearning_steps = 0
        self.health_check = False
        self.include_same_day_reviews = True
        self.fsrs_version = 0

    def SerializeToString(self) -> bytes:
        FakeComputeFsrsParamsRequest.last_request = self
        return b"request"


class FakeComputeFsrsParamsResponse:
    def __init__(self) -> None:
        self.params: list[float] = []
        self.fsrs_items = 0

    def ParseFromString(self, _data: bytes) -> None:
        self.params.extend([4.0, 5.0])
        self.fsrs_items = 12


class FakeSchedulerPb2:
    ComputeFsrsParamsRequest = FakeComputeFsrsParamsRequest
    ComputeFsrsParamsResponse = FakeComputeFsrsParamsResponse


class FakeRawBackend:
    def __init__(self) -> None:
        self.called = False
        self.request: FakeComputeFsrsParamsRequest | None = None

    def compute_fsrs_params_raw(self, data: bytes) -> bytes:
        self.called = data == b"request"
        self.request = FakeComputeFsrsParamsRequest.last_request
        return b"response"


class FakeRawCollection:
    decks = FakeOptimizerDecks()

    def __init__(self) -> None:
        self._backend = FakeRawBackend()


def test_optimize_preset_supports_raw_backend(monkeypatch):
    monkeypatch.setattr(gateway, "SCHEDULER_PB2_OVERRIDE", FakeSchedulerPb2)
    collection = FakeRawCollection()
    preset = AddonFsrsPresetConfig(
        id="addon:test:medical",
        name="Medical",
        fsrs_version="seven",
        params=(0.1, 0.2),
        desired_retention=0.9,
        historical_retention=0.8,
        deck="Medical",
    )

    result = optimize_preset(collection, preset)

    assert result.fsrs_items == 12
    assert result.params == (4.0, 5.0)
    assert collection._backend.called
    assert collection._backend.request.include_same_day_reviews is False


class FakeDecks:
    def all_names_and_ids(self, include_filtered: bool = True) -> list[dict[str, object]]:
        return [
            {"id": 1, "name": "Medical"},
            {"id": 2, "name": "Japanese"},
        ]


class FakeSearchCollection:
    decks = FakeDecks()

    def find_cards(self, search: str) -> list[int]:
        return {
            'deck:"Medical"': [1, 2, 3],
            'deck:"Japanese"': [4, 5],
            'deck:"Medical" firstgrade:1': [1],
            'deck:"Medical" tag:overlap': [1, 2],
            "tag:extra": [5],
            "is:new": [3, 5],
        }[search]


def test_card_count_helpers_use_search_results():
    collection = FakeSearchCollection()

    assert count_cards(collection, 'deck:"Medical" firstgrade:1') == 1
    assert deck_unselected_counts(
        collection, ['deck:"Medical" firstgrade:1', "tag:extra"]
    ) == [
        ("Medical", 2, 1, 3),
        ("Japanese", 1, 1, 2),
    ]


def test_count_cards_by_preset_uses_first_matching_rule():
    collection = FakeSearchCollection()

    assert count_cards_by_preset(
        collection,
        [
            {"search": 'deck:"Medical" firstgrade:1', "preset_id": "preset-a"},
            {"search": 'deck:"Medical" tag:overlap', "preset_id": "preset-b"},
        ],
    ) == {"preset-a": 1, "preset-b": 1}
