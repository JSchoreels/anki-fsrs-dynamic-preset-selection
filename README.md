# FSRS Dynamic Preset Selection

Anki add-on that maps cards to add-on-defined FSRS presets using ordered search
rules. The add-on writes Anki's synced `fsrsPresetOverlay` collection config and
lets Anki core resolve the effective FSRS preset during scheduling, search,
browser, and stats operations.

This add-on requires an Anki build that exposes:

- `Collection.set_fsrs_preset_overlay()`
- `anki.collection.FsrsPresetOverlay`

## Configuration

The add-on config contains add-on FSRS presets and ordered rules:

```json
{
  "presets": [
    {
      "id": "addon:example:medical",
      "name": "Medical",
      "fsrs_version": "seven",
      "params": [],
      "desired_retention": 0.9,
      "historical_retention": 0.9,
      "deck": "Medical",
      "search": "firstgrade:1"
    }
  ],
  "rules": [
    {
      "search": "tag:medical",
      "preset_id": "addon:example:medical"
    }
  ]
}
```

The add-on config screen edits the preset list directly. If a preset has a
deck selected and/or a search filter, the add-on writes one combined rule like
`deck:"Medical" firstgrade:1` before the advanced `rules` entries. Preset ids
are generated from the preset name. Use Move Up and Move Down in the dialog to
change preset precedence.

The config screen can refresh card counts for the current draft rules. Each
preset row shows how many cards its generated query selects. The deck summary
below the preset table shows, for every normal deck, how many cards are not
selected by any generated or advanced rule. It also shows the same unselected
count with `is:new` cards removed.

Use the Same-day Reviews checkbox on an FSRS-7 preset row to control whether
same-day reviews are included when optimizing that preset. Use Optimize on an
individual preset row to recompute only that preset's parameters. Use Optimize
All to recompute every visible preset row in current order. While optimization
is running, each row's optimize button is replaced by a progress bar: pending
rows show Pending, the active row shows Optimizing, and completed rows show
Done. The active row is filled from Anki's backend optimizer progress.

For the common first-answer split workflow, check **Split** on a preset row.
The row is replaced with four grade rows for Again, Hard, Good, and Easy. They
inherit the row's name, deck, and search filter, but keep separate desired
retention, same-day optimize, and parameter values. Their generated queries are ordered as
`deck:"..." firstgrade:N <search>`.

Rules are evaluated by Anki core in order. The first matching rule assigns the
card's FSRS preset. Cards that do not match any rule use their deck-config FSRS
preset.

## Development

Anki loads the installed add-on from
`~/Library/Application Support/Anki2/addons21/1885246001`, not directly from
this source repo. Copy changed runtime files into that folder and reload or
restart Anki before testing in the app.

When reading deck options through `collection.decks.config_dict_for_deck_id()`,
remember that Anki returns a legacy Python dict. Extra deck-option fields stored
in Rust as `DeckConfig.inner.other` are flattened into the top level, so
`fsrs7IncludeSameDayOptimize` is read as `config["fsrs7IncludeSameDayOptimize"]`.
This add-on stores the FSRS-7 same-day optimize choice on each add-on preset;
the deck option is only used to initialize older presets that do not yet have
the field.

Run tests with:

```sh
python3 -m pytest
```
