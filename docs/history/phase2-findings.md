# Phase 2 — static analysis findings (ultracode, 2026-10-11)

> **History.** This document describes an early stage of the project and may differ from the released 1.0.0 patch (the hybrid, see [docs/hybrid.md](../hybrid.md) and [README](../../README.md)). Kept to show how we arrived at the current solution.

Five subsystems, with an analyst and a skeptic for each. All addresses are in `docs/functions.md`, full data in `docs/history/phase2-static-raw.json`.

## Key points

1. **All 2D (HUD, menus, inventory, map, movies) is a single 640×480 canvas** in system memory, cut into 20 textures of 128×128. It is drawn in `stSurface2D::DrawTiles` 0x47E100 via `ortho(0,1,1,0)` and **does not set the viewport itself** — it is stretched to the current one.
2. **All drawing passes go through `RenderScene` 0x427850** (scene, camera, rectangle in 640×480 units or NULL). 2D passes are recognized by the cameras `0x659670` (overlay) and `0x659674` (square). So "centered 4:3 UI" = a single `RenderScene` hook: for 2D cameras set viewport/scissor to the central block, then restore.
3. **The game does not clear the side bars** — the patch must clear them itself every frame (on the first `RenderScene` call of the frame, return address 0x426A3F).
4. **3D view**: the rectangle comes from a table of 7 modes (0x647D30); the FOV is set **only in `SetViewport` 0x426250**: an 85°×71° plane over the whole virtual screen, cropped to the 3D view rectangle. Hor+ = widen the plane horizontally via the import slot `srCamera::setViewPlane(Rect,double)` 0x5EB4EC (only for calls with return addresses 0x4263A9/0x4263C3) + widen the viewport/scissor of the world pass to full width + fix the clear-scissor in `RenderFrame` (return 0x4269E8) and the "click on 3D" point (0x426BAC, not the global pushPick).
5. **Mouse**: three points — `GetCursorPos`/`SetCursorPos` (exe import slots) and a hook on `MouseHandler` 0x401C70. Done in Phase 3; the formula is ready for the centered block too.
6. **Window**: the game already creates a full-screen WS_POPUP; only `openWindow(mode)` changes the display mode. A 7-byte patch at 0x422895 — done in Phase 3.
7. **Bink**: all movies go through one screen (`IntroScreen`); without a "screen" the player writes the frame into the 2D canvas. Done in Phase 3.

## Phase 4 plan (based on the skeptics' findings)

1. `RenderScene` hook: 2D cameras → block `bw = round(640·H/480)`, `offX = (W−bw)/2`; `setViewPort`/`setScissor` take (x, y, w, h); the scissor is applied immediately — restoring is mandatory; filter on `ecx == g_gerd` (save thumbnails are drawn through a second GERD).
2. Clear the side bars every frame.
3. Switch the mouse to `HudLayout=Centered` (ready in layout.cpp).
4. Hor+ (only 3D view modes 0, 1, 6, where the 3D touches the 4:3 edges), then the 3D click point.
5. Check: menu, inventory, map (the automap sets the viewport itself), movies, save thumbnails.

## Open questions (check live)

- Does the plugin's `beginFrame` clear the whole buffer (otherwise there is garbage in the bars).
- Canvas alpha test (bit 0x800000) — holes in the HUD through which the world is visible.
- Mouse-look sensitivity may drop by a factor of `s`.
