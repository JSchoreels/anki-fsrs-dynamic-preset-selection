from __future__ import annotations

import logging
import sys

try:
    from . import fsrs_dynamic_preset_selection as _stable_package

    sys.modules.setdefault("fsrs_dynamic_preset_selection", _stable_package)
except ImportError:
    pass

try:
    from .fsrs_dynamic_preset_selection.addon import setup

    setup()
except Exception:
    logging.getLogger(__name__).exception(
        "failed to initialize FSRS Dynamic Preset Selection"
    )

