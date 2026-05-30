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
It preserves Anki-owned files such as `meta.json`. If `meta.json` is missing
display metadata, the script seeds the add-on name, homepage, and human version
from `manifest.json` so the local add-on manager does not display only the
numeric package id.
