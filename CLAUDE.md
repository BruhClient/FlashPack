# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PyQt6 desktop flashcard app (repo name FlashPack; window title "Flashcards"; Qt application and data-folder name "Flagship"). It has a class → chapter → card hierarchy, 1–5 confidence ratings, SM-2-style scheduling, local SQLite storage, and `.flashpack` export/import. README.md documents user-facing behaviour: the scheduling rules, card statuses, keyboard shortcuts and data location.

## Commands

```bash
pip install -r requirements.txt                 # PyQt6 is the only runtime dependency
python main.py                                  # run the app
python -m pytest                                # all tests (pytest.ini sets pythonpath=. and testpaths=tests)
python -m pytest tests/test_scheduler.py -k ease   # a subset; or tests/test_db.py::test_rename_class_and_chapter
```

No linter or formatter is configured.

- **Use throwaway data.** Set `FLAGSHIP_DATA_DIR` to a scratch folder when running the app for testing. The default is Qt's `AppDataLocation` (`%APPDATA%\Flagship` on Windows), which holds the owner's real cards.
- **UI changes need visual checks.** The tests don't cover `flashcards/ui/`, so check UI changes by rendering them headless:
  - Set `QT_QPA_PLATFORM=offscreen`. On Windows, also set `QT_QPA_FONTDIR=C:/Windows/Fonts`, or text renders without fonts.
  - Save screenshots with `widget.grab().save(path)`.
  - Check both themes: `theme.install(app, "light", persist=False)`, then `theme.manager().set_theme("dark")`.

## Architecture

There are two layers:

- **`flashcards/*.py`** is plain Python with no Qt imports: `models`, `db`, `scheduler`, `stats`, `media` and `transfer`. This is the layer the tests cover, so keep Qt out of it.
- **`flashcards/ui/`** holds the PyQt6 widgets.

### Data model

- Timestamps are ISO-8601 UTC strings (`models.to_iso` / `from_iso` / `utcnow`).
- A card is new (untested) while `due_at` is NULL.
- There are no status columns. The statuses (untested, struggling, learning, mastered) and the mastery scores are derived in `stats.py` from the scheduling fields.
- `db.CARD_COLUMNS` is the single list of card columns. It drives the SELECTs (rows become `Card(**row)`) and `transfer.py` export/import. A new card field means updating the `cards` table in `db.SCHEMA`, `CARD_COLUMNS` and the `Card` dataclass together.
- There is no migration step. The schema is applied with `CREATE TABLE IF NOT EXISTS`, and `PRAGMA user_version` is written but never read. Any schema change therefore needs an explicit migration for existing databases.
- Foreign keys cascade: class → chapters → cards → reviews. Moving a card only changes `chapter_id`, so it keeps its schedule and review history.

### Card HTML and images

- **Storage:** card sides are stored as Qt rich-text HTML.
- **Image references:** images are saved as `<data dir>/media/<uuid>.png` and referenced relatively as `media/<name>`.
- **Loading images:** `RichTextEdit` and `CardViewer` set the document base URL to the data dir and override `loadResource`. That goes through `media.resolve`, which matches the `media/<name>` suffix of whatever URL Qt passes in.
- **Orphan cleanup:** at startup, `media.cleanup_orphans` deletes every media file not referenced in `db.all_card_html()`, which reads only the cards' front and back HTML. If images are ever stored anywhere else, add that place to the scan, or its images will be deleted.
- **Fonts in stored HTML:** `toHtml()` bakes the editor's font family and size into `<body style>`. `rich_text.without_body_font` strips them on load, so the widget's font (the reading serif) applies.

### Scheduling flow

1. `scheduler.build_session` fills a test in order: due cards by `priority`, then new cards, then not-yet-due cards with the lowest `recall_probability`.
2. `StudySession` is the in-test queue. A rating of 2 or lower puts the card back 3–5 positions later.
3. `apply_rating(..., first_in_session)` computes the new schedule. Only a card's first rating in a session changes its ease and lapse count.
4. `TestSessionView` saves each rating with `db.record_review`, which updates the card and inserts a `reviews` row. Those rows feed the dashboard's activity chart.

### Export and import (`transfer.py`)

- A `.flashpack` is a zip holding `data.json` (checked against `format` and `schema_version`) plus `media/`.
- Import remaps every ID.
- Only media files with safe names are extracted (`media.is_safe_name`).
- Merge mode renames clashing class names.
- Replace mode first exports a backup to `<data dir>/backups/`.

### UI wiring

- **Layout:** `MainWindow` is a `Sidebar` plus a `FadeStack` of pages: a welcome `EmptyState`, `ClassDashboard`, `ChapterView` and `TestSessionView`.
- **Navigation:** the sidebar tree drives it, through `class_selected` and `chapter_selected`.
- **Menus:** the rename, reorder, move and delete menus are built only in `Sidebar` (`build_class_menu`, `build_chapter_menu`). The pages' ⋯ buttons get them through a `menu_builder` callback that `MainWindow` assigns.
- **Refreshing:** pages emit `changed` or `renamed`, which triggers `sidebar.refresh()`. Sidebar edits emit `structure_changed`, which triggers `MainWindow._refresh_current()`.
- **Charts:** they are hand-painted `charts._Chart` subclasses, which provide a grow-in animation, hover tooltips and click-to-open. Status colours come from `charts.status_color`, and segments are drawn in `charts.ORDER` (best status first).

### Theming

- **Tokens:** `theme.LIGHT` and `theme.DARK` must keep identical keys. `style.qss` is a `string.Template` filled with `safe_substitute`, so a missing or misspelt `$token` silently produces invalid QSS. Check both themes after touching either file.
- **Colours:** read them at paint time with `theme.color(key)` and never hard-code them. Widgets that cache theme-dependent values should connect to `theme.manager().changed`.
- **Icons:** they are inline SVG paths in `icons.PATHS`.
  - `icons.apply(widget, name, color_key)` registers the widget, so its icon is recoloured on theme change.
  - `icons.icon()` and `icons.pixmap()` are one-off and won't update. The sidebar works around this by rebuilding itself on theme change.
- **Fonts:** controls use Segoe UI. The serif is for titles, big numbers and card text: `theme.serif_font()` in code, `$serif` in QSS (Sitka on Windows).
- **Shared helpers:** build UI from these rather than raw widgets:
  - `dialogs`: `button`, `icon_button`, `more_button`, `ask_text`, `confirm`, `alert`, `hairline`, `EditableTitle`, `SearchField`, `FadeDialog`.
  - `animations`: `crossfade`, `fade_in`, `count_up`, `glide`.
  - `Toast` for confirmations.

## Visual direction

The owner rejected a generic "AI-generated" look: indigo accent, Inter font, icons in tinted squares, pill chips, rounded boxed panels everywhere, donut charts. The current style is "paper & ink":

- warm neutrals, with ink as the only UI accent (primary buttons are black in light mode and paper-coloured in dark mode);
- sections separated by headings and hairlines instead of boxes;
- earthy status colours;
- index-card motifs (card-shaped tiles, the red rule on the study card).

Use icons for actions, not decoration, and keep on-screen hint text minimal.
