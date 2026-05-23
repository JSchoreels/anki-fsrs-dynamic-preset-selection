# Agent Notes

This add-on has two common maintenance traps:

- Anki loads the installed add-on from
  `/Users/jschoreels/Library/Application Support/Anki2/addons21/1885246001`.
  The source repo is
  `/Users/jschoreels/workspace/anki-fsrs-dynamic-preset-selection`. After
  editing source files, run `./sync_to_anki.sh` and reload or restart Anki
  before expecting the app to use them. Do not edit the installed add-on folder
  directly.
- `collection.decks.config_dict_for_deck_id()` returns Anki's legacy deck
  config dict. Extra deck-option fields stored in Rust as `DeckConfig.inner.other`
  are flattened into the top-level Python dict. For example, read
  `config["fsrs7IncludeSameDayOptimize"]`, not
  `config["other"]["fsrs7IncludeSameDayOptimize"]`.
- FSRS-7 same-day optimize is stored on add-on presets as
  `include_same_day_reviews`. The selected deck's option is only a migration
  default for older presets where that field is missing.

See `docs/DATA.MD` before changing code that reads or writes Anki config data.
