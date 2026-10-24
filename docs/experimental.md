# Experimental features (1.0.2)

Features that are not part of the original game, are off by default and may change or be
removed in a later version. The player switches them in the game (Options, category
"Experimental") or in `wiz8wide.ini`, section `[Experimental]`. All of their code is in
`decomp\src\wiz8\experimental\` and `decomp\include\wiz8\experimental.h`; the few call sites
elsewhere are marked with an `Experimental` comment, so a feature can be taken out whole
(see "Removing" below). The shared helper `ExperimentalIniPath` (the path of `wiz8wide.ini`,
used by every switch to read and write its key) is in `ExperimentalOptions.cpp`, with the
category page.

## Options category "Experimental" (`ExperimentalOptions.cpp`)

What the player sees: the left column of the Options screen has a 5th small button under the
other four, "experimental" (English data) or "экспериментальные" (Russian data), and the
computer picture has a USB drive below the tower that lights up while the category is
selected (as the tower does for "General"). The button and the drive both open the
category's page: a heading, the switches (four checkboxes, "Animated Main Menu", "Map Mouse Controls", "Original Bug Fixes" and "Alternative Game Tick", in the style of the original pages: a name and a checkbox) and a note
that these features are off by default and may change or disappear. The page text is in
English, German, French or Russian, following the game's data.

The art is the patch's own files in `Data\WIDE\` (in `assets\`, not in git); the game's
originals are not touched:

| File | What |
|---|---|
| `OPTIONS_BASE_EXP.STI` | the original `options_base.sti` with the button area of the column one row taller (the room taken from under the keyboard and from the strip at the bottom) |
| `OPTIONS_COMPUTER_EXP.STI` | the computer picture, 6 frames of 239x163 (6 rows shorter than the original, to make room); frame 5 = the drive lit |
| `OPTIONS_COMPUTER_EXP169.STI` | the same drive at the original 239x169, for the fallback below |
| `OPTIONS_BUTTONS_EXP_EN.STI`, `_RU.STI` | the original 26 button sprites plus 3 of the new button: 26 normal, 27 selected, 28 pressed |

When the Options screen opens (`W8OptionsScreen::CreateControls`, first thing),
`ExperimentalOptionsPrepareArt` decides once per session which column to use and points the
catalog entries `0xee` (options_base), `0xef` (options_buttons) and `0xf0` (options_computer)
of `g_video_frames` at these files (the path is a `char[0x30]` in the catalog; a copy of the
old picture already loaded is released first). The button sprites carry the labels of one
language, so the 5-button column is used only when the game's own
`Data\Options\options_buttons.sti` is the known English (CRC32 `61B4571E`, GOG/Steam 1.2.4) or
Russian (`1D41BD3C`, the translation's data) one. Otherwise (German or French data, missing
files) only the computer picture is swapped (`_EXP169`) and the drive is an unlabelled click
area; with none of the files, the click area is still there, invisible. `wiz8wide.log` says
which: `[Experimental] options_buttons.sti CRC32 ...`.

In the 5-button layout the four original rows move up 13 px (tops 181, 207, 233, 259 instead
of 194, 220, 246, 272) and the new one is at 285. The new category is the 7th entry of the
menu selection (index 6, the screen's spare `m_panel[6]`), and its page is panel index 14
(the original has 0..13, so its region set lives in `ExperimentalOptionsRegionSet`). The
page needs one more replaced function, `W8OptionsScreen::SelectPanel` (`0x005a93c0`); the
other changed functions were replaced already.

## Animated main menu (`MenuAnimation.cpp`)

`[Experimental] AnimatedMenu=1` (or the checkbox; it writes the ini at once and takes effect
the next time the main menu opens): the main menu background is a looped animation instead
of the still picture. The video is `Data\WIDE\MENU_ANIM.AVI`, "V10 B Steel Shimmer" (made with generative AI):
856x480, 15 frames per second, 225 frames (15 s), 16-bit RGB 5:6:5 in the ZMBV codec (the
lossless DOSBox capture codec), keyframes every 25 frames, 14 MB. The 768 and 640 canvases
show its centre.

How it works:

- On menu entry (`MainMenuScreenEnter`) the whole file is read into memory and checked
  (`ParseAvi`: ZMBV, exactly 856x480, the frame time from the AVI header). Frames are zlib
  data (the game's own zlib 1.0.4): a keyframe is the whole picture, other frames are motion
  vectors and XOR differences per 16x16 block. The decoded 5:6:5 pixels are converted to the
  game's surface format with the game's own rule (`ConvertRGBDistribution565To555`).
- Each pass of the game loop on the main menu (`GameLoop`) calls `MenuAnimationTick`: when the
  time for the next frame has come, it decodes it and redraws the whole canvas (picture,
  menu items, version line). The picture holds while a dialog or a message box is up, and
  continues without fast-forward after Alt+Tab or a long pause. On leaving the menu
  (`MainMenuScreenLeave`) everything is freed and the frame number is remembered, so the next
  entry continues from the nearest keyframe.
- The background draw (`DrawCatalogSurfaceWide`, for `intro_bg_text.sti`) and the menu items
  (`DrawMainMenuItem`) are redirected while the animation runs. The item pictures
  (`introtext_*.sti`) are opaque strips with a piece of the original background baked in; only
  the pixels that differ from the original background are drawn (3x3 median of the
  difference over a threshold, small specks dropped, a thin fringe kept, the same rule as the
  1.0.0 art script `menutext_alpha.py`). The masks are made once per session from the
  installed language's item pictures, so any translation works.
- Failures fall back to the original still picture and never stop the game: no or a bad file
  (`wiz8wide.log`: `MENU_ANIM.AVI: ...`), a game folder path too long, a frame that does not
  decode (the picture stops and the still background is used until the game restarts; the
  game's zlib can crash on some damaged data, so `inflate` runs inside a structured exception
  handler).

To replace the video: any lossless ZMBV AVI of 856x480 in 16-bit 5:6:5 (ZMBV format 6) with
16x16 blocks and at most 4096 frames; the frame rate is taken from the file. Keyframes are
needed for looping back and for resuming (the decoder seeks to the nearest earlier one).

## Map Mouse Controls (`ModernMap.cpp`)

`[Experimental] ModernMap=1` (or the second checkbox; applies at once). The original map
zooms in on a left click and out on a right click, in fixed steps, and moves only with the
arrow keys or buttons. With the switch on (the first version of 2026-10-21 was reworked the
same day after the patch author found it slow and zooming by itself):

| Input on the map field | Result |
|---|---|
| wheel | zoom x0.8 / x1.25 per notch (in quarter-notch steps), the point under the pointer stays put |
| left drag (more than 3 game px) | the map follows the mouse; hand cursor (the map's own, catalog 0x14b+4), also outside the field; released over a button, the button does not fire (the original fired it: a press in the field released on Exit left the map) |
| single left click | nothing (arrow cursor instead of the magnifier), except on the party marker |
| single left click on the party marker (where the original hides the cursor: within 5% of the view height, not at the closest zoom) | the original's single click (below) |
| double click | the original's single click: `ZoomAutomapIn` at the pointer (the whole map -> the middle level -> the closest; at the closest it centres the view there) |
| right click, note tools, keys, buttons | as in the original |

Everything else stays the original's on the patch author's word (2026-10-22: as close to the
original as possible, only the wheel and the left button new; every zoom by a click or a key
is the original's). A version with x2 steps on the Zoom-In button, Enter, the right click, the
double click and the party click was dropped. The original knows three zoom levels
(whole map, middle, closest): after a wheel zoom its Zoom-In button, Enter, the double click
and the right click treat the view as "not the whole map", so Zoom-In and the double click go
straight to the closest zoom and the right click and Zoom-Out up to the middle height or to
the whole map.

How it works:

- Input: `AutomapScreenFrame` offers every event to `ModernMapHandleEvent`. Positions come
  from the events themselves (`uiParam` + cursor hotspot = pointer tip), not from the cursor
  polled once per frame, and the state machine (idle / pressed / dragging) does not look at the
  live button state. The first version reset the gesture when moves queued before the release
  were processed after the button had already gone up, and the release then zoomed; a quick
  drag inside one frame also measured zero movement. A release that never arrives (outside the
  window) ends the drag after two frames of `GetAsyncKeyState`. Two exceptions: the wheel takes
  the polled pointer (`SGPMouseGetPos`), because its message carries screen pixels when the
  canvas has no mouse mapping (640 wide, windowed; in a window, a wheel with the pointer
  outside the client area is ignored, as the polled position is stale there); and a left
  release just outside the field that the original would take as inside (it tests the polled
  cursor, a frame later) is still taken here, so the original's click zoom cannot run. The
  right release goes to the original code, and the cursor is set again after it (its
  `ResetAutomapZoom` sets the magnifier inline).
- Camera height: the map camera is orthographic, so its height only decides what is clipped.
  The original puts it the zoom above the ground it traces under the clicked point
  (`ZoomAutomapIn`: a vertical line of sight, the highest surface it hits), and at `top_y` for
  the whole map. The wheel does the same (`AutomapGroundAt`, a copy of that trace, under the
  pointer and under the new centre, the higher one) and stays just below `top_y` until the
  whole map, where the original right click, Zoom-Out button and Backspace stop acting. A drag
  keeps the height, as the arrow keys do. The first version took the camera height minus the
  zoom as the ground, which after the whole-map view is the lowest point of the level: on
  Lower Monastery (four layers) about nine wheel notches put the camera under the floors and
  the field went black except the party marker.
- Keys during a drag: a key or button that moves the camera (arrows, pan buttons) shifts the
  drag's start with it; one that zooms (Enter, Backspace, Home, the zoom buttons) restarts the
  drag from the new camera and pointer. The first version let the drag write the old camera
  height back, and the next zoom could show a black map.
- Speed: the original camera update (`SetAutomapCameraPoint`) and the redraw it triggers flush
  every resident texture twice (`SetResidentTexturePolicy` 3 then 0) and recompute the octree
  visibility; the frame cap also slept twice per redrawn frame. During a gesture the camera is
  moved directly ("live"): `RenderAutomapFrame` only sets the texture policy variable (textures
  keep the reduction they were made with), the visibility is refreshed at most every 100 ms,
  and `CanvasSkipNextFrameLimit` drops the first of the two waits (on every redrawn map frame
  while the switch is on, so the arrow keys pan about 1.3x faster in the sandbox; the original
  without the patch has no frame cap at all). When the gesture ends (drag
  release, 150 ms after the last wheel step) the original `SetAutomapCameraPoint` runs once, so
  the final picture is the original's. Leaving the map after live redraws invalidates the
  textures, so no reduced-detail textures reach the 3D view.
- Zoom buttons: our zooms set mode 3 (both buttons on; the closest and the whole map 2 and 0
  as the original). The original Zoom-In button and Enter then go to the closest zoom at the
  centre. The original Zoom-Out button, Backspace and right click go up to the original's
  middle height above the ground under the camera, keeping the position (from x1.3 to x4.6 out
  on Lower Monastery, depending on the zoom), and the next press to the whole map, recentred;
  from above the middle height they go straight to the whole map.
- Cursor: `SetAutomapToolCursor` (0x005820F0, replaced for this) shows the hand while dragging
  and the arrow over the field; with the switch off it is the original. The retail key code
  (`HandleAutomapKey`, `ResetAutomapZoom`, not replaced) sets the original magnifier inline
  after Esc or F1 drops a tool, after Backspace and Home, so `AutomapScreenFrame` calls
  `SetAutomapToolCursor` again after those keys.
- In the sandbox test (2026-10-21): five drags released while still moving all ended as drags
  with no zoom, a 1-px jitter was a click, the frame rate during a 10 s drag stayed near the cap
  (measured with per-gesture debug lines in `wiz8wide.log` that the release no longer writes;
  only a rare `[ModernMap]` line for a lost button release may remain).
- Audit (2026-10-22): every map control (the 16 buttons, the keys, the mouse, the note tools,
  the layers, leaving and re-entering) was listed from the code and played in the sandbox with
  the switch off and on, then triaged against the pure original. The black close zoom, the
  height lost by a zooming key during a drag, the magnifier coming back after Esc or
  Backspace, the screen-pixel wheel position and three rare state leftovers were fixed (see
  above). The retest on Lower Monastery (two saves) and an outdoor level: every zoom drawn, the
  layer cut correct at the closest zoom (where key 4 shows nothing, the original shows nothing
  either), notes, party and monster markers moving with the map during drags and wheel zooms,
  close-zoom drags clipped exactly where the original's arrow keys are; with the switch off the
  map matched the earlier original-mode logs.

## Original Bug Fixes (`OriginalFixes.cpp`)

`[Experimental] OriginalFixes=1` (or the third checkbox; applies at once). The patch does not
fix the original game's bugs unless they get in the way of widescreen; this one switch is the
exception the patch author asked for (2026-10-22): everything found that way goes here, off by
default, and with the switch off the game behaves exactly as the original.

| Bug | Fix |
|---|---|
| `W8Octree::ReadRegionLinkFile` (0x00432e90) leaves the level's region link file (`.RLK`) open when it cannot read the 4-byte count at its start (the jump at 0x00432f6c skips the `FileClose`). Five `.RLK` files in `Levels\Levels.slf` are empty (0 bytes): `CONNECTIVETISSUE\ARNIKA_STARTERDUNGEON` (Arnika Road from the starter dungeon), `CONNECTIVETISSUE\ARNIKA_TRYNTON`, `TRYNNIE\TRYNNIE1`, `SAVANTTOWER\SAVANTTOWER`, `ASCENSION\ASCENSION`, so every load of these levels (entering one, loading a save in it) leaks one open file of that archive. | the jump goes to a stub that closes the file first |
| `OpenFileFromLibrary` (0x004133d0) grows an archive's open file array with `realloc(array, count + 20)` in bytes, while each entry is 16 bytes (0x00413570). At the 20th file of one archive open at once (19 leaked by the bug above, after about 20 loads of those levels in one session) the array shrinks to 40 bytes and the entries past it are garbage; the next file name check reads through one of them and the game ends silently. This is the crash the patch author hit on Arnika Road (2026-10-22: Steam copy, `wiz8hy.log` "exception c0000005 at 004134aa" while opening `TR1-treered.tga`, no crash report), and most likely the old "crashes on Arnika Road, restart the game now and then" of the player forums. | the call goes to a wrapper that allocates `(count + 20) * 16` bytes and zeroes the new entries (a free entry has file id 0) |
| Closing the window (Alt+F4, or the X in window mode) crashes on exit (0xC0000005 at 0x00406dcf, `SetFontObjectPalette16BPP`). `WM_DESTROY` runs `ShutdownStandardGamingPlatform` first (fonts, video and memory freed, its flag 0x00650db4 set); then the atexit handler `SGPExit` (0x004017f0) still calls `GameloopExit` (0x004e34b0, the call at 0x0040181b), which sets the palettes of the fonts that are already freed. A quit from the menu runs `SGPExit` first, so there `GameloopExit` comes before the shutdown and nothing crashes. Settings are saved either way (`ShutdownGame` -> `SaveGameConfiguration` runs in the `WM_DESTROY` shutdown). With `Diagnostics=1` every such close wrote a CRASH line and a minidump. | the call goes to a wrapper that skips `GameloopExit` when the shutdown flag is already set |
| `RefreshRadarMap` (0x005a24a0) and `RefreshFormationBoard` (0x005b1c80) make the radar's map, frame and compass and the formation board's board and compass as SGP video surfaces (`MakeVSurfaceFromVObject`), copy them into sprites (`CreateSpriteFromSurface` copies the pixels) and never delete the surfaces: 5 surfaces leak on every level load (saved-game loads, quick loads), more on every radar show and board refresh. Under dgVoodoo each is a 44 KB file mapping with an open handle (traced in the pure original in the sandbox, 2026-10-23, `build\tmp\load-growth\`, not in git: exactly 5 mappings and 5 handles per quick load, the same with dgVoodoo's software renderer). | both functions are transplanted: they delete the surfaces after making the sprites (`DeleteVideoSurfaceFromIndex`) |

Switching on in the middle of a session stops the leak at once, but an array the original has
already shrunk cannot be repaired: after a long session with the switch off (about 17 or more
loads of those levels), restart the game. Once the wrapper has sized an array in entries, it
keeps doing so for the rest of the session even if the switch goes off, so turning it off never
shrinks an array again. In the sandbox (2026-10-22): off, the open count rose by one per load
and the game died silently during the 18th load, exactly like the pure original; switched on
after 4 loads, the count stayed at 4 for the next 10 loads; on from the start, 31 loads with
the count at 0 and no crash, then walking, the map and a fight worked.

The exit crash, in the sandbox (2026-10-23, `build\tmp\exit-crash\`, not in git): `WM_CLOSE` on
the main menu and in the game with the switch on - exit code 0, no CRASH line, no minidump; with
the switch off - 0xC0000005 at 0x00406dcf as the pure original; the menu's Quit exits with
code 1 both ways, as before.

How: `ExperimentalInstallOriginalFixes`, called once by `HybridInstall` (src\hybrid\hybrid_main.cpp),
patches the three spots of the original code, only over their exact original bytes, whatever
the switch; the stub and the wrappers check the switch every time they run. `wiz8hy.log` says
`original fixes: on|off ...; region link close patched, open file array patched, exit after
window close patched`. The open file bugs were found by a
monitor of the archives' open file counts in the sandbox (`build\tmp\crash-arnika\`, not in
git): `Levels.slf` gained one open `ARNIKA_STARTERDUNGEON.RLK` per load of the level.

## Alternative Game Tick (`FixedTick.cpp`, `FrameRateFixes.cpp`)

`[Experimental] FrameRateFix=1` (or the fourth checkbox; applies at once). Until 2026-10-23 these
fixes were part of Original Bug Fixes; the patch author gave them their own switch the same day.
The 2001 engine ties much of its behaviour to the rendered frame; with the switch on the game runs
the same at any frame rate. With the switch off the patched spots behave exactly as the original.

| Behaviour | Fix |
|---|---|
| Frame rate, the party's movement (`FixedTick.cpp`): `ApplyCameraMotion` (0x0041f5f0, called once per frame at 0x0044fd84 from `UpdateWorldCameraAndPaths`) moves the party one step sized by the frame time. The collision code has no step-up: a ledge or doorstep is climbed only when one frame's travel jumps the band where the riser stops it, and from rest a step must beat a fixed 0.1-unit cut. So the higher the frame rate, the harder the stairs and the Umpani doorsteps (304 high: from a walking run-up at almost any angle at 30-45 fps, straight on only at 60, never at 120), the slower stairs are climbed (Monastery: 1.3 s at 30, 2.0 s at 120, stuck from ~200), a little more falling damage, and uncapped the party may not start on slopes (measurements and a Python port of the movement code in `build\tmp\fps-ledges\` and `build\tmp\fps-indep\movement\`, not in git). | the call goes to a wrapper that runs the original step at a fixed 30 per second (the frame delta set to 1/3 of a tenth for each step, as many steps as the elapsed time asks (the frame clock caps a frame at 0.2 s: 6 steps; up to 8 kept for a step taken at once from rest); a step at once when the party starts from rest; short key presses between steps are kept), and `RenderFrame` draws the world (and picks) from a point between the last two steps, putting the camera back after the frame, so the picture stays as smooth as the frame rate. Turning stays per frame. No interpolation across a teleport, level load or anything else that moves the camera outside the steps, nor across a jump inside a step (the point is not where the step's own move puts it; a long fall keeps its interpolation and its speed); a step that raises a modal dialog or a screen change (a level exit) ends the frame's steps. A camera shake shakes around the interpolated point. While paused the original's (empty) step runs and the picture stays at the interpolated point; the original single step before the level data exists or during a camera path. Keys latched between steps are forgotten when the wrapper missed frames (another screen). Moving props (lifts, doors) push the party by their move per rendered frame (`ProbePropsAlongMotion` 0x0041b770 reads `W8Prop::GetDelta` 0x0044e130 at 0x0041b85e; the pose pair rolls once per frame): that call goes to a wrapper which, inside our steps, makes the push the prop's move since the last step: its position now minus where the previous step found it (the per-frame moves are uneven at high frame rates, so scaling one frame's move overshoots); when the previous step did not probe it, the frame's move x time since the previous step / this frame's time; the further steps of one frame get none. A lift carries the party as at 30 fps at any rate |
| Frame rate, monster AI (`FrameRateFixes.cpp`, like all rows below; the reference is the original at 30 fps, the rate of the fixed movement step, except where the code states a duration - the sound fades keep the designed one): `UpdateMonsterGroups` (0x00530150) runs once per frame (call at 0x005603ee). A pausing monster rolls `Random(20)` per evaluation to look about, and the cooldowns after facing a noise (0x1e) or a failed patrol (0x14) count evaluations, so at 240 fps monsters swivel 8 times as often as at 30 and forget a noise 8 times sooner. | the call goes to a wrapper that runs it once per 30-per-second logic tick (0..4 calls a frame; none while the game is paused). The ticks come from the game's frame clock (`W8GameTimeAccumulator`: its delta in game time x its `m_duration`, i.e. real time since the last frame, also while camping or resting runs the game clock faster; at most 0.2 s), counted once per rendered frame (a private counter that `RenderFrame` advances, `FrameRateCountFrame`) |
| Frame rate, idle fidget: `TryStartMonsterCycle2` (0x004e67a0) rolls `Random(20 * members) == 0` every frame while an idle monster sits on its last animation frame (0x004e68a3): a lone monster fidgets after 10 % of idle loops at 30 fps, 56 % at 240, 97 % uncapped. | the roll goes to a wrapper that rolls once per logic tick (0 ticks: no fidget) |
| Frame rate, flickering lights: `stLight::Update` (0x0049c960), a FLICKER light dark: `rand() / 32767 < flicker_chance` lights it every frame, and the next frame darkens it, so a flash lasts one frame and their number per second grows with the frame rate (Arnika lamps, Trynton fireflies become a strobe). | the block at 0x0049cf23 goes to a stub that does the same on/off step once per logic tick: the same chance per second, a flash 1/30 s long, the lamp prop's lit texture frame with it |
| Frame rate, floating damage numbers: `W8Monster::UpdateAttachedObjects` (0x004c3f70) lifts them each frame by 0.2 x (ms since the monster's last animation frame) and removes them 1000 units from the monster, so they stay up 3.1 s at 30 fps, 2.3 s at 60, 0.8 s at 240, 0.25 s at 1000. | the lift (0x004c4507) goes to a wrapper: the 30 fps lift (the elapsed time as it would be at 30 fps) times frame time / (1/30 s); identical at 30 fps, the same speed and life at any rate |
| Frame rate, SGP volume fades (music, footstep scuffs): `SoundSetFadeVolume` (0x00409140) is given a fade length (e.g. 500 ms) and splits it into one period per volume step, but `SoundServiceStreams` (0x004095b0) steps at most once per call and restarts the period at that call (0x00409719), so a full 0..127 fade designed as 0.5 s takes 4.2 s at 30 fps and 2.0 s at 64+ fps (GetTickCount steps). The code states the length, so the fix keeps the designed one, not the 30 fps one (the patch author's decision). | the period check goes to a stub: a step every period on the fade's own timeline (no drift), all the steps due in this call at once (the original's step code takes the last one and still stops a sound faded to zero): the designed length at any frame rate |
| Frame rate, ambient zone fades: `W8AmbientSound::UpdateFade` (0x0047a310) takes one volume step per frame when its period (1.5 s / target volume) has passed: 4.2 s at 30 fps, 2.1 at 60, the designed 1.5 at 85+. Designed length kept, as above. | the `GetProgress` call (0x0047a333) goes to a wrapper that takes the steps due beyond the one the original takes (`GetProgress` already keeps the timeline), at most what this frame's time can owe: every fade start leaves the timer's start near 0, so its first progress is the whole clock / the period and is not owed (one step, as the original): 1.5 s at any frame rate |
| Frame rate, automap arrow keys: `AutomapScreenFrame` (transplanted) pans 0.35 x zoom per frame. | the step is multiplied by `FrameRateAutomapPanScale()` (frame time from QueryPerformanceCounter / (1/30 s); 1 on the first frame on the map and with the switch off) |
| Frame rate, mouse-look smoothing (on by default): `ApplyPendingMouselook` (0x00568c40) applies 0.2 of the pending turn per frame below 20 ms of GetTickCount time, then 0.2 per whole 10 ms, all of it above 50 ms: 0.6 per frame at 30 fps; at the 60 fps cap the turn lags about twice as long, uncapped the smoothing is gone. | the fraction (0x00568c65) goes to a stub: 1 - 0.4^(dt x 30) with dt from QueryPerformanceCounter (0.6 at 30 fps, the same settling time at any rate). Smoothing off: unchanged, the whole turn at once |
| Frame rate, camera paths and scrolling textures: `PathAITick` (0x004aa1f0, camera fly-bys) and `UpdateRenderElapsedTime` (0x00482140, water/lava UV scroll, light oscillation) read GetTickCount, which moves in 15.6 ms steps: above 64 fps they move in stop-go jumps (speed correct). | their GetTickCount calls (0x004aa219, 0x00482143) go to a millisecond clock from QueryPerformanceCounter, kept 0..48 ms ahead of GetTickCount (so no time stored from GetTickCount elsewhere is ever ahead of it) and never going back; after the switch goes off it holds its last value until GetTickCount passes it |

How: the patches are installed once by `HybridInstall` (src\hybrid\hybrid_main.cpp), separately
from Original Bug Fixes and whatever the switch (`FixedTickInstall`, `FrameRateFixesInstall`);
every wrapper and stub checks `ExperimentalFrameRateFixEnabled()` each time it runs. `wiz8hy.log`
has its own line for it: `alternative game tick: on|off; ...` (followed by what was patched:
the fixed movement step, the prop push, the monster AI rate, ...).

## Removing

To take a feature out completely:

1. Delete `decomp\src\wiz8\experimental\` and `decomp\include\wiz8\experimental.h`, and their
   lines in `decomp\src\wiz8\sources.cmake`. (One feature alone: its .cpp, its part
   of the header, its call sites and its switch in `ExperimentalOptions.cpp`.)
2. Remove the call sites marked `Experimental`, with their `#include "wiz8/experimental.h"`:
   - `src\hybrid\hybrid_main.cpp` (`HybridInstall`: the Original Bug Fixes and the Alternative
     Game Tick installs and their log lines);
   - `MainMenuScreen.cpp` (`MainMenuScreenEnter`, `DrawMainMenuItem`, `MainMenuScreenLeave`),
     `Gameloop.cpp` (`GameLoop`), `VideoObjectManager.cpp` (`DrawCatalogSurfaceWide`): the
     animated menu;
   - `AutomapScreen.cpp`: `SetAutomapToolCursor`, `AutomapScreenEnter`, `AutomapScreenFrame`
     (the mouse controls and the arrow-key pan scale), `AutomapScreenLeave`,
     `RenderAutomapFrame` (the live redraw and the skipped frame-limit wait) and the whole
     `AutomapGroundAt`;
   - `Video2.cpp` (`RenderFrame`): the camera shake around the interpolated point, the
     interpolated camera and its restore after the frame, and `FrameRateCountFrame()`;
   - `MGSFormation.cpp` (`RefreshFormationBoard`) and `MGSRadarMap.cpp` (`RefreshRadarMap`):
     the deletion of the leaked surfaces;
   - `OptionsScreen.cpp` (`W8OptionsScreen::CreateControls`, `W8OptionsScreen::SelectPanel`, the
     `W8OptionsPanel` constructor).
3. Remove `0x005820f0` (SetAutomapToolCursor) from `scripts\hybrid\transplant_wide.json`,
   and `CanvasSkipNextFrameLimit` from `Canvas.cpp` / `canvas.h`, if nothing else needs them.
   Keep `0x005a93c0` (SelectPanel) and the `W8_FRAME_RATE_OPTIONS_PANEL` branch of the
   `W8OptionsPanel` constructor: the frame rate page (Video page 3, not experimental) needs
   them; only the experimental branch goes. `RefreshRadarMap` (`0x005a24a0`) and
   `RefreshFormationBoard` (`0x005b1c80`) also stay transplanted: they are replaced for the wide
   interface (`widescreen_ui`), only their leak fix is experimental.
4. Remove the `[Experimental]` section from `dist\wiz8wide.ini`, the paragraph from the four
   `dist\README_*.txt`, and the six files from `assets\Data\WIDE\` (`MENU_ANIM.AVI`,
   `OPTIONS_*_EXP*.STI`). The installer of the next version removes them from players' games
   on update, as it removes every file of the previous install.
