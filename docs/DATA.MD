# Data

This add-on reads its local add-on config through Anki's add-on manager,
writes one synced collection config entry, and rewrites selected card FSRS data
after optimization:

- key: `fsrsPresetOverlay`
- value: object containing `presets` and `rules`

The add-on never writes deck configs. Outside the post-optimize memory-state
rewrite described below, it does not write card rows directly. Anki core
validates the overlay before storing it, including FSRS params, search syntax,
forbidden FSRS metric properties in rules, and rule references to missing
presets.

The add-on config may store preset-level `deck` and `search` values. These
values are local add-on config only; before writing `fsrsPresetOverlay`, the
add-on converts them into a regular ordered rule such as
`deck:"Medical" firstgrade:1` with the preset id. These generated rules are
written before explicit advanced `rules`. The config dialog preserves preset
order, and Move Up / Move Down changes that stored order. Because Anki core
uses the first matching rule, moving presets changes precedence.

The add-on config may also store `first_grade` on presets. The dialog's
first-grade split checkbox creates four normal preset entries with
`first_grade` values `1` through `4`; each generated entry keeps its own
desired retention and parameter array. Rule generation always orders the terms
as deck, first grade, then the free-form search filter.

For FSRS-7 presets, the add-on config may store `include_same_day_reviews`.
This is an add-on optimization setting and is not written into
`fsrsPresetOverlay`, because Anki core does not use it for review-time preset
resolution. If the field is missing, the optimizer reads the selected deck's
legacy deck config once for backward compatibility.

For FSRS-7 presets, the add-on config may also store native Dynamic DR policy
data under `fsrs_dynamic_desired_retention_*`. The dialog writes the ADR enabled
flag from the ADR checkbox, writes the ADR clamp flag from the ADR Clamp
checkbox, and stores the policy/calibration fields returned by Anki core
optimization. `fsrsPresetOverlay` includes those ADR fields only when the preset
is enabled and has complete policy data. The dialog displays the valid target
average DR range from the stored calibration average DRs and the FSRS-equivalent
DR range from the stored FSRS-equivalent calibration DRs. Saving is blocked when
a preset has ADR enabled but has not been optimized yet.
The add-on config also stores ADR training simulator overrides:
`fsrs_dynamic_desired_retention_review_limit` and
`fsrs_dynamic_desired_retention_max_cost_perday_minutes`. These values are sent
to optimization only; they are not written into `fsrsPresetOverlay` because
review-time scheduling uses the trained policy/calibration output instead.

After single optimize or Optimize All finishes applying optimized params and
ADR policy data to the dialog draft, the dialog applies that optimized draft to
`fsrsPresetOverlay`, then rewrites memory states for the optimized preset or
presets. This happens as the post-optimize step, not when the dialog is saved
and not when the raw add-on config is updated. The rewrite adds `-is:new` to
each optimized preset's effective first-match search, asks Anki core to compute
each card's memory state with the newly applied overlay, and writes only the
card FSRS data fields: `memory_state`, `desired_retention`, and `decay`. It
uses batched `Collection.update_cards(..., skip_undo_entry=True)` calls and
does not update due dates, intervals, queues, or review-log rows. For native
Dynamic DR, the memory state is reconstructed from the actual review history by
Anki core; the stored desired-retention field follows Anki's
`compute_memory_state()` output until the next review stores the chosen
answer's Dynamic DR value.

Because Anki computes memory states against the collection's current overlay,
the post-optimize rewrite writes the optimized draft overlay before the dialog's
local add-on config is saved. Saving the dialog persists that same draft to the
local add-on config and applies the overlay again, but it does not rewrite
memory states. Canceling the dialog does not persist the local add-on config;
the next collection load or config update reapplies the saved config overlay.

The config dialog derives add-on preset ids from preset names. It stores the
derived ids in the add-on config and writes them to `fsrsPresetOverlay`, but the
dialog does not expose ids as editable data.

The config dialog also reads card ids through Anki search to display draft
counts. Per-preset counts read ordered generated and advanced rules, assigning a
card to the first matching preset only. The deck summary reads all normal deck
names, searches each deck, then subtracts the union of cards selected by
generated and advanced rules. The non-new deck summary column reads `is:new`
once and excludes those card ids from the unselected count. These count reads
do not write collection data.

Optimizing one preset reads that draft preset's `include_same_day_reviews`
value. The optimizer result first updates `params` and ADR policy data in the
dialog draft, then the post-optimize step above applies the optimized draft
overlay and rewrites matching memory states. If another single-preset Optimize
button is clicked while one is already running, the row is marked pending and
queued. Queued single-preset optimizations run one at a time. During the
optimizer phase, a row-local timer reads backend progress updates without
opening Anki's global progress popup, then drives the row progress bar with FSRS
optimization percentage and ADR training stage text. During the post-optimize
rewrite phase, the row progress bar switches to rewritten-card counts.
Optimization completion does not refresh card counts, because optimization
changes parameters and ADR policy data, not preset searches or rule membership.
Single optimize and Optimize All
both build the draft ordered rule list first, then send an effective search for
each preset: every rule that assigns that preset, with all earlier rules
subtracted, matching Anki core's first-match scheduling semantics. Optimize All
sends one batch optimizer request to Anki core with each draft preset's
effective search, current params, FSRS version, relearning step count, same-day
review training flag, ADR enabled flag, and ADR simulator limit overrides. Anki core
reads review logs for those searches and returns optimized params per preset.
When ADR is enabled, Anki core also returns ADR policy params, calibration
weights, calibration average DRs, FSRS-equivalent DR calibration pairs, and
retention bounds. The average-DR calibration weights returned by Anki core are
simulation-backed bisection results against average ADR DR targets; the
FSRS-equivalent calibration maps the table's fixed-FSRS DR to the ADR cost
weight used by review scheduling and visualization. The add-on stores those
values in the dialog draft, immediately applies the optimized draft overlay for
the post-optimize memory-state rewrite, and writes the values to the local
add-on config only when the user saves the dialog.

The config dialog's ADR visualizer reads the selected row's draft ADR policy,
calibration, retention bounds, and desired retention. Moving the DR control in
the visualizer only changes the temporary plotted cost weight. Pressing
`Save DR` writes the visualizer's target back to the selected row's
`desired_retention` spinbox; the add-on config is unchanged, and the collection
overlay is not updated by Save DR until the main config dialog is saved or
another optimize step applies the draft overlay.

When optimizing a preset, the add-on reads the selected deck's legacy deck
config dict with `collection.decks.config_dict_for_deck_id()` only when
`include_same_day_reviews` is missing from the add-on preset. That dict is not
shaped like the Rust `DeckConfig` struct: fields stored in
`DeckConfig.inner.other` are flattened into the top-level Python dict by Anki's
schema 11 conversion. For FSRS-7 same-day optimization, read
`config["fsrs7IncludeSameDayOptimize"]`. Do not assume the value is under
`config["other"]`.

When the add-on config changes or a collection is loaded, the add-on rewrites
`fsrsPresetOverlay` from the current add-on config. Removing all presets and
rules from the add-on config writes an empty overlay.

## Card Info Read

When Anki provides the `card_info_will_add_rows` GUI hook, the add-on evaluates
the current ordered generated and advanced rules for the Card Info card and
appends display-only rows for the dynamic FSRS preset match. This reads search
results for each rule combined with `cid:<card id>`. It does not create, update,
or delete collection data.

When the matched preset has a desired retention, Card Info also asks Anki's
scheduler for fresh scheduling states with a desired-retention override. If the
Dynamic Desired Retention add-on API is available, this add-on first asks it for
the effective desired retention, using the matched preset's desired retention as
the current value. This keeps the Card Info ADR mapping aligned with the
review-time desired-retention override. If Anki exposes native Dynamic DR
scheduling-state data, the add-on displays an `Effective Dynamic DR Scheduling`
row. When native Dynamic DR is active, the row maps the effective desired
retention to Again, Hard, Good, and Easy ADR values. If Anki reports Dynamic DR
is enabled but returns no mapping, Card Info displays that the effective desired
retention uses fixed FSRS DR. Older Anki builds without these scheduling-state
fields skip the extra row. When the matched preset has Dynamic DR policy data,
Card Info also displays the supported average ADR range and the supported
fixed-FSRS-equivalent DR range read from the preset calibration arrays.
