# Wizardry 8 Widescreen

Native widescreen patch for **Wizardry 8** (GOG / Steam version 1.2.4, both ship the same
`Wiz8.exe`). The 2D interface and the 3D view are drawn wide (16:9, 16:10, 3:2 and the
original 4:3), with new wide loading screens, borderless / window / fullscreen modes and
display settings inside the game. Current release: **1.0.3**, see
[docs/releases/1.0.3.md](docs/releases/1.0.3.md).

The original `Wiz8.exe` is never modified.

The patch draws the game through its own Direct3D 11 render driver, `Dll\srDD_D3D11.dll`
([drivers/srdd_d3d11](drivers/srdd_d3d11/README.md)), and always uses it: the package holds no
wrapper, and none is needed. The driver needs a graphics card with Direct3D feature level 10_0
(a Direct3D 10 card or newer). Full screen keeps the monitor's resolution, with the picture
scaled to fit.

What it was tested on: one laptop with an NVIDIA RTX 4080 under Windows 11, where the game was
played, and Windows Sandbox for the automated checks. AMD and Intel cards, integrated
graphics, a card that has only feature level 10_0 or 10_1, and Windows 7, 8 and 10 were not
tried ([docs/releases/1.0.3.md](docs/releases/1.0.3.md) has the details).

Wine and Proton (Linux): run `Wiz8WideSetup.exe` with Wine or Proton, in any Wine prefix, and
press Install; no launch option is needed ([docs/loader.md](docs/loader.md), "Wine and
Proton"). This was tested only in a Docker test bench (GE-Proton and plain Wine 9.0, with
software rendering), not on a real Linux PC and not on a Steam Deck.

Options - Experimental holds optional features that are off by default: an animated main menu,
map mouse controls, fixes of the original game's own bugs and an alternative game tick
([docs/experimental.md](docs/experimental.md)). For players whose game closes by itself the
installer has a "Diagnostics mode" checkbox, which records how the game ended
([docs/loader.md](docs/loader.md)).

Bug reports: the installer's "Report a problem..." button saves the logs, the settings, the
crash dumps and a summary of the system as one zip on the Desktop and opens the
[bug report form](https://github.com/abr17/wiz8-widescreen/issues/new?template=bug_report.yml);
describe what happened and add the file. Reports are public, and the logs contain folder names
(so the user name).

## Made with AI

This patch was built with AI. The reverse engineering, code, installer and documentation
were written by AI coding agents (Claude Code, using REA for reverse engineering), directed
and tested by abr17. The missing widescreen art (loading screens, menu and credits
backgrounds, and more) was outpainted with generative AI: original images are kept
pixel-for-pixel, only the new side areas are generated, blended over a narrow strip at the
original edge. The marble side wings of the windows that stay 4:3 are made from the game's
own marble (pieces of the original backgrounds, nothing generated). The animated main menu
video and the art of the Options category "Experimental" were made with generative AI.

## Screenshots

Each picture shows the same moment three times: the original game (4:3), then the patch at
16:10 and at 16:9.

**Main menu**: the menu art is extended to the full width; the corner shows the patch version.
![Main menu: original 4:3, patch 16:10, patch 16:9](docs/screenshots/compare-01-main-menu.jpg)

**Options**: full-width option pages, with the patch's new settings (view distance; display mode and resolution on page 2; frame rate limit on page 3).
![Options: original 4:3, patch 16:10, patch 16:9](docs/screenshots/compare-02-options.jpg)

**Character sheet**: kept at 4:3 in the centre, with stone side panels.
![Character sheet: original 4:3, patch 16:10, patch 16:9](docs/screenshots/compare-03-character.jpg)

**Exploring**: the 3D view grows sideways (Hor+), and the party HUD moves to the screen edges.
![Exploring: original 4:3, patch 16:10, patch 16:9](docs/screenshots/compare-04-explore.jpg)

**Combat**: the crab fight on the starting beach, at the end of round 1.
![Combat: original 4:3, patch 16:10, patch 16:9](docs/screenshots/compare-05-combat.jpg)

## How it works (one minute)

```
Wiz8.exe (original)  ──loads──>  version.dll   (our proxy: src/, built with llvm-mingw)
                                     │  checks the exe (SHA-256 and the first bytes of the
                                     │  functions it touches);
                                     │  unknown exe -> does nothing, game runs as original
                                     └─loads──>  wiz8hy.dll  (the "hybrid": game functions
                                                 rebuilt from decompiled source with our
                                                 widescreen changes; each one replaces the
                                                 original function via a jmp patch; 290 in 1.0.3)

sr.dll (original, the    ──loads──>  Dll\srDD_D3D11.dll  (our Direct3D 11 render driver, in
game's 3D engine)                    place of the game's DirectX 7 driver; the driver's name
                                     comes from 3DVideo.CFG, where wiz8hy.dll puts "D3D11"
                                     at every start)
```

* The game's source code comes from a public **decompilation** of Wizardry 8
  ([agluszak/wizardry-8-decomp](https://github.com/agluszak/wizardry-8-decomp)). Our changes to
  it are published as a fork, [abr17/wizardry-8-decomp](https://github.com/abr17/wizardry-8-decomp)
  (branch `widescreen`, tags `wiz8-widescreen-<version>`), included here as the `decomp/` submodule;
  `wiz8hy.dll` is built from it (see [docs/decomp-fork.md](docs/decomp-fork.md)). That code is
  **not** under this repository's MIT licence: upstream has no licence file, and part of it is
  under Strategy First's non-commercial source licence (see the fork's README). The release
  zip ships the prebuilt `wiz8hy.dll`. The game code can also be built as a whole new exe,
  `Wiz8Runtime.exe` (the "port"), an **internal** tool for testing; it is never shipped.
* `wiz8hy.dll` contains only the functions we changed; everything else stays the original,
  tested game code. See [docs/hybrid.md](docs/hybrid.md).
* The render driver is a project of its own, with its own version, releases, tests and
  documentation (repository [abr17/wiz8-d3d11](https://github.com/abr17/wiz8-d3d11),
  included here as the `drivers/srdd_d3d11` submodule); the patch only carries the built DLL.
  See [its README](drivers/srdd_d3d11/README.md).
* Wide art (loading screens, stretched panels, side wings) are `.STI` files in the game's
  own format, made from the game's art. They live in `assets/` (not in git).

## Repository map

| Path | What | In git |
|---|---|---|
| `src/` | `version.dll`: proxy loader, exe check, ini, hybrid loader (`hooks_hybrid.cpp`), diagnostics, game file names on UTF-8 Windows, the start under Wine; also the older stand-alone hooks, which run only with the unsupported `[Hybrid] Enabled=0` | yes |
| `src/hybrid/` | `HybridInstall` (patches the original functions); compiled **into `wiz8hy.dll`** | yes |
| `src/w8diff_dll/` | `w8diff.dll` of the internal comparison harness | yes |
| `CMakeLists.txt`, `cmake/`, `build.ps1` | build of `version.dll` (llvm-mingw, i686) | yes |
| `third_party/minhook` | hooking library (git submodule) | yes |
| `tools_src/setup/` | `Wiz8WideSetup.exe`, the installer (Win32 C++, en/ru/de/fr), and its tests | yes |
| `drivers/srdd_d3d11/` | `srDD_D3D11.dll`, the Direct3D 11 render driver: git submodule (repository [abr17/wiz8-d3d11](https://github.com/abr17/wiz8-d3d11)) with the driver's source, tests and documentation, see [its README](drivers/srdd_d3d11/README.md). Its `tools/` folder holds the driver's development tools, among them `srdd_trace` (records the calls between `sr.dll` and the game's DirectX 7 driver), `srdd_harness` (runs a render driver without the game) and `golden_compare` (compares the results of test runs) | yes (submodule) |
| `dist/` | files shipped as-is: `wiz8ws.ini`, `wiz8wide.ini`, `README_*.txt` for players | yes |
| `scripts/` | build, package, hybrid, test-play, art and analysis scripts, see [scripts/README.md](scripts/README.md) | yes |
| `docs/` | documentation, see [docs/README.md](docs/README.md) | yes |
| `decomp/` | game source: the decompilation + our changes; git submodule [abr17/wizardry-8-decomp](https://github.com/abr17/wizardry-8-decomp) at tag `wiz8-widescreen-1.0.3` (not MIT, see above) | yes (submodule) |
| `assets/` | wide `.STI` art, `FALCON.STI`, laid out like the game folder | no |
| `games/` | game copies: `reference` (pristine, read-only), `work` (test copy with the patch), `ru` (test copy with the Russian translation) | no |
| `Tools/` | portable toolchain (llvm-mingw, CMake, portable MSVC, Ghidra, ...) | no |
| `build/` | build output (`version.dll`, `hybrid/`, `vc2022/` port build, `package/`) | no |
| `release/` | released zips exactly as published (`Wiz8Widescreen-<version>.zip`) | no |
| `ghidra/`, `ref/` | Ghidra project and binaries for analysis; clone of the upstream decompilation (reference) | no |

The folders outside git contain game code, game-derived art or large downloads, so they
stay local. [docs/building.md](docs/building.md) says where each one comes from.

## Quick start

Clone the workspace with its submodules (`git submodule update --init`, which also fetches
`decomp\` and `drivers\srdd_d3d11`). The build scripts find the workspace from their own
location, not from a fixed path. The workspace needs `Tools\` and `assets\` (not in git, see
[docs/building.md](docs/building.md)); `assets\` comes from a release zip (1.0.2 or later) in
one command: `pwsh -File scripts\build\import-release.ps1 -Zip <Wiz8Widescreen-x.y.z.zip>`.

```powershell
. .\Tools\env.ps1                                       # portable tools for this shell only
.\build.ps1                                             # build\version.dll
powershell -File scripts\build\build-decomp.ps1         # once: port build, makes the .lib files the hybrid links against
powershell -File scripts\hybrid\build_hybrid.ps1        # build\hybrid\wiz8hy.dll + wiz8hy_hooks.txt
powershell -File drivers\srdd_d3d11\build.ps1           # drivers\srdd_d3d11\out\srDD_D3D11.dll, the render driver
pwsh -File scripts\build\make-hybrid-package.ps1        # build\package\Wiz8Widescreen-<VERSION>.zip
```

To try a change in the game, install into the test copy (`.\build.ps1 -Install`,
`scripts\hybrid\build_hybrid.ps1 -Install`) and run `games\work\Wiz8.exe`.
[docs/building.md](docs/building.md): toolchain, every build, changing game code, release
checklist. [docs/testing.md](docs/testing.md): test copies, automated play, pitfalls.

## Rules of this workspace

* Everything lives inside this folder: tools are portable, nothing goes to the system
  PATH, the registry or outside the folder (Python 3 and PowerShell 7 are the only
  system-wide programs the build uses; the Linux test bench also needs Docker Desktop with
  WSL2, see [docs/testing.md](docs/testing.md); the render driver has a Linux build for its
  test suites, see [its testing document](drivers/srdd_d3d11/docs/testing.md)).
* `games/reference` and the real GOG/Steam installs are read-only.
* `wiz8hy.dll` and `wiz8hy_hooks.txt` always travel together (a stale hooks file crashes the
  game at start-up).
* We fix original-game bugs only when they get in the way of widescreen. The one exception
  is the Options switch "Original Bug Fixes" (`[Experimental] OriginalFixes`, off by default):
  other fixes of the original game's bugs go behind it, and with the switch off the game
  behaves exactly as the original ([docs/experimental.md](docs/experimental.md)).
* Only the official GOG/Steam 1.2.4 exe is supported; unofficial builds (e.g. the Russian
  translation's own exe) are not. The Russian translation's `Data` works with the patch.

Rules for AI agents working here: [CLAUDE.md](CLAUDE.md).

## License

The code and documentation in this repository are under the [MIT License](LICENSE). This does
not cover Wizardry 8 itself, its files or art, the decompiled game code in the `decomp/`
submodule (upstream's terms and Strategy First's non-commercial source licence apply there), or
third-party components (MinHook has its own licence in `third_party/minhook`; dgVoodoo 2,
included in the release packages up to 1.0.2, is distributed under its author's terms). The
render driver in the `drivers/srdd_d3d11` submodule is a repository of its own, and its own
README states its licence (MIT).
