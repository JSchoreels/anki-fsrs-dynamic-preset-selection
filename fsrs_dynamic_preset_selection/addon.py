from __future__ import annotations

from logging import Logger
from types import SimpleNamespace
from typing import Any

from aqt import gui_hooks, mw
from aqt.addons import AddonManager
from aqt.qt import QAction, qconnect
from aqt.utils import showInfo, showWarning

from .config import ConfigError, load_config
from .gateway import AnkiFsrsPresetGateway
from .models import DynamicPresetSelectionConfig


class FsrsDynamicPresetSelectionAddon:
    def __init__(self, *, module: str, logger: Logger) -> None:
        self._module = module
        self._logger = logger
        self._config = DynamicPresetSelectionConfig(presets=(), rules=())
        self._config_action: QAction | None = None
        self._config_dialog: Any | None = None

    def setup(self) -> None:
        self._reload_config()
        if mw is not None:
            mw.addonManager.setConfigAction(self._module, self._open_config_dialog)
            mw.addonManager.setConfigUpdatedAction(self._module, self._on_config_updated)
            self._add_tools_menu_entry()
        gui_hooks.collection_did_load.append(self._on_collection_did_load)
        card_info_hook = getattr(gui_hooks, "card_info_will_add_rows", None)
        if card_info_hook is not None:
            card_info_hook.append(self.add_card_info_rows)

    def _on_collection_did_load(self, collection: Any) -> None:
        try:
            self._apply_to_collection(collection)
        except Exception:
            self._logger.exception("failed to apply FSRS preset overlay")

    def _on_config_updated(self, _config: Any) -> None:
        self._reload_config()
        if mw is not None and mw.col is not None:
            self._on_collection_did_load(mw.col)

    def _reload_config(self) -> None:
        raw_config = None
        if mw is not None:
            raw_config = mw.addonManager.getConfig(self._module)
        self._config = load_config(raw_config)
        self._logger.info(
            "loaded FSRS dynamic preset selection presets=%s rules=%s",
            len(self._config.presets),
            len(self._config.rules),
        )

    def _apply_to_collection(self, collection: Any) -> None:
        AnkiFsrsPresetGateway(collection).apply(self._config)

    def add_card_info_rows(self, rows: list[Any], card: Any) -> None:
        if mw is None or mw.col is None:
            return

        match = matched_dynamic_preset_for_card(
            config=self._config,
            collection=mw.col,
            card_id=card.id,
            logger=self._logger,
        )
        if match is None:
            return

        preset, search = match

        rows.append(_card_info_row(label="Dynamic FSRS Preset", value=preset.name))
        rows.append(_card_info_row(label="Dynamic FSRS Preset Match", value=search))
        if preset.has_dynamic_desired_retention_policy():
            rows.append(
                _card_info_row(
                    label="Supported ADR Range",
                    value=_retention_range_text(preset.dynamic_desired_retention_range()),
                )
            )
            rows.append(
                _card_info_row(
                    label="FSRS Equivalent DR Supported",
                    value=_retention_range_text(
                        preset.fsrs_equivalent_desired_retention_range()
                    ),
                )
            )
        adr_mapping = _card_info_adr_mapping_value(
            collection=mw.col,
            card=card,
            desired_retention=_card_info_desired_retention(
                collection=mw.col,
                card=card,
                preset_desired_retention=preset.desired_retention,
                logger=self._logger,
            ),
            logger=self._logger,
        )
        if adr_mapping is not None:
            rows.append(
                _card_info_row(
                    label="Effective Dynamic DR Scheduling",
                    value=adr_mapping,
                )
            )

    def _add_tools_menu_entry(self) -> None:
        if self._config_action is not None or mw is None:
            return
        self._config_action = QAction("FSRS Dynamic Preset Selection...", mw)
        qconnect(self._config_action.triggered, self._open_config_dialog)
        mw.form.menuTools.addAction(self._config_action)

    def _open_config_dialog(self) -> bool:
        if mw is None:
            return False

        if self._config_dialog is not None:
            self._config_dialog.raise_()
            self._config_dialog.activateWindow()
            return True

        try:
            from .dialog import FsrsPresetConfigDialog

            dialog = FsrsPresetConfigDialog(
                mw,
                addon_manager=mw.addonManager,
                module=self._module,
            )
        except ConfigError as exc:
            self._logger.warning("invalid FSRS dynamic preset config: %s", exc)
            showWarning(
                "FSRS Dynamic Preset Selection config is invalid. "
                f"Opening the raw config editor instead.\n\n{exc}"
            )
            return False

        self._config_dialog = dialog

        def on_finished(result: int) -> None:
            self._config_dialog = None
            if not result:
                return

            try:
                self._reload_config()
                if mw.col is not None:
                    self._apply_to_collection(mw.col)
            except ConfigError as exc:
                self._logger.warning("invalid FSRS dynamic preset config: %s", exc)
                showWarning(f"FSRS Dynamic Preset Selection config is invalid:\n\n{exc}")
            except Exception as exc:
                self._logger.exception("failed to apply FSRS preset overlay")
                showWarning(f"Failed to apply FSRS Dynamic Preset Selection:\n\n{exc}")

        qconnect(dialog.finished, on_finished)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return True


def setup() -> None:
    logger = AddonManager.get_logger(__name__)
    FsrsDynamicPresetSelectionAddon(module=__name__, logger=logger).setup()


def _card_info_row(label: str, value: str) -> Any:
    try:
        from aqt.browser.card_info import CardInfoRow
    except ImportError:
        return SimpleNamespace(label=label, value=value)

    return CardInfoRow(label=label, value=value)


def _card_info_adr_mapping_value(
    *,
    collection: Any,
    card: Any,
    desired_retention: float,
    logger: Logger,
) -> str | None:
    scheduler = getattr(collection, "sched", None)
    get_scheduling_states = getattr(scheduler, "get_scheduling_states", None)
    if not callable(get_scheduling_states):
        logger.debug("Card Info ADR mapping skipped: scheduling-state API unavailable")
        return None

    try:
        states = get_scheduling_states(
            card.id,
            desired_retention_override=desired_retention,
        )
    except Exception:
        logger.debug(
            "Card Info ADR mapping skipped: scheduling-state read failed for card %s",
            getattr(card, "id", None),
            exc_info=True,
        )
        return None

    if not hasattr(states, "dynamic_desired_retentions"):
        return None

    retentions = list(getattr(states, "dynamic_desired_retentions"))
    requested = _format_retention_percent(desired_retention)
    if len(retentions) == 4:
        grade_parts = [
            f"{grade} {_format_retention_percent(retention)}"
            for grade, retention in zip(("Again", "Hard", "Good", "Easy"), retentions)
        ]
        return f"{requested} -> {', '.join(grade_parts)}"

    if bool(getattr(states, "dynamic_desired_retention_enabled", False)):
        return f"{requested} -> fixed FSRS DR"

    return None


def _card_info_desired_retention(
    *,
    collection: Any,
    card: Any,
    preset_desired_retention: float,
    logger: Logger,
) -> float:
    try:
        from dynamic_desired_retention import effective_desired_retention
    except ImportError:
        return preset_desired_retention

    try:
        desired_retention = effective_desired_retention(
            collection=collection,
            card=card,
            current_desired_retention=preset_desired_retention,
        )
    except Exception:
        logger.debug(
            "Card Info ADR mapping skipped Dynamic DR effective retention for card %s",
            getattr(card, "id", None),
            exc_info=True,
        )
        return preset_desired_retention

    if desired_retention is None:
        return preset_desired_retention
    return float(desired_retention)


def _format_retention_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _retention_range_text(value: tuple[float, float] | None) -> str:
    if value is None:
        return "n/a"
    return f"{_format_retention_percent(value[0])} - {_format_retention_percent(value[1])}"


def matched_dynamic_preset_for_card(
    *,
    config: DynamicPresetSelectionConfig,
    collection: Any,
    card_id: int,
    logger: Logger,
) -> tuple[Any, str] | None:
    presets_by_id = {preset.id: preset for preset in config.presets}
    for rule in config.to_overlay_dict()["rules"]:
        search = rule["search"]
        preset_id = rule["preset_id"]
        try:
            card_search = collection.build_search_string(search, f"cid:{card_id}")
            if collection.find_cards(card_search, order=False):
                preset = presets_by_id.get(preset_id)
                if preset is not None:
                    return preset, search
        except Exception:
            logger.exception("card info FSRS preset rule search failed: %s", search)
    return None
