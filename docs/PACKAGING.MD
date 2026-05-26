# Packaging

Run:

```sh
./package.sh
```

The script writes `dist/fsrs-dynamic-preset-selection.ankiaddon`.

## Local Anki Sync

Run:

```sh
./sync_to_anki.sh
```

The script copies runtime files from the source repo into Anki's installed
add-on directory at
`/Users/jschoreels/Library/Application Support/Anki2/addons21/1798968356`.
It does not remove Anki-owned files such as `meta.json`.
