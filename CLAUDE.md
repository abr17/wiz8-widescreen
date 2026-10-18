# Wiz8 widescreen patch — rules for AI agents

First read `README.md` (what this is and where things live), then whatever you need from `docs/README.md`.
Version 1.0.1 is released (2026-10-18, after 1.0.0 on 2026-10-17); from now on only fixes based on bug reports. Version number: `VERSION`.

## Workspace
- **Everything lives only inside C:\dev\wiz8-ws** (tools, game copies, builds, Ghidra databases, temporary
  files). Do not create anything outside it.
- All tools are portable, in `Tools\`; do not touch the system PATH or the registry. In PowerShell:
  `. C:\dev\wiz8-ws\Tools\env.ps1` (MSVC scripts load it themselves via `Tools\msvcenv.ps1`).
- Do not install anything, do not change system settings, git is local only (no push) -
  unless the owner explicitly allows it.

## The game
- Target - Wiz8.exe GOG/Steam 1.2.4, SHA-256 18A74FF61C65B8A2D4CFA11FFCE82AD7FEF022A94EAF0C2F217E479E981420D2
  (Steam has the same exe). Unofficial builds (the Russian translation's exe, etc.) are not supported.
- `games\reference` - the pristine reference copy, never modify it. GOG/Steam installs in Program Files - read only.
- `games\work` - test copy with the patch; `games\ru` - copy with the Russian translation's data.
  Never run the Russian translation's exe.
- We fix original-game bugs only if they get in the way of widescreen; first check on the
  pure original (`scripts\tools\retail_asm.py`, patch disabled in `wiz8ws.ini`).

## Building and testing
- `version.dll`: `.\build.ps1 [-Install]`. `wiz8hy.dll`: `powershell -File scripts\hybrid\build_hybrid.ps1 [-Install]`
  (config `scripts\hybrid\transplant_wide.json`). Package: `pwsh -File scripts\build\make-hybrid-package.ps1`.
  Details - `docs\building.md`.
- Copy `wiz8hy.dll` and `wiz8hy_hooks.txt` only together (otherwise a crash at start-up).
  The hybrid code has no CRT initialization: do not use `_stricmp`, `strcspn`, `_snwprintf`, `wcsstr`.
- Game source - `decomp\` (git submodule, fork abr17/wizardry-8-decomp, branch `widescreen`;
  described in `docs\decomp-fork.md`). Its code is not MIT (upstream/SFI terms).
- Test in the game yourself: `. scripts\play\hybrid_session.ps1; Start-Wiz8; ...; T 'name'; Quit-Wiz8`
  (`docs\testing.md`). Delete screenshots showing the desktop or personal information immediately.
- Found addresses in the original: `docs\functions.md` (address, byte signature, how it was verified).
- Static analysis: rea MCP (`.mcp.json`) on top of Ghidra; copies of the binaries - `ghidra\bin`.
  Debugger: `Tools\x64dbg\release\x32\x32dbg.exe`.

## Communication
- The owner writes PHP/JS: explain C++ and assembly in plain words.
- Show graphics (new images) to the owner for approval before installing them into the game; seams are not acceptable.
