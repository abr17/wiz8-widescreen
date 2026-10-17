# Phase 3 — borderless: summary

> **History.** This document describes an early stage of the project and may differ from the released 1.0.0 patch (the hybrid, see [docs/hybrid.md](../hybrid.md) and [README](../../README.md)). Kept to show how we arrived at the current solution. The window mode (borderless / fullscreen / windowed) is now chosen in the game options (`wiz8wide.ini [Display] Mode`).

Tools: `scripts\play\modewatch.ps1` (prints every monitor mode change), `scripts\play\game.ps1` (auto-launch, clicks, screenshots).

## What was done in version.dll

| What | Where | How |
|---|---|---|
| No monitor resolution change | 0x422895 (inside `OpenRendererWindow`) | 7 bytes `8B F0 83 FE FF 75 12` → `83 CE FF EB 14 90 90`: the video mode number is always −1 → the engine opens "windowed" output the size of the client area (= monitor), `DDSCL_NORMAL`, without `SetDisplayMode` |
| Always "fullscreen" (WS_POPUP window over the whole monitor) | `VideoFullScreen` 0x422970 | replaced with a write of `g_fullscreen=1`; `/WINDOW`, the settings toggle and "maximize" no longer break the window |
| Movies without a mode change | `BeginVideoPresentation` 0x423390, `FinishVideoPresentation` 0x4234A0, `IntroScreenFrame` 0x5AE6F0 | Begin does not give the player a "screen" (and zeroes its +8 field), the player writes the frame into the 640×480 2D canvas; after each frame of the movie screen we call `RenderFrame` 0x426790. Finish only marks the canvas for redraw |
| Mouse hits at any resolution | IAT `GetCursorPos` 0x5EB250, IAT `SetCursorPos` 0x5EB254, `MouseHandler` 0x401C70 | screen ↔ logical 640×480 conversion (layout.cpp), clicks clamped to 0..639×0..479, SetCursorPos has a "already there — don't move" rule |
| Alt+Tab | `WindowProcedure` 0x4011E0 | when focus returns, the game's Shift/Ctrl/Alt flags are reset |

dgVoodoo2 stays on default settings (`FullscreenAttributes` empty) — `fake` is no longer needed.

## Checks (2026-10-11, 2560×1600, Windows scaling 150%, dgVoodoo2 2.87.5)

| Check | Result |
|---|---|
| Monitor mode over the whole run: intro, movies, menu, loading, gameplay | **not a single switch**, 2560×1600×32 the whole time (before: 640×480 during movies and exclusive fullscreen mode) |
| Sir-Tech movie | shown full-screen through the 2D layer (`screens/phase3/bink-intro-no-modeswitch.jpg`) |
| Clicks | "Load Game" and "Load" clicked at screen coordinates of the stretched UI, the save loaded |
| Alt+Tab out and back | the game minimized and came back, the picture intact, the mode did not change, the log shows the modifier reset |

## Known issues

- `SetProcessDpiAwarenessContext` returns an error (`dpiAware=0` in the log), but the window is already created at 2560×1600 — the process is apparently already DPI-aware (GOG/dgVoodoo compatibility). Investigate in Phase 5.
- When it loses focus, the game minimizes itself (`SuspendVideoManager`). For borderless this can be disabled later via an option.
- The UI is still stretched (`HudLayout=Stretch`) — that is Phase 4.

## A0. Experiments with dgVoodoo settings only (before code)

| dgVoodoo setting | Monitor mode change |
|---|---|
| default | 2560×1600 → 640×480 during the intro → 2560×1600 |
| `FullscreenAttributes = fake` | game — none; Bink movie — 640×480 for ~1.7 s |
