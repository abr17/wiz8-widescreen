# Function addresses (GOG Wiz8.exe, SHA-256 18A74FF6…20D2)

> The addresses in the original Wiz8.exe (GOG/Steam 1.2.4) are current. The "Phase 4" section describes the hooks of the old `version.dll` patch, not the hybrid; the addresses of the hybrid's 289 functions (1.0.2) are in `scripts\hybrid\transplant_wide.json`.

Source of names: the public decompilation https://github.com/agluszak/wizardry-8-decomp (locally `ref\wizardry-8-decomp`, commit 075cbd0 of 2026-10-10; it has no LICENSE — we do not copy code, only addresses and logic).

Statuses:
- **hypothesis** — name from the decompilation, not verified;
- **statically consistent** — by the bytes of our exe the address is the start of a function (preceded by `90`/`C3` padding), and the constants/globals found inside match the description;
- **verified in x32dbg** — a breakpoint fired in the expected situation.

| Name | Address | First bytes | Status | How verified |
|---|---|---|---|---|
| InitializeVideoDevice | 0x00422240 | `6a ff 68 4c 3d 5e 00 64` | statically consistent | function start (SEH prologue) |
| VideoResizeWindow | 0x00422550 | `a0 39 3c 60 00 53 33 db` | statically consistent | reads `g_fullscreen` 0x603C39 |
| OpenRendererWindow | 0x00422800 | `51 a0 39 3c 60 00 84 c0` | statically consistent | reads `g_fullscreen` 0x603C39 |
| BeginVideoPresentation | 0x00423390 | `8b 0d 34 96 65 00 83 ec` | statically consistent | reads `g_gerd` 0x659634 |
| FinishVideoPresentation | 0x004234A0 | `a1 ac 96 65 00 85 c0 74` | statically consistent | function start |
| FlushDirtyTiles | 0x00425B40 | `83 ec 78 a1 d8 96 65 00` | statically consistent | function start |
| SetAutomapScaledViewport | 0x00425C90 | `a1 e8 95 65 00 56 8b 74` | statically consistent | reads `g_viewport` 0x6595E8 |
| CreateWizardryWindow | 0x00425EC0 | `83 ec 28 a1 f8 95 65 00` | statically consistent | function start |
| InitializePrimaryDirectDrawSurface | 0x00426080 | `81 ec d8 00 00 00 6a 00` | statically consistent | references to 1/640 nearby (0x426281, 0x4262C0) |
| RenderFrame | 0x00426790 | `83 ec 3c 8d 4c 24 10 c7` | statically consistent | function start |
| RenderWorldToSurface | 0x00426F80 | `83 ec 0c 56 8b 35 1c 97` | statically consistent | references to 1/640 inside (0x4273FC, 0x42741D) and to 1/480 (0x42740A, 0x42742B) |
| RenderScene | 0x00427850 | `83 ec 18 8b 0d 34 96 65` | statically consistent | reads `g_gerd`; no direct references to 1/640 in the first 0x600 bytes — check where the scale comes from |
| WarpSystemCursor | 0x004280C0 | `a0 39 3c 60 00 83 ec 10` | statically consistent | reads `g_fullscreen` |
| PositionMouseCursor | 0x00428140 | `8b 15 88 96 65 00 83 ec` | statically consistent | contains immediates 640 and 480 |
| SyncSystemCursor | 0x00428340 | `83 ec 18 56 57 8d 44 24` | statically consistent | contains immediates 640 and 480; reference to 1/640 at 0x42830C (before it) |
| SGPMouseGetPos | 0x004284F0 | `56 8b 74 24 08 85 f6 74` | statically consistent | function start |
| stSurface2D::DrawTiles | 0x0047E100 | `83 ec 58 53 55 56 57 8d` | statically consistent | function start |

## Constants and globals

| Name | Address | Value / status |
|---|---|---|
| 1/640 (float) | 0x005EBB1C | `0.0015625` — confirmed by reading the file |
| 1/480 (float) | 0x005EBB20 | `0.00208333` — confirmed by reading the file |
| g_fullscreen | 0x00603C39 | hypothesis; read in 4 window/cursor functions |
| g_screen_width / height | 0x00603C3C / 0x00603C40 | hypothesis |
| g_viewport | 0x006595E8 | hypothesis |
| g_gerd (SR renderer) | 0x00659634 | hypothesis |
| ghWindow | 0x006596CC | hypothesis |
| g_surface_node | 0x00659664 | hypothesis |
| gzErrorMsg (`char[2048]`, sgp.cpp) | 0x006505AC | statically consistent: `// GLOBAL: WIZ8 0x006505ac` in decomp; in the retail code (llvm-objdump of `ghidra\bin\Wiz8.exe`, as `scripts\tools\retail_asm.py`) `SGPExit` (0x004017F0) takes its length at 0x401890 and passes it to `MessageBoxA` at 0x4018A9, `ShutdownWithErrorBox` (0x00401920) copies the message into it at 0x40192A. Read by `src\diagnostics.cpp` (the game's error text at exit) |
| gXStatus.fCombatMode (byte) | 0x00683F94 | statically consistent: `gXStatus` is `// GLOBAL: WIZ8 0x006836B8` (GameplayDatabase.cpp), the field is at +0x8DC (`xstatus.h`); in the retail code 307 byte accesses, the only writes `mov byte [0x683f94], 1` at 0x4E731D in `StartCombat` (0x004E7090) and `, 0` at 0x4EA481 in `EndCombat` (0x004EA310). Read by `src\diagnostics.cpp` (`combat=` in the log lines) |

All references to 1/640 in `.text`: 0x426281, 0x4262C0, 0x4273FC, 0x42741D, 0x42830C, 0x5823DC, 0x5823F1, 0x58258E, 0x5826A1, 0x5827B3, 0x5828C6, 0x58353B.

## Phase 2 map (static analysis, 5 subsystems + review by skeptic agents)

Source: ultracode analysis of 2026-10-11, full data in `docs/history/phase2-static-raw.json`. Status of all rows — **statically consistent** (exe/sr.dll bytes checked by agents); live checks are recorded in `docs/history/phase3-borderless.md`.

| Address | Name | Group | First bytes | Function start | What it does |
|---|---|---|---|---|---|
| 0x004011E0 | WindowProcedure | mouse | `a0ac0d650053555684c0577` | yes | Main WndProc. Does not process mouse position or buttons. |
| 0x00401950 | ProcessCommandLine | window | `51a118f55f0055568b74241` | yes | Tokenizes the command line. /WINDOW calls VideoFullScreen(0); /VIDEOCFG <file> sets the 3DVideo.CFG path; also handles /NOSOUND, /LOAD, /INSPECTOR, etc. |
| 0x00401B30 | KeyboardHandler (WH_KEYBOARD hook proc) | window | `8b44240433d23bc20f8c180` | yes | Thread keyboard hook. Tracks Shift/Ctrl/Alt state and forwards other keys to KeyChange. Ignores everything while gfApplicationActive == 0, which is the root cause of the stuck Alt. |
| 0x00401C70 | MouseHandler (WH_MOUSE hook procedure) | mouse | `83ec1053558b6c242456573` | yes | Source of every click and mouse-move event. Converts MOUSEHOOKSTRUCT.pt (screen coordinates) to game coordinates without any scaling, stores it, and queues button and move events that carry their own packed coordinates. |
| 0x00401F90 | QueueEvent | mouse | `53555657ff152cb05e00668` | yes | Pushes a 16-byte event record into the 256-entry ring 0x6EF4E0. The record's +0xC uiParam holds the packed mouse point. Also creates double-click events. |
| 0x00402140 | DequeueEvent / button repeat | mouse | `83ec0856ff152cb05e008bf` | yes | Creates button-repeat events from the polled position, then pops one event. |
| 0x00402270 | KeyChange | window | `83ec0853568b74241483fe0` | yes | Non-modifier key press/release to event queue. On a Tab release while gfAltState is set it calls ShowWindow(ghWindow, SW_MINIMIZE) and clears Alt (decomp; the bytes were not fully traced). |
| 0x00402750 | ClipCursor(NULL) helper | mouse | `6a00ff1530b25e00c605b80` | yes | Releases the cursor clip and clears byte 0x650DB8. |
| 0x00421F70 | LockPrimarySurface | hud2d | `8B 0D A8 96 65 00 83 EC` | yes | Locks the 640x480 sysmem canvas surface and returns pixels and pitch. SGP FRAME_BUFFER locks resolve here, which proves that all full-screen 2D screens draw into the canvas. |
| 0x00422050 | SuspendVideoManager | window | `a01097650084c07453e8d28` | yes | Focus-loss handler: pauses the world, closes the GERD window, saves the window rect if windowed, minimizes the window, frees the cursor clip. |
| 0x004220B0 | RestoreVideoManager | window | `a01097650084c07403b001c` | yes | Focus-gain handler: ShowWindow(SW_RESTORE), reopens the renderer through OpenRendererWindow if needed, OpenIcon, SetFocus, invalidates the whole screen. |
| 0x00422240 | InitializeVideoDevice | window | `6aff684c3d5e0064a100000` | yes | Reads 3DVideo.CFG (path in buffer 0x603C70, settable with /VIDEOCFG). Lines: device name, width, height, depth, sound provider. Then srInit, srConfig.set for DD_DIRECTX7/6, loadDevice('srDD_'+name), createContext(ghWindow), then OpenRendererWindow. |
| 0x00422550 | VideoResizeWindow | window | `a0393c60005333db3ac30f8` | yes | WM_SIZE/SIZE_RESTORED handler. Windowed only: closes the GERD window and reopens it at the new client size, then resets dirty tiles and transient scenes. |
| 0x00422800 | OpenRendererWindow | window | `51a0393c600084c0566a000` | yes | Applies the window style and size, then opens the SurRender output. Fullscreen: style WS_POPUP/WS_VISIBLE, SetWindowPos 0,0,SM_CX,SM_CY, getDisplayMode(cfg w,h,d), openWindow(mode) (mode switch). Windowed: style 0x10CE0000, SetWindowPos to g_window_rect, openWindow() (client-rect size). |
| 0x00422970 | VideoFullScreen | window | `8a442404a2393c6000a1cc9` | yes | Sets g_fullscreen from its byte argument. If the window, GERD and an open window exist: closeWindow(1), then tail-jump to OpenRendererWindow. |
| 0x004229B0 | VideoIsFullScreen | window | `a0393c6000c390909090909` | yes | Returns g_fullscreen (0x603C39). |
| 0x00423390 | BeginVideoPresentation | hud2d | `8B 0D 34 96 65 00 83 EC` | yes | Intro Bink path that skips the canvas: closeWindow + deleteContext on g_gerd, SetCooperativeLevel(ghWindow, 0x11), SetDisplayMode(640,480,16), creates a real DDSCAPS_PRIMARYSURFACE for Bink. |
| 0x004234A0 | FinishVideoPresentation (Bink) | window | `a1ac96650085c074108b085` | yes | After the movie: releases the primary surfaces, SetCooperativeLevel(NULL, DDSCL_NORMAL), createContext(ghWindow), then tail-jumps to OpenRendererWindow. |
| 0x00423500 | InitializeRendererSceneObjects | hud2d | `55 8B EC 83 E4 F8 6A FF` | yes | Creates the 2D scenes and cameras (overlay camera view plane 0..1 x 0..1; square camera 0..1 x 0..0.75), wraps the sysmem surface as srColorSurface type 9 (640x480, real pitch) and builds g_surface_node = stSurface2D(surf, 640, 480, g_scene_overlay0, 128). |
| 0x00425570 | SetPrimarySurfaceTextureHint2Enabled | hud2d | `8B 0D 64 96 65 00 85 C9` | yes | cdecl wrapper: g_surface_node->setAlphaTestEnabled(bool). |
| 0x00425B40 | FlushDirtyTiles | hud2d | `83 EC 78 A1 D8 96 65 00` | yes | Locks the 640x480 sysmem surface, merges dirty 8x8 cells (bit 0x40 in an 80x60 byte array at 0x652DDC) into rectangles, and uploads them to the canvas textures through stSurface2D::updateRectangle. |
| 0x00425C90 | SetAutomapScaledViewport | view3d | `a1 e8 95 65 00 56 8b 74` | yes | If the rect differs from g_viewport: setViewPort(rect*W/640, rect*H/480) directly, then stores the rect into g_viewport. It does not touch the camera. |
| 0x00425DA0 | SetWorldScaledViewport | view3d | `a1 e8 95 65 00 53 56 8b` | yes | Same as SetAutomapScaledViewport. Used while building region links offline at level load. |
| 0x00425EC0 | CreateWizardryWindow | window | `83ec28a1f89565005657894` | yes | Registers window class 'Wizardry 8' (string at 0x5FF490) and creates ghWindow. Fullscreen: WS_POPUP/WS_VISIBLE at 0,0,SM_CXSCREEN,SM_CYSCREEN. Windowed: centred 640x480 client rect in g_window_rect, adjusted with AdjustWindowRect(style 0x10CE0000). |
| 0x00426080 | InitializePrimaryDirectDrawSurface | hud2d | `81 EC D8 00 00 00 6A 00` | yes | DirectDrawCreate, QI to IDirectDraw2, SetCooperativeLevel(NULL, DDSCL_NORMAL = 8), creates the 640x480 16-bpp OFFSCREENPLAIN/SYSTEMMEMORY surface that backs the canvas, QI to IDirectDrawSurface2 into 0x6596A8, zero-fills it. |
| 0x00426250 | SetViewport (sets g_viewport and the world camera view plane, i.e. the FOV) | view3d | `55 8b ec 83 e4 f8 83 ec` | yes | Stores g_viewport = {l, t, r+1, b+1} in 640x480 units. Rebuilds the world camera (and sky camera) projection: a full-screen 85 by 71 degree plane, cropped to the viewport's share of the screen, giving an off-centre frustum. This is THE FOV function. |
| 0x004265C0 | Initialize16BitPixelFormatMasks | bink | `51 a1 48 3c 60 00 83 e8` | yes | Sets the 16-bit masks from g_pixel_format. |
| 0x00426790 | RenderFrame | hud2d | `83 EC 3C 8D 4C 24 10 C7` | yes | Draws one whole frame. Fixed order: FlushDirtyTiles, beginFrame, optional scissored clear of g_viewport, 2 prerender scenes, sky world, world (g_viewport), fullscreen scene (if not last), overlay0 (the canvas), user, square, fullscreen (if last), cursor, endFrame. |
| 0x00426ADC | RenderFrame pick-ray block (inside RenderFrame 0x426790) | mouse | `8b35bc9665008b0dd04a650` | no | Converts the logical cursor (position + hotspot) into viewport-relative normalised coordinates and sends a pick to sr.dll. |
| 0x00426F80 | RenderWorldToSurface | view3d | `83 ec 0c 56 8b 35 1c 97` | yes | Renders the world off-frame into the GERD buffer: viewport from the rect or from g_viewport. It then locks the buffer and copies it into a colour surface. |
| 0x004273F0 | GetScaledViewportBounds | view3d | `db 05 e8 95 65 00 8b 44` | yes | Returns g_viewport multiplied by (1/640, 1/480). |
| 0x00427850 | RenderScene | hud2d | `83 EC 18 8B 0D 34 96 65` | yes | Renders one srScene with a camera. If vp640 is non-NULL, sets viewport and scissor to vp*W/640, vp*H/480 and restores (0,0,W,H) afterwards; if NULL, leaves the viewport untouched. Every 2D overlay pass and the world passes go through it, so this is the place that decides where on screen each layer lands. |
| 0x00427A70 | VideoGetClientRect | mouse | `a1cc966500568b742408575` | yes | Client rect of HWND 0x6596CC converted to screen coordinates. |
| 0x00427AB0 | SetMouseCursorFromVideoObject | mouse | `558bec83ec24a0200e65008` | yes | Changes the cursor image and hotspot, with the same inline warp as SetMouseCursorHotspot. |
| 0x00427F00 | SetMouseCursorHotspot | mouse | `a1bc966500668b4c24088b1` | yes | Changes the hotspot and warps the OS cursor by (old hotspot - new hotspot) so that position + hotspot stays the same. Contains its own SetCursorPos call. |
| 0x004280C0 | WarpSystemCursor | mouse | `a0393c600083ec1084c0741` | yes | Moves the OS cursor to a logical point. |
| 0x00428140 | PositionMouseCursor | mouse | `8b158896650083ec2485d20` | yes | Stores the game cursor position in logical 640x480 space and moves the 2D cursor model in the overlay scene. |
| 0x00428230 | GetCursorPositionInViewport / IsCursorInsideViewport / IsCursorImageInsideViewport | view3d | `a1 bc 96 65 00 83 ec 08` | yes | Cursor-in-3D-view tests in 640x480 units against g_viewport. The siblings are at 0x428070 (8b 0d bc 96 65 00 ...) and 0x428030 (a1 d0 4a 65 00 3b 05 e8 95 65 00 ...). |
| 0x00428340 | SyncSystemCursor | mouse | `83ec1856578d44240850ff1` | yes | The only place the game reads the OS cursor. Fullscreen: clamps the raw screen point to 0..640 x 0..480 and, if it changed, updates the game cursor and warps the OS cursor to the clamped point. Windowed: subtracts the client top-left (no scaling), shows or hides the OS cursor depending on whether it is inside the client area, and updates the game cursor. |
| 0x004284F0 | SGPMouseGetPos | mouse | `568b74240885f67424e842f` | yes | Polled game cursor query: syncs with the OS cursor, then returns position + hotspot in logical units. |
| 0x00428580 / 0x004285A0 | GetAtomCursorX / GetAtomCursorY | mouse | `8b4c240433c0668b410c030` | yes | Reads the per-event coordinates: low or high word of the record's +0xC field, plus the hotspot 0x6596BC/0x6596C0. |
| 0x00429200 | SetOverlayViewport | hud2d | `8B 44 24 04 A3 68 96 65` | yes | Stores the 640-space rect pointer used for g_scene_fullscreen and g_scene_square. |
| 0x004297E0 | SetSurfaceScale | hud2d | `8B 44 24 04 8B 0D 64 96` | yes | Quality option: shifts canvas texcoords by 0.5 texel (stSurface2D::setScale 0x47E560) and stores g_surface_scale 0x659680. |
| 0x004298E0 | SetFullscreenSceneLast | hud2d | `8A 44 24 04 A2 4C 3C 60` | yes | Sets byte 0x603C4C, which decides whether g_scene_fullscreen is drawn before or after the canvas. |
| 0x0042F7E0 | W8Octree::UpdateCameraVisibility | view3d | `83 ec 50 56 57 8b f1 e8` | yes | Visibility culling of octree regions: reads the world camera's getHorizontalFOV/getVerticalFOV (calls at 0x42F847/0x42F856) and stores their cosines. |
| 0x004314C0 | W8Octree::BuildRegionLinks | view3d | `6a ff 68 ce 41 5e 00 64` | yes | Level-load preprocessing. Saves the H/V FOV (0x431648/0x431655), sets a 120x120 plane (0x431676, constant 2.094395102), renders region links through SetWorldScaledViewport, then restores a symmetric setViewPlane(savedH, savedV) at 0x431AB8. |
| 0x00450080 | SetCameraSwayMode | view3d | `51 56 6a 02 e8 b7 0a fd` | yes | Camera sway effect. Mode > 0 captures getHorizontalFOV/getVerticalFOV (IAT 0x5EB700/0x5EB6FC, calls at 0x4500A6/0x4500C2) in degrees. Each update then calls setViewPlane(h + 0.75*sin, v + 0.63*sin) (symmetric, IAT 0x5EB60C at 0x4501CE/0x450202). Mode < 0 restores the captured FOV. |
| 0x00476440 | GDCamera::CreateOrAttachCamera | view3d | `55 8b ec 83 e4 f8 6a ff` | yes | Creates the 'Sirtech Camera' with clip range 250..75000 and a default symmetric 90x90 degree plane (setViewPlane at 0x476555; pi 0x5EC538 * 1/180 double 0x5EC300 * 90.0 0x5EC568). |
| 0x0047DAE0 | stSurface2D::stSurface2D | hud2d | `6A FF 68 FD 50 5E 00 64` | yes | Constructor of the canvas node: computes the tile grid and creates the 128x128 stTexture2D tiles with clamp wrap. |
| 0x0047E0F0 | stSurface2D::process | hud2d | `8B 44 24 04 8B 10 52 E8` | yes | Scene-graph render callback of the canvas node; passes info.renderer to DrawTiles. |
| 0x0047E100 | stSurface2D::DrawTiles | hud2d | `83 EC 58 53 55 56 57 8D` | yes | Draws the 640x480 canvas as 5x4 textured quads (128x128 textures) in normalized 0..1 coordinates under an ortho(0,1,1,0,0,1) projection. Sets no viewport, so the canvas fills whatever srGERD viewport is current. |
| 0x0047E370 | stSurface2D::setAlphaTestEnabled | hud2d | `8A 44 24 04 84 C0 53 55` | yes | Turns the canvas between opaque and 1-bit-alpha (alpha test) modes: ORs or ANDs 0x800000 in shader bits +0x140, and toggles each tile's hints (enableHint/disableHint IAT 0x5EB5B4/0x5EB910) and invalidates them. |
| 0x0047E450 | stSurface2D::updateRectangle | hud2d | `51 8B 44 24 20 53 8B 5C` | yes | For each tile overlapping a dirty rectangle, calls srGERD::setTextureSubImage (partial texture upload). |
| 0x005618F0 | SetViewportMode | view3d | `a1 cc ed 68 00 8b 88 00` | yes | Picks one of the 7 preset 3D view rects (table 0x647D30), updates click region 0xE6 and the invalidate rect at 0x647F44..50, calls SetViewport, and caches the mode at *(0x68EDCC)+0x100. |
| 0x005AE510 | IntroScreenEnter | bink | `64 a1 00 00 00 00 6a ff` | yes | Builds the path Data\Flics\Intro\<name>, stops the music, disables the cursor, news a W8BinkVideo into gpVideo (0x69c258), calls SetTarget(BeginVideoPresentation()), then Open. |
| 0x005AE780 | AdvanceIntroScreen | bink | `a1 ac d8 64 00 81 ec f4` | yes | Chains sirtech.bik into Wizardry8.bik on the first run, otherwise ends the presentation (Finish), deletes gpVideo and schedules the next screen. |
| 0x005AE940 | IntroScreenLeave | bink | `a1 58 c2 69 00 85 c0 56` | yes | Screen-leave cleanup: Finish plus delete when gpVideo is set. |
| 0x005E2F90 | W8BinkVideo::ctor | bink | `8b c1 c7 00 00 00 00 00` | yes | Bink wrapper constructor. |
| 0x005E2FE0 | W8BinkVideo::Open | bink | `56 8b f1 e8 b8 78 e2 ff` | yes | Sets Miles as Bink's sound system and opens the .bik file. |
| 0x005E3020 | W8BinkVideo::UpdateFrame | bink | `56 8b f1 8b 06 85 c0 74` | yes | Per-frame Bink pump: wait, decode, copy to the target or to the 2D surface, advance. Returns 1 when the last frame has been reached. |
| 0x005E3070 | W8BinkVideo::CopyFrameToPrimarySurface | bink | `51 57 8d 44 24 04 50 8b` | yes | Fallback when there is no target. Copies the frame into the game's 640x480 555 system-memory 2D surface and marks dirty tiles, so the video appears through the normal 2D layer. |
| 0x005E3100 | W8BinkVideo::CopyFrameToTargetSurface | bink | `83 ec 6c 53 56 8b f1 8b` | yes | Writes the decoded frame straight into the locked exclusive primary surface at (0,0). No Blt or Flip. |
| 0x005E31E0 | W8BinkVideo::SetTarget | bink | `8b 44 24 04 83 ec 64 85` | yes | Stores the target surface and color-fills it black. Does nothing when the argument is NULL. |
| 0x10008CF0 | srDD_DirectX7 openWindow dispatcher | window | `6aff68e1090110 64a10000` | yes | Driver-level open: saves the window rect (GetWindowRect into this+0x418), then display_mode == -1 calls the windowed opener 0x100084E0, otherwise the fullscreen opener 0x10008900. |
| 0x1001A120 | sr.dll srGERD::openWindow(void) | window | `568bf1f6462801750 7b809` | yes | Windowed open. Back buffer = srWindow::getWidth/getHeight(device.window at gerd+0x374) = client rect. Calls openWindow(w,h) 0x1001A160, which sets display_mode = -1. |
| 0x1001A1F0 | sr.dll srGERD::openWindow(long mode) | window | `83ec1456578bf9f64728017` | yes | Fullscreen open by display-mode index. When mode < 0 it calls openWindow(void), the windowed path that uses the client rect. |
| 0x1001AA60 | sr.dll srGERD::getDisplayMode(w,h,depth) | window | `f641280153565774348b916` | yes | Linear search of the device mode list for the exact (w,h,depth). Returns the index or -1. |
| 0x1001D410 | srGERD::setViewPort (sr.dll export) | hud2d | `` | yes | Stores viewport left/top/right/bottom at gerd+0x1638/0x163C/0x1640/0x1644 (width/height clamped to at least 1 and to getWidth/getHeight) and sets dirty bit 0x80 in gerd+0x24; applied later by applyViewStateChanges. |
| 0x100459D0 | sr.dll srWindow::getWidth | window | `83ec10568b74241856e8520` | yes | Calls GetClientRect(hwnd) and returns its right. getHeight at 0x10045A00 returns bottom. |
| 0x10048820 | sr.dll srCamera::setViewPlane(Rect const&, double) | view3d | `dd 44 24 08 dc 1d 38 6e` | yes | Sets an arbitrary (possibly off-centre) view plane and distance. |
| 0x10048920 | sr.dll srCamera::setViewPlane(double,double) | view3d | `dd 05 30 6e 07 10 83 ec` | yes | Clamps both angles to [-pi, pi] (0x10076E30). Sets plane = {-tan(a/2), -tan(b/2), tan(a/2), tan(b/2)} (0.5 at 0x10075330) at +0x140..+0x158 and distance 1.0 at +0x160. |
| srDD_DirectX7.dll+0x8900 (VA 0x10008900) | srDD fullscreen open (srDD_DirectX7 internal method) | bink | `64 a1 00 00 00 00 6a ff` | yes | srDD device method that opens a fullscreen display mode: exclusive cooperative level, display-mode change, flip-chain primary. |
| srDD_DirectX7.dll+0x84E0 (VA 0x100084E0) | srDD windowed open (srDD_DirectX7 internal method) | bink | `64 a1 00 00 00 00 6a ff` | yes | srDD device method for windowed output: normal cooperative level, clipped primary plus an offscreen 3D render target of w x h. No mode change. |
| sr.dll+0x1A1F0 (VA 0x1001A1F0; Wiz8 IAT slot 0x5EBA68) | sr.dll srGERD::openWindow(long) | bink | `83 ec 14 56 57 8b f9 f6` | yes | Opens a display mode by index. If mode < 0 it forwards to openWindow() (windowed, sized to the window client area). |

## Phase 4 — hook points (verified by bytes while building the hooks, not yet verified live)

| Address | What | Check bytes | How verified |
|---|---|---|---|
| 0x00427850 | RenderScene, MinHook (cdecl, 4 args) | `83 ec 18 8b 0d 34 96 65 00 53 55 57` | llvm-objdump: vp only affects setViewPort/setScissor (0x427900/0x427953) and the restore (0x427A04/0x427A16) |
| 0x00426A3A | first RenderScene call of the frame, return 0x426A3F | `e8 11 0e 00 00` | after beginFrame (0x4268EF) and the 3D clear (0x4269FB) |
| 0x004269C8 / 0x004269E6 | mov ebx,[setScissor] / call ebx, return 0x4269E8 | `8b 1d 40 b6 5e 00` / `ff d3` | clear of the 3D area, colour+depth (flags 3), with the fog colour (setClearColor 0x4268AD). The branch 0x42692C..0x426A1D is skipped when the sky is drawn (0x65970C && !0x65970E && 0x603C6C && *0x659AB8). We clear the side margins to black BEFORE it (in the setScissor hook), otherwise in the first RenderScene |
| 0x00426340 / 0x004263A7 / 0x004263C1 | mov esi,[setViewPlane(Rect)] / call esi (world, return 0x4263A9) / call esi (sky, return 0x4263C3) | `8b 35 ec b4 5e 00` / `ff d6` / `ff d6` | Rect is built as {l, b, r, t}: the x fractions l/640 and R1/640 are written to +0 and +16 |
| 0x00426BAC | call [pushPick], return 0x426BB2; patch -> `e8 rel32 90` | `ff 15 30 b6 5e 00` | Pick {x, y, 1.0f, 0, 0}; x = (cx - L - halfw)/halfw, halfw = (R1-L)/2 |
| 0x00426F80 | RenderWorldToSurface, MinHook (cdecl, 3 args, uint8, plain ret) | `83 ec 0c 56 8b 35 1c 97 65 00` | calls at 0x5126E3/0x5158DC: push 1; lea rect; push target |
| sr.dll 0x10048820 | srCamera::setViewPlane(Rect const&, double), thiscall, retn 0xC | — | copies 32 bytes to +0x140; getHorizontalFOV 0x10048AB0 = atan(+0x150) - atan(+0x140) → Rect = {l, b, r, t} |
| sr.dll 0x1001CA30 / 0x1001CB40 | setClearColor(srVector4T const&) / getClearColor(srVector4T&), thiscall, retn 4 | — | 4 floats at gerd+0x1B08; getClearColor is not in the Wiz8 imports — we get it through GetProcAddress |
| sr.dll 0x10020D30 | srGERD::clear(srFlags const&), thiscall, retn 4 | — | flags are a DWORD passed by pointer: 1 colour, 2 depth, 8 stencil; applies the pending viewport before clearing |

Who loads our version.dll: VERSION.dll is imported by **sr.dll** (GetFileVersionInfoA/SizeA, VerQueryValueA), Wiz8.exe does not import it (llvm-objdump -p, 2026-10-11). So our DllMain runs before sr.dll's own DllMain: from it we can only read sr.dll's export addresses; calling its functions in DllMain is not allowed.
