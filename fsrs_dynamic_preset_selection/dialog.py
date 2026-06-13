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
    QTimer,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    Qt,
    QVBoxLayout,
    QWidget,
    qconnect,
)
from aqt.operations import CollectionOp, QueryOp
from aqt.utils import showInfo, showWarning

from .config import ConfigError, load_config
from .gateway import (
    AnkiFsrsPresetGateway,
    MemoryStateRewriteProgress,
    MemoryStateRewriteResult,
    count_cards_by_preset,
    deck_unselected_counts,
    optimize_preset,
    optimize_presets_batch,
    rewrite_memory_states_for_presets,
)
from .gateway import same_day_optimize_setting
from .models import (
    AddonFsrsPresetConfig,
    DynamicPresetSelectionConfig,
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
COL_ADR = 7
COL_ADR_CLAMP = 8
COL_ADR_REVIEW_LIMIT = 9
COL_ADR_DAILY_MINUTES = 10
COL_ADR_RANGE = 11
COL_FSRS_EQ_DR_RANGE = 12
COL_DESIRED_RETENTION = 13
COL_HISTORICAL_RETENTION = 14
COL_PARAMS = 15
COL_SELECTED_COUNT = 16
COL_OPTIMIZE = 17

DEFAULT_ADR_REVIEW_LIMIT = 9999
DEFAULT_ADR_DAILY_MINUTES = 720.0

DECK_COUNTS_SHOW_TEXT = "See Deck Cards Not Selected"
DECK_COUNTS_HIDE_TEXT = "Hide Deck Cards Not Selected"

ROLE_OLD_ID = 0x0100
ROLE_FIRST_GRADE = 0x0101
ROLE_ADR_PARAMS = 0x0102
ROLE_ADR_WEIGHTS = 0x0103
ROLE_ADR_AVG_DRS = 0x0104
ROLE_ADR_MIN = 0x0105
ROLE_ADR_MAX = 0x0106
ROLE_ADR_FSRS_EQ_WEIGHTS = 0x0107
ROLE_ADR_FSRS_EQ_DRS = 0x0108

FSRS_VERSIONS: tuple[tuple[str, FsrsPresetVersion], ...] = (
    ("7", "seven"),
    ("6", "six"),
    ("5", "five"),
    ("4", "four"),
)

FIRST_GRADES = (1, 2, 3, 4)


class _RowProgressUpdate:
    def __init__(self) -> None:
        self.user_wants_abort = False
        self.abort = False
        self.max = 0
        self.value = 0
        self.label = ""


class _MemoryRewriteUiState:
    def __init__(self) -> None:
        self.latest: MemoryStateRewriteProgress | None = None


class FsrsPresetConfigDialog(QDialog):
    def __init__(self, parent: QWidget, *, addon_manager: Any, module: str) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self._addon_manager = addon_manager
        self._module = module
        self._raw_config = addon_manager.getConfig(module) or {}
        self._config = load_config(self._raw_config)
        self._advanced_rules = list(self._raw_config.get("rules", []))
        self._deck_names = self._load_deck_names(parent)
        self._single_optimize_running = False
        self._single_optimize_queue: list[QTreeWidgetItem] = []
        self._single_optimize_progress_timer: QTimer | None = None
        self._memory_rewrite_progress_timer: QTimer | None = None

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
        self.tree.setColumnCount(18)
        self.tree.setHeaderLabels(
            [
                "Name",
                "Deck",
                "Search",
                "Split",
                "Grade",
                "FSRS Version",
                "Same-day Reviews",
                "ADR",
                "ADR Clamp",
                "ADR Reviews",
                "ADR Minutes",
                "ADR Range",
                "FSRS Eq DR Range",
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
        self.tree.header().setSectionResizeMode(
            COL_ADR, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tree.header().setSectionResizeMode(
            COL_ADR_CLAMP, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tree.header().setSectionResizeMode(
            COL_ADR_REVIEW_LIMIT, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tree.header().setSectionResizeMode(
            COL_ADR_DAILY_MINUTES, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tree.header().setSectionResizeMode(
            COL_ADR_RANGE, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tree.header().setSectionResizeMode(
            COL_FSRS_EQ_DR_RANGE, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tree.header().setSectionResizeMode(COL_PARAMS, QHeaderView.ResizeMode.Stretch)
        self.tree.headerItem().setToolTip(
            COL_SAME_DAY,
            "Include same-day reviews when optimizing this FSRS-7 preset.",
        )
        self.tree.headerItem().setToolTip(
            COL_ADR,
            "Train and use native Anki Dynamic DR for this FSRS-7 preset.",
        )
        self.tree.headerItem().setToolTip(
            COL_ADR_CLAMP,
            "Clamp unsupported Dynamic DR targets to the nearest calibrated target.",
        )
        self.tree.headerItem().setToolTip(
            COL_ADR_REVIEW_LIMIT,
            "Review limit used by the ADR training simulator for this preset.",
        )
        self.tree.headerItem().setToolTip(
            COL_ADR_DAILY_MINUTES,
            "Daily time budget in minutes used by the ADR training simulator for this preset.",
        )
        self.tree.headerItem().setToolTip(
            COL_ADR_RANGE,
            "Calibrated target average DR range available after optimization.",
        )
        self.tree.headerItem().setToolTip(
            COL_FSRS_EQ_DR_RANGE,
            "FSRS-equivalent Dynamic DR target range available after optimization.",
        )
        layout.addWidget(self.tree)

        row_actions = QHBoxLayout()
        add_button = QPushButton("Add Preset")
        remove_button = QPushButton("Remove Selected")
        move_up_button = QPushButton("Move Up")
        move_down_button = QPushButton("Move Down")
        visualize_adr_button = QPushButton("Visualize ADR")
        self.optimize_all_button = QPushButton("Optimize All")
        self.optimize_all_progress = QProgressBar()
        self.optimize_all_progress.setVisible(False)
        refresh_counts_button = QPushButton("Refresh Counts")
        qconnect(add_button.clicked, self._add_empty_preset_group)
        qconnect(remove_button.clicked, self._remove_selected_item)
        qconnect(move_up_button.clicked, lambda: self._move_selected_item(-1))
        qconnect(move_down_button.clicked, lambda: self._move_selected_item(1))
        qconnect(visualize_adr_button.clicked, self._visualize_selected_adr)
        qconnect(self.optimize_all_button.clicked, self._optimize_all)
        qconnect(refresh_counts_button.clicked, self._refresh_counts)
        row_actions.addWidget(add_button)
        row_actions.addWidget(remove_button)
        row_actions.addWidget(move_up_button)
        row_actions.addWidget(move_down_button)
        row_actions.addWidget(visualize_adr_button)
        row_actions.addWidget(self.optimize_all_button)
        row_actions.addWidget(self.optimize_all_progress)
        row_actions.addWidget(refresh_counts_button)
        row_actions.addStretch()
        layout.addLayout(row_actions)

        self.deck_counts_toggle_button = QPushButton(_deck_counts_toggle_text(False))
        self.deck_counts_toggle_button.setCheckable(True)
        qconnect(
            self.deck_counts_toggle_button.toggled,
            self._set_deck_counts_visible,
        )
        layout.addWidget(self.deck_counts_toggle_button)

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
        self.deck_counts_table.setVisible(False)
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
            fsrs_dynamic_desired_retention_enabled=template.fsrs_dynamic_desired_retention_enabled,
            fsrs_dynamic_desired_retention_clamp=template.fsrs_dynamic_desired_retention_clamp,
            fsrs_dynamic_desired_retention_review_limit=template.fsrs_dynamic_desired_retention_review_limit,
            fsrs_dynamic_desired_retention_max_cost_perday_minutes=template.fsrs_dynamic_desired_retention_max_cost_perday_minutes,
            fsrs_dynamic_desired_retention_params=template.fsrs_dynamic_desired_retention_params,
            fsrs_dynamic_desired_retention_weights=template.fsrs_dynamic_desired_retention_weights,
            fsrs_dynamic_desired_retention_avg_drs=template.fsrs_dynamic_desired_retention_avg_drs,
            fsrs_dynamic_desired_retention_fsrs_eq_weights=template.fsrs_dynamic_desired_retention_fsrs_eq_weights,
            fsrs_dynamic_desired_retention_fsrs_eq_drs=template.fsrs_dynamic_desired_retention_fsrs_eq_drs,
            fsrs_dynamic_desired_retention_min=template.fsrs_dynamic_desired_retention_min,
            fsrs_dynamic_desired_retention_max=template.fsrs_dynamic_desired_retention_max,
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
        adr_checkbox = self._adr_checkbox(preset)
        adr_clamp_checkbox = self._adr_clamp_checkbox(preset)
        adr_review_limit = self._adr_review_limit_spin(preset)
        adr_daily_minutes = self._adr_daily_minutes_spin(preset)
        qconnect(
            version_combo.currentIndexChanged,
            lambda _index, same_day=same_day_checkbox, adr=adr_checkbox, clamp=adr_clamp_checkbox, review_limit=adr_review_limit, daily_minutes=adr_daily_minutes, combo=version_combo: self._update_fsrs7_controls(
                same_day,
                adr,
                clamp,
                review_limit,
                daily_minutes,
                combo.currentData(),
            ),
        )
        self.tree.setItemWidget(item, COL_VERSION, version_combo)
        self.tree.setItemWidget(item, COL_SAME_DAY, same_day_checkbox)
        self.tree.setItemWidget(item, COL_ADR, adr_checkbox)
        self.tree.setItemWidget(item, COL_ADR_CLAMP, adr_clamp_checkbox)
        self.tree.setItemWidget(item, COL_ADR_REVIEW_LIMIT, adr_review_limit)
        self.tree.setItemWidget(item, COL_ADR_DAILY_MINUTES, adr_daily_minutes)
        self.tree.setItemWidget(item, COL_ADR_RANGE, self._adr_range_widget(preset))
        self.tree.setItemWidget(
            item, COL_FSRS_EQ_DR_RANGE, self._fsrs_eq_dr_range_widget(preset)
        )
        self._set_adr_policy_data(item, preset)
        self._update_fsrs7_controls(
            same_day_checkbox,
            adr_checkbox,
            adr_clamp_checkbox,
            adr_review_limit,
            adr_daily_minutes,
            preset.fsrs_version,
        )
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
            COL_ADR,
            COL_ADR_CLAMP,
            COL_ADR_REVIEW_LIMIT,
            COL_ADR_DAILY_MINUTES,
            COL_ADR_RANGE,
            COL_FSRS_EQ_DR_RANGE,
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
            config = load_config(new_config)
            missing_adr_policy = [
                preset.name
                for preset in config.presets
                if preset.fsrs_dynamic_desired_retention_enabled
                and not preset.has_dynamic_desired_retention_policy()
            ]
            if missing_adr_policy:
                raise ConfigError(
                    "optimize ADR-enabled presets before saving: "
                    + ", ".join(missing_adr_policy)
                )
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
            preset["fsrs_dynamic_desired_retention_enabled"] = self._checkbox(
                item, COL_ADR
            ).isChecked()
            preset["fsrs_dynamic_desired_retention_clamp"] = self._checkbox(
                item, COL_ADR_CLAMP
            ).isChecked()
            preset["fsrs_dynamic_desired_retention_review_limit"] = self._int_spin(
                item, COL_ADR_REVIEW_LIMIT
            ).value()
            preset["fsrs_dynamic_desired_retention_max_cost_perday_minutes"] = self._spin(
                item, COL_ADR_DAILY_MINUTES
            ).value()
            adr_policy = self._adr_policy_data(item)
            preset.update(adr_policy)
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

    def _set_deck_counts_visible(self, visible: bool) -> None:
        self.deck_counts_table.setVisible(visible)
        self.deck_counts_toggle_button.setText(_deck_counts_toggle_text(visible))

    def _visualize_selected_adr(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            showWarning("Select a preset row with optimized ADR data first.", parent=self)
            return
        if item.childCount():
            showWarning("Select one split preset row to visualize ADR.", parent=self)
            return

        try:
            from .adr_plot import valid_plot_policy
            from aqt.dynamic_desired_retention_plot import (
                open_dynamic_desired_retention_plot,
            )

            preset = self._config_preset_from_item(item)
        except (ConfigError, ValueError) as exc:
            showWarning(f"Unable to visualize ADR:\n\n{exc}", parent=self)
            return

        if not valid_plot_policy(preset):
            showWarning("Optimize this ADR preset before visualizing it.", parent=self)
            return

        def save_target(value: float) -> None:
            self._spin(item, COL_DESIRED_RETENTION).setValue(value)

        open_dynamic_desired_retention_plot(
            self,
            params=preset.fsrs_dynamic_desired_retention_params,
            calibration_weights=preset.fsrs_dynamic_desired_retention_weights,
            calibration_avg_drs=preset.fsrs_dynamic_desired_retention_avg_drs,
            fsrs_equivalent_weights=preset.fsrs_dynamic_desired_retention_fsrs_eq_weights,
            fsrs_equivalent_drs=preset.fsrs_dynamic_desired_retention_fsrs_eq_drs,
            retention_min=preset.fsrs_dynamic_desired_retention_min,
            retention_max=preset.fsrs_dynamic_desired_retention_max,
            target_average_dr=self._spin(item, COL_DESIRED_RETENTION).value(),
            save_target=save_target,
        )

    def _optimize_item(self, button: QPushButton) -> None:
        item = self._item_for_widget(button, COL_OPTIMIZE)
        if item is None:
            return
        FsrsPresetConfigDialog._queue_or_start_optimize_item(self, item)

    def _queue_or_start_optimize_item(self, item: QTreeWidgetItem) -> None:
        if getattr(self, "_single_optimize_running", False):
            queue = getattr(self, "_single_optimize_queue", [])
            self._single_optimize_queue = queue
            if item not in queue:
                queue.append(item)
                self._set_item_progress(item, value=0, text="Pending")
            return

        FsrsPresetConfigDialog._start_optimize_item(self, item)

    def _start_optimize_item(self, item: QTreeWidgetItem) -> None:
        self._single_optimize_running = True
        try:
            preset, ordered_rules = self._optimization_context(item)
        except (ConfigError, ValueError) as exc:
            showWarning(f"Unable to optimize preset:\n\n{exc}", parent=self)
            FsrsPresetConfigDialog._finish_optimize_item(self)
            return
        except Exception as exc:
            showWarning(f"Unable to optimize preset:\n\n{exc}", parent=self)
            FsrsPresetConfigDialog._finish_optimize_item(self)
            return

        self._set_item_progress(item, value=0, maximum=0, text="Optimizing...")
        getattr(self, "_start_item_backend_progress", lambda _item, _name: None)(
            item, preset.name
        )

        def on_success(result: Any) -> None:
            getattr(self, "_stop_item_backend_progress", lambda: None)()
            self._line_edit(item, COL_PARAMS).setText(_format_params(result.params))
            self._apply_optimized_adr(item, preset, result)
            self._start_single_memory_state_rewrite(item)

        def on_failure(exc: Exception) -> None:
            getattr(self, "_stop_item_backend_progress", lambda: None)()
            self._set_optimize_button(item)
            showWarning(f"Unable to optimize preset:\n\n{exc}", parent=self)
            FsrsPresetConfigDialog._finish_optimize_item(self)

        QueryOp(
            parent=self,
            op=lambda col: optimize_preset(col, preset, ordered_rules),
            success=on_success,
        ).failure(on_failure).run_in_background()

    def _start_item_backend_progress(
        self, item: QTreeWidgetItem, preset_name: str
    ) -> None:
        self._stop_item_backend_progress()
        timer = QTimer(self)
        self._single_optimize_progress_timer = timer

        def on_progress() -> None:
            from aqt import mw

            if mw is None:
                return
            update = _RowProgressUpdate()
            self._update_item_compute_progress(
                item,
                mw.backend.latest_progress(),
                update,
                preset_name,
            )

        qconnect(timer.timeout, on_progress)
        timer.start(100)

    def _stop_item_backend_progress(self) -> None:
        timer = getattr(self, "_single_optimize_progress_timer", None)
        if timer is None:
            return
        timer.stop()
        timer.deleteLater()
        self._single_optimize_progress_timer = None

    def _finish_optimize_item(self) -> None:
        self._single_optimize_running = False
        FsrsPresetConfigDialog._start_next_queued_optimize_item(self)

    def _start_next_queued_optimize_item(self) -> None:
        queue = getattr(self, "_single_optimize_queue", [])
        self._single_optimize_queue = queue
        if not queue:
            return
        items = list(self._all_items())
        while queue:
            item = queue.pop(0)
            if any(item is existing for existing in items):
                FsrsPresetConfigDialog._start_optimize_item(self, item)
                return

    def _optimize_all(self) -> None:
        items = self._leaf_items()
        if not items:
            return
        try:
            presets, ordered_rules = self._optimization_presets_and_rules()
        except (ConfigError, ValueError) as exc:
            showWarning(f"Unable to optimize all presets:\n\n{exc}", parent=self)
            return
        except Exception as exc:
            showWarning(f"Unable to optimize all presets:\n\n{exc}", parent=self)
            return

        self._show_optimize_all_progress(len(items))
        self._set_all_item_progress_pending(items)
        def op(col: Any) -> list[Any]:
            return optimize_presets_batch(col, presets, ordered_rules)

        def on_success(results: list[Any]) -> None:
            for item, preset, result in zip(items, presets, results, strict=False):
                self._line_edit(item, COL_PARAMS).setText(_format_params(result.params))
                self._apply_optimized_adr(item, preset, result)
                self._set_item_progress(item, value=100, text="Optimized")
            self._start_all_memory_state_rewrite(items, len(results))

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

    def _optimization_context(
        self, item: QTreeWidgetItem
    ) -> tuple[AddonFsrsPresetConfig, list[dict[str, str]]]:
        presets, ordered_rules = self._optimization_presets_and_rules()
        index = list(self._leaf_items()).index(item)
        return presets[index], ordered_rules

    def _optimization_presets_and_rules(
        self,
    ) -> tuple[list[AddonFsrsPresetConfig], list[dict[str, str]]]:
        config, ordered_rules = self._optimization_config_and_rules()
        return list(config.presets), ordered_rules

    def _optimization_config_and_rules(
        self,
    ) -> tuple[DynamicPresetSelectionConfig, list[dict[str, str]]]:
        preset_dicts = self._preset_dicts()
        config = load_config(
            {
                "presets": preset_dicts,
                "rules": self._updated_advanced_rules(preset_dicts),
            }
        )
        ordered_rules = config.to_overlay_dict()["rules"]
        if not ordered_rules:
            raise ConfigError("choose a deck or enter a search filter before optimizing")
        return config, ordered_rules

    def _start_single_memory_state_rewrite(self, item: QTreeWidgetItem) -> None:
        try:
            config, presets, ordered_rules = self._memory_rewrite_context([item])
        except (ConfigError, ValueError) as exc:
            self._set_optimize_button(item)
            showWarning(f"Unable to rewrite memory states:\n\n{exc}", parent=self)
            FsrsPresetConfigDialog._finish_optimize_item(self)
            return
        except Exception as exc:
            self._set_optimize_button(item)
            showWarning(f"Unable to rewrite memory states:\n\n{exc}", parent=self)
            FsrsPresetConfigDialog._finish_optimize_item(self)
            return

        state = _MemoryRewriteUiState()
        self._set_item_progress(item, value=0, maximum=0, text="Updating memory...")
        self._start_memory_rewrite_progress_timer([item], state, update_all=False)

        def on_success(_result: MemoryStateRewriteResult) -> None:
            self._stop_memory_rewrite_progress_timer()
            self._set_item_progress(item, value=100, text="Done")
            self._set_optimize_button(item)
            FsrsPresetConfigDialog._finish_optimize_item(self)

        def on_failure(exc: Exception) -> None:
            self._stop_memory_rewrite_progress_timer()
            self._set_optimize_button(item)
            showWarning(f"Unable to rewrite memory states:\n\n{exc}", parent=self)
            FsrsPresetConfigDialog._finish_optimize_item(self)

        CollectionOp(
            parent=self,
            op=lambda col: _apply_overlay_and_rewrite_memory_states(
                col,
                config,
                presets,
                ordered_rules,
                state,
            ),
        ).success(on_success).failure(on_failure).run_in_background()

    def _start_all_memory_state_rewrite(
        self, items: list[QTreeWidgetItem], optimized_count: int
    ) -> None:
        try:
            config, presets, ordered_rules = self._memory_rewrite_context(items)
        except (ConfigError, ValueError) as exc:
            self._hide_optimize_all_progress()
            self._restore_all_item_optimize_buttons(items)
            showWarning(f"Unable to rewrite memory states:\n\n{exc}", parent=self)
            return
        except Exception as exc:
            self._hide_optimize_all_progress()
            self._restore_all_item_optimize_buttons(items)
            showWarning(f"Unable to rewrite memory states:\n\n{exc}", parent=self)
            return

        state = _MemoryRewriteUiState()
        self.optimize_all_progress.setFormat("Memory %v/%m")
        self._update_optimize_all_progress(0, max(len(presets), 1))
        for item in items:
            self._set_item_progress(item, value=0, maximum=0, text="Memory pending")
        self._start_memory_rewrite_progress_timer(items, state, update_all=True)

        def on_success(result: MemoryStateRewriteResult) -> None:
            self._stop_memory_rewrite_progress_timer()
            for item in items:
                self._set_item_progress(item, value=100, text="Done")
            self._hide_optimize_all_progress()
            self._restore_all_item_optimize_buttons(items)
            showInfo(
                "Optimized "
                f"{optimized_count} presets. Rewrote FSRS memory state for "
                f"{result.cards_updated} cards.",
                parent=self,
            )

        def on_failure(exc: Exception) -> None:
            self._stop_memory_rewrite_progress_timer()
            self._hide_optimize_all_progress()
            self._restore_all_item_optimize_buttons(items)
            showWarning(f"Unable to rewrite memory states:\n\n{exc}", parent=self)

        CollectionOp(
            parent=self,
            op=lambda col: _apply_overlay_and_rewrite_memory_states(
                col,
                config,
                presets,
                ordered_rules,
                state,
            ),
        ).success(on_success).failure(on_failure).run_in_background()

    def _memory_rewrite_context(
        self, items: list[QTreeWidgetItem]
    ) -> tuple[
        DynamicPresetSelectionConfig,
        list[AddonFsrsPresetConfig],
        list[dict[str, str]],
    ]:
        config, ordered_rules = self._optimization_config_and_rules()
        leaf_items = self._leaf_items()
        selected_indexes = [leaf_items.index(item) for item in items]
        return (
            config,
            [list(config.presets)[index] for index in selected_indexes],
            ordered_rules,
        )

    def _start_memory_rewrite_progress_timer(
        self,
        items: list[QTreeWidgetItem],
        state: _MemoryRewriteUiState,
        *,
        update_all: bool,
    ) -> None:
        self._stop_memory_rewrite_progress_timer()
        timer = QTimer(self)
        self._memory_rewrite_progress_timer = timer

        def on_progress() -> None:
            progress = state.latest
            if progress is None:
                return
            if update_all:
                self._update_all_memory_rewrite_progress(items, progress)
            else:
                self._update_item_memory_rewrite_progress(items[0], progress)

        qconnect(timer.timeout, on_progress)
        timer.start(100)

    def _stop_memory_rewrite_progress_timer(self) -> None:
        timer = getattr(self, "_memory_rewrite_progress_timer", None)
        if timer is None:
            return
        timer.stop()
        timer.deleteLater()
        self._memory_rewrite_progress_timer = None

    def _update_item_memory_rewrite_progress(
        self, item: QTreeWidgetItem, progress: MemoryStateRewriteProgress
    ) -> None:
        maximum = max(progress.total, 1)
        current = min(progress.current, maximum)
        self._set_item_progress(
            item,
            value=current,
            maximum=maximum,
            text=_memory_rewrite_progress_text(progress),
        )

    def _update_all_memory_rewrite_progress(
        self,
        items: list[QTreeWidgetItem],
        progress: MemoryStateRewriteProgress,
    ) -> None:
        active_index = progress.preset_index - 1
        if 0 < active_index <= len(items):
            self._set_item_progress(items[active_index - 1], value=100, text="Done")
        if 0 <= active_index < len(items):
            self._update_item_memory_rewrite_progress(items[active_index], progress)

        completed_presets = active_index
        if progress.total == 0 or progress.current >= progress.total:
            completed_presets = progress.preset_index
        self._update_optimize_all_progress(
            completed_presets,
            max(progress.preset_count, 1),
        )

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
            text=_compute_params_progress_text(value),
        )
        update.max = maximum
        update.value = current
        update.label = f"{_compute_params_progress_label(value)} {preset_name}"
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
            text = (
                "Skipped"
                if preset_progress.skipped
                else _compute_params_progress_text(preset_progress)
            )
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

    def _int_spin(self, item: QTreeWidgetItem, column: int) -> QSpinBox:
        widget = self.tree.itemWidget(item, column)
        assert isinstance(widget, QSpinBox)
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

    def _adr_checkbox(self, preset: AddonFsrsPresetConfig) -> QCheckBox:
        checkbox = QCheckBox()
        checkbox.setText("Enable")
        checkbox.setToolTip("Train and use native Anki Dynamic DR for this FSRS-7 preset.")
        checkbox.setChecked(preset.fsrs_dynamic_desired_retention_enabled)
        return checkbox

    def _adr_clamp_checkbox(self, preset: AddonFsrsPresetConfig) -> QCheckBox:
        checkbox = QCheckBox()
        checkbox.setText("Clamp")
        checkbox.setToolTip(
            "Clamp unsupported Dynamic DR targets to the nearest calibrated target."
        )
        checkbox.setChecked(preset.fsrs_dynamic_desired_retention_clamp)
        return checkbox

    def _adr_review_limit_spin(self, preset: AddonFsrsPresetConfig) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(1, 999999)
        spin.setValue(
            preset.fsrs_dynamic_desired_retention_review_limit
            or DEFAULT_ADR_REVIEW_LIMIT
        )
        spin.setToolTip("Review limit used by the ADR training simulator.")
        return spin

    def _adr_daily_minutes_spin(self, preset: AddonFsrsPresetConfig) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.1, 1440.0)
        spin.setDecimals(1)
        spin.setSingleStep(30.0)
        spin.setValue(
            preset.fsrs_dynamic_desired_retention_max_cost_perday_minutes
            or DEFAULT_ADR_DAILY_MINUTES
        )
        spin.setToolTip("Daily time budget in minutes used by the ADR training simulator.")
        return spin

    def _adr_range_widget(self, preset: AddonFsrsPresetConfig) -> QLineEdit:
        widget = QLineEdit(_adr_range_text(preset.dynamic_desired_retention_range()))
        widget.setReadOnly(True)
        return widget

    def _fsrs_eq_dr_range_widget(self, preset: AddonFsrsPresetConfig) -> QLineEdit:
        widget = QLineEdit(
            _adr_range_text(preset.fsrs_equivalent_desired_retention_range())
        )
        widget.setReadOnly(True)
        return widget

    def _set_adr_policy_data(
        self, item: QTreeWidgetItem, preset: AddonFsrsPresetConfig
    ) -> None:
        item.setData(
            COL_ADR,
            ROLE_ADR_PARAMS,
            tuple(preset.fsrs_dynamic_desired_retention_params),
        )
        item.setData(
            COL_ADR,
            ROLE_ADR_WEIGHTS,
            tuple(preset.fsrs_dynamic_desired_retention_weights),
        )
        item.setData(
            COL_ADR,
            ROLE_ADR_AVG_DRS,
            tuple(preset.fsrs_dynamic_desired_retention_avg_drs),
        )
        item.setData(
            COL_ADR,
            ROLE_ADR_FSRS_EQ_WEIGHTS,
            tuple(preset.fsrs_dynamic_desired_retention_fsrs_eq_weights),
        )
        item.setData(
            COL_ADR,
            ROLE_ADR_FSRS_EQ_DRS,
            tuple(preset.fsrs_dynamic_desired_retention_fsrs_eq_drs),
        )
        item.setData(COL_ADR, ROLE_ADR_MIN, preset.fsrs_dynamic_desired_retention_min)
        item.setData(COL_ADR, ROLE_ADR_MAX, preset.fsrs_dynamic_desired_retention_max)

    def _adr_policy_data(self, item: QTreeWidgetItem) -> dict[str, object]:
        return {
            "fsrs_dynamic_desired_retention_params": list(
                item.data(COL_ADR, ROLE_ADR_PARAMS) or ()
            ),
            "fsrs_dynamic_desired_retention_weights": list(
                item.data(COL_ADR, ROLE_ADR_WEIGHTS) or ()
            ),
            "fsrs_dynamic_desired_retention_avg_drs": list(
                item.data(COL_ADR, ROLE_ADR_AVG_DRS) or ()
            ),
            "fsrs_dynamic_desired_retention_fsrs_eq_weights": list(
                item.data(COL_ADR, ROLE_ADR_FSRS_EQ_WEIGHTS) or ()
            ),
            "fsrs_dynamic_desired_retention_fsrs_eq_drs": list(
                item.data(COL_ADR, ROLE_ADR_FSRS_EQ_DRS) or ()
            ),
            "fsrs_dynamic_desired_retention_min": float(
                item.data(COL_ADR, ROLE_ADR_MIN) or 0.0
            ),
            "fsrs_dynamic_desired_retention_max": float(
                item.data(COL_ADR, ROLE_ADR_MAX) or 0.0
            ),
        }

    def _apply_optimized_adr(
        self, item: QTreeWidgetItem, preset: AddonFsrsPresetConfig, result: Any
    ) -> None:
        if not preset.fsrs_dynamic_desired_retention_enabled:
            self._set_adr_policy_data(
                item,
                AddonFsrsPresetConfig(
                    id=preset.id,
                    name=preset.name,
                    fsrs_version=preset.fsrs_version,
                    params=preset.params,
                    desired_retention=preset.desired_retention,
                    historical_retention=preset.historical_retention,
                    fsrs_dynamic_desired_retention_review_limit=preset.fsrs_dynamic_desired_retention_review_limit,
                    fsrs_dynamic_desired_retention_max_cost_perday_minutes=preset.fsrs_dynamic_desired_retention_max_cost_perday_minutes,
                    fsrs_dynamic_desired_retention_clamp=preset.fsrs_dynamic_desired_retention_clamp,
                ),
            )
            self._line_edit(item, COL_ADR_RANGE).setText(_adr_range_text(None))
            self._line_edit(item, COL_FSRS_EQ_DR_RANGE).setText(_adr_range_text(None))
            return

        updated = AddonFsrsPresetConfig(
            id=preset.id,
            name=preset.name,
            fsrs_version=preset.fsrs_version,
            params=result.params,
            desired_retention=preset.desired_retention,
            historical_retention=preset.historical_retention,
            fsrs_dynamic_desired_retention_review_limit=preset.fsrs_dynamic_desired_retention_review_limit,
            fsrs_dynamic_desired_retention_max_cost_perday_minutes=preset.fsrs_dynamic_desired_retention_max_cost_perday_minutes,
            fsrs_dynamic_desired_retention_enabled=True,
            fsrs_dynamic_desired_retention_clamp=preset.fsrs_dynamic_desired_retention_clamp,
            fsrs_dynamic_desired_retention_params=result.fsrs_dynamic_desired_retention_params,
            fsrs_dynamic_desired_retention_weights=result.fsrs_dynamic_desired_retention_weights,
            fsrs_dynamic_desired_retention_avg_drs=result.fsrs_dynamic_desired_retention_avg_drs,
            fsrs_dynamic_desired_retention_fsrs_eq_weights=result.fsrs_dynamic_desired_retention_fsrs_eq_weights,
            fsrs_dynamic_desired_retention_fsrs_eq_drs=result.fsrs_dynamic_desired_retention_fsrs_eq_drs,
            fsrs_dynamic_desired_retention_min=result.fsrs_dynamic_desired_retention_min,
            fsrs_dynamic_desired_retention_max=result.fsrs_dynamic_desired_retention_max,
        )
        self._set_adr_policy_data(item, updated)
        self._line_edit(item, COL_ADR_RANGE).setText(
            _adr_range_text(updated.dynamic_desired_retention_range())
        )
        self._line_edit(item, COL_FSRS_EQ_DR_RANGE).setText(
            _adr_range_text(updated.fsrs_equivalent_desired_retention_range())
        )

    def _same_day_default(self, preset: AddonFsrsPresetConfig) -> bool:
        collection = getattr(self.parent(), "col", None)
        if collection is not None and preset.deck:
            setting = same_day_optimize_setting(collection, preset)
            if setting is not None:
                return setting
        return True

    def _update_fsrs7_controls(
        self,
        same_day_checkbox: QCheckBox,
        adr_checkbox: QCheckBox,
        adr_clamp_checkbox: QCheckBox,
        adr_review_limit: QSpinBox,
        adr_daily_minutes: QDoubleSpinBox,
        fsrs_version: FsrsPresetVersion,
    ) -> None:
        enabled = fsrs_version == "seven"
        same_day_checkbox.setEnabled(enabled)
        adr_checkbox.setEnabled(enabled)
        adr_clamp_checkbox.setEnabled(enabled)
        adr_review_limit.setEnabled(enabled)
        adr_daily_minutes.setEnabled(enabled)
        if not enabled:
            adr_checkbox.setChecked(False)
            adr_clamp_checkbox.setChecked(False)

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


def _apply_overlay_and_rewrite_memory_states(
    collection: Any,
    config: DynamicPresetSelectionConfig,
    presets: list[AddonFsrsPresetConfig],
    ordered_rules: list[dict[str, str]],
    state: _MemoryRewriteUiState,
) -> MemoryStateRewriteResult:
    overlay_changes = AnkiFsrsPresetGateway(collection).apply(config)
    result = rewrite_memory_states_for_presets(
        collection,
        presets,
        ordered_rules,
        progress=lambda progress: setattr(state, "latest", progress),
    )
    return _with_op_changes(result, overlay_changes)


def _with_op_changes(
    result: MemoryStateRewriteResult,
    fallback_changes: Any | None,
) -> MemoryStateRewriteResult:
    if result.changes is not None:
        return result
    if fallback_changes is not None:
        return MemoryStateRewriteResult(
            cards_found=result.cards_found,
            cards_updated=result.cards_updated,
            changes=fallback_changes,
        )

    from anki.collection import OpChanges

    return MemoryStateRewriteResult(
        cards_found=result.cards_found,
        cards_updated=result.cards_updated,
        changes=OpChanges(),
    )


def _memory_rewrite_progress_text(progress: MemoryStateRewriteProgress) -> str:
    return f"Memory {progress.current}/{progress.total}"


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


def _adr_range_text(value: tuple[float, float] | None) -> str:
    if value is None:
        return "Optimize required"
    low, high = value
    return f"{low:.1%}-{high:.1%}"


def _compute_params_progress_text(progress: Any) -> str:
    if _is_dynamic_desired_retention_progress(progress):
        return "Compute ADR values %p%"
    return "Optimizing %p%"


def _compute_params_progress_label(progress: Any) -> str:
    if _is_dynamic_desired_retention_progress(progress):
        return "Compute ADR values for"
    return "Optimizing"


def _is_dynamic_desired_retention_progress(progress: Any) -> bool:
    phase = getattr(progress, "phase", 0)
    if phase == 1:
        return True
    return str(phase).endswith("TRAINING_DYNAMIC_DESIRED_RETENTION")


def _table_item(text: str) -> QTableWidgetItem:
    return QTableWidgetItem(text)


def _deck_counts_toggle_text(visible: bool) -> str:
    return DECK_COUNTS_HIDE_TEXT if visible else DECK_COUNTS_SHOW_TEXT
