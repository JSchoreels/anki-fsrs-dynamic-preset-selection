# Data

This add-on reads its local add-on config through Anki's add-on manager and
writes one synced collection config entry:

- key: `fsrsPresetOverlay`
- value: object containing `presets` and `rules`

The add-on never writes deck configs or card rows directly. Anki core validates
the overlay before storing it, including FSRS params, search syntax, forbidden
FSRS metric properties in rules, and rule references to missing presets.

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
value and updates `params` in the dialog's draft add-on config only. Optimize
All sends one batch optimizer request to Anki core with each draft preset's
generated search, current params, FSRS version, relearning step count, and
same-day review training flag. Anki core reads review logs for those searches
and returns optimized params per preset; the add-on stores them only in the
dialog draft until the user saves. The updated params are written to the local
add-on config and then to `fsrsPresetOverlay` only when the user saves the
dialog.

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
