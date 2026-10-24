# Testing

There are no unit tests for the patch itself; it is tested by running the game. This page
covers the test copies, the play-automation scripts and the pitfalls found so far.

## Test copies

| Copy | Contents | Use |
|---|---|---|
| `games\reference` | pristine GOG 1.2.4 | never run or modify; compare against it |
| `games\work` | GOG copy + `assets\` + inis (one-time setup, [building.md](building.md) section 2) + the patch DLLs from the `-Install` switches | main test copy |
| `games\ru` | GOG exe + Russian translation `Data` (Wizardry8_rus) + the patch | Russian text/fonts, `FALCON.STI` exit screen |

Never run the Russian translation's own `Wiz8.exe`: it is a different build, and the patch
switches itself off on it.

For release testing, make throw-away clean copies (copy the GOG install, or the Steam install
`steamapps\common\Wizardry8`), install the package with the installer and check:

1. The installer finds the game; installing works; an unknown exe gets the warning; a foreign
   `version.dll` is refused.
2. The game starts wide (logs next to the exe: `wiz8ws.log` says `hooks installed: yes` and
   `wiz8hy.dll: N functions replaced` with N = entries in `transplant_wide.json`, 289 in 1.0.2;
   `wiz8wide.log` shows the canvas width `W=`; `wiz8hy.log` lists the hooks and, after a crash,
   the crash addresses: turn them into names with `scripts\hybrid\symbolize.py`).
3. A walk through the screens: main menu, options (all pages), load/save list, game, journal,
   map, camp, combat, spell and item panels, character sheet tabs, a chest or NPC.
4. Uninstall: the folder matches the original byte for byte (compare file hashes before/after).

`wiz8wide.log` also prints `[Stretch] no strip: ...` when a stretched panel has no seamless art
file in `assets\Data\WIDE\STRETCH`. Such a line means a visible seam; make the strip with
`scripts\art\stretch_quilt.py` (see [scripts/README.md](../scripts/README.md)).

## Testing a given screen shape

The canvas width follows the output proportions: 856 for 16:9 and wider, 768 for 16:10,
640 for 4:3. To test a shape your monitor does not have, set in `games\work\wiz8wide.ini`
either `[Display] Mode=window` with `ScreenWidth=1920`, `ScreenHeight=1080` (a 16:9 window),
or `[Canvas] Width=856`. Check `W=` in `wiz8wide.log`, and pass the same width to the helper:
`. scripts\play\hybrid_session.ps1 -CanvasW 856`. The click helpers assume the game covers the
whole primary screen (borderless/fullscreen), so for automated runs prefer `[Canvas] Width=856`.
Options: gear button at the bottom left (`Click640 -52 465` at W=768), then the page buttons
on the left; the Video page has a second page with display mode and resolution and a third with the frame rate limit.

## Automated play (PowerShell, `scripts\play\`)

```powershell
. scripts\play\hybrid_session.ps1          # retail Wiz8.exe in games\work, wide-canvas mouse mapping
Start-Wiz8                                  # start, skip the intro
Click640 323 257                            # click at 640x480 game coordinates (menu "Load game")
Key 'ENTER'; KeyCombo 'CTRL' 'S'            # keys
T 'loadlist'                                # screenshot -> docs\screens\tour\loadlist.png
Quit-Wiz8
```

* Coordinates are always the game's 640x480 space; with the wide canvas, `x` may be negative
  or above 640 for elements in the side areas (`x640 = screen_x * canvasW / screenW - (canvasW-640)/2`).
* `game.ps1` is the base (start/quit, clicks, `Shot`); `play.ps1` adds held keys, `Snap` and
  `GShot`; `play_create.ps1` has a quick-new-party macro; `win_shot.ps1` captures the game
  window; `boost_shot.ps1` brightens a screenshot to make seams visible.

### Pitfalls

* Dot-sourcing `game.ps1`/`play.ps1` resets `$script:GameDir` and `$script:Exe`
  (`play.ps1` defaults to `games\ru` + `Wiz8Runtime.exe`). Set them after dot-sourcing, as
  `hybrid_session.ps1` does.
* The in-game screenshot `GShot` (file request `wiz8shot.req`; works even with the monitor off)
  failed in window/fullscreen modes and on freshly installed clean copies; use `T`/`win_shot.ps1`
  there.
* Clicks and screenshots go to whatever window is in front. If the user moves the mouse,
  retry. Windows notifications can cover the bottom-right corner: `T` blanks it, and you must
  delete any screenshot that shows the desktop or private information.
* Saves made in the Russian game show garbled text in the English game's message log; that is
  the save's content, not a bug.
* A stale `wiz8hy_hooks.txt` next to a new `wiz8hy.dll` crashes the game at start.

## Fast testing (the patch author's rule, 2026-10-22)

Sandbox runs are slow and block the one sandbox, so a test takes the shortest route to the
state it needs; normal play only when nothing faster can show the result (say why in the
report). Plan the shortcut before running. Known shortcuts (scripts in `build\tmp\`, not in
git; addresses are the GOG/Steam 1.2.4 exe):

* Position: camera `0x65a0f8`, `+0x8c` position (x, y, z floats), `+4` yaw
  (`build\tmp\fps-ledges\scripts\fp.ps1`: teleport, turn). A drop of a few thousand units kills
  the party by fall damage: the quickest party wipe.
* Level change: write the pending screen `0x68ed10` (`+4` = 3, `+8` = level id, `+0xC` = 4,
  then the id = 4) for the game's own "Entering..." load at the level's entrance; current level
  `0x686a70`, current screen `0x68ec78`. Which level a save is in: `build\tmp\fps-ledges\scripts\savelevel.py`.
* Many loads of a level: Options - Load Game - Load in a loop (`build\tmp\crash-arnika\reproduce\`).
* Archive open files: the monitor in `build\tmp\crash-arnika\reproduce\` (per library: count,
  array size, open names).
* Map state (zoom, position, tool, cursor): `build\tmp\map-audit\ingame\maplib.ps1`.
* Developer mode (`0x689B32`) is not usable: with it set, the main game and the menu request the
  exit screen every frame.

## Comparing with the original code

* `scripts\tools\retail_asm.py 0x<address>`: disassembly of one original function, to check a
  suspected bug against the original before changing anything (we only fix original bugs that
  block widescreen). To check behaviour, test with the patch off: `[Hybrid] Enabled=0` or
  `[General] Enabled=0` in `wiz8ws.ini`.
* w8diff ([w8diff.md](w8diff.md)): runs the same function in the original exe and in the port with
  the same inputs and compares the results (internal; needs the port build).
