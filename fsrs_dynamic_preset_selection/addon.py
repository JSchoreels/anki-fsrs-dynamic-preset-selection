from __future__ import annotations

from logging import Logger
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

        from aqt.browser.card_info import CardInfoRow

        rows.append(CardInfoRow(label="Dynamic FSRS Preset", value=preset.name))
        rows.append(CardInfoRow(label="Dynamic FSRS Preset Match", value=search))

    def _add_tools_menu_entry(self) -> None:
        if self._config_action is not None or mw is None:
            return
        self._config_action = QAction("FSRS Dynamic Preset Selection...", mw)
        qconnect(self._config_action.triggered, self._open_config_dialog)
        mw.form.menuTools.addAction(self._config_action)

    def _open_config_dialog(self) -> bool:
        if mw is None:
            return False

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

        if not dialog.exec():
            return True

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
        return True


def setup() -> None:
    logger = AddonManager.get_logger(__name__)
    FsrsDynamicPresetSelectionAddon(module=__name__, logger=logger).setup()


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
