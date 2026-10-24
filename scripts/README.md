# scripts

Run from the repository root. PowerShell scripts: `powershell -File` or `pwsh -File`
(PowerShell 7 must be installed: several scripts call `pwsh`); Python scripts:
`python -I <script>` (standard library only).
Most scripts print usage in their header comment.

## build/ — building and packaging

| Script | What |
|---|---|
| `build-decomp.ps1 [-Clean]` | builds the internal port `build\vc2022\Wiz8Runtime.exe` (+ `.lib`s the hybrid links against) from `decomp\` with portable MSVC |
| `make-hybrid-package.ps1` | builds the installer and assembles `build\package\Wiz8Widescreen\` + `.zip` |
| `import-release.ps1 -Zip <zip> [-Force] [-Binaries]` | fills `assets\` (not in git) from a released zip; `-Binaries` also takes its prebuilt DLLs |
| `toolchain\env.ps1`, `toolchain\msvcenv.ps1` | copies of `Tools\env.ps1` / `Tools\msvcenv.ps1` (session PATH for the portable tools) |
| `toolchain\portable-msvc.py` | downloads portable MSVC + Windows SDK into `Tools\msvc` (public-domain script by Mārtiņš Možeiko) |

`version.dll` is built by `build.ps1` in the root; the installer by `tools_src\setup\build.ps1`.

## hybrid/ — wiz8hy.dll

| Script | What |
|---|---|
| `build_hybrid.ps1 [-Install] [-NoCompile] [-Config file]` | entry point; builds `build\hybrid\wiz8hy.dll` + `wiz8hy_hooks.txt` |
| `build_hybrid.py`, `coff.py` | the build itself: compile, rewrite COFF objects to bind to original addresses, link |
| `transplant_wide.json` | **the release config**: units to compile and the 289 original functions to replace |
| `try_hybrid.ps1` | start the original exe in `games\work` with the hybrid, optionally load a save, print logs |
| `hy_screens.ps1`, `hy_play.ps1` | screenshots / mouse helpers for the hybrid driven through the in-game test stand |
| `stack_retail.ps1`, `symbolize.py` | dump and symbolize the main-thread stack of a hung game (original + `wiz8hy.map`) |
| `find_users.py` | which original functions touch a given global address range |

## play/ — running the game for tests

`hybrid_session.ps1` (start here: retail exe + wide-canvas mouse mapping + safe screenshots),
`game.ps1` (start/quit, clicks in 640x480 coordinates, `Shot`), `play.ps1` (held keys,
`Snap`, in-game `GShot`, memory reads of the port), `play_create.ps1` (quick new party),
`shot.ps1`, `win_shot.ps1` (screenshots), `boost_shot.ps1` (brighten to see seams),
`modewatch.ps1` (prints display-mode changes), `frame_delta.ps1` (frame time from memory).
See [docs/testing.md](../docs/testing.md).

## art/ — wide art (`.STI` files in `assets\`)

| Script | Makes |
|---|---|
| `stretch_config.py` → `stretch_quilt.py` | seamless stretched-panel strips `assets\Data\WIDE\STRETCH\S*_768/856.sti` (config from the original UI STIs extracted into `build\stretch\en` with `scripts\tools\slf_extract.py`) |
| `niche_quilt.py` (+ `make_lock_niche.py`) | `assets\Data\WIDE\LOCKPICKGAPS_*.STI` |
| `make_wings.py`, `neutralize_wings.py` | `assets\Data\WIDE\WIDEFRAME_*.STI` of 1.0.0-1.0.1 (the AI-painted marble side wings of 4:3 windows) |
| `native_wings.py` | `assets\Data\WIDE\WIDEFRAME_768.STI` and `WIDEFRAME_856.STI` since 1.0.2 (side wings stitched from the game's own marble), with `--edge makewings`; output in `build\tmp\native-wings\` |
| `find_slice.py` | finds a self-tiling slice of an image |
| `artkit.py`, `sti8.py` | libraries: PNG and 16-bit STI read/write, 8-bit STI decode |

The wide loading screens, menu and credits backgrounds of 1.0.0 were redrawn with an
external image service and approved by eye; those one-off scripts were removed after the
release (they are in git history at tag `1.0.0`). The same goes for the art of the
experimental Options category and the animated menu video of 1.0.2 (drawn by Astra, fitted
into the game's `.STI` files by one-off scripts; see [docs/experimental.md](../docs/experimental.md)).

## tools/ — analysis and game-format utilities

`retail_asm.py` (disassemble an original function by address), `audit_chunks.py` (split
decompiled functions for side-by-side audits), `pe_read.py`, `map_lookup.py`,
`port_symbolize.py`, `sample_eip.ps1` (port-only symbolization), `slf_list.py`,
`slf_extract.py`, `slf_images.py` (the game's `.SLF` archives), `stringdata.py`
(`StringData.DAT` texts).

## w8diff/ — differential test harness (internal)

Runs the same functions in the original exe and in the port and compares results.
Entry points `run.ps1`, `run_all.ps1`, `build_dll.ps1`; specs in `specs\`; library in
`w8diff\` (its `symbols.py` is also used by the hybrid build). See
[docs/w8diff.md](../docs/w8diff.md).
