# Documentation

Start with the repository [README](../README.md). All documents are in English.

## Guides (current)

| Document | Read it to |
|---|---|
| [building.md](building.md) | set up the toolchain, build every piece, package and release |
| [testing.md](testing.md) | test the patch in the game, automate play, avoid known pitfalls |
| [decomp-fork.md](decomp-fork.md) | understand the game source in `decomp\`: what is ours, where each screen's code is |
| [loader.md](loader.md) | know what `version.dll` does besides loading the hybrid: crash and exit diagnostics (`Wiz8Logs\`), game file names on UTF-8 Windows |
| [experimental.md](experimental.md) | understand, change or remove the experimental features: the Options category "Experimental" and its four switches (Animated Main Menu, Map Mouse Controls, Original Bug Fixes, Alternative Game Tick) |

## Releases

| Release | Notes |
|---|---|
| 1.0.1 (2026-10-18) | [releases/1.0.1.md](releases/1.0.1.md): fixes after 1.0.0, installer updates in place |
| 1.0.0 (2026-10-17) | [releases/1.0.0.md](releases/1.0.0.md): package contents, hashes, source tags, tests |

## Design reference (current)

| Document | Covers |
|---|---|
| [hybrid.md](hybrid.md) | how `wiz8hy.dll` is built from the decompiled source and patched into the original exe |
| [wide-canvas.md](wide-canvas.md) | the wide 2D canvas and everything drawn on it: HUD layout, panels, backgrounds, seams, wings, automap, option/journal windows, frame cap, view distance. Written for the port; the hybrid ships the same code |
| [decomp-port.md](decomp-port.md) | how the decompilation was made to build with MSVC 2022 as `Wiz8Runtime.exe`: flags, ABI glue with the original `sr.dll`, fixes, `wiz8wide.ini`, Russian text support |
| [functions.md](functions.md) | addresses in the original `Wiz8.exe` / `sr.dll` with byte signatures and how each was verified |
| [w8diff.md](w8diff.md) | the internal harness that compares original and port functions call by call |

## History (superseded, kept for context)

The project started as a classic hook DLL (`version.dll` only), then moved to rebuilding
the game from its decompilation, and shipped as the hybrid. These documents describe the
earlier stages; statements in them may no longer be true.

| Document | Stage |
|---|---|
| [history/spec.md](history/spec.md) | the original plan (hook DLL, phases 0-5) |
| [history/recon.md](history/recon.md) | phase 0: versions, hashes, how the renderer loads, why `version.dll` |
| [history/phase2-findings.md](history/phase2-findings.md), [history/phase2-static-raw.json](history/phase2-static-raw.json) | phase 2: static analysis of drawing, window, mouse, 3D, video |
| [history/phase3-borderless.md](history/phase3-borderless.md) | phase 3: borderless window in the hook DLL |
| [history/phase4-hud.md](history/phase4-hud.md) | phase 4: centred 4:3 HUD + Hor+ 3D in the hook DLL |
| [history/widescreen-source-research.md](history/widescreen-source-research.md) | research that led to rebuilding from the decompilation |
| [history/responsive-ui-plan.md](history/responsive-ui-plan.md) | plan for wide windows (which screens go wide, which stay 4:3) |
| [history/assets-catalog.txt](history/assets-catalog.txt) | generated list of every image in the game's `DATA.SLF` |

`screens/` holds screenshots referenced by these documents.
