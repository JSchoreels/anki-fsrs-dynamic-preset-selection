from __future__ import annotations

import pytest

from fsrs_dynamic_preset_selection.config import ConfigError, load_config


def test_load_config_converts_to_overlay_dict():
    config = load_config(
        {
            "presets": [
                {
                    "id": "addon:test:medical",
                    "name": "Medical",
                    "fsrs_version": "six",
                    "params": [1, 2.5],
                    "desired_retention": 0.9,
                    "historical_retention": 0.8,
                    "ignore_revlogs_before_date": "2024-01-02",
                    "deck": 'Medical_A* "A"',
                    "search": "tag:extra",
                    "first_grade": 1,
                    "include_same_day_reviews": False,
                }
            ],
            "rules": [
                {
                    "search": " tag:medical ",
                    "preset_id": "addon:test:medical",
                }
            ],
        }
    )

    assert config.to_overlay_dict() == {
        "presets": [
            {
                "id": "addon:test:medical",
                "name": "Medical",
                "fsrs_version": "six",
                "params": [1.0, 2.5],
                "desired_retention": 0.9,
                "historical_retention": 0.8,
                "ignore_revlogs_before_date": "2024-01-02",
            }
        ],
        "rules": [
            {
                "search": 'deck:"Medical\\_A\\* \\"A\\"" firstgrade:1 tag:extra',
                "preset_id": "addon:test:medical",
            },
            {
                "search": "tag:medical",
                "preset_id": "addon:test:medical",
            }
        ],
    }
    assert config.presets[0].include_same_day_reviews is False


def test_load_config_converts_dynamic_dr_policy_to_overlay_dict():
    config = load_config(
        {
            "presets": [
                {
                    "id": "addon:test:medical",
                    "name": "Medical",
                    "fsrs_version": "seven",
                    "params": [1.0],
                    "desired_retention": 0.9,
                    "historical_retention": 0.8,
                    "fsrs_dynamic_desired_retention_enabled": True,
                    "fsrs_dynamic_desired_retention_review_limit": 123,
                    "fsrs_dynamic_desired_retention_max_cost_perday_minutes": 45.0,
                    "fsrs_dynamic_desired_retention_params": [0.0] * 15,
                    "fsrs_dynamic_desired_retention_weights": [0.0, 15.0],
                    "fsrs_dynamic_desired_retention_avg_drs": [0.9, 0.8],
                    "fsrs_dynamic_desired_retention_fsrs_eq_weights": [0.0, 15.0],
                    "fsrs_dynamic_desired_retention_fsrs_eq_drs": [0.91, 0.81],
                    "fsrs_dynamic_desired_retention_min": 0.3,
                    "fsrs_dynamic_desired_retention_max": 0.995,
                }
            ],
            "rules": [],
        }
    )

    preset = config.to_overlay_dict()["presets"][0]
    assert preset["fsrs_dynamic_desired_retention_enabled"] is True
    assert preset["fsrs_dynamic_desired_retention_params"] == [0.0] * 15
    assert preset["fsrs_dynamic_desired_retention_weights"] == [0.0, 15.0]
    assert preset["fsrs_dynamic_desired_retention_avg_drs"] == [0.9, 0.8]
    assert preset["fsrs_dynamic_desired_retention_fsrs_eq_weights"] == [0.0, 15.0]
    assert preset["fsrs_dynamic_desired_retention_fsrs_eq_drs"] == [0.91, 0.81]
    assert preset["fsrs_dynamic_desired_retention_min"] == 0.3
    assert preset["fsrs_dynamic_desired_retention_max"] == 0.995
    assert "fsrs_dynamic_desired_retention_review_limit" not in preset
    assert "fsrs_dynamic_desired_retention_max_cost_perday_minutes" not in preset
    assert config.presets[0].fsrs_dynamic_desired_retention_review_limit == 123
    assert (
        config.presets[0].fsrs_dynamic_desired_retention_max_cost_perday_minutes
        == 45.0
    )


def test_load_config_keeps_enabled_dynamic_dr_without_policy_out_of_overlay():
    config = load_config(
        {
            "presets": [
                {
                    "id": "addon:test:medical",
                    "name": "Medical",
                    "fsrs_version": "seven",
                    "params": [1.0],
                    "desired_retention": 0.9,
                    "historical_retention": 0.8,
                    "fsrs_dynamic_desired_retention_enabled": True,
                }
            ],
            "rules": [],
        }
    )

    assert config.presets[0].fsrs_dynamic_desired_retention_enabled is True
    assert "fsrs_dynamic_desired_retention_enabled" not in config.to_overlay_dict()["presets"][0]


def test_load_config_rejects_invalid_dynamic_dr_simulator_limits():
    with pytest.raises(ConfigError, match="review_limit.*positive"):
        load_config(
            {
                "presets": [
                    {
                        "id": "addon:test:medical",
                        "name": "Medical",
                        "fsrs_version": "seven",
                        "params": [1.0],
                        "desired_retention": 0.9,
                        "historical_retention": 0.8,
                        "fsrs_dynamic_desired_retention_review_limit": 0,
                    }
                ],
                "rules": [],
            }
        )

    with pytest.raises(ConfigError, match="max_cost_perday_minutes.*positive"):
        load_config(
            {
                "presets": [
                    {
                        "id": "addon:test:medical",
                        "name": "Medical",
                        "fsrs_version": "seven",
                        "params": [1.0],
                        "desired_retention": 0.9,
                        "historical_retention": 0.8,
                        "fsrs_dynamic_desired_retention_max_cost_perday_minutes": 0,
                    }
                ],
                "rules": [],
            }
        )


def test_load_config_rejects_unknown_rule_preset():
    with pytest.raises(ConfigError, match="unknown preset"):
        load_config(
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
                        "preset_id": "addon:test:missing",
                    }
                ],
            }
        )


def test_load_config_without_preset_deck_does_not_add_rule():
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
            "rules": [],
        }
    )

    assert config.to_overlay_dict()["rules"] == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("desired_retention", 1.2),
        ("historical_retention", 0),
    ],
)
def test_load_config_rejects_invalid_retention(field: str, value: float):
    preset = {
        "id": "addon:test:medical",
        "name": "Medical",
        "fsrs_version": "six",
        "params": [1.0],
        "desired_retention": 0.9,
        "historical_retention": 0.8,
    }
    preset[field] = value

    with pytest.raises(ConfigError, match=field):
        load_config({"presets": [preset], "rules": []})


def test_load_config_rejects_non_addon_preset_id():
    with pytest.raises(ConfigError, match="addon:"):
        load_config(
            {
                "presets": [
                    {
                        "id": "deck-config:1",
                        "name": "Medical",
                        "fsrs_version": "six",
                        "params": [1.0],
                        "desired_retention": 0.9,
                        "historical_retention": 0.8,
                    }
                ],
                "rules": [],
            }
        )


def test_load_config_rejects_invalid_same_day_flag():
    with pytest.raises(ConfigError, match="include_same_day_reviews"):
        load_config(
            {
                "presets": [
                    {
                        "id": "addon:test:medical",
                        "name": "Medical",
                        "fsrs_version": "seven",
                        "params": [1.0],
                        "desired_retention": 0.9,
                        "historical_retention": 0.8,
                        "include_same_day_reviews": "false",
                    }
                ],
                "rules": [],
            }
        )
