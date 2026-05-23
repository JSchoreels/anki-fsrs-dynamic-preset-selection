from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .models import AddonFsrsPresetConfig, DynamicPresetSelectionConfig, deck_search

LOGGER = logging.getLogger(__name__)
SCHEDULER_PB2_OVERRIDE: Any | None = None
FSRS7_INCLUDE_SAME_DAY_OPTIMIZE_KEY = "fsrs7IncludeSameDayOptimize"


class AnkiFsrsPresetGateway:
    def __init__(self, collection: Any) -> None:
        self.collection = collection

    def apply(self, config: DynamicPresetSelectionConfig) -> None:
        setter = getattr(self.collection, "set_fsrs_preset_overlay", None)
        if not callable(setter):
            raise RuntimeError("Anki does not expose set_fsrs_preset_overlay()")

        from anki.collection import FsrsPresetOverlay

        overlay = FsrsPresetOverlay.from_dict(config.to_overlay_dict())
        setter(overlay)
        LOGGER.info(
            "applied FSRS preset overlay presets=%s rules=%s",
            len(config.presets),
            len(config.rules),
        )


def optimize_preset(collection: Any, preset: AddonFsrsPresetConfig) -> tuple[int, tuple[float, ...]]:
    response = _compute_fsrs_params(
        collection._backend,
        _optimization_request_kwargs(collection, preset),
    )
    params = _float_tuple_field(response, "params")
    fsrs_items = _int_field(response, "fsrs_items", "fsrsItems")
    LOGGER.info(
        "optimized FSRS dynamic preset preset_id=%s fsrs_items=%s param_count=%s",
        preset.id,
        fsrs_items,
        len(params),
    )
    return fsrs_items, params


def optimize_presets_batch(
    collection: Any, presets: list[AddonFsrsPresetConfig]
) -> list[tuple[int, tuple[float, ...]]]:
    if not presets:
        return []

    items = []
    for preset in presets:
        item = _optimization_request_kwargs(collection, preset, include_health_check=False)
        item["id"] = preset.id
        item["name"] = preset.name
        items.append(item)

    response = _compute_fsrs_params_batch(collection._backend, {"items": items})
    response_items = list(_repeated_field(response, "items"))
    results_by_id = {
        str(getattr(item, "id", item.get("id") if isinstance(item, dict) else "")): item
        for item in response_items
    }
    results = []
    for preset in presets:
        item = results_by_id.get(preset.id)
        if item is None:
            raise RuntimeError(f"optimizer response missing preset: {preset.name}")
        params = _float_tuple_field(item, "params")
        fsrs_items = _int_field(item, "fsrs_items", "fsrsItems")
        results.append((fsrs_items, params))

    LOGGER.info("optimized FSRS dynamic presets count=%s", len(results))
    return results


def _optimization_request_kwargs(
    collection: Any, preset: AddonFsrsPresetConfig, include_health_check: bool = True
) -> dict[str, Any]:
    rule = preset.to_rule_dict()
    if rule is None:
        raise ValueError("preset has no deck or search filter")
    deck_settings = _optimization_deck_settings(collection, preset)
    include_same_day_reviews = _include_same_day_reviews(preset, deck_settings)
    kwargs: dict[str, Any] = {
        "search": rule["search"],
        "ignore_revlogs_before_ms": 0,
        "current_params": preset.params,
        "num_of_relearning_steps": deck_settings.num_of_relearning_steps,
        "fsrs_version": _version_number(preset.fsrs_version),
    }
    if include_health_check:
        kwargs["health_check"] = False
    if include_same_day_reviews is not None:
        kwargs["include_same_day_reviews"] = include_same_day_reviews
    return kwargs


@dataclass(frozen=True)
class OptimizerDeckSettings:
    num_of_relearning_steps: int = 0
    include_same_day_reviews: bool | None = None


def _optimization_deck_settings(
    collection: Any, preset: AddonFsrsPresetConfig
) -> OptimizerDeckSettings:
    if not preset.deck:
        return OptimizerDeckSettings()

    deck = collection.decks.by_name(preset.deck)
    if deck is None:
        raise ValueError(f"deck not found: {preset.deck}")

    config = collection.decks.config_dict_for_deck_id(int(deck["id"]))
    include_same_day_reviews = (
        _fsrs7_include_same_day_reviews(config) if preset.fsrs_version == "seven" else None
    )
    return OptimizerDeckSettings(
        num_of_relearning_steps=_relearning_step_count(config),
        include_same_day_reviews=include_same_day_reviews,
    )


def _include_same_day_reviews(
    preset: AddonFsrsPresetConfig, deck_settings: OptimizerDeckSettings
) -> bool | None:
    if preset.fsrs_version != "seven":
        return None
    if preset.include_same_day_reviews is not None:
        return preset.include_same_day_reviews
    return deck_settings.include_same_day_reviews


def same_day_optimize_setting(
    collection: Any, preset: AddonFsrsPresetConfig
) -> bool | None:
    return _optimization_deck_settings(collection, preset).include_same_day_reviews


def _relearning_step_count(config: Mapping[str, Any]) -> int:
    lapse = config.get("lapse")
    if not isinstance(lapse, Mapping):
        return 0
    delays = lapse.get("delays")
    if not isinstance(delays, list):
        return 0
    return len(delays)


def _fsrs7_include_same_day_reviews(config: Mapping[str, Any]) -> bool | None:
    value = config.get(FSRS7_INCLUDE_SAME_DAY_OPTIMIZE_KEY)
    if isinstance(value, bool):
        return value

    other = config.get("other")
    if not isinstance(other, Mapping):
        return None
    value = other.get(FSRS7_INCLUDE_SAME_DAY_OPTIMIZE_KEY)
    return value if isinstance(value, bool) else None


def count_cards(collection: Any, search: str) -> int:
    return len(collection.find_cards(search))


def count_cards_by_preset(
    collection: Any, ordered_rules: list[dict[str, str]]
) -> dict[str, int]:
    assigned: set[int] = set()
    counts: dict[str, int] = {}
    for rule in ordered_rules:
        search = rule["search"].strip()
        if not search:
            continue
        preset_id = rule["preset_id"]
        card_ids = {int(card_id) for card_id in collection.find_cards(search)}
        newly_assigned = card_ids - assigned
        assigned.update(newly_assigned)
        counts[preset_id] = counts.get(preset_id, 0) + len(newly_assigned)
    return counts


def deck_unselected_counts(
    collection: Any, selected_searches: list[str]
) -> list[tuple[str, int, int, int]]:
    selected_card_ids = _selected_card_ids(collection, selected_searches)
    new_card_ids = {int(card_id) for card_id in collection.find_cards("is:new")}
    counts = []
    for deck_name in _deck_names(collection):
        deck_card_ids = set(collection.find_cards(deck_search(deck_name)))
        unselected_card_ids = deck_card_ids - selected_card_ids
        counts.append(
            (
                deck_name,
                len(unselected_card_ids),
                len(unselected_card_ids - new_card_ids),
                len(deck_card_ids),
            )
        )
    return counts


def _selected_card_ids(collection: Any, searches: list[str]) -> set[int]:
    selected: set[int] = set()
    for search in searches:
        if search.strip():
            selected.update(int(card_id) for card_id in collection.find_cards(search))
    return selected


def _deck_names(collection: Any) -> list[str]:
    names = []
    for deck in collection.decks.all_names_and_ids(include_filtered=False):
        if isinstance(deck, Mapping):
            names.append(str(deck["name"]))
        else:
            names.append(str(getattr(deck, "name")))
    return names


def _call_backend(backend: Any, method_name: str, kwargs: dict[str, Any]) -> Any:
    method = getattr(backend, method_name)
    try:
        return method(**kwargs)
    except TypeError:
        camel_kwargs = {_snake_to_camel(key): value for key, value in kwargs.items()}
        return method(**camel_kwargs)


def _compute_fsrs_params(backend: Any, kwargs: dict[str, Any]) -> Any:
    raw_method = getattr(backend, "compute_fsrs_params_raw", None)
    if raw_method is not None:
        pb2 = _scheduler_pb2()
        request = pb2.ComputeFsrsParamsRequest()
        _assign_request_fields(request, kwargs)
        response = pb2.ComputeFsrsParamsResponse()
        response.ParseFromString(raw_method(request.SerializeToString()))
        return response
    return _call_backend(backend, "compute_fsrs_params", kwargs)


def _compute_fsrs_params_batch(backend: Any, kwargs: dict[str, Any]) -> Any:
    raw_method = getattr(backend, "compute_fsrs_params_batch_raw", None)
    if raw_method is not None:
        pb2 = _scheduler_pb2()
        request = pb2.ComputeFsrsParamsBatchRequest()
        for item_kwargs in kwargs["items"]:
            _assign_request_fields(request.items.add(), item_kwargs)
        response = pb2.ComputeFsrsParamsBatchResponse()
        response.ParseFromString(raw_method(request.SerializeToString()))
        return response
    return _call_backend(backend, "compute_fsrs_params_batch", kwargs)


def _assign_request_fields(request: Any, kwargs: dict[str, Any]) -> None:
    for key, value in kwargs.items():
        if value is None:
            continue
        if not hasattr(request, key):
            LOGGER.debug("skipping unsupported backend request field %s", key)
            continue
        if key == "current_params":
            getattr(request, key).extend(float(item) for item in value)
        else:
            setattr(request, key, value)


def _scheduler_pb2() -> Any:
    if SCHEDULER_PB2_OVERRIDE is not None:
        return SCHEDULER_PB2_OVERRIDE
    from anki import scheduler_pb2

    return scheduler_pb2


def _float_tuple_field(response: Any, name: str) -> tuple[float, ...]:
    values = getattr(response, name, None)
    if values is None and isinstance(response, dict):
        values = response.get(name)
    if values is None:
        return ()
    return tuple(float(value) for value in values)


def _repeated_field(response: Any, name: str) -> Any:
    if isinstance(response, dict):
        values = response.get(name)
    else:
        values = getattr(response, name, None)
    return values or []


def _int_field(response: Any, *names: str) -> int:
    for name in names:
        value = getattr(response, name, None)
        if value is None and isinstance(response, dict):
            value = response.get(name)
        if value is not None:
            return int(value)
    return 0


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def _version_number(version: str) -> int:
    return {"seven": 7, "six": 6, "five": 5, "four": 4}[version]
