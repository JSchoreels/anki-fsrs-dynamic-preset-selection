from __future__ import annotations

from types import SimpleNamespace

from fsrs_dynamic_preset_selection.dialog import (
    DECK_COUNTS_HIDE_TEXT,
    DECK_COUNTS_SHOW_TEXT,
    COL_OPTIMIZE,
    FsrsPresetConfigDialog,
    _adr_range_text,
    _compute_params_progress_label,
    _compute_params_progress_text,
    _deck_counts_toggle_text,
)
import fsrs_dynamic_preset_selection.dialog as dialog_module


class FakeTable:
    def __init__(self) -> None:
        self.visible: bool | None = None

    def setVisible(self, visible: bool) -> None:
        self.visible = visible


class FakeButton:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, text: str) -> None:
        self.text = text


def test_deck_counts_toggle_text_matches_visibility() -> None:
    assert _deck_counts_toggle_text(False) == DECK_COUNTS_SHOW_TEXT
    assert _deck_counts_toggle_text(True) == DECK_COUNTS_HIDE_TEXT


def test_adr_range_text_formats_calibrated_range() -> None:
    assert _adr_range_text(None) == "Optimize required"
    assert _adr_range_text((0.75, 0.95)) == "75.0%-95.0%"


def test_compute_params_progress_text_names_adr_phase() -> None:
    progress = SimpleNamespace(phase=1)

    assert _compute_params_progress_text(progress) == "Compute ADR values %p%"
    assert _compute_params_progress_label(progress) == "Compute ADR values for"
    assert _compute_params_progress_text(SimpleNamespace(phase=0)) == "Optimizing %p%"


def test_set_deck_counts_visible_updates_table_and_button() -> None:
    dialog = SimpleNamespace(
        deck_counts_table=FakeTable(),
        deck_counts_toggle_button=FakeButton(),
    )

    FsrsPresetConfigDialog._set_deck_counts_visible(dialog, True)

    assert dialog.deck_counts_table.visible is True
    assert dialog.deck_counts_toggle_button.text == DECK_COUNTS_HIDE_TEXT

    FsrsPresetConfigDialog._set_deck_counts_visible(dialog, False)

    assert dialog.deck_counts_table.visible is False
    assert dialog.deck_counts_toggle_button.text == DECK_COUNTS_SHOW_TEXT


def test_single_preset_optimize_uses_row_local_progress(monkeypatch) -> None:
    item = object()
    button = object()
    preset = SimpleNamespace(name="Medical")
    progress_calls: list[tuple[object, dict[str, object]]] = []
    started_ops = []

    class FakeQueryOp:
        def __init__(self, *, parent, op, success) -> None:
            self.parent = parent
            self.op = op
            self.success = success

        def with_backend_progress(self, _progress_update):
            raise AssertionError("single preset optimize should not use global progress")

        def failure(self, _failure):
            return self

        def run_in_background(self) -> None:
            started_ops.append(self)

    monkeypatch.setattr(dialog_module, "QueryOp", FakeQueryOp)

    dialog = SimpleNamespace(
        _item_for_widget=lambda widget, column: (
            item if widget is button and column == COL_OPTIMIZE else None
        ),
        _optimization_context=lambda optimized_item: (
            preset,
            [{"search": "tag:medical", "preset_id": "addon:test:medical"}],
        ),
        _set_item_progress=lambda optimized_item, **kwargs: progress_calls.append(
            (optimized_item, kwargs)
        ),
    )

    FsrsPresetConfigDialog._optimize_item(dialog, button)

    assert progress_calls == [
        (item, {"value": 0, "maximum": 0, "text": "Optimizing..."})
    ]
    assert len(started_ops) == 1
