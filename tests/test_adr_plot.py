from __future__ import annotations

from fsrs_dynamic_preset_selection.adr_plot import (
    cost_weight_for_desired_retention,
    target_calibration,
    valid_plot_policy,
)
from fsrs_dynamic_preset_selection.models import AddonFsrsPresetConfig


def test_target_calibration_prefers_fsrs_equivalent_points() -> None:
    weights, drs, label = target_calibration(
        (0.0, 16.0),
        (0.9, 0.8),
        (0.0, 16.0),
        (0.91, 0.81),
    )

    assert weights == (0.0, 16.0)
    assert drs == (0.91, 0.81)
    assert label == "FSRS7 Eq. DR"


def test_target_calibration_falls_back_to_average_adr_points() -> None:
    weights, drs, label = target_calibration((0.0, 16.0), (0.9, 0.8), (), ())

    assert weights == (0.0, 16.0)
    assert drs == (0.9, 0.8)
    assert label == "Avg ADR DR"


def test_cost_weight_uses_log_interpolation() -> None:
    weight = cost_weight_for_desired_retention(0.85, (0.0, 15.0), (0.9, 0.8))

    assert weight is not None
    assert abs(weight - 3.0) < 1e-12


def test_valid_plot_policy_requires_trained_adr_policy() -> None:
    preset = AddonFsrsPresetConfig(
        id="addon:test",
        name="Test",
        fsrs_version="seven",
        params=(0.0,) * 19,
        desired_retention=0.9,
        historical_retention=0.9,
        fsrs_dynamic_desired_retention_params=(0.0,) * 15,
        fsrs_dynamic_desired_retention_weights=(0.0, 15.0),
        fsrs_dynamic_desired_retention_avg_drs=(0.9, 0.8),
        fsrs_dynamic_desired_retention_fsrs_eq_weights=(0.0, 15.0),
        fsrs_dynamic_desired_retention_fsrs_eq_drs=(0.91, 0.81),
        fsrs_dynamic_desired_retention_min=0.3,
        fsrs_dynamic_desired_retention_max=0.995,
    )

    assert valid_plot_policy(preset)

    untrained = AddonFsrsPresetConfig(
        id="addon:test",
        name="Test",
        fsrs_version="seven",
        params=(0.0,) * 19,
        desired_retention=0.9,
        historical_retention=0.9,
    )
    assert not valid_plot_policy(untrained)
