from __future__ import annotations

from typing import Any

from aqt.qt import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    qconnect,
)
from aqt.operations import QueryOp
from aqt.utils import showInfo, showWarning

from .config import ConfigError, load_config
from .gateway import (
    count_cards_by_preset,
    deck_unselected_counts,
    optimize_preset,
    optimize_presets_batch,
)
from .gateway import same_day_optimize_setting
from .models import (
    AddonFsrsPresetConfig,
    FsrsPresetVersion,
    preset_id_from_name,
)

COL_NAME = 0
COL_DECK = 1
COL_SEARCH = 2
COL_SPLIT = 3
COL_GRADE = 4
COL_VERSION = 5
COL_SAME_DAY = 6
COL_DESIRED_RETENTION = 7
COL_HISTORICAL_RETENTION = 8
COL_PARAMS = 9
COL_SELECTED_COUNT = 10
COL_OPTIMIZE = 11

ROLE_OLD_ID = 0x0100
ROLE_FIRST_GRADE = 0x0101

FSRS_VERSIONS: tuple[tuple[str, FsrsPresetVersion], ...] = (
    ("7", "seven"),
    ("6", "six"),
    ("5", "five"),
    ("4", "four"),
)

FIRST_GRADES = (1, 2, 3, 4)


class FsrsPresetConfigDialog(QDialog):
    def __init__(self, parent: QWidget, *, addon_manager: Any, module: str) -> None:
        super().__init__(parent)
        self._addon_manager = addon_manager
        self._module = module
        self._raw_config = addon_manager.getConfig(module) or {}
        self._config = load_config(self._raw_config)
        self._advanced_rules = list(self._raw_config.get("rules", []))
        self._deck_names = self._load_deck_names(parent)

        self.setWindowTitle("FSRS Dynamic Preset Selection")
        self.resize(1280, 640)
        self._setup_ui()
        self._load_presets()
        self._refresh_counts()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()
        self.setLayout(layout)

        layout.addWidget(QLabel("Add-on FSRS presets"))

        self.tree = QTreeWidget()
        self.tree.setColumnCount(12)
        self.tree.setHeaderLabels(
            [
                "Name",
                "Deck",
                "Search",
                "Split",
                "Grade",
                "FSRS Version",
                "Same-day Reviews",
                "Desired R",
                "Historical R",
                "Params",
                "Selected Cards",
                "Optimize",
            ]
        )
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.header().setSectionResizeMode(
            COL_SAME_DAY, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tree.header().setSectionResizeMode(COL_PARAMS, QHeaderView.ResizeMode.Stretch)
        self.tree.headerItem().setToolTip(
            COL_SAME_DAY,
            "Include same-day reviews when optimizing this FSRS-7 preset.",
        )
        layout.addWidget(self.tree)

        row_actions = QHBoxLayout()
        add_button = QPushButton("Add Preset")
        remove_button = QPushButton("Remove Selected")
        move_up_button = QPushButton("Move Up")
        move_down_button = QPushButton("Move Down")
        self.optimize_all_button = QPushButton("Optimize All")
        self.optimize_all_progress = QProgressBar()
        self.optimize_all_progress.setVisible(False)
        refresh_counts_button = QPushButton("Refresh Counts")
        qconnect(add_button.clicked, self._add_empty_preset_group)
        qconnect(remove_button.clicked, self._remove_selected_item)
        qconnect(move_up_button.clicked, lambda: self._move_selected_item(-1))
        qconnect(move_down_button.clicked, lambda: self._move_selected_item(1))
        qconnect(self.optimize_all_button.clicked, self._optimize_all)
        qconnect(refresh_counts_button.clicked, self._refresh_counts)
        row_actions.addWidget(add_button)
        row_actions.addWidget(remove_button)
        row_actions.addWidget(move_up_button)
        row_actions.addWidget(move_down_button)
        row_actions.addWidget(self.optimize_all_button)
        row_actions.addWidget(self.optimize_all_progress)
        row_actions.addWidget(refresh_counts_button)
        row_actions.addStretch()
        layout.addLayout(row_actions)

        layout.addWidget(QLabel("Deck cards not selected by preset queries"))
        self.deck_counts_table = QTableWidget(0, 4)
        self.deck_counts_table.setHorizontalHeaderLabels(
            ["Deck", "Not Selected", "Not Selected (Non New)", "Total Cards"]
        )
        self.deck_counts_table.verticalHeader().setVisible(False)
        self.deck_counts_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.deck_counts_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        layout.addWidget(self.deck_counts_table)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        qconnect(buttons.accepted, self._save)
        qconnect(buttons.rejected, self.reject)
        layout.addWidget(buttons)

    def _load_presets(
        self, presets: tuple[AddonFsrsPresetConfig, ...] | None = None
    ) -> None:
        preset_list = list(presets or self._config.presets)
        index = 0
        while index < len(preset_list):
            preset = preset_list[index]
            if preset.first_grade is None:
                self._add_preset_group(preset)
                index += 1
                continue

            key = (preset.name, preset.deck, preset.search)
            split_presets = []
            while index < len(preset_list):
                candidate = preset_list[index]
                if (
                    candidate.first_grade is None
                    or (candidate.name, candidate.deck, candidate.search) != key
                ):
                    break
                split_presets.append(candidate)
                index += 1
            self._add_split_preset_group(split_presets)

    def _add_split_preset_group(
        self, presets: list[AddonFsrsPresetConfig]
    ) -> QTreeWidgetItem:
        template = presets[0]
        parent = self._add_parent_item(
            name=template.name,
            deck=template.deck,
            search=template.search,
            split=True,
            template=template,
        )
        added_grades = set()
        for preset in presets:
            assert preset.first_grade is not None
            self._add_grade_child(parent, preset, preset.first_grade, template)
            added_grades.add(preset.first_grade)
        for grade in FIRST_GRADES:
            if grade not in added_grades:
                self._add_grade_child(parent, None, grade, template)
        parent.setExpanded(True)
        return parent

    def _add_empty_preset_group(self) -> None:
        self._add_preset_group(
            AddonFsrsPresetConfig(
                id=preset_id_from_name("New preset"),
                name="New preset",
                fsrs_version="seven",
                params=(),
                desired_retention=0.9,
                historical_retention=0.9,
                include_same_day_reviews=True,
            )
        )

    def _add_preset_group(self, preset: AddonFsrsPresetConfig) -> QTreeWidgetItem:
        parent = self._add_parent_item(
            name=preset.name,
            deck=preset.deck,
            search=preset.search,
            split=False,
            template=preset,
        )
        self._set_detail_widgets(parent, preset)
        self._set_selected_count_widget(parent)
        self._set_optimize_button(parent)
        return parent

    def _add_parent_item(
        self,
        *,
        name: str,
        deck: str,
        search: str,
        split: bool,
        template: AddonFsrsPresetConfig,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem(self.tree)
        item.setData(COL_NAME, ROLE_OLD_ID, template.id if not split else "")
        item.setData(COL_GRADE, ROLE_FIRST_GRADE, None)
        item.setFirstColumnSpanned(False)
        self.tree.setItemWidget(item, COL_NAME, QLineEdit(name))
        self.tree.setItemWidget(item, COL_DECK, self._deck_combo(deck))
        self.tree.setItemWidget(item, COL_SEARCH, QLineEdit(search))
        split_checkbox = QCheckBox()
        split_checkbox.setChecked(split)
        qconnect(
            split_checkbox.stateChanged,
            lambda _state, checkbox=split_checkbox: self._split_changed(checkbox),
        )
        self.tree.setItemWidget(item, COL_SPLIT, split_checkbox)
        return item

    def _add_grade_child(
        self,
        parent: QTreeWidgetItem,
        preset: AddonFsrsPresetConfig | None,
        grade: int,
        template: AddonFsrsPresetConfig,
    ) -> QTreeWidgetItem:
        preset = preset or AddonFsrsPresetConfig(
            id=preset_id_from_name(template.name, grade),
            name=template.name,
            fsrs_version=template.fsrs_version,
            params=template.params,
            desired_retention=template.desired_retention,
            historical_retention=template.historical_retention,
            deck=template.deck,
            search=template.search,
            first_grade=grade,
            include_same_day_reviews=template.include_same_day_reviews,
        )
        child = QTreeWidgetItem(parent)
        child.setData(COL_NAME, ROLE_OLD_ID, preset.id)
        child.setData(COL_GRADE, ROLE_FIRST_GRADE, grade)
        child.setText(COL_GRADE, _grade_label(grade))
        self._set_detail_widgets(child, preset)
        self._set_selected_count_widget(child)
        self._set_optimize_button(child)
        return child

    def _set_detail_widgets(
        self, item: QTreeWidgetItem, preset: AddonFsrsPresetConfig
    ) -> None:
        version_combo = self._version_combo(preset.fsrs_version)
        same_day_checkbox = self._same_day_checkbox(preset)
        qconnect(
            version_combo.currentIndexChanged,
            lambda _index, checkbox=same_day_checkbox, combo=version_combo: self._update_same_day_checkbox(
                checkbox, combo.currentData()
            ),
        )
        self.tree.setItemWidget(item, COL_VERSION, version_combo)
        self.tree.setItemWidget(item, COL_SAME_DAY, same_day_checkbox)
        self._update_same_day_checkbox(same_day_checkbox, preset.fsrs_version)
        self.tree.setItemWidget(
            item, COL_DESIRED_RETENTION, self._retention_spin(preset.desired_retention)
        )
        self.tree.setItemWidget(
            item,
            COL_HISTORICAL_RETENTION,
            self._retention_spin(preset.historical_retention),
        )
        self.tree.setItemWidget(item, COL_PARAMS, QLineEdit(_format_params(preset.params)))

    def _set_selected_count_widget(self, item: QTreeWidgetItem) -> None:
        selected_count = QLineEdit("")
        selected_count.setReadOnly(True)
        self.tree.setItemWidget(item, COL_SELECTED_COUNT, selected_count)

    def _set_optimize_button(self, item: QTreeWidgetItem) -> None:
        optimize_button = QPushButton("Optimize")
        qconnect(
            optimize_button.clicked,
            lambda _checked=False, button=optimize_button: self._optimize_item(button),
        )
        self.tree.setItemWidget(item, COL_OPTIMIZE, optimize_button)

    def _set_item_progress(
        self,
        item: QTreeWidgetItem,
        *,
        value: int,
        maximum: int = 100,
        text: str,
    ) -> None:
        progress = self.tree.itemWidget(item, COL_OPTIMIZE)
        if not isinstance(progress, QProgressBar):
            progress = QProgressBar()
            self.tree.setItemWidget(item, COL_OPTIMIZE, progress)
        progress.setRange(0, maximum)
        progress.setValue(value)
        progress.setFormat(text)
        QApplication.processEvents()

    def _deck_combo(self, selected: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem("Any deck", "")
        for deck_name in self._deck_names:
            combo.addItem(deck_name, deck_name)
        index = combo.findData(selected)
        if index >= 0:
            combo.setCurrentIndex(index)
        return combo

    def _version_combo(self, selected: FsrsPresetVersion) -> QComboBox:
        combo = QComboBox()
        for label, version in FSRS_VERSIONS:
            combo.addItem(label, version)
        index = combo.findData(selected)
        if index >= 0:
            combo.setCurrentIndex(index)
        return combo

    def _retention_spin(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.01, 1.0)
        spin.setDecimals(4)
        spin.setSingleStep(0.01)
        spin.setValue(value)
        return spin

    def _split_changed(self, checkbox: QCheckBox) -> None:
        parent = self._item_for_widget(checkbox, COL_SPLIT)
        if parent is None:
            return
        if checkbox.isChecked():
            if parent.childCount():
                return
            template = self._config_preset_from_item(parent)
            self._clear_detail_widgets(parent)
            for grade in FIRST_GRADES:
                self._add_grade_child(parent, None, grade, template)
            parent.setExpanded(True)
        else:
            if not parent.childCount():
                return
            template = self._config_preset_from_item(parent.child(0))
            while parent.childCount():
                parent.removeChild(parent.child(0))
            self._set_detail_widgets(parent, template)
            self._set_selected_count_widget(parent)
            self._set_optimize_button(parent)

    def _clear_detail_widgets(self, item: QTreeWidgetItem) -> None:
        for column in (
            COL_VERSION,
            COL_SAME_DAY,
            COL_DESIRED_RETENTION,
            COL_HISTORICAL_RETENTION,
            COL_PARAMS,
            COL_SELECTED_COUNT,
            COL_OPTIMIZE,
        ):
            self.tree.removeItemWidget(item, column)

    def _remove_selected_item(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        parent = item.parent()
        if parent is None:
            index = self.tree.indexOfTopLevelItem(item)
            self.tree.takeTopLevelItem(index)
        else:
            parent.removeChild(item)

    def _move_selected_item(self, offset: int) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        try:
            groups = self._preset_groups()
        except (ConfigError, ValueError) as exc:
            showWarning(f"Unable to move preset:\n\n{exc}", parent=self)
            return

        parent = item.parent()
        if parent is None:
            group_index = self.tree.indexOfTopLevelItem(item)
            new_group_index = group_index + offset
            if not 0 <= new_group_index < len(groups):
                return
            groups.insert(new_group_index, groups.pop(group_index))
            self._replace_preset_groups(groups, new_group_index, None)
        else:
            group_index = self.tree.indexOfTopLevelItem(parent)
            child_index = parent.indexOfChild(item)
            new_child_index = child_index + offset
            if not 0 <= new_child_index < len(groups[group_index]):
                return
            groups[group_index].insert(
                new_child_index, groups[group_index].pop(child_index)
            )
            self._replace_preset_groups(groups, group_index, new_child_index)

    def _preset_groups(self) -> list[list[dict[str, object]]]:
        groups = []
        used_ids: set[str] = set()
        for parent in self._top_level_items():
            if parent.childCount():
                group = []
                for child in self._child_items(parent):
                    preset = self._preset_dict(child, used_ids)
                    used_ids.add(str(preset["id"]))
                    group.append(preset)
                groups.append(group)
            else:
                preset = self._preset_dict(parent, used_ids)
                used_ids.add(str(preset["id"]))
                groups.append([preset])
        return groups

    def _replace_preset_groups(
        self,
        groups: list[list[dict[str, object]]],
        selected_group_index: int,
        selected_child_index: int | None,
    ) -> None:
        presets = [preset for group in groups for preset in group]
        self._config = load_config({"presets": presets, "rules": []})
        self.tree.clear()
        self._load_presets(self._config.presets)
        selected = self.tree.topLevelItem(selected_group_index)
        if selected is not None and selected_child_index is not None:
            selected = selected.child(selected_child_index)
        if selected is not None:
            self.tree.setCurrentItem(selected)
        self._refresh_counts()

    def _save(self) -> None:
        try:
            presets = self._preset_dicts()
            new_config = {
                "presets": presets,
                "rules": self._updated_advanced_rules(presets),
            }
            load_config(new_config)
        except (ConfigError, ValueError) as exc:
            showWarning(f"FSRS Dynamic Preset Selection config is invalid:\n\n{exc}", parent=self)
            return

        self._addon_manager.writeConfig(self._module, new_config)
        self.accept()

    def _preset_dicts(self) -> list[dict[str, object]]:
        used_ids: set[str] = set()
        presets: list[dict[str, object]] = []
        for parent in self._top_level_items():
            if parent.childCount():
                for child in self._child_items(parent):
                    preset = self._preset_dict(child, used_ids)
                    used_ids.add(str(preset["id"]))
                    presets.append(preset)
            else:
                preset = self._preset_dict(parent, used_ids)
                used_ids.add(str(preset["id"]))
                presets.append(preset)
        return presets

    def _preset_dict(
        self, item: QTreeWidgetItem, used_ids: set[str] | None = None
    ) -> dict[str, object]:
        name = self._group_name(item)
        deck = self._group_deck(item)
        search = self._group_search(item)
        first_grade = self._first_grade(item)
        fsrs_version = self._combo(item, COL_VERSION).currentData()
        preset_id = self._unique_preset_id(name, first_grade, used_ids or set())
        preset: dict[str, object] = {
            "id": preset_id,
            "name": name,
            "fsrs_version": fsrs_version,
            "params": _parse_params(self._line_edit(item, COL_PARAMS).text()),
            "desired_retention": self._spin(item, COL_DESIRED_RETENTION).value(),
            "historical_retention": self._spin(item, COL_HISTORICAL_RETENTION).value(),
        }
        if fsrs_version == "seven":
            preset["include_same_day_reviews"] = self._checkbox(item, COL_SAME_DAY).isChecked()
        if deck:
            preset["deck"] = deck
        if search:
            preset["search"] = search
        if first_grade is not None:
            preset["first_grade"] = first_grade
        return preset

    def _config_preset_from_item(self, item: QTreeWidgetItem) -> AddonFsrsPresetConfig:
        return load_config({"presets": [self._preset_dict(item)], "rules": []}).presets[0]

    def _updated_advanced_rules(
        self, presets: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        old_items = list(self._leaf_items())
        id_map = {
            old_id: presets[index]["id"]
            for index, item in enumerate(old_items[: len(presets)])
            if (old_id := item.data(COL_NAME, ROLE_OLD_ID))
        }
        rules = []
        for rule in self._advanced_rules:
            updated = dict(rule)
            preset_id = updated.get("preset_id")
            if isinstance(preset_id, str) and preset_id in id_map:
                updated["preset_id"] = id_map[preset_id]
            rules.append(updated)
        return rules

    def _refresh_counts(self) -> None:
        collection = getattr(self.parent(), "col", None)
        if collection is None:
            return
        try:
            presets = self._preset_dicts()
            config = load_config(
                {
                    "presets": presets,
                    "rules": self._updated_advanced_rules(presets),
                }
            )
            ordered_rules = config.to_overlay_dict()["rules"]
            preset_counts = count_cards_by_preset(collection, ordered_rules)
            for item, preset in zip(self._leaf_items(), config.presets, strict=False):
                self._line_edit(item, COL_SELECTED_COUNT).setText(
                    str(preset_counts.get(preset.id, 0))
                )
            all_searches = [rule["search"] for rule in ordered_rules]
            self._set_deck_counts(deck_unselected_counts(collection, all_searches))
        except (ConfigError, ValueError) as exc:
            showWarning(f"Unable to refresh card counts:\n\n{exc}", parent=self)
        except Exception as exc:
            showWarning(f"Unable to refresh card counts:\n\n{exc}", parent=self)

    def _set_deck_counts(self, counts: list[tuple[str, int, int, int]]) -> None:
        self.deck_counts_table.setRowCount(0)
        for deck_name, unselected, unselected_non_new, total in counts:
            row = self.deck_counts_table.rowCount()
            self.deck_counts_table.insertRow(row)
            self.deck_counts_table.setItem(row, 0, _table_item(deck_name))
            self.deck_counts_table.setItem(row, 1, _table_item(str(unselected)))
            self.deck_counts_table.setItem(row, 2, _table_item(str(unselected_non_new)))
            self.deck_counts_table.setItem(row, 3, _table_item(str(total)))

    def _optimize_item(self, button: QPushButton) -> None:
        item = self._item_for_widget(button, COL_OPTIMIZE)
        if item is None:
            return
        try:
            preset = self._preset_for_optimize(item)
        except (ConfigError, ValueError) as exc:
            showWarning(f"Unable to optimize preset:\n\n{exc}", parent=self)
            return
        except Exception as exc:
            showWarning(f"Unable to optimize preset:\n\n{exc}", parent=self)
            return

        self._set_item_progress(item, value=0, text="Optimizing %p%")

        def on_success(result: tuple[int, tuple[float, ...]]) -> None:
            fsrs_items, params = result
            self._line_edit(item, COL_PARAMS).setText(_format_params(params))
            self._set_item_progress(item, value=100, text="Done")
            self._set_optimize_button(item)
            self._refresh_counts()
            showInfo(f"Optimized {preset.name} with {fsrs_items} FSRS items.", parent=self)

        def on_failure(exc: Exception) -> None:
            self._set_optimize_button(item)
            showWarning(f"Unable to optimize preset:\n\n{exc}", parent=self)

        QueryOp(
            parent=self,
            op=lambda col: optimize_preset(col, preset),
            success=on_success,
        ).with_backend_progress(
            lambda progress, update: self._update_item_compute_progress(
                item, progress, update, preset.name
            )
        ).failure(on_failure).run_in_background()

    def _optimize_all(self) -> None:
        items = self._leaf_items()
        if not items:
            return
        try:
            presets = [self._preset_for_optimize(item) for item in items]
        except (ConfigError, ValueError) as exc:
            showWarning(f"Unable to optimize all presets:\n\n{exc}", parent=self)
            return
        except Exception as exc:
            showWarning(f"Unable to optimize all presets:\n\n{exc}", parent=self)
            return

        self._show_optimize_all_progress(len(items))
        self._set_all_item_progress_pending(items)
        def op(col: Any) -> list[tuple[int, tuple[float, ...]]]:
            return optimize_presets_batch(col, presets)

        def on_success(results: list[tuple[int, tuple[float, ...]]]) -> None:
            for item, (_fsrs_items, params) in zip(items, results, strict=False):
                self._line_edit(item, COL_PARAMS).setText(_format_params(params))
                self._set_item_progress(item, value=100, text="Done")
            self._refresh_counts()
            self._hide_optimize_all_progress()
            self._restore_all_item_optimize_buttons(items)
            showInfo(f"Optimized {len(results)} presets.", parent=self)

        def on_failure(exc: Exception) -> None:
            self._hide_optimize_all_progress()
            self._restore_all_item_optimize_buttons(items)
            showWarning(f"Unable to optimize all presets:\n\n{exc}", parent=self)

        QueryOp(parent=self, op=op, success=on_success).with_backend_progress(
            lambda progress, update: self._update_all_compute_progress(
                items, progress, update
            )
        ).failure(on_failure).run_in_background()

    def _preset_for_optimize(self, item: QTreeWidgetItem) -> AddonFsrsPresetConfig:
        preset = load_config({"presets": [self._preset_dict(item)], "rules": []}).presets[0]
        if not preset.to_rule_dict():
            raise ConfigError("choose a deck or enter a search filter before optimizing")
        return preset

    def _set_all_item_progress_pending(self, items: list[QTreeWidgetItem]) -> None:
        for item in items:
            self._set_item_progress(item, value=0, text="Pending")

    def _update_item_compute_progress(
        self,
        item: QTreeWidgetItem,
        progress: Any,
        update: Any,
        preset_name: str,
    ) -> None:
        if not progress.HasField("compute_params"):
            return
        value = progress.compute_params
        maximum = max(value.total, 1)
        current = min(value.current, maximum)
        self._set_item_progress(
            item,
            value=current,
            maximum=maximum,
            text="Optimizing %p%",
        )
        update.max = maximum
        update.value = current
        update.label = f"Optimizing {preset_name}"
        if update.user_wants_abort:
            update.abort = True

    def _update_all_compute_progress(
        self,
        items: list[QTreeWidgetItem],
        progress: Any,
        update: Any,
    ) -> None:
        if not progress.HasField("compute_all_params"):
            return

        value = progress.compute_all_params
        for index, preset_progress in enumerate(value.presets):
            if index >= len(items):
                break
            maximum = max(preset_progress.total, 1)
            current = min(preset_progress.current, maximum)
            text = "Skipped" if preset_progress.skipped else "Optimizing %p%"
            if preset_progress.finished and not preset_progress.skipped:
                text = "Done"
                current = maximum
            self._set_item_progress(
                items[index],
                value=current,
                maximum=maximum,
                text=text,
            )

        update.max = max(value.total, 1)
        update.value = value.current
        update.label = f"Optimizing presets {value.current}/{value.total}"
        if update.user_wants_abort:
            update.abort = True
        self._update_optimize_all_progress(value.current, max(value.total, 1))

    def _restore_all_item_optimize_buttons(self, items: list[QTreeWidgetItem]) -> None:
        for item in items:
            self._set_optimize_button(item)

    def _show_optimize_all_progress(self, total: int) -> None:
        self.optimize_all_button.setVisible(False)
        self.optimize_all_progress.setRange(0, total)
        self.optimize_all_progress.setValue(0)
        self.optimize_all_progress.setFormat("Optimizing %v/%m")
        self.optimize_all_progress.setVisible(True)
        QApplication.processEvents()

    def _update_optimize_all_progress(self, value: int, total: int) -> None:
        self.optimize_all_progress.setRange(0, total)
        self.optimize_all_progress.setValue(value)
        QApplication.processEvents()

    def _hide_optimize_all_progress(self) -> None:
        self.optimize_all_progress.setVisible(False)
        self.optimize_all_button.setVisible(True)
        QApplication.processEvents()

    def _item_for_widget(
        self, widget: QWidget, column: int
    ) -> QTreeWidgetItem | None:
        for item in self._all_items():
            if self.tree.itemWidget(item, column) is widget:
                return item
        return None

    def _unique_preset_id(
        self, name: str, first_grade: int | None, used_ids: set[str]
    ) -> str:
        base = preset_id_from_name(name, first_grade)
        preset_id = base
        index = 2
        while preset_id in used_ids:
            preset_id = f"{base}-{index}"
            index += 1
        return preset_id

    def _leaf_items(self) -> list[QTreeWidgetItem]:
        leaves = []
        for parent in self._top_level_items():
            if parent.childCount():
                leaves.extend(self._child_items(parent))
            else:
                leaves.append(parent)
        return leaves

    def _all_items(self) -> list[QTreeWidgetItem]:
        items = []
        for parent in self._top_level_items():
            items.append(parent)
            items.extend(self._child_items(parent))
        return items

    def _top_level_items(self) -> list[QTreeWidgetItem]:
        return [self.tree.topLevelItem(row) for row in range(self.tree.topLevelItemCount())]

    def _child_items(self, parent: QTreeWidgetItem) -> list[QTreeWidgetItem]:
        return [parent.child(row) for row in range(parent.childCount())]

    def _group_parent(self, item: QTreeWidgetItem) -> QTreeWidgetItem:
        return item.parent() or item

    def _group_name(self, item: QTreeWidgetItem) -> str:
        return self._line_edit(self._group_parent(item), COL_NAME).text().strip()

    def _group_deck(self, item: QTreeWidgetItem) -> str:
        return self._combo(self._group_parent(item), COL_DECK).currentData()

    def _group_search(self, item: QTreeWidgetItem) -> str:
        return self._line_edit(self._group_parent(item), COL_SEARCH).text().strip()

    def _first_grade(self, item: QTreeWidgetItem) -> int | None:
        value = item.data(COL_GRADE, ROLE_FIRST_GRADE)
        return int(value) if value is not None else None

    def _line_edit(self, item: QTreeWidgetItem, column: int) -> QLineEdit:
        widget = self.tree.itemWidget(item, column)
        assert isinstance(widget, QLineEdit)
        return widget

    def _combo(self, item: QTreeWidgetItem, column: int) -> QComboBox:
        widget = self.tree.itemWidget(item, column)
        assert isinstance(widget, QComboBox)
        return widget

    def _spin(self, item: QTreeWidgetItem, column: int) -> QDoubleSpinBox:
        widget = self.tree.itemWidget(item, column)
        assert isinstance(widget, QDoubleSpinBox)
        return widget

    def _checkbox(self, item: QTreeWidgetItem, column: int) -> QCheckBox:
        widget = self.tree.itemWidget(item, column)
        assert isinstance(widget, QCheckBox)
        return widget

    def _same_day_checkbox(self, preset: AddonFsrsPresetConfig) -> QCheckBox:
        checkbox = QCheckBox()
        checkbox.setText("Include")
        checkbox.setToolTip("Include same-day reviews when optimizing this FSRS-7 preset.")
        if preset.include_same_day_reviews is not None:
            checkbox.setChecked(preset.include_same_day_reviews)
            return checkbox
        checkbox.setChecked(self._same_day_default(preset))
        return checkbox

    def _same_day_default(self, preset: AddonFsrsPresetConfig) -> bool:
        collection = getattr(self.parent(), "col", None)
        if collection is not None and preset.deck:
            setting = same_day_optimize_setting(collection, preset)
            if setting is not None:
                return setting
        return True

    def _update_same_day_checkbox(
        self, checkbox: QCheckBox, fsrs_version: FsrsPresetVersion
    ) -> None:
        checkbox.setEnabled(fsrs_version == "seven")

    def _load_deck_names(self, parent: QWidget) -> list[str]:
        collection = getattr(parent, "col", None)
        if collection is None:
            return []
        return [
            deck.name
            for deck in collection.decks.all_names_and_ids(include_filtered=False)
        ]


def _format_params(params: tuple[float, ...]) -> str:
    return ", ".join(f"{param:g}" for param in params)


def _parse_params(text: str) -> list[float]:
    if not text.strip():
        return []
    return [float(part) for part in text.replace(",", " ").split()]


def _grade_label(first_grade: int) -> str:
    return {
        1: "1 Again",
        2: "2 Hard",
        3: "3 Good",
        4: "4 Easy",
    }[first_grade]


def _table_item(text: str) -> QTableWidgetItem:
    return QTableWidgetItem(text)
