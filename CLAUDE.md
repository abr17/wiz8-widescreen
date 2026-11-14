# Wiz8 widescreen patch — rules for AI agents

First read `README.md` (what this is and where things live), then whatever you need from `docs/README.md`.
Version number: `VERSION`; what each release holds: `docs\releases\`.

## Workspace
- **Everything lives only inside the workspace, the folder of this clone** (tools, game copies, builds, Ghidra
  databases, temporary files). Do not create anything outside it. The existing exceptions: the Linux test bench
  (`scripts\linux\`, `docs\testing.md`) runs in Docker Desktop with WSL2, and the render driver
  has a Linux build that its test suites run on (`drivers\srdd_d3d11\docs\testing.md`).
- All tools are portable, in `Tools\`; do not touch the system PATH or the registry. In PowerShell:
  `. .\Tools\env.ps1` (MSVC scripts load it themselves via `Tools\msvcenv.ps1`).
- Do not install anything, do not change system settings, git is local only (no push) -
  unless the person you work for explicitly allows it.
- What depends on the machine or on the person is not in git: `.mcp.json`, `.claude\` and
  `CLAUDE.local.md` (personal preferences). `docs\building.md` has an example of the set-up.

## The game
- Target - Wiz8.exe GOG/Steam 1.2.4, SHA-256 18A74FF61C65B8A2D4CFA11FFCE82AD7FEF022A94EAF0C2F217E479E981420D2
  (Steam has the same exe). Unofficial builds (the Russian translation's exe, etc.) are not supported.
- `games\reference` - the pristine reference copy, never modify it. GOG/Steam installs in Program Files - read only.
- `games\work` - test copy with the patch; `games\ru` - copy with the Russian translation's data.
  Never run the Russian translation's exe.
- We fix original-game bugs only if they get in the way of widescreen; first check on the
  pure original (`scripts\tools\retail_asm.py`, patch disabled in `wiz8ws.ini`). The one
  exception: other fixes of the original game's bugs go behind the switch
  `[Experimental] OriginalFixes` (Options, "Original Bug Fixes"), which is off by default; with
  it off the game behaves exactly as the original (`docs\experimental.md`).

## Building and testing
- `version.dll`: `.\build.ps1 [-Install]`. `wiz8hy.dll`: `powershell -File scripts\hybrid\build_hybrid.ps1 [-Install]`
  (config `scripts\hybrid\transplant_wide.json`). Package: `pwsh -File scripts\build\make-hybrid-package.ps1`.
  Details - `docs\building.md`.
- Copy `wiz8hy.dll` and `wiz8hy_hooks.txt` only together (otherwise a crash at start-up).
  The hybrid code has no CRT initialization: do not use `_stricmp`, `_strnicmp`, `strcspn`, `_snwprintf`, `wcsstr`.
- Game source - `decomp\` (git submodule, fork abr17/wizardry-8-decomp, branch `widescreen`;
  described in `docs\decomp-fork.md`). Its code is not MIT (upstream/SFI terms).
- Installer (`Wiz8WideSetup.exe`): `pwsh -File tools_src\setup\build.ps1`. Its tests:
  `tools_src\setup\tests\test_all.ps1` (in Windows Sandbox) and `tools_src\setup\tests\zip_writer_test.py`
  (`docs\testing.md`).
- Test in the game yourself: `. scripts\play\hybrid_session.ps1; Start-Wiz8; ...; T 'name'; Quit-Wiz8`
  (`docs\testing.md`). Delete screenshots showing the desktop or personal information immediately.
- Found addresses in the original: `docs\functions.md` (address, byte signature, how it was verified).
- Static analysis: rea MCP (your own `.mcp.json`, `docs\building.md`) on top of Ghidra; copies of the binaries - `ghidra\bin`.
  Debugger: `Tools\x64dbg\release\x32\x32dbg.exe`.

## Render driver
- `Dll\srDD_D3D11.dll`, the Direct3D 11 render driver the package carries, is a project of its own in
  `drivers\srdd_d3d11` (git submodule, like `decomp\`): its own version (`src\version.h` there, not `VERSION`)
  and its own documents. First read `drivers\srdd_d3d11\README.md`.
- Two builds: `powershell -File drivers\srdd_d3d11\build.ps1` (MSVC) makes the release build, the DLL that
  ships (the fast path only), and with `-Reference` the reference build (also the exact paths, `out\ref\`);
  `sh drivers/srdd_d3d11/build.sh` (clang-cl, Linux) makes both (`--reference`), and its Linux test suites use both.
- The results of L1, the driver's exact layer, never change: after any edit its output for the same input
  is the same byte for byte (what L1 is and how that is checked: `drivers\srdd_d3d11\docs\verification.md`).
- Its tests and how to run them: `drivers\srdd_d3d11\docs\testing.md`.

## Graphics
- Show new images to the person you work for and get approval before installing them into the game; seams are not acceptable.
