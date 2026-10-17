# Phase 4 — 4:3 UI without stretching + Hor+

> **History.** This document describes an early stage of the project and may differ from the released 1.0.0 patch (the hybrid, see [docs/hybrid.md](../hybrid.md) and [README](../../README.md)). Kept to show how we arrived at the current solution. The centered 4:3 HUD was replaced by the wide canvas ([wide-canvas.md](../wide-canvas.md)).

Written by the ultracode workflow (1 implementer, 3 skeptics with different angles: ABI/bytes, render logic, robustness; 7 remarks, 6 confirmed and fixed), checked live by an automated test on 2026-10-11 at 2560×1600 (16:10).

## Hooks

| Where | What it does |
|---|---|
| `RenderScene` 0x427850 (MinHook) | 2D passes (cameras 0x659670/0x659674) are drawn into the central block `bw = round(640·H/480)`, `offX = (W−bw)/2`; world passes into the rectangle from `View3dWorldRect` (full width with Hor+); after each pass the viewport/scissor are restored to (0,0,W,H); the bars are cleared to black if the frame did not clear them itself |
| `setScissor` slot 0x5EB640, only return 0x4269E8 | before the game clears the 3D area — black bars, then the clear area = the world rectangle |
| `setViewPlane(Rect,double)` slot 0x5EB4EC, only returns 0x4263A9/0x4263C3 | Hor+: the camera plane is widened horizontally (vertical angle unchanged), only if the 3D view touches the 4:3 edges (modes 0, 1, 6) |
| call at 0x426BAC (6 bytes → `call thunk; nop`) | a click on a 3D object is recomputed for the widened view |
| `RenderWorldToSurface` 0x426F80 | save thumbnails are drawn with the original plane (no distortion) |

Settings: `[Display] HudLayout=Centered`, `HorPlus=1` (default in `dist\wiz8ws.ini`). `HudLayout=Stretch` restores the Phase 3 behavior.

## Live checks (2560×1600)

| Screen | Result | Screenshot |
|---|---|---|
| Main menu | 4:3 centered, black bars, the "eight" is round | `screens/phase4/main-menu-centered.jpg` |
| Gameplay | 4:3 HUD without distortion, round compass, 3D continues into the side bars (Hor+) | (screenshot not kept) |
| Clicks | "Load Game", "Load", minimap, portrait, gear — all hit | (screenshot not kept) |
| Automap | 4:3 centered, black bars | `screens/phase4/automap-centered.jpg` |
| Settings / save | 4:3 centered, thumbnails not distorted | (screenshot deleted: a system notification got into it) |
| Sir-Tech movie | centered, no mode change | `screens/phase4/bink-centered.jpg` |
| Alt+Tab | the game came back, layout intact | — |
| Saves | files in `Saves` unchanged | — |

## What remains / known limitations

- Only 16:10 was checked (the screen's native resolution). 16:9 and 21:9 require changing the desktop resolution — a system setting, not done.
- 3D objects in the side bars cannot be clicked: the game picks objects only inside its 640×480 rectangle.
- "Object in view" checks (`srCamera::project`) see a wider angle — small gameplay differences are possible; pop-in at the edges is possible due to culling.
- Fades and flashes stay inside the block; the bars are not darkened.
- The "panels at the edges" mode (Anchored) was not done: the whole HUD is a single 640×480 canvas, this is a separate large task.
- The inventory/character screen could not be opened by the automated test (key not found) — check manually.
