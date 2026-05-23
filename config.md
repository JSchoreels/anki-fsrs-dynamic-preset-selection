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
preset's `params` value in the draft config. Save is still required to persist
those new params to the add-on config.

Anki core rejects rule searches that use `prop:r`, `prop:s`, or `prop:d`,
because those values depend on FSRS preset resolution.
