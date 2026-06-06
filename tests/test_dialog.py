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
from fsrs_dynamic_preset_selection.models import AddonFsrsPresetConfig


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


def test_range_widgets_show_adr_and_fsrs_equivalent_ranges(monkeypatch) -> None:
    class FakeLineEdit:
        def __init__(self, text: str) -> None:
            self.text = text
            self.read_only = False

        def setReadOnly(self, value: bool) -> None:
            self.read_only = value

    monkeypatch.setattr(dialog_module, "QLineEdit", FakeLineEdit)
    preset = AddonFsrsPresetConfig(
        id="addon:test:ranges",
        name="Ranges",
        fsrs_version="seven",
        params=(),
        desired_retention=0.9,
        historical_retention=0.8,
        fsrs_dynamic_desired_retention_weights=(0.0, 15.0),
        fsrs_dynamic_desired_retention_avg_drs=(0.9, 0.8),
        fsrs_dynamic_desired_retention_fsrs_eq_weights=(0.0, 15.0),
        fsrs_dynamic_desired_retention_fsrs_eq_drs=(0.91, 0.81),
    )

    adr_widget = FsrsPresetConfigDialog._adr_range_widget(None, preset)
    fsrs_eq_widget = FsrsPresetConfigDialog._fsrs_eq_dr_range_widget(None, preset)

    assert (adr_widget.text, adr_widget.read_only) == ("80.0%-90.0%", True)
    assert (fsrs_eq_widget.text, fsrs_eq_widget.read_only) == ("81.0%-91.0%", True)


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


def test_single_preset_optimize_success_does_not_show_popup(monkeypatch) -> None:
    item = object()
    button = object()
    preset = SimpleNamespace(name="Medical")
    started_ops = []
    popup_messages: list[str] = []

    class FakeLineEdit:
        def __init__(self) -> None:
            self.text = ""

        def setText(self, text: str) -> None:
            self.text = text

    class FakeQueryOp:
        def __init__(self, *, parent, op, success) -> None:
            self.success = success

        def failure(self, _failure):
            return self

        def run_in_background(self) -> None:
            started_ops.append(self)

    line_edit = FakeLineEdit()
    monkeypatch.setattr(dialog_module, "QueryOp", FakeQueryOp)
    monkeypatch.setattr(
        dialog_module,
        "showInfo",
        lambda message, parent=None: popup_messages.append(message),
    )

    dialog = SimpleNamespace(
        _item_for_widget=lambda widget, column: (
            item if widget is button and column == COL_OPTIMIZE else None
        ),
        _optimization_context=lambda optimized_item: (preset, []),
        _set_item_progress=lambda optimized_item, **kwargs: None,
        _line_edit=lambda optimized_item, column: line_edit,
        _apply_optimized_adr=lambda optimized_item, optimized_preset, result: None,
        _set_optimize_button=lambda optimized_item: None,
        _refresh_counts=lambda: None,
    )

    FsrsPresetConfigDialog._optimize_item(dialog, button)
    started_ops[0].success(SimpleNamespace(params=(0.1, 0.2), fsrs_items=42))

    assert line_edit.text == "0.1, 0.2"
    assert popup_messages == []
