# TODO: Installer folder-picker fix (app dir vs data dir confusion)

## Context
Two folder pickers in the installer let users pick mismatched paths:
- `wpSelectDir` (standard Inno) — `{app}` install location (default: `{autopf}\KTHEALTHERP`)
- `DataFolderPage` (custom) — data folder (was: `{commonappdata}\KTHEALTHERP\data`)

User chose **Option 2: auto-link the two**. The data folder default tracks `{app}\data` so picking the install location automatically determines the data location. User can still override on DataFolderPage.

## License inspect extraction
- [x] Already done — `app/services/license_inspect.py` exists; `license_service.py:11–23` re-exports the pure helpers. No action needed.

## Installer changes (`installer/installer.iss`)
- [x] Add `LastAutoDataDir: String` global to remember the auto-populated value.
- [x] In `CreateDataFolderPage`, change the three default texts so they are populated lazily (initialize empty; real value set on page entry once `{app}` is known).
- [x] In `CurPageChanged(DataFolderPage.ID)`: compute `Default := ExpandConstant('{app}\data')`. For each of the three data-dir edits, if current text is empty OR equals `LastAutoDataDir`, replace it with `Default`. Then set `LastAutoDataDir := Default`.
- [x] Update the explanatory `LblDataIntro.Caption` to mention the data folder defaults to `<install folder>\data`.
- [x] Browse buttons + manual editing left intact so users can override.

## Verify
- [x] No other code path resets the text (only NextButtonClick's `StripTrailingSlash` normalisation, which is fine).
- [x] `NextButtonClick(DataFolderPage)` still validates non-empty + writable via `check-writable`.
