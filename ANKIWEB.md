# FSRS Dynamic Preset Selection

FSRS Dynamic Preset Selection lets you choose FSRS parameters by card search
rules instead of only by deck preset assignment.

With normal Anki, a card gets its FSRS parameters from the deck preset attached
to its deck. This add-on lets you define extra FSRS presets in the add-on
configuration, then assign them to cards with ordered Anki searches. During
review, Anki uses the first matching dynamic preset for the card. Cards that do
not match any dynamic rule keep using their normal deck preset.

## Requirements

This add-on requires an Anki build that supports dynamic FSRS preset overlays.
It will not work on standard Anki releases that do not expose this FSRS overlay
API.

## What It Is For

Use this add-on when cards in the same deck should use different FSRS
parameters. Common examples:

- separate FSRS parameters for cards created from different sources
- different parameters for first-answer outcomes such as first `Again`,
  `Hard`, `Good`, or `Easy`
- one deck organization, but several scheduling profiles selected by tags,
  note fields, or other Anki search terms

The add-on does not move cards between decks and does not change deck options.
It only provides card-specific FSRS preset selection to Anki.

## Basic Usage

1. Open Anki's add-on manager.
2. Select `FSRS Dynamic Preset Selection`.
3. Open `Config`.
4. Add one or more dynamic FSRS presets.
5. Choose a deck and optional search filter for each preset.
6. Move presets up or down to set precedence.
7. Save the configuration.

Rules are evaluated from top to bottom. If a card matches multiple presets, the
first matching preset wins.

## Presets And Rules

Each dynamic preset has:

- a display name
- an FSRS version
- FSRS parameters
- desired retention and historical retention
- an optional deck
- an optional search filter

The deck and search filter are combined into an Anki search rule. For example,
a preset with deck `Japanese` and search `tag:yomitan` applies to cards matching
both terms.

Advanced users can also define explicit ordered rules in the JSON config. Each
rule maps an Anki search query to one dynamic preset id.

## First-Answer Split

The `Split` checkbox creates four related preset rows for first `Again`,
`Hard`, `Good`, and `Easy` outcomes. This is useful when you want separate FSRS
parameters based on the first grade a card received.

Each split row keeps its own parameters and desired retention. The generated
rules use Anki's `firstgrade:N` search term.

## Optimizing Parameters

The config screen can optimize one dynamic preset or all visible dynamic
presets.

Optimization updates the draft parameters shown in the dialog. You still need
to save the add-on configuration for those parameters to be written to Anki's
dynamic FSRS overlay.

For FSRS-7 presets, the `Same-day Reviews` checkbox controls whether same-day
reviews are included during optimization for that preset.

## Checking Which Preset Matched

In Card Info, the add-on can show the dynamic FSRS preset that matched the card
and the rule that selected it. This is display-only information to help verify
your configuration.

If no dynamic rule matches, the card uses its normal deck preset.

## Important Notes

- Search rule order matters.
- Cards can stay in their current decks.
- Dynamic presets are stored in Anki's synced collection configuration.
- Add-on UI preferences and draft configuration are local until saved.
- Searches using FSRS metric properties such as `prop:r`, `prop:s`, or `prop:d`
  are rejected for dynamic preset rules, because those values depend on the
  selected FSRS preset.

## Troubleshooting

If a card does not use the expected preset:

- check the Card Info dynamic preset rows
- confirm the card matches the generated Anki search
- move the intended preset above broader matching presets
- check that the add-on configuration was saved
- confirm you are running a compatible Anki build

If optimization does not produce useful parameters, check that the preset search
matches enough reviewed cards for FSRS optimization.
