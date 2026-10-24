# The game source (`decomp\`)

`decomp\` is a git submodule: [abr17/wizardry-8-decomp](https://github.com/abr17/wizardry-8-decomp),
a fork of the public Wizardry 8 decompilation
([agluszak/wizardry-8-decomp](https://github.com/agluszak/wizardry-8-decomp)). Its branch
`widescreen` is upstream commit `075cbd0` (2026-10-10) plus the widescreen patch's commits: one commit
with everything of 1.0.0, then the 1.0.1 fixes. Tag `wiz8-widescreen-<version>` is the source of the
released `wiz8hy.dll` of that version (1.0.0, 1.0.1). Both `wiz8hy.dll` and the internal `Wiz8Runtime.exe` are built from it.

**Licensing:** upstream has no licence file; `src/sgp` is under Strategy First's non-commercial
SFI Source Code License, and code derived from it is not offered under broader terms. Our
changes in the fork follow the same terms; they are not under this repository's MIT licence.

The upstream `README.md` in the fork (after our note at the top) describes upstream's
workflow (VC6 in Docker/Wine, `uv run wiz8 ...`); that workflow is not used here.

## Development history (the author's private copy)

Up to 1.0.0 the published fork has a single commit on top of upstream. The patch was developed in a
private copy with its full history, described below; `docs\wide-canvas.md` and
`docs\decomp-port.md` cite commits from that history by hash.


* `720e1d8` - the import: upstream `075cbd0` copied as files (Windows line endings), without
  upstream's `docs/`, `evidence/`, `AGENTS.md`, `CLAUDE.md`, `.beads/`, `.claude/`.
  `f0d38ea` then restored the `evidence` folders the build needs.
* everything after - our commits (building with MSVC 2022, ABI glue with the original
  `sr.dll`, fixes, the wide canvas and all widescreen work, Russian text support). Commit
  messages explain each change; `docs\wide-canvas.md` and `docs\decomp-port.md` cite them
  by hash.
* tag `1.0.0` (`84a34ab`) - the source of the released `wiz8hy.dll` 1.0.0.

The single public commit on `widescreen` has the same content as private tag `1.0.0`,
with comments translated to English (the rebuilt `wiz8hy.dll` differs from the released one
only in timestamps).

## What is ours

| Path | What |
|---|---|
| `src/msvc2022_compat/` | msvcrt heap/CRT bridges and SR template imports (MSVC 2022 vs the original VC6 runtime) |
| `include/wiz8/compat/` | `msvc2022.h` (force-included), `modern_msvc` headers |
| `cmake/ModernMsvc.cmake` + the MSVC 2022 branch in `CMakeLists.txt` | flags for the modern compiler |
| `tools/msvc2022/` | generators of import libraries (`msvcrt.def`, SR assert import) |
| `src/w8diff/` | in-process side of the w8diff comparison harness |
| edits across `src/wiz8`, `src/sgp` | the widescreen patch itself (see below) |

Not used by us: `docker/`, `.github/`, `vendor/ghidra/`, `tools/wiz8decomp/` (upstream CLI),
`tests/` (upstream harness).

## Where the code is (`decomp\src\wiz8\...`)

| Area | Files |
|---|---|
| wide canvas, display modes, settings ini, screenshots | `engine_code/Canvas.cpp`, `engine_code/Video2.cpp` (`VideoApplyDisplaySettings`), `decomp\include\wiz8\canvas.h` |
| wide art loading, stretched panel strips | `engine_code/WideArt.cpp`, `local_screens/MainGameLayout.cpp` (`DrawCatalogImageWide`) |
| main game HUD (layout "A"), bottom panels, portraits | `local_screens/MainGameScreen.cpp`, `local_screens/MainGameLayout.cpp`, `local_screens/MGSButtons.cpp` |
| options (all pages, display settings and resolution list on Video page 2, frame rate limit on Video page 3), save/load list | `local_screens/OptionsScreen.cpp` (`AddDisplaySettings`, option text anchoring `OptionsTextAnchor`) |
| journal, automap, main menu, intro/credits | `local_screens/JournalScreen.cpp`, `local_screens/AutomapScreen.cpp`, `local_screens/MainMenuScreen.cpp`, `local_screens/IntroScreen.cpp` |
| NPC dialogue panel | `local_screens/NPCInteractionSubscreen.cpp` |
| Russian text (cp1251 font table, layout switch) | `russian_text.cpp`, `../sgp/Font.cpp`, `../sgp/input.cpp` |
| window, mouse, WM_SIZING | `../sgp/sgp.cpp`, `../sgp/mousesystem.cpp` |
| experimental features (animated main menu, Options category "Experimental") | `experimental/`, `decomp\include\wiz8\experimental.h`; call sites marked "Experimental" ([experimental.md](experimental.md)) |

A change in `decomp\` reaches the shipped `wiz8hy.dll` only if the changed function is
listed in `scripts\hybrid\transplant_wide.json` (see [hybrid.md](hybrid.md) and
[building.md](building.md), "Changing game code").

Functions carry `// FUNCTION: WIZ8 0x<address>` annotations with their address in the
original `Wiz8.exe`; the hybrid build relies on them, so keep them on every function you change.
