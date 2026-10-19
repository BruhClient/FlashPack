# Flashcards

A desktop flashcard app in the spirit of Anki, built with PyQt6. Cards are organised as
**class → chapter → card**. After each answer you rate your confidence from 1 to 5, and a
spaced-repetition scheduler uses those ratings to pick what to test next. Everything is
stored locally, and you can export it to a single file to move it to another device.

## Features

- **Rich cards.** Both sides support bold, italic, underline, strikethrough, headings,
  lists, text colours, highlights and images (paste, drag in or insert).
- **Confidence ratings.** Rate each answer: 1 No idea, 2 Barely, 3 Unsure, 4 Good,
  5 Perfect.
- **Smart tests.** Start a test from a class and choose its chapters. Due and weak cards
  come first, then untested ones. Cards you miss come back later in the same session.
- **Class dashboard.** Shows mastery, cards due today, untested cards, each chapter's
  status mix, every card as a coloured tile, and reviews over the last 30 days. Hover for
  details; click a chapter to open it.
- **Easy to reorganise.**
  - Drag cards onto a chapter in the sidebar, or use Move.
  - Move chapters between classes and reorder them.
  - Rename anything inline.
- **Light and dark themes.** It follows your system setting until you pick one.
- **Local and portable.** One SQLite database plus an image folder; export and import
  through `.flashpack` files.

## Getting started

You need Python 3.10 or newer (developed on 3.12).

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python main.py
```

### First steps

1. Click **+** next to *Classes* in the sidebar to create a class.
2. Open the class and click **Chapter** to add chapters.
3. Select a chapter and click **Add card**. Use *Save & add another* to enter several in
   a row.
4. Go back to the class and click **Start test**. Pick the chapters and the session size,
   then go.
5. Press Space to reveal the answer, then 1–5 to rate it.

To rename a class or chapter, click its title on its page, or double-click it in the
sidebar (or press F2). Use the **⋯** buttons for everything else.

## Keyboard shortcuts

| Where        | Keys                         | Action                       |
|--------------|------------------------------|------------------------------|
| Anywhere     | Ctrl+Shift+N                 | New class                    |
|              | Ctrl+E / Ctrl+I              | Export / import data         |
|              | Ctrl+Shift+L                 | Toggle light / dark          |
|              | Ctrl+Q                       | Quit                         |
| Sidebar      | F2 or double-click           | Rename                       |
| Chapter page | Ctrl+N                       | Add card                     |
|              | Ctrl+F                       | Search cards                 |
|              | Enter / Delete               | Edit / delete selected cards |
| Card editor  | Ctrl+Enter                   | Save                         |
|              | Ctrl+Shift+Enter             | Save and add another         |
|              | Ctrl+B / I / U               | Bold / italic / underline    |
|              | Ctrl+Shift+X                 | Strikethrough                |
|              | Ctrl+Shift+8 / Ctrl+Shift+7  | Bulleted / numbered list     |
|              | Ctrl+\\                      | Clear formatting             |
| Test         | Space or Enter               | Show answer                  |
|              | 1–5                          | Rate                         |
|              | Esc                          | End the test                 |

## How cards are chosen

Scheduling is a variant of SM-2, adapted to the 1–5 scale (`flashcards/scheduler.py`).

- **Rated 1–2 (missed).** The card is due again in 10 minutes and returns 3–5 cards
  later in the current test, until you rate it 3 or higher.
- **Rated 3–5.** The next review is 1 day away, then 3 days (6 if you rated it 4–5), then
  the previous interval × the card's *ease*. A 3 shortens that interval (×0.8) and a 5
  lengthens it (×1.3).
- **Ease.** Starts at 2.5. A 5 raises it, a 4 keeps it, and 3 or lower reduces it, never
  below 1.3. Only a card's first rating in a test changes its ease.

When you start a test, the session is filled in this order:

1. **Due cards**, most urgent first. Urgency combines how overdue a card is with how weak
   it is (low last rating, low ease).
2. **Untested cards**, oldest first, if *Include untested cards* is on.
3. **Not-yet-due cards** you're most likely to have forgotten, if there's still room.

### Card status and mastery

| Status     | Meaning                                                            |
|------------|--------------------------------------------------------------------|
| Untested   | Never reviewed                                                     |
| Struggling | Last rated 1–2                                                     |
| Learning   | Reviewed, but not yet mastered                                     |
| Mastered   | Last rated 4–5 **and** its review interval has reached 21 days     |

A card's mastery is half your last confidence and half how long the card has held up
(interval out of 21 days). A chapter's or class's mastery is the average over its
*tested* cards. Untested cards are counted separately, so they don't pull the score down.

## Your data

Everything lives in one folder. The folder button at the bottom of the sidebar opens it.

| OS      | Default location                         |
|---------|------------------------------------------|
| Windows | `%APPDATA%\Flagship`                     |
| macOS   | `~/Library/Application Support/Flagship` |
| Linux   | `~/.local/share/Flagship`                |

Set the `FLAGSHIP_DATA_DIR` environment variable to use a different folder.

The folder contains:

- `flashcards.db`: classes, chapters, cards and review history (SQLite).
- `media/`: images used on cards. Images no card uses any more are cleaned up at startup.
- `backups/`: automatic backups made before a *Replace everything* import.

### Moving to another device

1. **Export** (Ctrl+E, or the share icon in the sidebar). This writes a `.flashpack`
   file, which is a zip of your data (`data.json`) and images.
2. **Import** (Ctrl+I) on the other device and choose a mode:
   - **Merge** adds the file's classes next to the ones you already have. Clashing names
     get a suffix.
   - **Replace everything** swaps your data for the file's. Your current data is saved to
     `backups/` first.

You can also copy the whole data folder while the app is closed.

## Development

Run the tests:

```bash
pip install pytest
python -m pytest
```

The tests cover the scheduler, the database layer, the statistics and export/import. The
logic modules don't depend on Qt.

```
main.py                 entry point: picks the data folder, applies the theme, opens the window
flashcards/
  models.py             dataclasses for classes, chapters, cards and reviews
  db.py                 SQLite schema and queries
  scheduler.py          spaced-repetition rules and test-session selection
  stats.py              card status, mastery and dashboard aggregates
  media.py              image storage and cleanup
  transfer.py           .flashpack export / import
  ui/
    main_window.py      sidebar + page stack, export/import, shortcuts
    sidebar.py          class / chapter tree, rename, reorder, card drops
    class_dashboard.py  class page with figures and charts
    chapter_view.py     card list, search, filters, move dialog
    card_editor.py      add / edit card dialog
    rich_text.py        rich text editor and card viewer
    test_setup.py       choose chapters and session size
    test_session.py     the test itself and its summary
    charts.py           hand-painted chart widgets
    theme.py            light / dark colour tokens and fonts
    style.qss           stylesheet template filled from theme.py
    icons.py            inline SVG icons, recoloured per theme
    animations.py       fades, count-ups and page transitions
    dialogs.py          shared buttons, dialogs and small widgets
    toast.py            brief confirmation messages
tests/                  pytest suite
```

UI colours always come from the tokens in `ui/theme.py`, through `theme.color(key)` in
code or `$token` in `style.qss`. When changing the UI, check it in both themes.
#   F l a s h P a c k  
 