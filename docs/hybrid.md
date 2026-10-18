# The hybrid: original Wiz8.exe + functions from the port

This is how the released patch (1.0.x) works. The **original** Wiz8.exe (GOG/Steam 1.2.4) is launched,
and at startup `version.dll` replaces only the functions we changed (the wide
canvas and everything drawn on it, display modes, settings in the options, draw distance,
frame limit...). The code of these functions comes from the game sources in `decomp\` (the decompilation +
our changes). The rest of the game is native, tested code, with no porting bugs in it.

## How wiz8hy.dll is built

`powershell -File scripts\hybrid\build_hybrid.ps1 [-Install]` (portable MSVC from
`Tools\msvc`, the same flags as the port; it needs the `build\vc2022\*.lib` libraries from the port build,
see [building.md](building.md)). The list is `scripts\hybrid\transplant_wide.json` (the default):

* `units` and `auto_units` - files from `decomp\src` that are compiled in full;
* `transplant` - addresses of original functions that are replaced by versions from `decomp`
  (287 of them in 1.0.x);
* `dll_owned_globals`, `glue` - global variables that live in the DLL (for example,
  enlarged arrays), and glue code.

Then `scripts\hybrid\build_hybrid.py`:

1. In the object files, everything that exists in the original (`FUNCTION`/`GLOBAL`/`VTABLE` annotations in
   the `decomp` sources), except the transplanted functions, is turned into external references
   (`scripts\hybrid\coff.py` edits the COFF: a COMDAT keeps a dead definition,
   references are redirected to a new external symbol; statics are renamed to `__w8r_<address>`).
2. `w8bind.obj` is generated: original functions become `push address; ret` stubs, data becomes
   absolute symbols with the original's address. Verified: link does not create base relocations for absolute
   symbols, so the DLL can be loaded at any address.
3. Linking; if functions that do not exist in the original are missing (new code or functions
   merged by ICF in the original), their files are added automatically. Functions without a definition
   that are referenced only by dead code get int3 traps in separate COMDATs
   (a live reference to a trap is a build error).
4. `wiz8hy_hooks.txt`: original address -> RVA of the function in the DLL. **The DLL and this file are always
   copied together**: an old `wiz8hy_hooks.txt` next to a new DLL crashes the game at startup.
5. Dynamic initialization of globals (`.CRT$XC*`) is stripped out: it would overwrite the
   original's globals. So new hybrid code must not rely on CRT initialization
   or on UCRT functions that need the locale (`_stricmp`, `strcspn`, `_snwprintf`, `wcsstr`):
   use our own simple helpers instead.

## How it is enabled

1. `version.dll` checks Wiz8.exe (SHA-256 and a code signature). If the exe is unknown,
   nothing is replaced and the game runs as the original.
2. `wiz8ws.ini`: `[Hybrid] Enabled=1` (the shipped `dist\wiz8ws.ini` has this;
   `[General] Enabled=0` turns off the whole patch).
3. In the hook on the original's `WinMain` (0x00401670, `src\hooks_hybrid.cpp`), before video initialization
   and window creation, `version.dll` loads `wiz8hy.dll` and calls `HybridInstall`
   (`src\hybrid\hybrid_main.cpp`, built into `wiz8hy.dll` itself): a `jmp` to the new version is written at the start of each transplanted
   original function, plus a wrapper around `RenderFrame` with the
   frame limit. Log: `wiz8hy.log`; on a crash the addresses are written there too (they are
   translated into names by `scripts\hybrid\symbolize.py`).
4. The hybrid reads the widescreen settings from `wiz8wide.ini` (`[Canvas]`, `[Display]`:
   window mode, resolution, MaxFps, ViewDistance) - the same file as the port; they are also changed by
   the second "Video" page in the game options. Log: `wiz8wide.log`.

Trial run: `powershell -File scripts\hybrid\try_hybrid.ps1 [-Save "444"] [-Off]`.

## How to change a game function

Step by step (in English) - [building.md](building.md), "Changing game code". The key point: a change to a
function in `decomp\` gets into `wiz8hy.dll` only if its address is in `transplant` in
`transplant_wide.json`; otherwise the build succeeds, but the game keeps running the original.

## History

First trial (2026-10-13): 9 draw-distance functions + the frame limit. Then everything widescreen from the port
was moved into the hybrid ([wide-canvas.md](wide-canvas.md)), and it became
the released product instead of `Wiz8Runtime.exe`.
