# Configuration

## `presets`

List of FSRS presets provided by this add-on. Each preset is written into
Anki's synced `fsrsPresetOverlay` config.

- `id`: stable id starting with `addon:`
- `name`: display name
- `fsrs_version`: one of `seven`, `six`, `five`, or `four`
- `params`: FSRS parameter array
- `desired_retention`: base desired retention, greater than 0 and at most 1
- `historical_retention`: historical retention, greater than 0 and at most 1
- `deck`: optional deck name selected in the add-on config UI
- `search`: optional Anki search filter such as `firstgrade:1`
- `first_grade`: optional first answer button, `1`, `2`, `3`, or `4`
- `include_same_day_reviews`: optional FSRS-7 optimize flag edited by the
  Same-day Reviews checkbox. When present, optimization uses this value instead
  of reading the selected deck option.
- `fsrs_dynamic_desired_retention_enabled`: optional FSRS-7 ADR flag edited by
  the ADR checkbox. When enabled, optimization asks Anki core to train native
  Dynamic DR policy data for the preset.
- `fsrs_dynamic_desired_retention_clamp`: optional FSRS-7 ADR scheduling flag
  edited by the ADR Clamp checkbox. When enabled, requested Dynamic DR targets
  outside the supported calibration range are clamped to the nearest supported
  target instead of using fixed FSRS DR.
- `fsrs_dynamic_desired_retention_review_limit`: optional positive integer
  review limit used by the ADR training simulator. Defaults to `9999`.
- `fsrs_dynamic_desired_retention_max_cost_perday_minutes`: optional positive
  daily time budget, in minutes, used by the ADR training simulator. Defaults
  to `720`.
- `fsrs_dynamic_desired_retention_params`, `weights`, `avg_drs`,
  `fsrs_eq_weights`, `fsrs_eq_drs`, `min`, and `max`: native Dynamic DR policy
  and calibration data returned by Anki core. The dialog shows the valid target
  average DR range from `avg_drs`; visualization can use `fsrs_eq_*` to map the
  table's fixed-FSRS DR to the ADR cost weight.

## `rules`

Ordered list of card selection rules.

- `search`: Anki search query used to find matching cards
- `preset_id`: id of a preset defined in `presets`

Preset-level `deck` and `search` values are converted into combined rules
before these advanced rules are appended to the overlay.
If `first_grade` is present, it is inserted between deck and search, producing
queries in the form `deck:"..." firstgrade:N <search>`.
The dialog's Move Up and Move Down buttons change the stored preset order, which
changes generated rule precedence.

The config dialog reads card ids with Anki search to display draft counts. The
per-preset count follows Anki's ordered rule behavior, so a card matching
multiple rules is counted for the first matching preset only. The deck summary
counts cards in each normal deck and subtracts cards selected by any generated
or advanced rule. Its non-new column subtracts `is:new` cards from the
unselected cards.

The dialog can optimize one preset row or optimize all visible preset rows.
Optimization uses each row's `include_same_day_reviews` value and updates each
preset's `params` value in the draft config. If ADR is enabled for a row,
optimization also stores native Dynamic DR policy and calibration output and
shows the valid target average DR range. Save is still required to persist those
new values to the add-on config. The Visualize ADR action opens the selected
row's trained ADR curve with a temporary DR selector; pressing Save DR in that
window copies the selected value back to the row's `desired_retention` field.

Anki core rejects rule searches that use `prop:r`, `prop:s`, or `prop:d`,
because those values depend on FSRS preset resolution.
