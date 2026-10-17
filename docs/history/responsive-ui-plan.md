# "Responsive layout" for Wizardry 8 windows: assessment (2026-10-12)

> **History.** This document describes an early stage of the project and may differ from the released 1.0.0 patch (the hybrid, see [docs/hybrid.md](../hybrid.md) and [README](../../README.md)). Kept to show how we arrived at the current solution.

Assessment from reading the code (5 analysts in parallel + a reviewer); the game was not
run for it. A "session" is 2-4 hours of my work: code, build, in-game check.

## Key points

- It can be done: everything needed already exists after HUD "A" and the wide map - anchoring to
  the left/right edge, stretching images by repeating a piece, shifting the drawing origin.
- Web analogy: this is a flex layout with fixed-size blocks. The panel images
  are drawn for a specific size, and the screen height is always 480, so
  the extra width goes either into the gaps between blocks or into extra
  columns where there is a list (party shared items, journal text).
- In total, the recommended set is about **11-12 sessions**. A full rework of all
  windows, including character creation, is about 20 - not recommended: there is almost nothing
  to gain there.

## By window

| Window | What the width gives | Work | New art | Advice |
|---|---|---|---|---|
| Inventory and stats (rest/character screen, 5 pages) | **Party shared items: 16 items at 16:10 and 24 at 16:9 instead of 8** - 2-3 times less scrolling. The rest (paper doll, backpack, stats) is fixed and simply moves apart to the edges | ~7 (3.5-4 layout + 2-2.5 wide item grid + 0.5-1 art and check) | 1 marble bridge piece in the top row (Astra) | **Do** |
| Options, save/load, settings | Looks only: 5 save rows per page - a height limit | ~1-1.5 | not needed (stretching pieces) | **Do first**: quick and seen often |
| Journal | Entry column 29% wider (16:10) / 50% (16:9): long lines are not cut off (line wrapping is off in the journal) | ~1-1.5 | wider parchment (Astra) | **Do** |
| Character creation and party selection | Almost nothing: lists are limited by height, there will be empty gaps | ~7 | page backgrounds (Astra), 8-bit party background | Keep centered with marble |
| Popups (item info, chest, confirmations) | Nothing: these are "modal windows" with a maximum width, they are already centered over the wide screen | ~1 (credits with a wide background, a click on the wings closes the window) | wide credits background (Astra) | Keep centered |

**Owner's decision (2026-10-12):** the character screen (items, magic, skills,
statistics) laid out full-width by the window layouter looked bad - it was returned to 4:3 centered with
marble on the sides, not responsive. Character creation is not made responsive either.
The window layouter (canvas.h, Video2.cpp) remains in the code, but no window enables it.

Already wide and needing no work: main menu, loading screens, map, main
screen (HUD "A"). Movies stay 4:3 centered (they cannot be redrawn).

## Order

1. Art preparation (0.5): unpack the backgrounds of saves, journal, skills page;
   right away give Astra the inventory bridge, journal parchment, credits background.
2. Options and saves (1-1.5): left column to the left edge, the frame on the right stretched
   to the right edge, content centered. Also here: a shared wide-window "helper" and
   a single ini key, so that the journal and inventory use the same thing.
   **Done (2026-10-12), in two stages.** Stage 2 at the owner's request: content
   not centered but spread across the stretched panel - labels on the left, sliders, checkboxes,
   toggles and keys on the right, save rows full-width (repeating the piece
   [171, 299) of the row image), longer name field. Checked at 768: dragging
   a slider, toggles, key selection, entering a long name, selecting a row by clicking
   on the stretched part (screenshots of that test are not kept).
3. Inventory - layout (3.5-4): top row with the bridge, bottom button strip,
   all 5 pages. A separate release.
4. Journal (1-1.5).
5. Inventory - wide shared items grid (2-2.5): the riskiest part
   (drag and drop, scrolling, mouse regions); needs a check on a save with
   lots of items.
6. Credits with a wide background, clicks on the wings while a window is open (1).
7. Optional: party selection with portraits at the edges (~2).

## Risks

- SGP draws an image no wider than 640 from the window origin: wide pieces are drawn in parts
  with their own origin (like the map frame); text can be drawn wider in a single call.
- Inventory: 75 mouse regions and about 260 places with coordinates; growing the item grid
  beyond 8 cells touches indices and redraw flags in 4 files.
- Before each window, record the check results against the shared mechanism checklists
  (A1-A20, S1-S40 in `docs\wide-canvas.md` are not ticked yet).

Detailed analyst data (files, lines, counters): the result of the
`survey-responsive-ui` run in the session log.
