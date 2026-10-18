# Wide 2D canvas in the built Wiz8Runtime.exe

> Written while the product was `Wiz8Runtime.exe`; the released hybrid uses this same code (the functions from `scripts\hybrid\transplant_wide.json`). Commit hashes in the text are from the `decomp\` repository. The "live test" checklists below were not ticked off item by item; the final 1.0.0 verification is in [releases/1.0.0.md](releases/1.0.0.md).

The "canvas-scope" step from `docs\history\widescreen-source-research.md`: a 2D canvas of width
**W = 640 / 768 / 856** (height 480), every existing screen is drawn unchanged
**centered** with an offset `ox = (W - 640) / 2`, the side bars are black
(or show the 3D world, where the game shows it anyway), and the mouse hits the right spot.

- Sources: `C:\dev\wiz8-ws\decomp`, commits `4f3cf25`, `4c2b5e6`, `4181d53`
  (on top of `e73bc0b`). Patch: `patches\decomp-msvc2022.patch`.
- Build: `pwsh -NoProfile -File C:\dev\wiz8-ws\scripts\build\build-decomp.ps1` ->
  `build\vc2022\Wiz8Runtime.exe` (built, links, only the old warnings).
- The game was **not run** (as per the task). Everything below about in-game behavior is expected
  behavior, to be checked against the checklist at the end.
- Settings: `wiz8wide.ini` next to the exe, sample `dist\wiz8wide.ini`, description in
  `docs\decomp-port.md` (section "Wide 2D canvas").

## Main idea: "a window inside a wide surface"

A web analogy: an old fixed-width 640px page placed in the
center of a wide `<body>`. The page itself (all game logic, thousands of coordinates of
buttons and images) does not change: it still lives in 640x480 coordinates.
Only the "frame" around it changes, plus the places where coordinates cross the boundary
between the game and the screen.

Two coordinate systems:

| Name | Range | Who uses it |
|---|---|---|
| game | 0..640 x 0..480 | the whole game: screens, mouse regions, buttons, `g_viewport`, tooltips |
| canvas | 0..W x 0..480 | DirectDraw surface, 2D texture for rendering, cursor, 2D sprites |

`canvas_x = game_x + ox`, the height is the same. At W = 640 `ox = 0`, and all the code
computes exactly the same as the original (this was checked line by line during the change:
the integer arithmetic was kept the same).

The whole canvas is stretched over the whole output window (2560x1600). So W is chosen by the
screen's aspect ratio: at 16:10 the 768x480 canvas is also 16:10, pixels are square, and the 4:3
game window is not distorted (as in the Centered mode of our DLL).

## Central module

`include\wiz8\canvas.h` + `src\wiz8\engine_code\Canvas.cpp` (comments in Russian):

- `g_canvas_w`, `g_canvas_ox`, `g_canvas_cols` (W/8), `g_canvas_cells` (W/8*60);
  before initialization - 640/0, as in the original;
- `CanvasInitialize()` - reads the ini, chooses W, writes `wiz8wide.log`;
- `CanvasHorPlusEnabled/Applies` - whether Hor+ is enabled and whether the 3D view touches the 4:3 edges;
- `CanvasInverseWidth()` (1/W), `CanvasSpriteScaleX()` (the same as a float),
  `CanvasSquareTop()` (480/W);
- `CanvasSetFrameBufferPitch/CanvasFrameBufferPitch` - the real row pitch of the
  surface for `LineDraw`;
- `CanvasScreenToCanvas`, `CanvasCanvasToScreen`, `CanvasToGame` - the mouse.

## What was changed, by subsystem

### 1. Surface and canvas texture

- The DirectDraw surface is created as W x 480 (`InitializePrimaryDirectDrawSurface`),
  and its real pitch is remembered.
- `W8ColorSurface` (how the renderer sees the surface) and `stSurface2D` (slicing into
  128x128 tiles for textures) - W x 480. At 856 this gives a 7th partial column
  of tiles (768..896) - the same case as the partial 4th row (384..512) in the original.
- The side bars of the surface are always zeros (black, alpha 0): nobody writes there.
  In menus (canvas opaque) they are black, in the game (alpha test enabled) transparent -
  what is drawn under the canvas shows through there (the 3D world or a black fill).

### 2. Pointer to the window (LockPrimarySurface)

- `LockPrimarySurface` returns `start + ox*2` bytes with the real pitch. Everyone
  who draws 2D through this pointer (SGP blitters, fonts, buttons, Bink,
  `MGSPortraits`, `MGSTextBox`, `RCSItemsPage`, `AutomapScreen`,
  `DialogNumericInput`) draws centered without changes, and their 640x480 clipping now
  clips to the window.
- New `LockPrimarySurfaceFull` - the start of the whole surface; it is used by
  the clear in `InitializeGame` (previously `memset(pitch*480)` from the shifted pointer
  would have overrun the end by ox*2 bytes). `ResetVideoFrameState`, `ClearPrimarySurface`
  and surface creation already lock the whole surface directly.
- Direct writes to the surface in game coordinates: `ClearSurfaceRect`,
  `DrawVideoInspector`, `DrawColorSurface` - +ox.

### 3. Grid of "dirty" cells

The game does not re-upload the whole 2D texture every frame; it marks changed 8x8
cells and uploads only those.

- Arrays `g_tile_dirty_flags`, `g_surface_nodes` - for 107x60 cells; the row stride is
  `g_canvas_cols` (W/8) instead of 80.
- `InvalidateRegion` (game coordinates): clamp to the 640 window as before, shift by
  ox, rounding to cells is done in canvas space (at 856 the window starts at x = 108, in
  the middle of a cell). The original body is now `InvalidateCanvasRegion` (canvas).
- "Whole page dirty" = the whole 640x480 window is covered (the bars do not change).
- Full-screen resets (`ResetVideoFrameState`, `InitializeVideoManager`,
  `ResetTransientRenderScenes`, `ClearVideoDirtyBlocks`, `RestoreVideoManager`)
  call the new `InvalidateCanvas` - the full width W.
- `FlushDirtyTiles` walks W/8 columns. `InvalidateDirtyTile` converts a cell
  back to game coordinates to compare it with `g_viewport`.

### 4. Rendering: rectangle conversion and 2D sprites

- Helper `MapRectToOutput`: `(x + ox) * width / W` (integer, like the
  original), for the world under Hor+ - the full width. Used by `RenderScene`, the clear of the
  3D area in `RenderFrame`, `SetAutomapScaledViewport`, `SetWorldScaledViewport`.
- `RenderWorldToSurface` (save thumbnail, automap background) is **left as in the
  original** (the whole output = 0..640): it renders into the whole buffer and copies the whole
  buffer, otherwise the bars would end up in the thumbnail. The 80x60 thumbnails are the same, save
  compatibility is untouched.
- 2D sprites are normalized by 1/W instead of 1/640: `MakePolygonBrush`
  (`configure2D`), `CreateSpriteFromTexture`, `PositionToolTipNode` (+ox -
  it is used to place the radar, the formation board, highlights, automap markers,
  tooltips), `Video2DRectToSquarePolygon`, `Video2DRectToPolygon` (+ox),
  `CreateColoredPolygonSprite`, automap markers in `AutomapScreen.cpp`.
- The "square" camera (a scene where sprites rotate without distortion: the radar compass,
  the party marker on the automap): top of the plane 480/W instead of 0.75.
- Cursor: brush 128/W instead of 0.2, width on resize `extent / W`.
- `g_viewport_x_scale` (constant 1/640) was **not changed**: it is also used to compute the camera
  plane in `SetViewport` and the direction of a thrown item - these are game coordinates.

### 5. Black bars and Hor+

- `ClearCanvasSideBars` at the start of every frame (`RenderFrame`) fills both bars
  in the buffer with black (color + depth), then gives the game back its clear color.
  Without this the transparent bars would contain garbage from previous frames.
- Hor+ (from `src\hooks_view3d.cpp` of our DLL): in `SetViewport`, if the 3D view
  touches the 4:3 edges (`left <= 23`, `right+1 >= 618`: modes 0, 1, 6 and the menu
  0..640), the camera plane is extended along the same line to the canvas edges
  (game -ox .. 640+ox). Degrees per pixel stay the same, the vertical angle stays the
  same. The world and sky (`RenderScene` with `&g_viewport`) and the 3D-area clear cover
  the full canvas width. Narrow modes 2-5 stay inside the window.
- `IsWorldViewWidened` checks that the widening is still in effect: the same world camera,
  and its plane has the same width (or the camera "sway" is on, which every
  frame builds the plane from the widened angle). The automap and `SetWorldScaledViewport`
  reset the widening.
- Click on 3D (`RenderFrame`, pick): when widened, -1..1 covers the whole canvas,
  x is recomputed the same way as `PickThunk` in the DLL.
- Thumbnails: for the duration of `RenderWorldToSurface`, cameras that have our
  widened plane get the original one back (like `HookRenderWorldToSurface`).

### 6. Mouse

Previously (and in the original) one screen pixel = one game unit, so at
2560x1600 without the DLL the cursor was locked in the top-left corner. Now there are two steps:

1. screen -> canvas: `canvas_x = (screen_x - pic_x) * W / pic_width`, `canvas_y =
   (screen_y - pic_y) * 480 / pic_height` (rounded down; picture = client area of the game
   window, in borderless mode the whole screen; in fullscreen mode dgVoodoo
   (`ScalingMode = stretched_ar`) keeps the monitor's mode and fits the chosen resolution
   into it with black bars, so the picture is the centered rectangle of that resolution's
   aspect ratio, `OutputRect` in Canvas.cpp). dgVoodoo's `CaptureMouse` is off: with it on,
   dgVoodoo confines the cursor to the chosen resolution's size from the top-left corner
   (1920x1080 of a 2560x1600 screen), so the right and bottom of the picture were unreachable;
2. canvas -> game: `game_x = canvas_x - ox`, clamp to 0..639 / 0..479 - the same
   in polling (`PositionMouseCursor` -> `SGPMouseGetPos`), in events
   (`MouseHandler`) and for the wheel, so that hover and click always see the same point.

- **When the conversion is on.** `CanvasMouseMapActive()` = `ox > 0` or
  `MouseScale=1`. The `MouseScale` key defaults to 1 when W > 640 and 0 when
  W = 640. So `Width=640` without other keys is **exactly the original**: no
  scaling, no clamps, `SyncSystemCursor` pins the Windows cursor on every
  change, the wheel gets the raw `lParam`.
- **Click in a side bar.** A left/right button press while the cursor is in a bar
  (canvas_x < ox or >= ox+640) is dropped by `MouseHandler`: no event, no
  `gfLeft/RightButtonState`. The matching release is also dropped, wherever it
  happens (a screen will not see a "release" without a "press"). A press in the window with
  the release in a bar arrives as before (clamped to the edge), so
  drags and sliders finish. Hover in a bar is still seen by the
  game as the window edge (highlight/tooltip at the edge - cosmetic only).
- **Wheel.** `WindowProcedure` (`WM_MOUSEWHEEL` and the old `MSH_MOUSEWHEEL`)
  gets screen coordinates; `WheelParamToGame` (sgp.cpp) converts them along the same
  path (`CanvasScreenToGame`, in windowed mode `ScreenToClient` first). The wheel
  in a bar is not dropped but clamped to the edge (some dialogs scroll a
  list with the wheel without regard to the point).

- `SyncSystemCursor` (every frame): step 1, clamp as in the original, but in canvas space
  (0..W). The cursor is drawn in the canvas (`g_cursor_canvas_x/y`), the game is given
  `g_cursor_width/height` in game coordinates (`PositionMouseCursor`). Therefore
  `SGPMouseGetPos`, `GetAtomCursorX/Y`, `DispatchRegionInput`, region tooltips
  were **not changed** - they already receive game coordinates.
- The original called `SetCursorPos` on every movement (to pin the cursor to the
  clamped point). With scaling this means snapping to the canvas grid and jitter, so
  the Windows cursor is moved only if the clamp actually kicked in.
- `MouseHandler` (SGP, clicks and movements into the event queue): the same two steps.
- Reverse conversion (`WarpSystemCursor` - game coordinates, `MoveSystemCursor`
  on hotspot change - canvas): `SetSystemCursorToCanvas` puts the cursor in the
  middle of a canvas cell and **does not touch** it if it is already in that cell. This
  matters for mouse look and the 3D spell cursor: after every event the game
  returns the cursor to (320,240), and without this small movements (less than a cell,
  ~3 screen pixels) would be lost.
- `MouseScale=0` in the ini - both conversions are identity (as in the original); at
  W > 640 subtracting ox, the clamp and dropping clicks in the bars remain.
- Windowed mode: client area W x 480, scale 1.

### 7. SGP

- `FRAME_BUFFER` as an SGP video surface is now 640 wide (the window): all
  SGP clipping by `usWidth` (BltVideoSurface, ShadowVideoSurfaceRect...) works
  against the window.
- Paths through DirectDraw (rectangles, not the pointer): `FillSurface` (fills
  only the window), `FillSurfaceRect`, `BltVSurfaceUsingDD` (Blt and BltFast) - +ox,
  if FRAME_BUFFER is the source or destination (`FrameBufferRectToDD`).
- `LineDraw`: 4 screens hard-coded the row width as 0x500 (= 640*2), and
  `line.cpp` addresses by it; now the real pitch (`CanvasFrameBufferPitch`).
- The other "640"s in SGP (`ClippingRect`, the hard clip in `Blt16BPPTo16BPP`,
  tooltip clamps in `mousesystem.cpp`, `RegionManager.cpp`) are game coordinates of the
  window, no change needed.

### 8. What was deliberately not changed

- Save thumbnails (80x60 from the full frame) and the save format.
- Bink: the 640x480 frame is centered thanks to the shifted pointer.
- `BeginVideoPresentation` (`SetDisplayMode(640,480)`, the old fullscreen path for
  movies) and `GetCurrentVideoSettings` (640x480 for SGP).
- Full-screen fades (`CreateColoredPolygonSprite(640,480)` for the
  "surprise attack" flash and the camp screen): they cover the 640x480 window, the bars are not
  darkened (same as in the DLL).

## List of changed functions (decomp, after the review-fixes commit)

`include\wiz8\canvas.h` - new (the whole file).

`src\wiz8\engine_code\Canvas.cpp` - new: `PathNextToExe` :24, `CanvasLog` :44,
`ReadOutputSize` :57, `NormalizeWidth` :84, `CanvasInitialize` :96 (default
`MouseScale` by W), `CanvasHorPlusEnabled` :155, `CanvasHorPlusApplies` :160,
`CanvasInverseWidth` :168, `CanvasSpriteScaleX` :173, `CanvasSquareTop` :179,
`CanvasSetFrameBufferPitch` :184, `CanvasFrameBufferPitch` :189,
`CanvasMouseScaleEnabled` :194, `FloorDiv`, `CeilDiv`, `OutputSize`,
`CanvasScreenToCanvas` :228, `CanvasAxisToScreen`, `CanvasCanvasToScreen` :253,
`CanvasMouseMapActive` :266, `CanvasIsInSideBar` :271, `CanvasToGame` :276
(clamp 639/479), `CanvasScreenToGame` :298.

`src\wiz8\sources.cmake` - added `Canvas.cpp` after `Video2.cpp`.

`include\wiz8\engine_code\Video2.h` - `#include "wiz8/canvas.h"`, declarations of
`LockPrimarySurfaceFull`, `InvalidateCanvas`, size of `g_surface_nodes`.

`src\wiz8\engine_code\Video2.cpp`:

| Line | Function / object | What |
|---|---|---|
| 208, 228 | `g_surface_nodes`, `g_tile_dirty_flags` | size 107x60 |
| 289-298 | `g_cursor_canvas_x/y`, `g_hor_plus_*` | new state |
| 302 | `IsWorldViewWidened` (new) | whether Hor+ is in effect |
| 329 | `MapRectToOutput` (new) | (x+ox)*width/W |
| 347 | `ClearCanvasSideBars` (new) | black bars |
| 377 | `SetSystemCursorToCanvas` (new) | canvas -> Windows cursor |
| 428 | `LockPrimarySurface` | +ox*2 |
| 445 | `LockPrimarySurfaceFull` (new) | the whole surface |
| 459 | `ResetVideoFrameState` | `InvalidateCanvas` |
| 487 | `InitializeVideoManager` | `CanvasInitialize`, `InvalidateCanvas` |
| 679 | `CreateWizardryWindow` | windowed mode W x 480 |
| 742 | `InitializePrimaryDirectDrawSurface` | surface W, pitch |
| 1004 | `ResetTransientRenderScenes` | `InvalidateCanvas` |
| 1021 | `ClearVideoDirtyBlocks` | `InvalidateCanvas(1)` |
| 1060 | `RestoreVideoManager` | `InvalidateCanvas` |
| 1153 | `RenderScene` | viewport conversion, world under Hor+ |
| 1242 | `RenderFrame` | bars, 3D-area clear, pick |
| 1432 | `RenderWorldToSurface` | original plane for the duration of the snapshot |
| 1599 | `MakePolygonBrush` | `configure2D(width*W)` |
| 1657 | `CreateSpriteFromTexture` | width * W |
| 1742 | `MoveSystemCursor` | via `SetSystemCursorToCanvas` |
| 1748 | `ResizeMouseCursorSurface` | brush extent/W, position in canvas |
| 1795 | `SetMouseCursorHotspot` | offset in canvas |
| 1812 | `SetMouseCursorFromVideoObject` | offset in canvas, u-extent 1/W |
| 1891 | `WarpSystemCursor` | game -> canvas -> screen |
| 1899 | `PositionMouseCursor` | canvas for drawing, game for logic |
| 1963 | `SyncSystemCursor` | screen -> canvas, clamp 0..W |
| 2088 | `InitializeMouseCursorScene` | brush 128/W, start (640+ox, 480) |
| 2145 | `ReleaseSurfaceNode` | `g_canvas_cells` |
| 2168 | `InvalidateDirtyTile` | stride W/8, cell -> game |
| 2224 | `InvalidateCanvasRegion` (former body of `InvalidateRegion`) | canvas |
| 2286 | `InvalidateRegion` | clamp to window, +ox |
| 2301 | `InvalidateCanvas` (new) | full width |
| 2325 | `FlushDirtyTiles` | W/8 columns |
| 2373 | `SetAutomapScaledViewport` | conversion, Hor+ reset |
| 2403 | `SetViewport` | Hor+ (plane widening) |
| 2477 | `DrawVideoInspector` | +ox |
| 2658 | `InitializeRendererSceneObjects` | square camera 480/W, `W8ColorSurface`/`stSurface2D` W |
| 2788 | `ClearSurfaceRect` | +ox |
| 3141 | `PositionToolTipNode` | +ox, 1/W, 480/W |
| 3188 | `Video2DRectToSquarePolygon` | 1/W |
| 3322 | `CreateColoredPolygonSprite` | 1/W |
| 3458 | `Video2DRectToPolygon` | +ox, 1/W |
| 3958 | `DrawColorSurface` | +ox |
| 3966 | `SetWorldScaledViewport` | conversion, Hor+ reset |

Other files:

| File:line | Function | What |
|---|---|---|
| `src\sgp\input.cpp:134` | `MouseHandler` | screen -> canvas -> game (`CanvasScreenToGame`), dropping presses in the bars |
| `src\sgp\sgp.cpp:34` | `WheelParamToGame` (new) | wheel: screen -> canvas -> game |
| `src\sgp\sgp.cpp:103` | `WindowProcedure` | both wheel paths via `WheelParamToGame` |
| `src\sgp\vsurface.cpp:335` | `SetPrimaryVideoSurfaces` | `ghFrameBuffer->usWidth = 640` |
| `src\sgp\vsurface.cpp:1623` | `FrameBufferRectToDD` (new) | +ox for FRAME_BUFFER |
| `src\sgp\vsurface.cpp:1631` | `FillSurface` | fills only the window |
| `src\sgp\vsurface.cpp:1664` | `FillSurfaceRect` | +ox |
| `src\sgp\vsurface.cpp:1697` | `BltVSurfaceUsingDD` | +ox (Blt and BltFast) |
| `src\wiz8\game_init.cpp:65` | `InitializeGame` | `LockPrimarySurfaceFull` |
| `src\wiz8\local_screens\IntroScreen.cpp:52` | `IntroScreenEnter` | pitch instead of 0x500 |
| `src\wiz8\local_screens\MainGameScreen.cpp:2922` | `MainGameScreenEnter` | pitch instead of 0x500 |
| `src\wiz8\local_screens\PleaseWaitScreen.cpp:140` | entry of the "Please wait" screen | pitch instead of 0x500 |
| `src\wiz8\local_screens\ReviewCharacterScreen.cpp:1309` | entry of the camp screen | pitch instead of 0x500 |
| `src\wiz8\local_screens\AutomapScreen.cpp:1836` | `CreateAutomapMarkerSprite` | 1/W |
| `src\wiz8\local_screens\AutomapScreen.cpp:1858` | `CreateAutomapMarkerSprites` (party marker) | 1/W on both axes |
| `src\wiz8\local_screens\AutomapScreen.cpp:2085` | item marker on the automap | 1/W |

Outside `decomp`: `dist\wiz8wide.ini` (sample), `scripts\play\game.ps1` (the
`canvas` layout for automated tests: `$script:Layout='canvas'; $script:CanvasW=768`),
`.gitattributes` (patches without line-ending conversion).

## Risks and what was not verified

1. **The game was not run.** The build links, but all behavior is based on reading the code.
2. `srColorSurface::blit` from the retail `sr.dll` must clip the source
   rectangle of the 7th tile (768..896) to the surface width 856. Vertically the
   original already lives with the 384..512 tile at height 480, so almost certainly
   yes. At W = 768 the tiles are even - **do the first live test at 768**.
3. At 856 Bink gets a pointer aligned to 8 rather than 16 bytes (ox*2 = 216).
   If a movie draws with garbage/crashes only at 856 - this is the cause.
4. Small mouse movements in mouse look accumulate thanks to "do not touch the cursor if
   it is already in the right cell". Sensitivity of mouse look and the 3D spell cursor is lower
   than in the original at 2560x1600 without the DLL (one game unit = ~3.3 screen
   pixels), i.e. like the original on a 640x480 monitor.
5. A press in a side bar is dropped. Consequences: a click on a black bar
   does not skip a movie/intro and does not close a "click anywhere" dialog (you have to
   click on the picture); with Hor+ a press on the world in a bar (right-button mouse
   look, clicking a monster) does nothing. Hover over a bar is "seen" by the game
   as the window edge (highlight/tooltip at the edge, 3D pick at the window edge).
6. Hor+: "object visible to the camera" checks (`srCamera::project` in `Targeting.cpp`,
   `Prop.cpp`, `PolyPick.cpp`) see a wider angle; you cannot click on 3D in the bars
   (pick only inside `g_viewport`), same as in the DLL.
7. With camera "sway" (a status effect) the save thumbnail may be slightly
   squashed: the original plane is restored only on an exact match.
8. `SetWorldScaledViewport` (region link builder in `Octree.cpp`, an editor
   path) now draws a quarter of the window rather than a quarter of the screen; this affects the pixel
   count proportionally.
9. Full-screen fades and flashes do not cover the bars.

## LIVE TEST CHECKLIST

Preparation (by hand, outside this task):

1. Copy `build\vc2022\Wiz8Runtime.exe` to `games\work` (next to the retail
   `sr.dll`), and `dist\wiz8wide.ini` there as well.
2. Run three configurations: `Width=768` (main, 16:10), `Width=640`
   (regression), `Width=856` (16:9 on a 16:10 screen: the picture will be slightly squeezed
   horizontally - this is expected, we only check that it works).
3. After each run open `games\work\wiz8wide.log`: it must contain
   `[Canvas] Width=... -> W=..., ox=..., grid ...x60`. With `auto` on 2560x1600:
   `output 2560x1600 (3DVideo.CFG), aspect 1.600`, `W=768, ox=64`.
4. For automated tests: `. scripts\play\game.ps1; $script:Exe='Wiz8Runtime';
   $script:Layout='canvas'; $script:CanvasW=768`.

What to look at (W = 768 unless stated otherwise):

| # | Screen / action | Expected result |
|---|---|---|
| 1 | Logos and intro movie (Bink) | 640x480 frame centered, black bars, no garbage at the edges and no row shift |
| 2 | Main menu | menu centered, the "eight" is round (not stretched), black bars; hover highlights the items exactly under the cursor |
| 3 | Cursor in the menu | moves across the whole screen, visible on top of the black in the bars; does not "jump" at the window edges; does not jitter on slow movement |
| 4 | Click on menu items near the edges (top, bottom) | exactly the item under the cursor fires |
| 5 | Tooltips on hover | next to the cursor, inside the 640x480 window |
| 6 | Load Game -> list, thumbnails | list and thumbnails in place, thumbnails not squashed; clicks on slots and buttons hit |
| 7 | Loading a save, "Please wait" screen | centered, lines/frames straight (checks pitch in `LineDraw`) |
| 8 | Game, default view mode (0) | 4:3 HUD centered without distortion; the 3D world continues in the bars (Hor+), joins without gaps or garbage; radar compass is round and rotates without distortion |
| 9 | Radar and formation board | in their places in the bottom panel (not shifted left by ox) |
| 10 | Hover over a monster / item / door in 3D | what is under the cursor gets highlighted, both in the center and at the edges of the 3D view |
| 11 | Clicks on portraits, roof buttons and bottom panel | all hit; the right column of portraits too |
| 12 | Switching view modes (layout buttons) | in narrow modes (between the portraits) the world is only in the window, bars are black; in wide modes - world to the edges; switching back and forth without garbage |
| 13 | Mouse look (right button in 3D) | smooth turning, slow mouse movement also turns; after exit the cursor is in its previous place |
| 14 | Casting a spell with the 3D cursor (area) | the cursor in the world follows the mouse, slow movement too |
| 15 | Dragging an item with the cursor, throwing into the world | item icon on the cursor, the throw flies toward the cursor |
| 16 | Inventory / character screen (RCS) | centered, black bars; item selection frame is straight (`LineDraw`) |
| 17 | NPC dialog, number input (trading, splitting a stack) | text and caret in place; keyboard input works |
| 18 | Automap | map centered, party marker and item markers in the right places and the right size; scrolling/zooming the map with the mouse |
| 19 | Options, saving the game | centered; the new save thumbnail is normal (not squashed, no HUD and bars) |
| 20 | Save, load this save and an old save (made by the original) | they load, thumbnails look the same |
| 21 | Combat: "surprise attack" flash, dimming | the 640x480 window is dimmed (the bars are not dimmed - known limitation) |
| 22 | Alt+Tab and back | picture intact, black bars, mouse hits |
| 23 | `Width=640` (without `MouseScale`) | behaves like the build before the change (on 2560x1600 the cursor moves 1:1, as before); log shows `MouseScale=0` |
| 24 | `Width=640`, `MouseScale=1` | UI stretched to the whole screen as before, but the mouse works across the whole screen |
| 25 | `Width=856` | same as 1-22; especially the right edge of the canvas (7th partial tile: no garbage on the right) and the Bink movie |
| 26 | `HorPlus=0` at 768 | in the game the bars are black, the world is only in the window, clicks in 3D hit |
| 27 | Windowed mode (`/WINDOW`, if used) | client area W x 480, mouse hits |
| 28 | Wheel over the message window, NPC transcript, item lists, stat pages | exactly the element under the cursor scrolls (768 and 856) |
| 29 | Click (left and right) in the left/right bar in the main game | nothing happens: no portrait gets selected, no button near the edge fires |
| 30 | Press in the window on a slider/item, release in a bar | the drag finishes normally, nothing "sticks" |
| 31 | Press in a bar, release in the window over a button | the button does not fire |
| 32 | Cursor at the right edge of the window (x ~ 639) and in the right bar | highlight and click on the right column of portraits match (click - only inside the window) |

## Main screen HUD layout "A" (W > 640)

Commits in `decomp`: `edb015b` (mechanism), `848c067` (layout), `939c52a`
(save thumbnails). The game was **not run**: everything below is from reading the code,
to be checked with the checklist at the end of the section.

### What is visible

Only the main game screen and only when W > 640. At W = 640 all shifts
are zero, the code takes the same paths as before.

| Element (640 coordinates) | Where on a canvas of width W (ox = (W-640)/2) |
|---|---|
| Left portrait column x 0..128 (slots 0, 2, 4, 6) | x 0..128 (pinned to the left edge) |
| Right column x 512..640 (slots 1, 3, 5, 7) | x W-128..W (pinned to the right edge) |
| 3D view, all 7 modes `g_viewport_modes` | wider by ox on each side, top/bottom the same: modes 2-5 - x 128..W-128, modes 0/1/6 - x 23..W-23 |
| Bottom panel: strip 0..23 + radar 23..128 | at the left edge (x 0..128) |
| Message log 128..512, text 168..452 | x 128..W-128, text 168..W-188; line wrapping itself is wider by 2*ox |
| Log scroll arrows (right edge of the log + 5) | move with the right edge of the log |
| Formation board 512..617 + strip 617..640 | at the right edge (x W-128..W) |
| Roof 0..640 (view buttons on the left, spell icons on the right) | full width: left end at the left edge, right end at the right edge, middle - repeat of the middle 40 px piece of the `main_roof` image |
| Combat progress bar on the roof (177..463) | centered |
| Bottom row y 450-480: options disc, action buttons, frame, arrows (0..343) | at the left edge |
| ... "name - profession / action" caption (343..528) | stretched by 2*ox (repeat of the middle 16 px slice), text centered |
| ... panel buttons (541, 571) and combat button (610) | at the right edge |
| Popup panels at a portrait (health/conditions/enchantments), "keyboard" menu above a portrait, speech "bubbles", combat effect icons at the columns | together with their column |
| Combat popup menu above a bottom row button | above its button (turn menu - on the right, the rest - on the left) |
| Bottom panel sub-screens (spells, item, NPC, lock, trap) | since 2026-10-12 laid out across the wide panel (left part on the left, right part on the right, middle stretched) - see the section "Bottom panel sub-screens in layout A" below |
| Dialogs, tooltips, monster list in combat, party movement panel | centered, as before |

No new graphics: stretched backgrounds (log 384 px, caption 185 px, roof 640 px)
are assembled from three pieces of the same image (`DrawCatalogImageWide`).

### How it works (to understand the code)

Web analogy: before, the whole game was a "640px-wide page, centered".
Now every HUD element has something like CSS `position: absolute;
left: 0` or `right: 0`. The numbers themselves in the game code (portrait x 512, button 610)
we did **not touch** - the element only got an "anchor":

| Anchor | Game x shift | Where on the canvas |
|---|---|---|
| `W8_ANCHOR_CENTER` (default, 0) | 0 | x + ox, as before |
| `W8_ANCHOR_LEFT` | -ox | x (left edge of the canvas) |
| `W8_ANCHOR_RIGHT` | +ox | x + 2*ox (right edge of the canvas) |

1. **Mouse coordinates.** While the layout is on (`CanvasSetWideLayout(true)`
   in `MainGameScreenEnter`, turned off in `MainGameScreenLeave`), game
   mouse coordinates are still "centered" (`game_x = canvas_x - ox`), but
   are **not clamped** to 0..639: the cursor at the left edge of the canvas gives a negative
   x (down to -ox), at the right edge - up to 639+ox. In the game's 16-bit fields a negative
   number is stored as 65535-..., so all hit tests read x as
   signed short (`RegionContainsPoint`, `GetAtomCursorX`, SGP mousesystem).
   Clicks in the "side bars" are no longer thrown away: the HUD is there now.
2. **Mouse regions.** A region (`W8Region::layout_anchor`, an SGP button
   `MOUSE_REGION::bLayoutAnchor`, a panel `Controls::m_layoutAnchor`) has
   an anchor. The hit test subtracts its shift from the cursor x, and the
   region handler receives the event already in its own 640 coordinates
   (`RegionLocalEvent`). So the `g_regions` table kept its old
   numbers - only anchors were added (`ApplyMainGameRegionAnchors`).
   All three anchor fields live in former padding bytes: the structure
   sizes did not change.
3. **Drawing.** All 2D is drawn through the "window origin" on the canvas
   (`CanvasDrawOrigin()`, ox by default): the `LockPrimarySurface` pointer,
   `InvalidateRegion`, `ClearSurfaceRect`, DirectDraw blits by
   rectangles, 2D sprite positions (`PositionToolTipNode` - radar and formation
   board). `CanvasDrawScope scope(anchor)` (RAII, like `try/finally`)
   sets the origin to 0 or 2*ox while an element is drawn and restores the old one.
   SGP buttons and `Controls` draw themselves with their own anchor.
4. **Stretched elements** (log, 3D view, bottom row caption) - anchor
   CENTER, but the left edge is shifted by -ox, the right by +ox (`MainGameWideLeft`,
   `MainGameWideRight`, `MainGameViewportRect`, `SetMainTextBoxRegionBounds`).
   3D view: the rectangle is wider, and `SetViewport` with its usual linear
   formula extends the camera plane - this is exactly Hor+ for the new
   rectangle (the separate Hor+ branch is off in the layout).
5. **Dirty rectangles.** `ApplySavedRedrawInvalidates` marks each
   entry of `g_main_game_invalidate_rects` with its place
   (`g_main_game_invalidate_places`: slot column, left, right, center,
   stretched). "Whole page dirty" in the layout = the whole canvas.
6. **3D frame.** In the layout the whole back buffer is cleared (black) at the start of the frame,
   not just the side bars: the 3D view now extends into the bars.
7. **Transitions.** Enter: `MainGameLayoutEnter` + the whole canvas is refilled.
   Exit to any other screen: `MainGameLayoutLeave` fills the side bars of the 2D surface
   with zeros (HUD leftovers) and refills the whole canvas; the next
   screen is centered again. Since 2026-10-12 the bottom panel sub-screens themselves
   fill the whole wide panel (`PlaceSubscreenPanel`, section below); erasing
   the bars next to a centered sub-screen (`ClearBottomPanelAroundSubscreen`)
   was removed.

### Where the code is

| File | What |
|---|---|
| `include\wiz8\canvas.h`, `src\wiz8\engine_code\Canvas.cpp` | anchors, `CanvasSetWideLayout`, `CanvasAnchorShift`, `CanvasDrawOrigin`, `CanvasDrawScope`, `CanvasOriginScope`, unclamped mouse (`CanvasToGame`), Hor+ off in the layout |
| `include\wiz8\local_screens\MainGameLayout.h`, `src\wiz8\local_screens\MainGameLayout.cpp` (new) | the single place for the layout: static region anchors, stretched images and clears, extended 3D view and log |
| `src\wiz8\engine_code\Video2.cpp` | window origin instead of ox in 2D paths, full buffer clear, signed `GetAtomCursorX`, thumbnails with the original camera plane |
| `src\sgp\vsurface.cpp` | DD blits by rectangles - through the window origin |
| `src\sgp\mousesystem.*`, `src\sgp\Button System.*`, `src\wiz8\dialog_code\stButton.cpp`, `include\wiz8\dialog_code\DialogButton.h` | SGP button anchor: hit testing and drawing |
| `include\wiz8\regions.h`, `src\wiz8\local_code\RegionManager.cpp` | region anchor, signed check, events in region coordinates, full-width tooltips |
| `include\wiz8\local_code\Controls.h`, `src\wiz8\local_code\Controls.cpp` | anchor for panels and their children |
| `src\wiz8\local_screens\MainGameScreen.cpp` | enter/exit, 3D view modes, panel redraw, dirty rectangles, panels at portraits |
| `MGSButtons.cpp`, `MGSPortraitCombat.cpp` | roof, bottom row, buttons, combat popup menu |
| `MGSPortraits.cpp`, `MGSSpellIcons.cpp`, `MGSKeyboard.cpp`, `MGSRadarMap.cpp`, `MGSFormation.cpp`, `QuoteManager.cpp`, `NPCInteractionSubscreen.cpp`, `Screens.cpp`, `MGSSpellCasting.cpp` | portraits, icons, menu above a portrait, radar, board, speech, log |

### What stayed centered (deliberately)

- ~~Bottom panel sub-screens~~ - wide since 2026-10-12, see the section "Bottom panel
  sub-screens in layout A". Only the middle panel of the
  lock (pins) stayed centered; the gaps next to it are a continuation of its black casing.
- Modal dialogs and message boxes, tooltips (but the region tooltip
  can now sit at the edge of the canvas), monster list in combat, party movement
  panel, formation window (button on the formation board), debug labels.
- Full-screen dimming (surprise attack flash) - 640x480 centered.
- All other screens (menu, camp, automap, options, loading) - as before.

### Risks to check in-game

1. Everything is from reading the code; not a single frame was seen.
2. Images stretched by repeating a slice (roof - slice x 300..340, log -
   184..200, caption - 84..100): if there is a pattern there, an "accordion" will be visible.
   The slices are changed in the `DrawCatalogImageWide` calls.
3. ~~Black bars next to sub-screens~~ - obsolete (2026-10-12), sub-screens are
   wide. Still check: radar and board do not stick out on top of a sub-screen
   (the original hides them itself).
4. The NPC transcript is now pinned to the right edge together with the right column of
   portraits and covers it exactly as in the original (portraits 3/5/7 under
   the expanded list are hidden) - both at 768 and at 856.
5. The "camera sway" effect (drunkenness etc.) rebuilds the camera plane
   itself - in the wide 3D view the picture may stretch/squeeze while the effect lasts.
6. Negative game x at the left edge: code that reads the mouse coordinate
   as unsigned and compares "x < 640" will see 65xxx. For centered
   screens this is a "miss", for the HUD everything was converted; but leftovers are possible.
7. The transition "to camp" with the portrait slide-out animation (`PumpReviewTransition`) and
   other animations on old coordinates were not checked.
8. Spell 3D cursor, item throw, monster selection at the very edges of the
   extended 3D view.

### LIVE TEST CHECKLIST for layout A

Preparation: as in the general checklist (Wiz8Runtime.exe + `wiz8wide.ini` in
`games\work`). Main run `Width=768`, then `Width=856`, then
`Width=640` (regression).

| # | What to do | Expected result |
|---|---|---|
| A1 | Load a save, "portraits" mode (button 1 on the roof) | left portrait column at the left edge of the screen, right one - at the right; between them the 3D world without gaps; roof full width without breaks, view buttons on the left, spell icons on the right |
| A2 | Look at the bottom panel | on the left strip + radar, on the right formation board + strip, the log between them across all the remaining width; scroll arrows at the right edge of the log |
| A3 | Bottom row | on the left options disc and action buttons, on the right panel buttons and combat button, "name - profession" caption centered on the stretched plate |
| A4 | Hover and click on each portrait (both columns), on the name, condition/enchantment orbs, side inspection strips | highlight exactly under the cursor, that character gets selected, the popup panel appears next to its column |
| A5 | Roof buttons 1/2/3 (portraits / formation / radar) | they fire; when switching there is no garbage and no leftovers of old portraits in the middle of the screen |
| A6 | "Formation" mode: hover over the narrow portrait strip at an edge | the portrait slides out from its edge, a click selects the character |
| A7 | Layout arrows on the left (radar / log / board) | panels hide/appear, the 3D view changes size, without garbage |
| A8 | Click on the radar (circle), on the formation board, hover over board tokens | the radar zooms; the board opens the formation window (centered); tooltip at the token |
| A9 | Log: scrolling with the arrows, with the wheel over the log, dragging the slider, clicks on channel tabs, click on a line | everything works; long lines wrap at the new (wide) width |
| A10 | All bottom row buttons (journal, camp, search, item, spells, attack/defend in combat, character arrows, panel buttons, combat button, options disc) | each fires on a click in its place; tooltips next to the button |
| A11 | Combat: "attack"/"defend" buttons - popup menu | menu above its button, items are clickable; turn menu (button on the right) - on the right |
| A12 | Combat: effect icons at the columns, action buttons at the portraits (24..42 / 595..613), menu above a portrait (right button / keyboard) | at their columns, clickable |
| A13 | Open the spell book, item selection, NPC conversation, lock, trap; close each | (since 2026-10-12) sub-screen across the whole wide panel without black bars, details - checklist S1-S40 below; after closing the wide panel is fully restored |
| A14 | NPC conversation with a transcript (768 and 856) | (since 2026-10-12) transcript at the right edge, above the right column; portraits 3/5/7 under the expanded list are hidden, as in the original |
| A15 | Click and hover over the 3D world at the very edges of the extended view (monster, item, door) | what is under the cursor gets highlighted; a thrown item flies toward the cursor |
| A16 | Mouse look (right button in 3D), spell 3D cursor | as before |
| A17 | Open inventory/character, automap, options, exit to the menu, come back | these screens are centered with black bars, no HUD leftovers on the sides; back in the game - layout A again |
| A18 | Save the game and look at the thumbnail | the thumbnail is not squashed or stretched (as in the original) |
| A19 | Message boxes, confirmations, monster info (right click on a monster) | centered, buttons are clickable |
| A20 | `Width=640` | everything as before this change (640x480 HUD, no shifts) |

## Bottom-panel sub-screens in layout A (W > 640), 2026-10-12

Commits in `decomp`: `44a6e30` (mechanism), `b772a0e` (NPC), `1527939`
(spells), `29a3e77` (item selection), `b0813ce` (lock and trap, removal of
black bars), `2005926` (NPC regions follow the current state), then a fix after
review (slices taken from the real images, trap stretched - see "Background slices"
below). The game was **not run** - everything is from reading the code and the images; verify with
checklist S1-S40 at the end.

### What changed for the player

Previously, the sub-screens that temporarily replace the bottom panel (NPC conversation and
trade, spell book, item selection, lock, trap) were drawn
centered in 640, and the wide panel was black on either side of them. Now each
sub-screen occupies the whole wide panel, just like the layout A HUD itself:

- the left part of the sub-screen is pinned to the left edge of the canvas (where the radar is);
- the right part - to the right edge (where the formation board is);
- the middle (text, lists) is stretched by 2*ox, like the message log: the background is assembled from
  the same image by repeating a slice from its smooth interior (the slice
  is chosen per image, see "Background slices"), and the text window is wider by
  ox on each side, so lines wrap at the new width and lists
  fit more text. No new art.

At W = 640 and outside layout A (camp, other screens) all offsets are zero - the code
follows exactly the original's paths.

### How it works (to understand the code)

A web analogy: a sub-screen has three `<div>` panels. Previously the whole trio sat in a
`margin: 0 auto` block 640 wide. Now the left panel got `left: 0`, the right one
`right: 0`, and the middle one both `left`/`right` at once (it stretches); the middle one's background
is like a `border-image` with a repeating middle.

Technically, each panel (`Controls`) got its place via
`PlaceSubscreenPanel(panel, W8_SUBSCREEN_...)` (`MainGameLayout.h:107`):

| Place | Anchor of the panel and its children's regions | Background (`Controls::m_wideMode`) |
|---|---|---|
| `W8_SUBSCREEN_LEFT` | LEFT | as in the original |
| `W8_SUBSCREEN_RIGHT` | RIGHT | as in the original |
| `W8_SUBSCREEN_STRETCH` | LEFT (left edge stays, children on the left) | `W8_PANEL_WIDE_STRETCH`: the piece before the slice at the left edge, the piece after the slice at the right edge, the slice repeated between them (`DrawCatalogImageWide`); the slice comes from the `s_subscreen_art_cuts` table, for an unknown image the middle 16 px |
| `W8_SUBSCREEN_CENTER_FILL` | CENTER | `W8_PANEL_WIDE_FILL_GAPS`: panel centered, the ox-wide gaps to the neighbours on the left and right continue its background: the image edges move out to the gap edges, with a repeated interior slice between them (the `s_subscreen_art_cuts` table; for an unknown image - 8 px slices 4 px inside the edges) |

- `m_wideMode` lives in a former padding byte of `Controls` (after
  `m_fWholeAreaDirty`); the structure size did not change.
- The background is drawn by `Controls::DrawBackground` (via `DrawSubscreenPanelArt`); the whole
  panel is marked dirty by `InvalidateSubscreenPanelArt` - on the canvas from the panel's left
  edge to its right edge + 2*ox (the same for both modes).
- A partial dirty rectangle of a stretched panel comes only from
  the text window (`InvalidateMainGameActionPanelRect` for NPCs), and that window lives in
  centered coordinates with edges +-ox - so it is marked in the
  CENTER area (`Controls::RedrawControls`).
- Overridden `Redraw` methods (their own drawing bypassing `Controls::Redraw`) got
  `CanvasDrawScope(m_layoutAnchor)`; the direct erasing of the transcript is there too.
- Text windows: in NPC conversation and in item selection this is the main log window,
  it is already widened (`SetMainTextBoxRegionBounds`) and fits exactly into the
  stretched middle (scroll arrows at its right edge). The spell
  book has its own window `(0xea..0x18c)`, now also wider by +-ox.
- The keyword input field (SGP field, `Text_Input.cpp`) got an anchor in
  its mouse region: `SetTextInputFieldLayoutAnchor`; field drawing, the caret
  and mouse selection are computed with this anchor.

### Per sub-screen: what goes where

Canvas coordinates; ox = 64 at W = 768, ox = 108 at W = 856. The wide panel is
from 23 to W-23 (768: 23..745, 856: 23..833), y 358..450.

| Sub-screen | Left (LEFT) | Middle | Right (RIGHT) |
|---|---|---|---|
| NPC conversation: topic menu, services, transcript, trade/give/sell (`CreateNpcDialogueControls`) | panel 0: NPC name, action buttons, "back" button, 6 item filters; 23..164 | panel 1 **stretched**: conversation text, item/service list, price column, arrows; 164..604 (768) / 164..692 (856); text 168..580 / 168..668, line wrap 402 / 490 px instead of 274 | panels 2-6 at the right edge: keyword transcript (expands upward over the right column of portraits), sort and category buttons, right image of the topic menu, item and price in trade, word input panel with input field; 604..745 / 692..833 |
| Spell book (`CreateSpellCastingViewControls`) | panel 0: six magic schools with animated icons; 23..230 | panel 1 **stretched**: spell list and cost on the right; 230..547 / 230..635, text 234..524 / 234..612 (was 234..396) | panel 2: power pips (round regions), name/cost, "cancel"; 548..744 / 636..832 |
| Item selection (`CreateUseItemSelectControls`) | panel 0: "own/shared", caption; 23..164 | panel 1 **stretched**: item list (main log window); 164..604 / 164..692 | panel 2: item icon, filters, "cancel"; 604..745 / 692..833 |
| Lock (`W8LockInteraction`) | character info (skill, spell chance, power); 23..211 | the pin mechanism **centered** (pins sit at their places on the background): image 275..551 / 319..595, pins 315..531 / 359..575; the gaps are a **continuation of the black casing**: the image's left edge (stone, 4 px) at 211, then repeated black with the bottom rail; on the right repeated black, frame and stone (9 px) at 606..615 / 694..703 | spell/power/item/done buttons; 615..745 / 703..833 |
| Trap (`W8MainGameScreen`) | status panel (character, skill, spell chances); 23..211 | device panel **stretched** (211..615 / 211..703): frame with 8 icons and the check bar on the left (211..348), black list field 351..611 / 351..699; trap list wider (353..591 / 353..679, region and drawing), scroll bar at the right edge of the field 592..610 / 680..698 (RIGHT anchor) | action buttons; 615..745 / 703..833 |

### Background slices (fix after review, 2026-10-12)

The review found: for the trap the right gap was filled by repeating 8 px taken 4 px
inside the image's right edge, and that is where the list field's frame is (stripes instead of
background). The sub-screen images were extracted from `DATA.SLF` (a copy of the Russian 1.2.6 in
`build\rus`, `scripts\tools\slf_extract.py`, 8-bit STI converted to PNG) and
checked by assembling the bottom panel at 768 and 856 before changing the code. The result is the table
`s_subscreen_art_cuts` in `MainGameLayout.cpp` (an entry applies only if the
image width matches; otherwise the old middle 16 px / 8 px edges):

| Image (object, frame) | Width | Mode | Slice / edges | Why |
|---|---|---|---|---|
| `Npc_bottompanel.sti` (0x1a9, 1) | 312 | STRETCH | repeat 100..197 (97 px) | the texture repeats exactly every 97 px - a one-period slice without seams; the old 148..164 hit a dark crack (stripes every 16 px) |
| `item_bottompanel.sti` (0x97, 1) | 312 | STRETCH | 100..197 | the same texture |
| `MagicBottomNew.sti` (0x190, 1) | 190 | STRETCH | 61..141 (80 px) | no period; a wide slice with the least visible seam gives fewer repeats |
| `traps_bottompanel.sti` (0x1b1, 1) | 276 | STRETCH | 152..184 (32 px) | inside the black list field (140..271); the icon frame on the left 0..137 is not stretched |
| `lockpick_bottompanel.sti` (0x1af, 1) | 276 | CENTER_FILL | edge 0..4 to the left gap, repeat 4..9; repeat 267..272, edge 267..276 to the right gap | the black casing of the mechanism is extended, frame and stone stay at the edges; the old slices 4..12 and 264..272 touched the cylinder/frame and the rail |

The trap was switched from CENTER_FILL to STRETCH: the icons and the check bar sit
not on the list field's background but in their own frame on the left, so what can be stretched is
the list field itself (like the log). For this: the trap list
(`W8MainGameTextKeyHandler`) is wider by 2*ox - the region (`StretchWidgetRegion`) and
the fill/text (`Redraw`, via `SubscreenPanelStretch`); the scroll bar
(`m_range`, a separate `W8RangeControl` panel) is anchored RIGHT and sits at the
field's right frame, as in the original; the check bar and the highlight of the icon frame
are drawn in the panel's anchor area (`W8MainGameTextPanel::Redraw`).

Deliberately unchanged (they do not replace the bottom panel and do not produce black bars):

- the party movement panel in combat (y 319..339, above the bottom panel) - centered
  over the widened 3D view;
- the formation window (button on the formation board) - a centered modal window;
- the monster list in combat (x 250, y 25..) - text over the widened 3D view,
  centered, as before.

### Where the code is (functions and lines after the commits)

| File:line | Function | What |
|---|---|---|
| `include\wiz8\local_code\Controls.h:58` | `W8PanelWideMode` | panel background modes |
| `include\wiz8\local_code\Controls.h:93` | `Controls::m_wideMode` | padding byte |
| `include\wiz8\local_code\Controls.h:132` | `Controls::DrawBackground` | declaration |
| `src\wiz8\local_code\Controls.cpp:68, 88` | `Controls` constructors | `m_wideMode = 0` |
| `src\wiz8\local_code\Controls.cpp:2001` | `Controls::RedrawControls` | wide background marking, partial rectangle of a stretched panel centered |
| `src\wiz8\local_code\Controls.cpp:2036` | `Controls::Redraw` | background via `DrawBackground` |
| `src\wiz8\local_code\Controls.cpp:2057` | `Controls::DrawBackground` (new) | background per mode |
| `include\wiz8\local_screens\MainGameLayout.h:95-133` | `W8SubscreenPlacement` and declarations | sub-screen API |
| `src\wiz8\local_screens\MainGameLayout.cpp:244, 264, 288` | `W8SubscreenArtCuts`, `s_subscreen_art_cuts`, `FindSubscreenArtCuts` (new, review) | background slices per image |
| `src\wiz8\local_screens\MainGameLayout.cpp:303` | `PlaceSubscreenPanel` (new) | anchor + background mode |
| `src\wiz8\local_screens\MainGameLayout.cpp:336` | `FillCanvasWithImageSlice` (new) | slice repeat in a canvas strip |
| `src\wiz8\local_screens\MainGameLayout.cpp:368` | `SubscreenArtGeometry` (new) | image size and own offset |
| `src\wiz8\local_screens\MainGameLayout.cpp:386` | `DrawSubscreenPanelArt` (new) | stretched background / gaps (3 pieces + 2 repeats) |
| `src\wiz8\local_screens\MainGameLayout.cpp:456` | `InvalidateSubscreenPanelArt` (new) | marking the full width |
| `src\wiz8\local_screens\MainGameLayout.cpp:476` | `StretchWidgetRegion` (new) | child region +2*ox (outside the layout - as in the original) |
| `src\wiz8\local_screens\MainGameLayout.cpp:493` | `SubscreenPanelStretch` (new, review) | 2*ox for a stretched panel in layout A, otherwise 0 |
| `src\wiz8\local_screens\MainGameLayout.cpp:501` | `SetBottomPanelRegionBounds` (new) | region of the whole panel +-ox |
| `src\wiz8\local_screens\MainGameLayout.cpp` | `ClearBottomPanelAroundSubscreen`, `IsBottomPanelSubscreenActive` | removed |
| `include\wiz8\text_input.h` | `SetTextInputFieldLayoutAnchor` | declaration |
| `src\wiz8\local_code\Text_Input.cpp:892, 897` | `FieldMouseX`, `SetTextInputFieldLayoutAnchor` (new) | mouse x in field coordinates, field anchor |
| `src\wiz8\local_code\Text_Input.cpp:908, 974, 1358` | `MouseMovedInTextRegionCallback`, `MouseClickedInTextRegionCallback`, `SelectAllText` | caret/selection position from `FieldMouseX` |
| `src\wiz8\local_code\Text_Input.cpp:1084, 1113, 1204` | `RenderBackgroundField`, `RenderActiveTextField`, `RenderInactiveTextFieldNode` | drawing in the field's anchor area |
| `src\wiz8\local_screens\NPCInteractionSubscreen.cpp:201` | `W8NpcTypedDialoguePanel::SetEnabled` | input field anchor |
| `src\wiz8\local_screens\NPCInteractionSubscreen.cpp:221, 276` | `W8NpcTypedDialoguePanel::Redraw`, `W8NpcDialogueOptionsPanel::Redraw` | panel anchor area |
| `src\wiz8\local_screens\NPCInteractionSubscreen.cpp:675` | `OpenNpcDialoguePanel` | region 0x8a via `SetBottomPanelRegionBounds` |
| `src\wiz8\local_screens\NPCInteractionSubscreen.cpp:878` | `CreateNpcDialogueControls` | places of the seven panels, text region, region 9 |
| `src\wiz8\local_screens\NPCInteractionSubscreen.cpp:1332` | `IsPortraitObscuredByNpcDialogue` | the original's check again (transcript on the right) |
| `src\wiz8\local_screens\NPCInteractionSubscreen.cpp:1367` | `ActivateNpcDialoguePanels` | regions follow the current state on a full redraw |
| `src\wiz8\local_screens\NPCInteractionSubscreen.cpp:2294, 4567, 4996` | `CloseNpcDialogueTranscriptLayout`, `SetNpcDialogueHidden`, `SetNpcDialoguePanelVisible` | erasing the transcript at the right edge |
| `src\wiz8\local_screens\MainGameScreen.cpp:874, 1916` | `W8LockInfoPanel::Redraw`, `W8MainGameStatusPanel::Redraw` | texts in the anchor area |
| `src\wiz8\local_screens\MainGameScreen.cpp:891` | `W8LockInteraction::W8LockInteraction` | places of the lock panels |
| `src\wiz8\local_screens\MainGameScreen.cpp:1399` | `W8MainGameTextKeyHandler::Redraw` (review) | trap list wider by 2*ox |
| `src\wiz8\local_screens\MainGameScreen.cpp:1705` | `W8MainGameTextPanel::Redraw` (review) | check bar and highlight in the panel's anchor area |
| `src\wiz8\local_screens\MainGameScreen.cpp:1933` | `W8MainGameScreen::W8MainGameScreen` | places of the trap panels; (review) device panel STRETCH, scroll RIGHT, list region wider |
| `src\wiz8\local_screens\MainGameScreen.cpp:2560, 2669, 2744` | `W8NpcDialogueTextController::Redraw`, `Collapse`, `ClearBackground` | transcript at its own edge |
| `src\wiz8\local_screens\MainGameScreen.cpp:3610` (~3733) | `ApplyMainGameRedrawFlags` | removed erasing of the bars next to the sub-screen |
| `src\wiz8\local_screens\MGSSpellCasting.cpp:116` | `CreateSpellCastingViewControls` | places of the three panels |
| `src\wiz8\local_screens\MGSSpellCasting.cpp:285` | `OpenSpellCastingView` | spell list window +-ox |
| `src\wiz8\local_screens\MGSSpellCasting.cpp:1049` | `PreviewSpellPowerPipHover` | fill of the name plate at the right edge |
| `src\wiz8\local_screens\MGSUseItemSelect.cpp:99` | `CreateUseItemSelectControls` | places of the three panels |

### Risks, what to check in-game

1. Not a single game frame has been seen. The **slices** are now chosen from the
   images themselves (see "Background slices") and checked by assembling PNGs, but the images are taken
   from the Russian 1.2.6 (`build\rus`), not from GOG 1.2.4 in `games\work` (that one was not
   touched). The widths match what the code expects; if an image in GOG has a
   different width, the table entry will not apply and the middle 16 px will come back - for
   the trap that is the junction of the icon frame and the list field (stripes). The weak
   repeatability of the spell book texture (80 px slice with no period) may
   be noticeable on a uniform area. The fix is the `s_subscreen_art_cuts` table.
2. Image widths are taken from the files (`GetCatalogImageSize`); if the left/right
   image of a sub-screen is narrower than its panel, there will be a gap between it and the stretched middle
   (in the original it would not look any different from now: the same images).
3. A partial dirty rectangle of a stretched panel is treated as
   centered (that is how the NPC text window works; of the four stretched panels -
   NPC, spells, item, trap - only NPC calls `Controls::Invalidate(rect)` with a
   rectangle, verified by search). If another source of
   partial rectangles for the middle panel appears, its area will be updated
   shifted by ox (symptom: text does not update until the next full
   redraw).
4. The NPC transcript at 856 now covers the right portraits 3/5/7 (as in the
   original); previously (centered) it did not. This is intentional: the right column of the
   sub-screen sits above the formation board.
5. Lock: the middle is not stretched (the pins sit at their places on the background), the gaps are a
   continuation of the casing. Trap (review): the device panel is stretched, its
   list and scroll bar are shifted/widened - this is new code, check
   S30-S31 especially: scrolling (arrows, thumb, wheel), selecting a row
   by clicking across the full width, highlighting the row under the cursor, the thumb's trail while
   dragging (its old place is erased by the thumb's own fill - in
   its own anchor area).
6. Keyword input field: hit-testing and drawing follow the anchor; if
   some path in `Text_Input.cpp` reads `gusMouseXPos` bypassing `FieldMouseX`,
   the caret on click will land shifted by ox (5 places checked - all
   converted).
7. The radar and the formation board (2D render sprites) - the original hides them while a
   sub-screen is open; if not, they will be on top of the left/right part of the sub-screen.
8. If an NPC conversation is started outside the main screen and continued on it (or
   vice versa), the stretched regions are recalculated on the first full
   redraw (`ActivateNpcDialoguePanels(true)`); the spell book window -
   only when it is opened.

### LIVE TEST CHECKLIST for sub-screens

Setup: `Wiz8Runtime.exe` + `wiz8wide.ini` in `games\work` (as in the general
checklist). Runs: `Width=768` (main), `Width=856`, `Width=640`
(regression). It is convenient to stand by a merchant (Arnika) and by a locked chest/door with
a trap. "Correct" for every item: no black bars in the bottom
panel between the outer strips, no HUD leftovers (radar/log/board)
inside the sub-screen, after closing - a normal wide panel without garbage.

| # | What to do | Expected result (768 / 856) |
|---|---|---|
| S1 | Talk to an NPC (topic menu) | on the left (23..164) the NPC name and buttons, the middle stretched to 604 / 692 without a seam, on the right (604..745 / 692..833) the right menu image; the line text in the middle wraps at the wide line width |
| S2 | Buttons on the left: "services", "talk", "leave", "attack", etc. | hover highlights the button under the cursor, the tooltip is next to it, clicks work |
| S3 | Go to conversation (transcript) | on the right the keyword list expands upward over the right column of portraits (portraits 3/5/7 under it are hidden, as in the original), below it the sort/category buttons and the word input panel |
| S4 | Click a word in the line text (in the middle, including the stretched right part) | the word is highlighted and goes into the input field; double click - ask |
| S5 | Click a word in the transcript, wheel over the transcript, transcript arrows | exactly the word under the cursor is selected, the list scrolls |
| S6 | Category buttons (people/places/items/misc/all) and sorting | they work, the list is filtered |
| S7 | Input field: click into it, type a word, click with the mouse inside the text, select with the mouse | the caret lands under the cursor (not shifted by ox), selection follows the mouse, Enter/"ask" button work |
| S8 | Right mouse button (hide the conversation) and bring it back | the transcript and the right panel go away without garbage, the portraits on the right are visible; returning restores everything |
| S9 | Scrolling the conversation text: arrows at the right edge of the middle, wheel, thumb | all at the right edge of the stretched middle, works |
| S10 | Trade: buy/sell/give/steal | on the left the mode and filter buttons, in the middle the item list across the full width, prices at the right edge of the list; on the right the selected item's icon, price, gold, buttons |
| S11 | Click an item row, Shift+click, double click, right click (identify) | the row under the cursor is selected across the full width; identify opens |
| S12 | Item filters (hands/body/accessories/other/character/party) | the buttons on the left are clickable, the list is rebuilt |
| S13 | Entering a quantity/gold (split window) | window centered, buttons work |
| S14 | Drag an item from the hand (item on the cursor) onto the NPC / into the trade | works as before |
| S15 | Services (healing, removing curses) | on the left a list of buttons, on the right an image, clicks work |
| S16 | Close the conversation (leave / Esc) | the bottom panel again: radar on the left, wide log, board on the right, no sub-screen pieces; portraits on the right normal |
| S17 | Spell book (spells button) | on the left six schools (23..230), the middle with the list stretched (to 547 / 635), on the right the power pips, name, "cancel" (548..744 / 636..832) |
| S18 | Pick a school, hover/click list rows | long names "(target) name" are fully visible, the cost at the right edge of the list; hover and click across the full row width |
| S19 | Hover the power pips | the name plate shows the cost without garbage (fill at the right edge), tooltips next to them |
| S20 | Pick a power, cast, right click on a row (spell info) | everything works, the info window is centered |
| S21 | Scrolling the spell list (arrows at the right edge of the middle, wheel) | works |
| S22 | "Cancel" / close the book | the wide HUD panel is restored |
| S23 | Spell book in combat, switching characters in combat | the same, without garbage |
| S24 | Item selection ("use" button) | on the left "own/shared" (23..164), the middle with the item list across the full width (to 604 / 692), on the right the icon, filters, "cancel" |
| S25 | Toggle "own/shared", filter, click a row, right click (identify) | everything works in its place |
| S26 | Close item selection | the wide panel is restored |
| S27 | Lock: walk up to a locked chest/door | on the left the character info, on the right the buttons, the pin mechanism centered; the black casing of the mechanism reaches the side panels (on the left a narrow stone border at 211, on the right the frame and border at 606..615 / 694..703), the light bottom rail runs through the gaps; no vertical stripes in the gaps |
| S28 | Click pins, "power", "spell" (switch to the book), "item" (switch to item selection), "done" | clicks land; switching to the book/item and back without garbage |
| S29 | Open the lock / leave | the wide panel is restored |
| S30 | Trap: disarm a trap on a chest | on the left the character status, right after it the frame with 8 icons (211..348), the black list field extends to the buttons on the right (to 611 / 699) without stripes or seams; the scroll bar at the field's right frame (592..610 / 680..698) |
| S31 | Device icons, trap list: hover (yellow row), click a row (including in the right part of the wide list), arrows, thumb (drag), wheel, up/down keys; "inspect", "spell", "item", "done" | clicks land; the row is highlighted across the full list width; the thumb moves without a trail; the check bar runs in the icon frame on the left; the icon frame highlight (blinking after a choice) is in place |
| S32 | Trap triggered / disarmed | the wide panel is restored |
| S33 | Combat: party movement panel (forward/back) | centered above the bottom panel, as before, buttons work |
| S34 | Combat: monster list (top left of the 3D view) | in place, clicks on rows work |
| S35 | Formation window (click on the formation board) | centered, as before |
| S36 | Switching sub-screens in a row: conversation -> trade -> conversation -> close; book -> close -> item -> close | at every step no leftovers of the previous sub-screen |
| S37 | Saving/loading during a conversation is not possible; after closing - the thumbnail is normal | unchanged |
| S38 | `Width=856`: S1, S3, S10, S17, S24, S27, S30 | all the same; the right edge (the 7th partial canvas tile) without garbage |
| S39 | Camp: spell book / item selection from camp | centered, as before (layout A is off in camp) |
| S40 | `Width=640`: S1-S32 | everything as in the original (no offsets, no stretching, texts wrap at the old width) |

## Wide fullscreen backgrounds (W > 640), 2026-10-12

Commits in `decomp`: `e111c81` (shared mechanism), `412bb8c` (main menu
on the shared mechanism), `c4c128b` (camp picture), `1fd8dfd` (camp without
a pair - as before, stretched). The game was **not run** -
everything is from reading the code; check with the W1-W16 checklist at the end of the section.

### What the player sees

Fullscreen 640x480 pictures (level loading screens, camp, party death,
endings, main menu) used to sit in the center with black bars.
If the picture has a **wide pair** lying next to it, the wide canvas draws
the pair instead - across the full width, all W columns. No pair - everything as before. Text and
decorations on top (loading gears and progress bar, level name, death screen
caption, ending text, menu items) stay in their places in the
center.

### How to name the file

| What | Rule |
|---|---|
| Name | original name + `_<W>`, same extension: `ARNIKA.STI` -> `ARNIKA_768.STI` and `ARNIKA_856.STI` |
| Folder | the same as the original's inside `Data`: `Data\LEVEL LOAD\`, `Data\OPTIONS\` (a separate file next to the game; can also be inside an SLF) |
| W | canvas width from `wiz8wide.log` (`[Canvas] ... W=768`): 768 (16:10) or 856 (16:9); each width has its own pair |
| Format | 16-bit STI (RGB 5:6:5, flag `STCI_RGB`, uncompressed), **exactly W x 480**. This is what `scripts\art\artkit.py tosti <png> <original.sti> <output.sti>` produces (the header is taken from the original) and `scripts\finish_levelload.ps1` (removed after 1.0.0, available in git at tag 1.0.0) |
| Letter case | does not matter (Windows): the game catalog asks for `Data\Level Load\Marten's Bluff.sti`, `MARTEN'S BLUFF_768.STI` will do |

A file of a different size or color depth is not used (the reason is written to the
log), and the game draws the original.

### Where it works

The mechanism is shared: **any** 16-bit 640x480 picture from the catalog
(`g_video_frames`) that the game draws whole at point (0,0) of the window gets
a wide pair if one exists. Currently these are:

| Screen | Picture (`Data\...`) | Where it is drawn |
|---|---|---|
| Level loading (33 backgrounds from the `g_level_backdrops` table) | `Level Load\Arnika.sti` ... `Level Load\Wilderness Clearing2.sti` | `DrawPleaseWaitScreen` (`PleaseWaitScreen.cpp:189`) |
| Level loading without its own background, game saving (same screen) | `Options\intro_bg.sti` (fallback background 0xe4) or the current level's background | same place |
| Party death | `Level Load\DeathScreen.sti` | `DrawPartyDeathScreen` (`ReviewCharacterScreen.cpp:2735`) |
| Endings | `Level Load\DarkLord.sti`, `Cosmic ending.sti`, `BlowOut.sti`, `DeathScreen.sti` | `ShowEndingScreen` (`ReviewCharacterScreen.cpp:2823`) |
| Main menu | `Options\intro_bg_text.sti` -> `INTRO_BG_TEXT_<W>.STI` (the same file as before) | `MainMenuScreenEnter` / `MainMenuScreenFrame` (`MainMenuScreen.cpp:170, 249`) |
| Camp (rest) | `Level Load\Camping Screen.sti` | `UpdateSurpriseFade` (`MainGameScreen.cpp:8452`) - a special path, see below |
| Incidentally, if pairs appear | credits `Options\intro_bg_credits.sti`, options and other 640x480 backgrounds from the catalog | their normal `DrawCatalogImage` calls |

### How it works (for understanding the code)

A web analogy: every `<img src="x.png">` picture got an
optional "wide screen" `srcset` - `x_768.png`. The game still
asks for `x.png`; one intermediary function (`DrawCatalogImage`) checks whether
a wide variant exists, and if it does, draws it across the full width of the "page".

1. **Hook.** All such backgrounds are drawn by one catalog function
   `DrawCatalogImage` (`VideoObjectManager.cpp:816`). Before the normal blit it
   calls `DrawCatalogSurfaceWide` (`:770`), which fires only if all of these hold
   at once: the canvas is wider than 640; the target is `FRAME_BUFFER`; point (0,0); the blit is "the whole
   picture as is" (no regions, sub-rectangles, fills, mirroring);
   the 2D drawing origin is the normal window (not a piece of the layout A HUD); the source
   surface is 640x480, 16-bit. Then `DrawWideFullscreenArt(path)`; if there is no
   pair - the normal `BltVideoSurface`, as in the original.
2. **Cache** (`WideArt.cpp`, like a `Map` in JS): the key is the original's path. The first time,
   the pair is looked up (`FileExists`: first the file on disk, then the SLF) and read by
   the game's own STI loader (`CreateImage`) - it converts 5:6:5 colors to
   the screen format exactly the same way as for original surfaces (black
   stays 0, everything else becomes 5:5:5 + alpha bit). "No pair" is also remembered -
   the file is not looked up every frame. At most 6 pictures are kept in memory
   (~0.75 MB each at 768); the oldest is unloaded and read again the next time
   it is encountered. Each lookup is written once to `wiz8wide.log`:
   `[WideArt] Data\Level Load\Arnika_768.sti: loaded 768x480`,
   `...: no file, original 640x480 is used` or
   `...: ignored, need 16-bit 768x480, file is ...`.
3. **Drawing.** Pixels are copied row by row into the **whole** canvas surface
   (`LockPrimarySurfaceFull`), like SGP's 16->16 blit - without transparency.
   The side bars are marked for refill (`InvalidateCanvasSideBars`,
   `Video2.cpp:2403`; the normal `InvalidateCanvas` would skip them if
   the page is already marked "entirely dirty" - outside layout A this flag
   only means the 640 window). The center is marked by the calling code itself, as for the
   original (`DrawCatalogImageAndInvalidate`, `ResetTransientRenderScenes`).
4. **Leaving the screen.** The module remembers "a wide background is in the bars".
   `ReleaseWideFullscreenArt` (`WideArt.cpp:190`) in that case fills the bars
   with zeros (`CanvasClearSideBars`) and marks them for refill. It is called in
   `GameLoop` before entering **any** next screen (`Gameloop.cpp:172`) -
   level loading -> game, death/ending -> menu/credits, menu -> anything.
   The main menu additionally, as before, clears the bars and refills
   the whole canvas in `MainMenuScreenLeave` (`MainMenuScreen.cpp:379`).
   The death screen and endings live inside the main game screen: their bars are cleared
   when the game leaves the main game screen after them (`EndReviewTransition` ->
   `ResetMainGameMode` -> `RequestScreenTransition`) - until then, in the last
   frame of the fade-out the bars match the center.
5. **Camp - a special path.** The camp picture is not drawn into the 2D window: it is
   a separate render layer (`stSurface2D` in the `g_scene_fullscreen` scene),
   which stretches its surface over the whole screen (0..1 on both axes),
   under the HUD. Previously, at W > 640 the 640x480 surface was stretched across the full
   width (the picture squashed/stretched by 1.2-1.34x). If there is a wide
   pair `Camping Screen_<W>.sti`, `BuildWideFullscreenOverlay`
   (`WideArt.cpp:200`) returns a W x 480 copy of it, and the layer is built W wide - over
   the whole screen without distortion. The buffer belongs to the module and is not freed
   (the render layer holds a pointer to it while it is alive). **No pair** or
   W = 640 - the function returns 0, and the layer is built from the 640x480 original, as
   before (at W > 640 it is still stretched across the full width). The first version
   (`c4c128b`) without a pair put the original in the center with black margins; this
   changed the look without any new files, fixed in `1fd8dfd`.
6. **Main menu.** Its own reading of `INTRO_BG_TEXT_<W>.STI` (raw pixels,
   alpha bit on all of them, including black ones) was removed: the menu draws catalog picture
   0xe8 like the original, and the wide pair is substituted by the shared mechanism. The file name is
   the same. The only difference is that black (0x0000) now stays 0, as in the
   original surface; in the menu the canvas is opaque - on screen it looks the same.

At W = 640 (`ox = 0`) the hook does not fire, `ReleaseWideFullscreenArt`
does nothing, and the camp layer is built as in the original.

### Where the code is (functions and lines after the commits)

| File:line | Function | What |
|---|---|---|
| `include\wiz8\wide_art.h` (new) | API | naming convention, 4 functions |
| `src\wiz8\engine_code\WideArt.cpp:42` (new) | `MakeWidePath` | `X.sti` -> `X_<W>.sti` |
| `src\wiz8\engine_code\WideArt.cpp:57` | `LoadWideArt` | lookup and reading of the STI with the game's loader, size check, log line |
| `src\wiz8\engine_code\WideArt.cpp:97, 117` | `TrimDecoded`, `FindEntry` | cache: at most 6 pictures, 64 paths |
| `src\wiz8\engine_code\WideArt.cpp:147` | `FindWideFullscreenArt` | the pair's pixels or 0 |
| `src\wiz8\engine_code\WideArt.cpp:167` | `DrawWideFullscreenArt` | copy over the whole canvas, marking the bars |
| `src\wiz8\engine_code\WideArt.cpp:190` | `ReleaseWideFullscreenArt` | clear the bars if a wide background is there |
| `src\wiz8\engine_code\WideArt.cpp:200` | `BuildWideFullscreenOverlay` | W x 480 copy of the pair for the camp layer; without a pair 0 (original as before) |
| `src\wiz8\sources.cmake:173` | - | `WideArt.cpp` |
| `src\wiz8\local_code\VideoObjectManager.cpp:770` | `DrawCatalogSurfaceWide` (new) | hook conditions |
| `src\wiz8\local_code\VideoObjectManager.cpp:816, 836` | `DrawCatalogImage` | hook call before `BltVideoSurface` |
| `src\wiz8\engine_code\Video2.cpp:2403` | `InvalidateCanvasSideBars` (new) | marking both bars bypassing the "whole page" flag |
| `include\wiz8\engine_code\Video2.h` | - | declaration of `InvalidateCanvasSideBars` |
| `src\wiz8\engine_code\Canvas.cpp:64`, `include\wiz8\canvas.h` | `CanvasLogLine` (new) | a line in `wiz8wide.log` |
| `src\wiz8\local_code\Gameloop.cpp:172` | `GameLoop` | `ReleaseWideFullscreenArt` before the new screen's `enter()` |
| `src\wiz8\local_screens\MainMenuScreen.cpp:170, 249` | `MainMenuScreenEnter`, `MainMenuScreenFrame` | `DrawCatalogImage(0xe8)` again, `DrawMainMenuBackground` removed |
| `src\wiz8\local_screens\MainMenuScreen.cpp:379` | `MainMenuScreenLeave` | + `ReleaseWideFullscreenArt` |
| `src\wiz8\local_screens\MainGameScreen.cpp:8452` | `UpdateSurpriseFade` | camp layer W wide if there is a pair |

### Risks, what to check in-game

1. Not a single frame has been seen. The mechanism is verified only by building and reading
   the code; the header of the finished `INTRO_BG_TEXT_768.STI` was checked (STCI, RGB,
   5:6:5 masks, 16-bit, 768x480, uncompressed) - the game's loader will read it.
2. **Center seam.** The whole pair is drawn, including the 640 center. If the pair's center
   differs from the original (the extension painting touched the strip near the edges), and the screen
   then redraws pieces of the center from the original surface, a seam will be
   visible. The loading, death, ending and camp screens have no such redraws;
   the main menu redraws only its items (as before).
3. **Camp without a pair** - as before the mod: 640x480 stretched across the full width
   (1.2-1.34x distortion). Removed only by installing
   `CAMPING SCREEN_<W>.STI` (`scripts\finish_levelload.ps1`, removed after 1.0.0; ready files are in `assets\`).
4. Camp at 856: the layer is 7 tiles of 128 (the last one partial, 768..896) - the same
   case as the canvas itself at 856 (risk 2 of the general section).
5. Pictures drawn with transparent (black, 0x0000) pixels, in
   screens with an alpha test (death and endings over the main game screen), are transparent
   both on the sides and in the center - as in the original in the center.
6. If some screen draws a 640x480 background every frame and it has a pair,
   W x 480 pixels are copied every frame and the bars are refilled
   (2 x ox x 480) - cheap, but noticeable in a profile.
7. The first appearance of each picture reads the file (~0.75 MB) right during
   drawing - a short pause on the loading frame, like the first load of the
   original.

### LIVE TEST CHECKLIST for wide backgrounds

Preparation: `Wiz8Runtime.exe` + `wiz8wide.ini` in `games\work` (as in the general
checklist); pairs `*_768.STI` / `*_856.STI` in `games\work\Data\LEVEL LOAD\` and
`games\work\Data\OPTIONS\` (`scripts\finish_levelload.ps1`, removed after 1.0.0; ready files are in `assets\`). Runs:
`Width=768`, `Width=856`, `Width=640`. After each run open
`games\work\wiz8wide.log` and find the `[WideArt]` lines.

| # | What to do | Expected result |
|---|---|---|
| W1 | Launch, main menu (768) | background across the full width without bars, as before the change; menu items centered, highlighting works; in the log `[WideArt] Data\Options\intro_bg_text_768.sti: loaded 768x480` |
| W2 | From the menu open and close a dialog (message), go into options/load and come back | the menu background is fully redrawn, without black bars; in options/load the bars are black (if their backgrounds have no pairs), with no leftovers of the menu background |
| W3 | Load a save (level loading screen) | level background across the full width; gears, progress bar and the "Loading..." caption centered at the bottom, as before; gears spin without garbage; `loaded` in the log for the level background |
| W4 | After loading - main game screen (layout A) | HUD at the edges, world at the edges of the 3D view, **no pieces of the loading background** in the side parts (neither in 3D nor under the HUD) |
| W5 | Move to another zone (through a zone exit) | loading screen with the new zone's background across the full width; after loading - a clean main game screen |
| W6 | Save the game from the main game screen (the "saving" screen = the same loading screen) | current zone background across the full width, after saving - a clean main game screen |
| W7 | Enter the same zone again | no pause for reading the file (cache); no repeated log line for this file |
| W8 | Camp (rest button) with the pair `Camping Screen_768.STI` | after the fade, the camp picture over the whole screen without distortion, HUD on top at the edges; when the rest ends (or on an ambush) - the world, with no leftovers of the picture |
| W9 | Camp **without** the pair (temporarily rename it) | as before the mod: the 640x480 picture stretched across the full width, without black bars; `no file` in the log for `Camping Screen_<W>.sti` |
| W10 | Party death (or a test: lose a fight) | death screen across the full width, caption bottom right in the 640 window, no HUD leftovers on the sides; on a key press - fade and exit to the menu, the menu has its own background without pieces of the death screen |
| W11 | Ending (save before the finale) | ending picture across the full width, text centered; transition to the credits - the credits have black bars (or their wide background if there is a pair) |
| W12 | A zone that has no pair (temporarily remove the file) | 640x480 background centered with black bars, as before; in the log `no file, original 640x480 is used` |
| W13 | A pair of the wrong size (for example, `_768` at 856) | ignored, background centered; in the log `ignored, need 16-bit 856x480, file is 16-bit 768x480` |
| W14 | `Width=856`: W1, W3, W4, W8, W10 | the same with `_856` files; right edge (7th partial tile) without garbage |
| W15 | `Width=640` | everything as in the original: no `[WideArt]` in the log, camp 640x480 over the whole screen |
| W16 | Alt+Tab on the loading screen and in the main menu | after returning, the background is intact across the full width |

## 2D layer seams at 128 tile joints (2026-10-12, commit `644b020`)

**What was visible.** Thin vertical lines on the canvas at x = 128, 256,
384, 512, 640 and horizontal ones at y = 128, 256, 384 - on any 2D (menu,
HUD, windows). The player took them for seams in the menu background extension. The background file itself is
clean (checked column by column); the lines came from the output.

**Cause.** `stSurface2D` cuts the W x 480 2D surface into 128x128 textures
(`WRAP_CLAMP`) and draws each as its own quad. When stretched to 2560x1600
with a bilinear filter, texels of neighboring tiles do not blend, and there is
a kink at the joint. In the original with 640x480 output at 1:1 this is not visible.

**Fix.** `[Display] SingleTexture2D=1` (default): the tile side
`SurfaceTileExtent` (`Video2.cpp`) is the nearest power of two covering
the whole layer (1024 for 768/856 x 480), if the renderer supports it
(`srGERD::getMaxTextureWidth/Height`, 2048 under dgVoodoo). Otherwise 128, as
before. The same for the camp picture layer (`MainGameScreen.cpp`). Texture texels
beyond the picture edge (x >= W, y >= 480) are filled by extending
the edge column/row (`ExtendTileEdges` in `surface2d.cpp`, two texels;
`updateRectangle` extends the piece at the edge by the same amount), otherwise the filter
would mix garbage into the last column/row. In the log:
`[Display] SingleTexture2D: 768x480 layer -> one texture 1024x1024 (renderer max 2048x2048)`.

**Verified in-game** (games\ru, 768): menu screenshot - column by column, the gradient at
x = 128/256/384/512/640 dropped to the level of neighbors (it was 2.5-4x higher);
before/after screenshots `docs\screens\seams\menu_center_before_after.jpg`. Game from
a save, HUD, bottom right corner - without garbage. Speed (`[Debug] LogFps=1`):
menu ~4600 fps vs ~3290 with tiles, in game ~500-660 for both.

## Stone wings by the interface windows (2026-10-12, commit `2c227ee`)

**What is visible.** For fullscreen windows made of marble panels - inventory and
stats (the `CAMP` screen, also known as RCS), character creation (`CHARACTER`) and
party creation (`PARTY_SELECTION`), options and saves (`OPTIONS`), journal (`JOURNAL`),
the map with `WideAutomap=0` - the side bars instead of black are covered with dark
marble with a bevel at the window edge. The window looks like part of one stone wall.
The main game screen (layout A), menu, loading screens and credits are not touched.

**Picture.** `Data\Wide\WideFrame_<W>.sti` (16-bit, W x 480, the center is not
used). The marble was painted by Astra from an inventory screenshot; the bevel and
darkening toward the edge are added by `scripts\art\make_wings.py` (for 768 the
inner part of the 856 margins is used). Without the file - black bars, as before.

**Code.** `UpdateWideSideWings(screen)` (`WideArt.cpp`) is called from `GameLoop`
before the screen's frame. It draws only the bars, if the screen is in the list, layout A
is off, there is no wide background, and the wings are not there yet or have been cleared. "Cleared"
is detected by the counter `CanvasSideBarsClearCount()`: it is incremented by everything that
clears the surface or the bars (`ClearPrimarySurface`, `ResetVideoFrameState`,
`CanvasClearSideBars`, surface creation, `DrawWideFullscreenArt`).
`ReleaseWideFullscreenArt` on a screen change also removes the wings.

**Check in-game:** inventory from the game and during rest (whether the
camp picture covered anything needed), options from the menu and from the game, journal, character
creation; going back into the game with no marble leftovers in the HUD.

## Wide map (2026-10-12, commit `0c40537`)

**What is visible.** At W > 640 and `[Canvas] WideAutomap=1` (default) the map
field is extended by ox in both directions (game x 12-ox .. 467+ox instead of
12..467): the same scale, more of the map visible to the left and right. The button column is
pinned to the right edge of the canvas, the letter N is above the middle of the field.

**How it works.** For the duration of the map screen, canvas layout A is turned on
(`CanvasSetWideLayout(true)` in `AutomapScreenEnter`, turned off in
`AutomapScreenLeave`): the mouse sees the whole canvas, the 16 buttons have a RIGHT anchor.
The `MAP_BORDER` frame (catalog 0x14a) is drawn in pieces by `DrawAutomapBorderWide`
(`DrawCatalogImagePiece` from `MainGameLayout`): [0,218) at the left edge, N
[218,260) in the center, [260,640) at the right edge, the gaps - a repeat of the smooth piece
[150,210). The world snapshot (mode `g_automap_surface_mode`) is rendered into
a W x 480 surface in canvas coordinates (`RenderWorldToCanvasSurface`),
the camera plane is wider in x by (455+2ox)/455. All conversions cursor -> world,
markers, notes, note tooltips go through `AutomapWorldWidth()`,
`AutomapViewLeft/Right/Pixels()`; at ox = 0 they give the original's numbers.

**Risks:** not checked which map drawing mode is used under dgVoodoo
(`g_automap_surface_mode`; in the second mode the camera plane is set by someone
else); negative x of markers and note text at the left edge of the field.

## Wide windows: options and journal (2026-10-12)

**What is visible.** At W > 640 and `[Canvas] WideWindows=1` the options window and the journal
take up the whole canvas. In options the left column (computer and section buttons) is at
the left edge, the right panel is stretched to the right edge; setting labels on the left,
sliders, checkboxes, toggles and keys at the right edge; rows of the save
list across the full width (repeat of the [171, 299) piece of the row picture), the name field
is longer by 2*ox. In the journal the level column is on the left, the entries column is wider by 2*ox
(line wrapping in the journal is off - long entries are cut less),
the parchment is stretched, the bottom strip and the page strip are stretched, the mode and
exit buttons are at the right edge. The character screen (inventory etc.) and character creation
by the owner's decision stay 4:3 in the center with stone wings.

**How it works.** While shown, the window turns on canvas layout A
(`CanvasSetWideLayout`), panels with a stretched background get `m_wideMode =
W8_PANEL_WIDE_STRETCH`, children get a mouse region anchor
(`AnchorOptionsWidget` in OptionsScreen.cpp, `AnchorJournalControl` in
JournalScreen.cpp); the child is also drawn by it (`Controls::ChildLayoutAnchor`).
Labels of the options panel choose the edge by their alignment (`OptionsTextAnchor`).
Code that reads the cursor itself (`SGPMouseGetPos`) and subtracts the widget corner
also subtracts the anchor shift: the slider (`RangeThumbAnchorShift`, Controls.cpp),
the click on a save name. Everything drawn in the layout stays within game
0..640 of its anchor area (fills and pictures are clipped at 640); the save name
field is therefore anchored to the right edge with x shifted left.
Journal parchment: repeating a piece produced vertical stripes (the paper has a smooth
brightness gradient), so the 2*ox insert is filled by mirroring the columns before
the cut directly in the surface (`DrawJournalParchment`).

## Re-wrapping log lines to the width (2026-10-12)

The log stores messages already cut into lines by the width of the text window at the time
they were written, and they are stored the same way in the save. After a width change (a save from 4:3, the log in
layout A is wider) old lines wrapped too early. `ReflowMessageStorage`
(MGSTextBox.cpp) on entering the main game screen joins word-wrap continuations
(an entry with link > 0 that starts with a space) and cuts again with the
`ShowNotice` rule at the current width (windows 0, 1 and the conversation transcript 3; name
highlighting is carried over by offsets). At W = 640 the log of an original save is not touched
if it has no lines wider than the window.

## Hang during rest (port bug, 2026-10-12)

In a frame without game time, the speed of a walking NPC in `W8Navigator::UpdateNavigation`
is computed as 0/0 = NaN. The original compares via FCOMP + TEST AH,1, and for NaN
takes the minimum speed; the port kept NaN, and `W8GrCycle::TickAnimation`
spun the animation for 2^32 frames. Fixed with the comparison `!(speed >= minimum)`.

## Main menu items without a baked-in background (2026-10-12)

The menu item pictures `Data\Options\introtext_{normal,highlight,depressed,unavailable}.sti`
(in both the English and the Russian editions) are opaque 346x44 strips with a piece of
the original menu background under the letters. On the new menu background (a full repaint
by Astra) they were visible as rectangles. `scripts\menutext_alpha.py` (removed after 1.0.0, available in git at tag 1.0.0) made the background
transparent (letters, outline and highlight glow remain; the mask is by difference from
the original background), the files lie next to the game in `Data\OPTIONS` (a loose file
takes priority over the DATA.SLF archive), copies were in `art\menutext\{ru,work}` (the folder was removed). `DrawMainMenuItem`
restores the background under an item before drawing it (`RestoreWideFullscreenArtRect`, at W = 640 -
a piece of the original surface), otherwise a halo remains after highlighting.
**Package:** the pictures depend on the language; `make-package.ps1` (the old port package) did not include them; the hybrid package `scripts\build\make-hybrid-package.ps1` does not include them either
(ru/en needs to be chosen at install time).

## Party gets stuck on slopes: frame rate limit (2026-10-12)

On the beach by the chest (game start) the party could not start moving forward, while the original at the same
spot walked. The cause is the frame rate. The party's speed is reset to 0 if during
a frame it moved less than 0.1 world units (`AdvanceEnvironmentMotion`:
`motion_length <= 0.1`, and `UpdateMotionProgress(moved = 0)` zeroes
`camera_motion_velocity`). From standstill, the shift in the first frame = 112.5 * f * dt^2
(dt - `camera_scale`, tenths of a second; f - `motion_factor`, ~1 on the ground).
On a slope the ground touches the party every frame, and at dt < 0.03 (more than ~330 frames/s)
the shift is always below the threshold: speed never builds up. Memory measurement
(`scripts\play\frame_delta.ps1`): the original here runs ~220 frames/s (dt 0.045, passes),
the build without a limit - ~1000 frames/s (dt 0.01, got stuck).

The fix is the frame rate limit `CanvasLimitFrameRate` (Canvas.cpp,
called once per frame from `RenderFrame`): `wiz8wide.ini [Display] MaxFps`, by
default 120 (0 - no limit, 1..29 is raised to 30). Waiting via QPC,
`timeBeginPeriod(1)` + `Sleep(1)`, the last 2 ms `Sleep(0)`; a frame that is late
by more than one period resets the schedule (no burst of catch-up frames).

## Log background in layout A without the "accordion" (2026-10-12)

`main_textbox_back.sti` (384 px) was stretched by repeating the middle 16 px - their joint
did not match, and vertical stripes ran through the middle of the log. The dark texture
repeats every 97 px (as with the NPC and item panels), the slice `[152, 249)` from
`scripts\art\find_slice.py` tiles without a seam (MainGameScreen.cpp, `DrawCatalogImageWide(0x87 ...)`).

## Party in combat did not pick a target (decompilation bug, 2026-10-13)

`RepickActionTarget` (Targeting.cpp) aimed the new target into the context block `arg`
(the third argument, almost always 0 = "out of combat"), instead of the resolved context block.
The original 0x00536863 passes to `AimAtTarget` the value it itself wrote over
the context argument (the resolved context), and does the repeat check (0x00536891)
only for the "out of combat" context. In the port the combat target (`target_in_combat`)
stayed empty: characters with the "attack" action never hit, monsters
in the log only "retreated" (found no one to attack on approach). Fixed:
`AimAtTarget(party_slot, &new_target, action_context)` in both branches, check by
`action_context == OUT_OF_COMBAT`.

## Crash after the death of a monster without loot (decompilation bug, 2026-10-13)

`DropMonsterLoot` (ItemManager.cpp) with an empty loot list took `GetAt(0)` and
added a garbage pointer to the world item list; the next
`UpdateNearbyWorldItems` crashed in `ActivateItem`. Original 0x004F9099: one item -
it is dropped, none - nothing, more - a container.

## Night play session 2026-10-13: combat logic and monster pathing

Found in the game and checked against Wiz8.exe (details in the message of commit `e47bc10` in decomp):
- monsters in combat "walked in place": `PlanMovement` (OctPath.cpp) cut the route at the first node
  (the budget check was inverted and looked at the wrong node) and appended the anchor at the end instead of
  the last node - the route ended in the starting cell;
- closed eyes on portraits: `UpdateCharacterEventState` set the animation flag instead of
  `portrait_pose_dirty` (ESI in the original is offset by +1 from the start of the record);
- round hang on a spell: `W8SpellEmitterHost::ReadCycleData` took the slot number from
  the 4th argument instead of the 3rd - TARGET/EXPLOSION/CONE effects did not load, the fallback effect
  spun forever, and combat waited for it to end;
- comparison of ~800 combat/magic/AI/vision functions with the original (workflow, two reviewers per
  finding): 65 confirmed discrepancies fixed.

Helpers: `scripts\tools\retail_asm.py` (disassembler of one function of the original up to the next
annotated address), `pe_read.py`, `stringdata.py`, `map_lookup.py` (crash address ->
function via .map), `audit_chunks.py`; in play.ps1 `GShot` (a screenshot taken by the game itself via the file
`wiz8shot.req` - works with the monitor off), `KeyCombo`, `Wander`.

## Draw distance (mod, 2026-10-13)

`wiz8wide.ini [Display] ViewDistance` (default 1.5, maximum 2.0). The camera gets a far
plane = level range x k (`WorldSetFarClip`); fog, depth cue (Environment.cpp) and
octree visibility read `WorldGetRenderFarClip`; `WorldGetFarClip` still returns
the gameplay range - monster vision, group loading (1.5x), AI and spells rely on it.
`IsWithinWorldRange` at k > 1 is additionally limited by the gameplay range; items
are enabled/disabled at 20000/25000 x k; the "sun shadow" of monsters - render range x k.
The sky world is not scaled. At k = 1 everything is as in the original. On this machine 2.0 holds
120 frames/s. (Checked with screenshots in Northern Wilderness; they are not kept in the repository.)
