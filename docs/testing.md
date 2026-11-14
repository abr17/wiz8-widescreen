# Testing

Most of the patch is tested by running the game. This page covers the automated tests, the
test copies, the play-automation scripts and the pitfalls found so far.

## Automated tests

| Test | What it checks | Described in |
|---|---|---|
| `build\test_filenames.exe` (`cmake --build build --target test_filenames`) | the loader's file name wrappers for UTF-8 Windows, without the game | [loader.md](loader.md), "Game file names on UTF-8 Windows" |
| `python -I scripts\hybrid\build_hybrid.py --selftest` | the annotation and name parsers, the binding guard's own logic and the Mod check's; every build of `wiz8hy.dll` runs it first | [hybrid.md](hybrid.md) |
| `python3 tools_src/setup/tests/zip_writer_test.py` | the archive writer of the installer's report file, without Windows | "The installer's tests" below |
| `tools_src\setup\tests\test_all.ps1` | the installer's scenarios on a clean game copy, in Windows Sandbox | "The installer's tests" below |
| `scripts\linux\linux_bench.ps1` | the start under Wine and Proton with the real game, in a Docker container | "Linux / Proton bench" below |
| the render driver's test suites | the render driver, as a project of its own | [its testing.md](../drivers/srdd_d3d11/docs/testing.md) |

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
   `wiz8hy.dll: N functions replaced` with N = entries in `transplant_wide.json`, 290 in 1.0.3;
   `wiz8wide.log` shows the canvas width `W=`; `wiz8hy.log` lists the hooks and, after a crash,
   the crash addresses: turn them into names with `scripts\hybrid\symbolize.py`).
3. A walk through the screens: main menu, options (all pages), load/save list, game, journal,
   map, camp, combat, spell and item panels, character sheet tabs, a chest or NPC.
4. Uninstall: the folder matches the original byte for byte (compare file hashes before/after).
5. A read-only `3DVideo.CFG` that names another driver or size (the original's `DirectX7`,
   say): the game starts as usual, the file is rewritten and has lost the attribute, and
   `wiz8wide.log` has `[Display] 3DVideo.CFG rewritten: ...`. A file that cannot be written
   at all gives `[Display] 3DVideo.CFG could not be written: ...`, and the game starts with
   the driver and the size the file names.
6. The error boxes of the video start. With `Dll\srDD_D3D11.dll` taken out of the game folder
   the game stops with "Video device cannot be started: the render driver Dll\srDD_D3D11.dll
   is missing, could not be loaded or found no graphics device it can use." and the advice
   that follows it (reinstall the patch; a Direct3D 10 class card and current graphics
   drivers; the driver's log). An output that cannot be opened stops with "Could not open video
   output device. See the log of the widescreen patch's render driver, Dll\srDD_D3D11.log."

`wiz8wide.log` also prints `[Stretch] no strip: ...` when a stretched panel has no seamless art
file in `assets\Data\WIDE\STRETCH`. Such a line means a visible seam; make the strip with
`scripts\art\stretch_quilt.py` (see [scripts/README.md](../scripts/README.md)).

## The installer's tests

`tools_src\setup\tests\test_all.ps1` runs the installer's scenarios on a fresh copy of
`games\reference` in Windows Sandbox ([building.md](building.md), section 8): a fresh install,
an update from the previous release, the game running, a rollback from a newer version, a newer
manifest format, a copy that fails halfway, an install over a manual one, an empty manifest and
the diagnostics checkbox; the uninstalls on the way must give the original back byte for byte.
Four more scenarios:

* S9 starts the installer with the game folder as its working directory, as after unpacking
  the archive into it (the Sandbox has no GOG key): `--install ""` is refused (exit code 1, the
  "does not contain Wizardry 8" message, the folder unchanged: no folder named after a package
  file), `--install .` installs and `--uninstall .` gives the folder back byte for byte, and
  the window started there shows the not-found status with an empty folder box
  ([loader.md](loader.md), "Finding the game under Wine", on the full-path rule).
* S10 is the report file ([loader.md](loader.md), "The report file"). It makes the logs,
  session folders and crash dumps a played and crashed game leaves, one of the logs longer
  than 8 MB, runs `--report` and reads the zip back with Windows' own `System.IO.Compression`:
  the expected files byte for byte, the long log cut in its middle with the line that says so,
  nothing foreign, the dump that does not fit left out and named, under 25 MB, the game folder
  unchanged; `report.txt` with the patch, game and system lines, the lines of the program
  files in the game folder (the patch's three with size, time and SHA-256, the dgVoodoo files
  absent) and the note on the cut log. Then it presses "Report a problem..." in the window,
  declines the question (so no browser starts) and checks the file on the Desktop, its path on
  the clipboard and the sentence of the message that says not everything fit. A reinstall
  after that moves the last session's five logs into one new `Wiz8Logs\` folder.
* S11 is a game folder without `3DVideo.CFG`: the install lists the file, a reinstall removes
  the one the patched game wrote in between and does not save it as an original, and an
  uninstall, also by the previous release's installer, removes it.
* S12 is a package without the render driver (`files\Dll\srDD_D3D11.dll` deleted): a fresh
  install and an update from the previous release are refused with the message that names the
  missing file, and the folder stays as it was.

The archive writer alone, `tools_src\setup\zip_writer.h`, is plain C++ and has its own test,
which needs no Windows: `python3 tools_src/setup/tests/zip_writer_test.py` builds
`zip_writer_test.cpp` with `g++`, packs edge cases (empty and tiny files, runs around the
longest match, repeats just inside and just outside the 32 KB window, random bytes, logs, a
dump-like file, a non-English name) and a few hundred random archives, and reads every one back
with Python's `zipfile` (and `unzip -t`). It also checks the archive's size limit (a file that
fills it exactly goes in; with a limit one byte smaller it is refused; of three files the one
that does not fit is refused and the next goes in) and the other refusals: a file without a
name and the 65535th file. `--exe` runs a Windows build of the test program instead, for
example through Wine.

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

## Fast testing

Sandbox runs are slow and block the one sandbox, so a test takes the shortest route to the
state it needs; normal play only when nothing faster can show the result (say why in the
report). Plan the shortcut before running. Known shortcuts, written into the memory of the
running game (the addresses are those of the GOG/Steam 1.2.4 exe; no script for them is in the
repository):

* Position: camera `0x65a0f8`, `+0x8c` position (x, y, z floats), `+4` yaw. A drop of a few
  thousand units kills the party by fall damage: the quickest party wipe.
* Level change: write the pending screen `0x68ed10` (`+4` = 3, `+8` = level id, `+0xC` = 4,
  then the id = 4) for the game's own "Entering..." load at the level's entrance; current level
  `0x686a70`, current screen `0x68ec78`.
* Many loads of a level: Options - Load Game - Load in a loop.
* Developer mode (`0x689B32`) is not usable: with it set, the main game and the menu request the
  exit screen every frame.

## Comparing with the original code

* `scripts\tools\retail_asm.py 0x<address>`: disassembly of one original function, to check a
  suspected bug against the original before changing anything (we only fix original bugs that
  block widescreen; other fixes go behind the Original Bug Fixes switch,
  [experimental.md](experimental.md)). To check behaviour, test with the patch off:
  `[General] Enabled=0` in `wiz8ws.ini`. `[Hybrid] Enabled=0` is not the original game: it
  leaves the loader's older hooks on, and it is not supported ([hybrid.md](hybrid.md), "How it
  is enabled").
* w8diff ([w8diff.md](w8diff.md)): runs the same function in the original exe and in the port with
  the same inputs and compares the results (internal; needs the port build).

## Linux / Proton bench

`scripts\linux\` runs the game under Linux Wine or Proton on a Windows PC, in a Docker
container (Docker Desktop, WSL2 backend, Linux containers). It answers "does the patch load and
start under Wine/Proton, and through which route" for the Wine and the Proton of its image. No
real Linux PC and no Steam Deck was used; "Limits" below lists what the bench does not cover.

Isolation, as with Windows Sandbox:

* Every run is a new container (`docker run --rm`) from the same image; it starts from a fresh
  copy of a clean prefix baked into the image and a fresh copy of the game, and nothing of it
  is left afterwards.
* Only three folders are mounted: the game (read-only, default `games\reference`), the patch
  package (read-only, default `build\package\Wiz8Widescreen`) and a new output folder
  `build\tmp\linux-bench\<time>-<runner>-<install>\`. The game files never leave the machine;
  the image contains none. `-Zip` also extracts the zip once into
  `build\tmp\linux-bench\_zip\<name>-<hash>\` (a new folder when the zip's content changes).
* No network (`--network none`), a non-root user, `--cap-drop ALL`, `no-new-privileges`,
  memory and CPU limits.
* `-Gpu` adds only WSL's GPU device `/dev/dxg` and the WSL driver libraries (`/usr/lib/wsl`,
  read-only); see "The GPU" below.
* `-Show` runs the same image as a throw-away WSL2 distro instead, to watch the game in a window
  (see "Watching a run" below).

The image (`scripts\linux\Dockerfile`, built by the script on first use and again whenever
`Dockerfile`, `bake.sh`, `bench.sh`, `sandbox.sh` or `wsl.conf` change): Ubuntu 24.04, Ubuntu's
Wine 9.0 (`-Runner wine`), GE-Proton10-25 (`-Runner proton`, the default; started like
umu/Lutris do, checked against a fixed SHA-256 when the image is built), Xvfb, Xephyr, xdotool,
and Mesa's software
drivers (llvmpipe for OpenGL, lavapipe for Vulkan/DXVK). By default the game runs in a Wine
virtual desktop of `-Desktop` size. `-Desktop none` (`none:1920x1080` for another size) runs it
on a bare X screen instead (the bench's own X server, not a real Linux desktop): there Ubuntu's
Wine 9.0 has only the screen's own mode, at 0 Hz, so a display mode change fails (the patch
before 1.0.3 then falls back to borderless; the original game stops with "Video device does not
support video resolution."), while GE-Proton10 lists its emulated modes at 60 Hz and changes
modes fine (it scales the picture; the X screen keeps its size). The patch's own full screen
asks for no mode change at all ([loader.md](loader.md), "Full screen under Wine").
The first build downloads about 1 GB and takes 5-10 minutes; the image takes about 5 GB
in Docker Desktop's disk (see the note on Docker Desktop below). A run takes about 10 s plus
the game copy and `-Wait`.

```powershell
powershell -File scripts\linux\linux_bench.ps1                                        # Proton, files copied, version=n,b (Wine's own ddraw)
powershell -File scripts\linux\linux_bench.ps1 -Overrides none                        # a player who set no launch option
powershell -File scripts\linux\linux_bench.ps1 -Install setup -Overrides none         # the installer's registry route
powershell -File scripts\linux\linux_bench.ps1 -Gpu                                   # OpenGL on the Windows GPU; the game's 3D stays on software Vulkan ("The GPU" below)
powershell -File scripts\linux\linux_bench.ps1 -Show -Gpu -Hold                       # in a window, to watch (and play)
powershell -File scripts\linux\linux_bench.ps1 -Overrides 'version=n,b;ddraw=n,b'     # a DDraw.dll in the game folder (up to 1.0.2: dgVoodoo), for experiments
powershell -File scripts\linux\linux_bench.ps1 -Runner wine -Actions build\tmp\linux-bench\menu.txt -Canvas 768
powershell -File scripts\linux\linux_bench.ps1 -Zip release\Wiz8Widescreen-1.0.2.zip  # a released package
powershell -File scripts\linux\linux_bench.ps1 -Then none                                # + a second start without the launch option
powershell -File scripts\linux\linux_bench.ps1 -Install setup -Overrides none -Then none -Uninstall
powershell -File scripts\linux\linux_bench.ps1 -Launcher shortcut -Install setup -SetupPrefix other -Overrides none -Then 'version=n,b,none'
powershell -File scripts\linux\linux_bench.ps1 -Ini Display.Mode=fullscreen,Display.ScreenWidth=1024,Display.ScreenHeight=768 -Desktop none
powershell -File scripts\linux\linux_bench.ps1 -Load <a save>.SAV -Wait 90                # straight into the 3D world (Wiz8.exe /LOAD)
```

Since 1.0.3 the game's 3D goes through the package's `Dll\srDD_D3D11.dll` (Direct3D 11: DXVK on
lavapipe under Proton, wined3d on llvmpipe under Ubuntu's Wine). The bench copies the driver's
log into the output folder as `srDD_D3D11.log` and puts a `render driver:` line into
`summary.txt`: the device, where the shaders came from (embedded, or compiled at run time on
Wine's own Direct3D 11) and the number of error lines. The package has no `DDraw.dll`. The game's own
`DDRAW.DLL` import gets Wine's `ddraw.dll`. With a package up to 1.0.2 and the default `-Install
files`, which copies `files\` by hand, dgVoodoo included, `-Overrides 'version=n,b;ddraw=n,b'`
loads dgVoodoo: 2.8.7.5 crashes at its first `CreateSurface` under every Wine (`ddraw+0x9928`,
with software rendering and on the GPU alike; Wine bug 58731; [loader.md](loader.md), "Which
ddraw").

`-Overrides none` and `-Overrides ''` both mean "WINEDLLOVERRIDES not set"; use `none` when
calling from Windows PowerShell 5.1, which drops an empty `''` argument to `powershell -File`.
The three standard checks (repeat with `-Runner wine`):

| Check | Options | Expected in `summary.txt` |
|---|---|---|
| the bug: no launch option | `-Overrides none` | `patch loaded: no`, `loaddll version.dll: builtin` |
| the launch option | (defaults) | `patch loaded: yes (... hooks installed: yes ...)`, `started from: version.dll`, `loaddll version.dll: native, then builtin`, `loaddll ddraw.dll: builtin`; since 1.0.3 also `wine settings: *version written (native,builtin), *ddraw written (builtin); the patch starts without WINEDLLOVERRIDES in this prefix \| game folder listed in ...` |
| the installer | `-Install setup -Overrides none` | `registry AppDefaults\Wiz8.exe: *ddraw=builtin *version=native,builtin` and `patch loaded: yes`; with the 1.0.3 installer and the GOG/Steam game also `started from: binkw32.dll (no launch option needed); version.dll: our copy, forwarding only`, `loaddll binkw32.dll: native`, `loaddll binkw32_wiz8wide.dll: native`; with the 1.0.3 installer `game-added.txt` has no `DDraw.dll`, `D3DImm.dll` or `dgVoodoo.conf` (the package has none and the installer never installs them), and `loaddll ddraw.dll: builtin` |

The installer route needs an installer with the Wine registry code (after 1.0.2; the 1.0.2
installer writes no registry key, so the third check gives `registry AppDefaults\Wiz8.exe: not
present` and `patch loaded: no` with it). The 1.0.3 installer under Wine also sets up the
binkw32 route over the game's original `binkw32.dll` ([loader.md](loader.md), "The patch starts
through binkw32.dll"), and it writes the registry values because the bench's game folder is
one no launcher lists (the verdict "Wine prefix not known"); so both copies of the patch load,
and the `binkw32.dll` one starts it. The bench prints the value names as the installer
wrote them (`*ddraw` or `ddraw`; Wine takes both). With
`-Install setup` the bench runs `Wiz8WideSetup.exe --install` in the same prefix the game then
uses (or, with `-SetupPrefix other`, in a second one) and answers its message boxes with keys: a box gets `y` (Yes on a Yes/No box, whose
default button is No) until the screen changes, and a box that `y` does not close is an OK box
and gets Return. Escape is never sent: Wine answers a Yes/No box with Cancel on Escape, which
the installer takes as No. Every box is saved as `setup-NN.png`. With the GOG/Steam 1.2.4 exe
the only box is the final message; the "not the tested version" Yes/No box appears only for
another exe (as with a test mock).

Options for the Linux features of 1.0.3 (the patch's own Wine setting, the binkw32 route,
finding the game, full screen under Wine; `bench.sh`'s header has the details):

* `-Then <overrides|none>`: one more start of the game in the same prefix and game copy, with
  that `WINEDLLOVERRIDES`. Several in one string: `-Then 'version=n,b,none'` is a second start
  with the launch option and a third one without it (`powershell -File` passes an array as one
  string anyway; the script splits it before each `none` and each `NAME=`). Each start gets the
  same `-Wait`, `-Actions`, `-Timeout` and `-Hold`; its files go to `start2\`, `start3\`, ...,
  its summary lines end in `(start 2)`, ...
* `-Uninstall`: `Wiz8WideSetup.exe --uninstall` after the last start, in the installer's prefix;
  then the registry again (`(after uninstall)` lines, `uninstall\`) and the game copy compared
  with the one before the install (`uninstall\game-diff.txt`: `+` added, `-` missing, `~`
  changed).
* `-GlobalOverride NAME=ORDER[,...]`: values in `HKCU\Software\Wine\DllOverrides` of the game's
  prefix, as winecfg or winetricks set them (`ddraw=native`), before the installer and the
  first start.
* `-SetupPrefix other`: the installer runs in a second fresh prefix, not the game's (as when it
  is added to Steam as a non-Steam game of its own, or started with plain wine); needs
  `-Install setup` or `-Uninstall`. Its registry after the install: the `(setup prefix)` lines
  and `setup-prefix\`.
* `-Launcher shortcut|heroic|lutris`: a fake home folder (the runner's `HOME`, which Wine passes
  on as `WINEHOMEDIR`) with that launcher's files for a GOG game, the game copy and its prefix
  where that launcher keeps them, and the game started by its Linux path with that launcher's
  environment; `home.txt` lists the files. `shortcut`: Steam with the game as a non-Steam game
  (`shortcuts.vdf`, the prefix `compatdata/<shortcut id>/pfx` with only `C:` and `Z:`; Proton
  with Steam's variables, but `UMU_ID` set and empty, which skips Proton's `steam.exe`, which
  would wait for a Steam client). `heroic`: `~/.config/heroic`, the prefix
  `~/Games/Heroic/Prefixes/default/Wizardry 8`, Proton started as umu starts it. `lutris`: a
  `games/*.yml`, the game in its prefix's `drive_c/GOG Games/Wizardry 8`. The installer always
  gets the folder as `Z:\...`.
* `-Ini Section.Key=Value[,...]`: written into the game copy's ini files after the install,
  before the first start. The file is the one whose section has the key (also as a `;Key=`
  comment), else the one that has the section, else `wiz8ws.ini` for `[General]` and `[Hybrid]`
  and `wiz8wide.ini` for any other; a missing key, section or file is added, and the changed
  files are copied to the output folder.
* `-Desktop none`, `none:WxH`: a bare X screen, no Wine virtual desktop (above).

The checks (repeat each with `-Runner wine`). "The GOG/Steam game" is the real one, where the
installer sets up the binkw32 route; without the route (another mod's `binkw32.dll`, or a mock
game without RAD's file) the registry values and the launch option do the job:

| Check | Options | Expected in `summary.txt` |
|---|---|---|
| the patch keeps its own setting | `-Then none` | `wine settings: *version written (native,builtin), *ddraw written (builtin); the patch starts without WINEDLLOVERRIDES in this prefix \| game folder listed in ...`; `patch loaded (start 2): yes`, `loaddll version.dll (start 2): native, then builtin`, `wine settings (start 2): *version already set (native,builtin), *ddraw already set (builtin); ...` |
| install, two starts, uninstall | `-Install setup -Overrides none -Then none -Uninstall` | `patch loaded: yes` at both starts; `game copy after uninstall: the same as before the install (every file and its contents)`; `registry AppDefaults\Wiz8.exe (after uninstall): not present`, `registry Wiz8Wide (after uninstall): not present` |
| the player asks for dgVoodoo | `-Overrides 'version=n,b;ddraw=n,b' -Then none` (with a package up to 1.0.2 and `-Install files`, the default: since 1.0.3 neither the package nor the installer puts dgVoodoo into the folder) | start 1 (the game crashes in dgVoodoo): `wine settings: *version written (native,builtin), *ddraw not written: WINEDLLOVERRIDES asks for ddraw=n,b; ...`; start 2: `loaddll ddraw.dll (start 2): builtin`, `patch loaded (start 2): yes` |
| a global ddraw setting | `-GlobalOverride ddraw=native -Then none` (with a package up to 1.0.2 and `-Install files`, as above; with a 1.0.3 package there is no `DDraw.dll` and the game does not start: [loader.md](loader.md), "Which ddraw") | start 1: `loaddll ddraw.dll: native`, `wine settings: ..., *ddraw written (builtin; ddraw.dll came from the game folder this time, Wine's own from the next start); ...` (the real game then crashes in dgVoodoo); start 2: `loaddll ddraw.dll (start 2): builtin` |
| the installer in the game's prefix | `-Launcher shortcut -Install setup -Overrides none` (also `heroic`, `lutris`) | `registry AppDefaults\Wiz8.exe: *ddraw=builtin *version=native,builtin`, `patch loaded: yes`; the final message (`setup-NN.png`) for the GOG/Steam game `the patch starts by itself under Wine and Proton ...`, without the route `the game's own Wine prefix is now set up for the patch ...` |
| the installer in another prefix | `-Launcher shortcut -Install setup -SetupPrefix other -Overrides none -Then 'version=n,b,none'` (also `heroic`, `lutris`) | `registry AppDefaults\Wiz8.exe (setup prefix): not present`; the GOG/Steam game: `patch loaded: yes` at every start, start 1 `started from: binkw32.dll (no launch option needed); version.dll: Wine's own` and `*version written`, starts 2 and 3 `started from (start N): binkw32.dll (no launch option needed); version.dll: our copy, forwarding only` (start 2 through the option, start 3 through the `*version` value start 1 wrote); without the route: the final message `the game (found by: Steam shortcut "Wizardry 8") runs in another Wine prefix ...`, start 1 `patch loaded: no`, start 2 `yes` with `*version written`, start 3 `yes` without the option |
| full screen under Wine | `-Ini Display.Mode=fullscreen,Display.ScreenWidth=1024,Display.ScreenHeight=768` (also 1280x720; `-Desktop 1920x1080`, `-Desktop none`) | `fullscreen picture: 1024x768 drawn, scaled into 1066x800 at (107,0) of the 1280x800 window (click640 maps into it)`; `start.png` letterboxed with black bars; `click640 323 257` opens the load list, a click in a bar does nothing; after a switch back to borderless in Options `click640` aims at the whole screen again (`[Display] output: borderless, no scaling`). Needs a `wiz8hy.dll` built from 1.0.3's `decomp\` |

For the binkw32 route also look at the screenshots and `runner.log` of a longer run (`-Wait 60`
or `-Actions`): the intro videos play (no `unimplemented function` in `runner.log`), the menu
shows the patch's version and the 3D world works. The bench has no option for a store's file
check (the original `binkw32.dll` put back after the install); that case was checked only with
mocks ("Wine checks without the game" below).

`summary.txt`, one line per check:

* `patch loaded`: `yes` when `wiz8ws.log` was written (the patch writes it when it starts, as
  `version.dll` or as `binkw32.dll`), with its key lines (`hooks installed`, `wiz8hy.dll: N
  functions replaced`, `patch inactive (...)`, the Wine ddraw line).
* `started from`: which copy started the patch: `version.dll`; `binkw32.dll (no launch option
  needed); version.dll: Wine's own` (or `...: our copy, forwarding only`); `version.dll;
  binkw32.dll: a copy of the patch, forwarding only (...)`.
* `wine settings`: what the patch did with its own Wine setting (the text after `wine settings
  (HKCU\...\DllOverrides): ` in `wiz8ws.log`), then ` | ` and its other `wine settings:` lines
  (the game folder's entry); with a patch before 1.0.3 `no "wine settings" line in wiz8ws.log
  (a patch that keeps no Wine setting)`.
* `loaddll <dll>`: how Wine loaded the dll into the game process, from the `+loaddll` lines
  (`loaddll.txt`): `native` = the file in the game folder, `builtin` = Wine's own; with the patch
  `version.dll` is `native, then builtin` (the proxy loads Wine's real `version.dll`).
  `loaddll binkw32_wiz8wide.dll` appears when the game copy has that file (the binkw32 route).
* `fullscreen picture`: from `wiz8wide.log`'s full-screen line (`[Display] fullscreen
  1024x768: scaled into ...`): `1024x768 drawn, scaled into 1066x800 at (107,0) of the
  1280x800 window (click640 maps into it)`; `none: ...` with the borderless fallback's line;
  `no [Display] fullscreen line in wiz8wide.log (wiz8wide.ini has Mode=fullscreen)` with a
  `wiz8hy.dll` before 1.0.3. Only when the log has such a line or the ini asks for full screen.
* `registry AppDefaults\Wiz8.exe`: the values in the prefix at the end (`appdefaults.reg`).
* `registry Wiz8Wide`: the notes of the installer and the patch in `HKCU\Software\Wiz8Wide`
  (`Wine: *ddraw=builtin *version=native,builtin; Wine\Folders: Z:\...`), or `not present`
  (`wiz8wide.reg`). Both registry lines also come with ` (setup prefix)`, ` (after uninstall)`
  and ` (setup prefix, after uninstall)`.
* `overrides requested` / `overrides effective`: what the bench set, and what the game process
  really got (Proton appends its own entries, such as `d3d11=n` for DXVK).
* `gpu` and `gl renderer`: whether `-Gpu` was on, and the OpenGL renderer that the 64-bit
  `glxinfo` gets with the game's GL settings (`llvmpipe (...)` without `-Gpu`, `D3D12 (<the
  Windows GPU>)` with it).
* `install` (with `-Install files`: how many package files replaced game files; names match
  in any letter case, as on Windows, so `Data\` goes into an existing `DATA\`), `game copy
  after install` (`game-added.txt`), `game exit` (`exited by itself` or `stopped by the bench`
  after the screenshots; the exit code of a game run with Proton is that of the `proton`
  script), `actions` (`N of M done`; when the game has quit before a step, the rest are not
  run and the line says before which step), `hold` (with `-Hold`: how long, and whether the
  game was quit or the window closed), `timeout`, `screenshots`, timings.
* `uninstall` and `game copy after uninstall` (`-Uninstall`); `launcher`, `setup prefix`,
  `desktop`, `global overrides`, `ini`: how the run was set up.
* Every line of a start comes again for each later start, with ` (start N)`.
* `result: ok`, or `bench error: ...` (exit code 2) when the bench itself failed. `patch loaded:
  no` is a result, not an error.

Other files: `runner.log` (Wine's stderr or the Proton log), `setup-runner.log`, `wiz8*.log`,
`Wiz8Wide.installed.txt`, `appdefaults.reg`, `wiz8wide.reg`, `loaddll.txt`, `actions.log` (each
step with the time it started, counted from the game start), `xserver.log` (Xvfb's or Xephyr's
output), the screenshots (`start.png` after `-Wait` seconds); `start2\`, ... for later starts;
`uninstall-runner.log`, `uninstall-NN.png` and `uninstall\` with `-Uninstall`; `setup-prefix\`
with `-SetupPrefix other`; `home.txt` with `-Launcher`; the changed ini files with `-Ini`.

Watching a run (`-Show`), as in Windows Sandbox: Docker Desktop cannot show a window on the
Windows desktop, but WSL can (WSLg, Windows 11 or WSL from the Microsoft Store). With `-Show`
the script still builds the image with Docker, exports it once per image version to
`build\tmp\linux-bench\_wsl\rootfs-<image id>.tar` (about 4 GB, half a minute; a newer image
replaces it) and imports it as a new WSL2 distro `wiz8-bench-<label>` for this run, with its
disk in `_wsl\<label>\` (import and start: about 15 s); after the run the distro and its disk
are deleted (`wsl --unregister`). The bench's screen is then an Xephyr window titled "Wizardry 8
bench" on the Windows desktop instead of the invisible Xvfb; the screenshots and actions work as
before, and a click, a key press or the mouse pointer in the window reaches the game too (keep
the mouse off the window while `-Actions` run). `-Hold` keeps the game running after the actions
until it is quit or the window is closed. Isolation in the distro (`scripts\linux\sandbox.sh`,
run as root by the script, and `scripts\linux\wsl.conf` as its `/etc/wsl.conf`): the Windows
drives are not mounted and Windows programs cannot be started (WSL's handler for them stays
registered, as it is shared by all distros of the VM, but with interop off a start never reaches
Windows); the same three folders are mounted (the game and the package read-only) in a mount
namespace of `sandbox.sh`'s own; `bench.sh` runs as the non-root user without new privileges in
a network namespace of its own (no network). What differs from the container: the distro runs in
WSL's VM next to the other distros (Docker Desktop's included), WSL's memory and CPU limits
apply instead of `-Memory` and `-Cpus`, and the bench can use WSLg's X server (the window, the
clipboard). The game copy goes through WSL's Windows file sharing, which is slower than Docker's
mount. Run one `-Show` bench at a time: a new one deletes `wiz8-bench-*` distros left by a run
that was killed.

The GPU (`-Gpu`, Proton only): Docker passes no GPU by default, so the bench draws with Mesa's
software drivers. `-Gpu` gives the container WSL's `/dev/dxg` and `/usr/lib/wsl` (a WSL distro
has them anyway, so with `-Show` it only switches the driver), and Mesa's
d3d12 driver then draws OpenGL on the Windows GPU (`gl renderer: D3D12 (...)`). WSL's driver is
64-bit only, so the game runs in Proton's WoW64 mode (`PROTON_USE_WOW64=1`, set by `-Gpu`):
a 32-bit game on the 64-bit libraries. Ubuntu's Wine 9.0 has no such mode (`-Gpu -Runner
wine` is refused). Only OpenGL: Ubuntu's Mesa has no Vulkan driver for the GPU, so DXVK, and
with it the game's 3D (the patch's Direct3D 11 render driver), stays on lavapipe. So with a
1.0.3 package `-Gpu` does not put the game's 3D on the GPU: it changes the OpenGL renderer
(`gl renderer` in `summary.txt`) and runs the game in the WoW64 mode.

`-Actions` takes a text file, one step per line (`#` starts a comment; CRLF, a BOM or UTF-16
from a Windows editor are fine); it runs after `start.png`. `-Timeout` (default 300 s) covers
`-Wait` and the actions:

```text
sleep 3
shot menu                # -> menu.png
click640 323 257         # the game's 640x480 coordinates, as Click640 above (canvas: -Canvas, else W= from wiz8wide.log;
                         # in full screen under Wine inside the picture that wiz8wide.log's last
                         # output line names)
rclick640 -52 465
click 640 400            # desktop pixels
key Escape               # xdotool key names: Return, ctrl+s, F5
```

The steps run at fixed times, and the game's pace differs between runs: without `-Gpu` the
main menu comes after the Sirtech logo at about 30 s with `-Show` (no CPU limit) and about 43 s
in the container. Write steps that fit either screen: wait for the menu instead of pressing
Escape while the logo shows (in the main menu Escape quits the game); a click in a corner,
`click 5 5`, does nothing on the logo or in the menu. When the game has quit, the remaining
steps are not run and `actions` in summary.txt says before which one.

Limits: software rendering unless `-Gpu` (slow; frame rates mean nothing, colours and
filtering may differ from a GPU), and with `-Gpu` OpenGL only, through D3D12 and WoW64, which
is not what a Linux PC or a Steam Deck uses (with `-Gpu` the game, the original too, can hang while
loading a save or opening the automap: a fault of that path, not of the patch); under Ubuntu's
Wine 9.0 the original game without the patch, and the patch up to 1.0.2, show a black 3D view
in the world (Wine 9.0's DirectDraw colour fill makes the game's 2D layer opaque; the patched
game fills by itself since 1.0.3, [releases/1.0.3.md](releases/1.0.3.md)); no sound device; not the Steam client (no
Steam runtime container, overlay or per-game Steam settings; `-Launcher` only lays out the
launchers' files) and GE-Proton rather than Valve's Proton; the game runs in a Wine virtual
desktop, or with `-Desktop none` on an X server without a window manager, so alt-tab and
window-manager behaviour are not tested, and a real monitor mode switch needs Xorg's dummy
driver (`xserver-xorg-video-dummy`, not in the image); the clicks assume the game window starts
at the screen's top left corner and, outside full screen under Wine, covers the whole screen;
gamescope (Steam Deck game mode) and Wayland are not covered; a 2 GB game copy through the
Windows mount adds some seconds to every run.

Docker Desktop keeps its images in its own disk file, by default under `%LOCALAPPDATA%\Docker`,
outside the workspace; to keep everything in the workspace, move it in Docker Desktop:
Settings - Resources - Advanced - Disk image location. Its WSL2 memory (default half of the RAM)
must be at least `-Memory` (default 6g). After a build, Docker's build cache can hold a second
copy of the image's layers (with the containerd image store); `docker builder prune -a` frees
it (it removes the build cache of other projects too) and leaves the image. The disk file grows
to its largest size and does not shrink by itself: each run's game copy (about 2 GB) is freed
inside it when the container ends.

## Wine checks without the game

The Linux side of the loader and the installer can be checked on any Linux machine with Wine
and GE-Proton (a container is enough), without the game's files: mock files behave like the
game where it matters. The scripts of such a run are not in the repository; the method:

* Build with the llvm-mingw of `Tools\` (Linux build of the same release): Ubuntu's own LLVM 18
  lld writes wrong forwarder texts ([building.md](building.md), section 3).
* The mock game: a `Wiz8.exe` that imports `ddraw.dll`, the 12 `BINKW32.DLL` functions under the
  same decorated names, then `sr.dll`, creates a window (the patch starts on the first
  `CreateWindowExA`) and writes which modules it got and which one hooked `CreateWindowExA`; an
  `sr.dll` that imports `GetFileVersionInfoSizeA` from `version.dll`; a `binkw32.dll` with RAD's
  83 export names; a fake `DDraw.dll` that leaves a marker file. To the patch the mock exe is an
  unknown one (`patch inactive (unknown exe)`): the loader, the route and the Wine setting run,
  the game hooks do not. The mock `binkw32.dll` is not RAD's file, so the installer recognises
  it by its exports; the SHA-256 path stays untested.
* Every run in a new throw-away `WINEPREFIX`, with `WINEDEBUG=-all,+loaddll`; `wiz8ws.log`, the
  `+loaddll` lines and `user.reg` are read after `wineserver -w` (the registry is saved when the
  prefix's last program ends).
* Fake home folders with Steam's (`libraryfolders.vdf`, `shortcuts.vdf`, an appmanifest),
  Heroic's, Lutris' and Bottles' files pointing at mock game copies, as `-Launcher` lays them out.

The loader and the installer of 1.0.3 were checked this way under Ubuntu's Wine 9.0 (a 64-bit
and a 32-bit prefix) and GE-Proton10-25 (its `proton` script with `UMU_ID=umu-default` and
`waitforexitandrun`, as umu starts it; for the installer also as Steam starts it, with Steam's
variables and no `UMU_ID`), on a build that still drew through the game's DirectX 7 driver.
What is listed here does not depend on the render driver:

* `version.dll`: the export check (83 forwarders, all `binkw32_wiz8wide.<name>`, the same names
  as RAD's; the other exports exactly the 17 version functions); no option (not started), the
  launch option (started, values written, folder listed), the next start without it ("already
  set"), the binkw32 route on a fresh prefix and again (one header line, one `CreateWindowExA`
  hook, the Bink calls reach the original, its `BinkOpenMiles` pointer kept), both copies
  loaded, an exe that imports `sr.dll` first (then `version.dll` starts and the `binkw32.dll`
  copy only forwards), a stale `binkw32.dll` copy and a deleted `version.dll` (nothing starts,
  the videos still work), the setting's rules (the player's own value, a deleted value,
  `ddraw=n,b`, `DDRAW.DLL=native` and `*ddraw=n;ddraw=b` in `WINEDLLOVERRIDES`, a global
  `ddraw=native`, another exe, `wiz8.exe` in small letters, the game folder under a `Y:` link,
  `\\?\unix`, `X:`/`Z:` and `V:`/`Z:` names); folder names with Cyrillic and accented letters
  under a UTF-8 locale; a `version.dll` that is a hard link or a symlink to `binkw32.dll`.
* The installer: the route (install, a start with no setting, uninstall byte for byte, the
  original put back as by a store's file check: the "restored" status and Reinstall, the backup
  deleted, another mod's `binkw32.dll`, a package without forwarders, an interrupted and a
  failed install, a reinstall, the files in use); the window (preselection, the "Found by"
  line, Browse at the home folder, pasted folder forms) and every final message; each verdict
  with `--install` and `--uninstall` (the registry before and after, the clipboard read back
  with an X11 clipboard reader); an `X:`/`Z:` pair installed under one name and uninstalled
  under the other; a prefix without `Z:` (`\\?\unix` paths); a full disk (an 8 MB tmpfs) while
  the original `binkw32.dll` is saved and while it is put back (no cut-off backup and no
  cut-off `binkw32.dll` left, the copy kept when `binkw32.dll` cannot be put back), a cut-off
  backup left by an earlier run; the installer started in the game folder (no empty entry; an
  empty folder, or a relative one typed into the window, refused; `--install .` and
  `--uninstall .` made full paths) and through its own Steam shortcut there (not taken for the
  game's).
* Which `ddraw.dll` the game gets with a global `ddraw=native` (as winetricks sets it), after
  an install in that prefix and after a start with the launch option: Wine's own, in a 64-bit
  prefix, under Proton and in a 32-bit prefix, where the installer and the patch also write a
  per-program plain `ddraw=builtin` because such a prefix looks Wine's own `ddraw.dll` up by
  the plain name first ([loader.md](loader.md), "Which ddraw"). The same with a `DDraw.dll` of
  the player's in the game folder.
* That per-program plain `ddraw=builtin`: the install and a start with the launch option
  write it with its note; Uninstall removes it; with a `DDraw.dll` left in the game folder it
  stays and its note goes; a `*ddraw` or plain `ddraw` of the player's stays and nothing is
  written; `ddraw=n,b` in `WINEDLLOVERRIDES` writes nothing at that start; a note left under
  either name counts as deleted by the player.
* The bench: every option on mock games, under both runners.

What these cannot show: the real game (its videos and their sound through the forwarders, the 3D
world, `sr.dll`'s exports read from the `binkw32.dll` copy's DllMain), the render driver,
`wiz8hy.dll` built with MSVC, Windows. Those are the Linux bench with the real game, the
Windows Sandbox run and players' reports.
