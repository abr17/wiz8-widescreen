# Building the Wizardry 8 decompilation with MSVC 2022

> `Wiz8Runtime.exe` is an internal build of the whole game (not released). The released patch uses the same code from `decomp\` through the hybrid ([hybrid.md](hybrid.md)); it reads `wiz8wide.ini` too. The change log below stops at the port era; the full history is `git -C decomp log`.

Result: `Wiz8Runtime.exe` compiles and links with MSVC 2022 (v14.44, x86) with no
unresolved symbols. The game has not been run yet: that is the next step.

- Sources (working copy, git): `C:\dev\wiz8-ws\decomp`, base: commit
  `720e1d8 upstream decomp 075cbd0`.
- Build output: `C:\dev\wiz8-ws\build\vc2022\Wiz8Runtime.exe` (2 308 096 bytes), with
  `.map` and `.pdb` next to it.
- Patch against the base: `C:\dev\wiz8-ws\patches\decomp-msvc2022.patch`.

## How to rebuild

```powershell
powershell -File C:\dev\wiz8-ws\scripts\build\build-decomp.ps1          # configure + build
powershell -File C:\dev\wiz8-ws\scripts\build\build-decomp.ps1 -Clean   # from scratch (~2 min)
```

The script sets up the portable MSVC itself (`Tools\msvcenv.ps1`), runs CMake
(NMake generator) and builds the `WIZ8_RUNTIME` target. The log is written to
`build\vc2022\build.log`. Python 3 is required (the system one is used, standard
library only): during configure it generates `sr-assert-import.lib` and
`msvcrt-bridge-import.lib`, see below. The script works in both Windows PowerShell
5.1 and pwsh 7.

## What had to change and why

In short: the original was built with the ancient Visual C++ 6 (1998). The new
compiler is stricter and does some things differently. Almost everything is solved
with compiler switches and small "shims"; in the game files themselves only
three variable declarations were changed (section 7).

### 1. Files missing from the copy

`decomp` had no `include\wiz8\evidence` and
`tools\wiz8decomp\evidence` folders: everything named
"evidence" was skipped during copying. The game headers include `*.inc` files with structure descriptions from there.
Copied from `ref\` unchanged (separate commit).

### 2. Compiler switches (`cmake\ModernMsvc.cmake`)

PHP/JS analogy: it is like turning on a "compatibility mode for an older language
version" in the settings instead of rewriting the code.

| Switch / define | Why |
|---|---|
| `/Zc:wchar_t-` | in VC6 `wchar_t` is just `unsigned short`. The "decorated" function names (mangling) in `sr.dll` depend on this |
| `/Zc:forScope-` | in VC6 a variable from `for (int i...)` is still visible after the loop |
| `/permissive`, `/wd4430` | old C++ liberties (for example, "default type int") |
| `/Zc:threadSafeInit-` | static variables inside functions without thread-safety guards, as in VC6 |
| `/GS-` | no stack "canaries": the original had none, and known overflow bugs in the game would otherwise become a crash |
| `/arch:IA32` | floating-point math on the old x87 FPU, as in the original (the new compiler uses SSE2 by default, results differ slightly) |
| `/source-charset:utf-8`, `/bigobj` | non-ASCII characters appear only in comments; large files |
| `/MT` | static C library, see the CRT section |
| `/GR-` (as before) | no RTTI, as in the original |
| `_CRT_NON_CONFORMING_SWPRINTFS`, `_CRT_NON_CONFORMING_WCSTOK` | old forms `swprintf(buf, fmt, ...)` and `wcstok(s, delim)` without a length parameter (~200 calls) |
| `_CRT_SECURE_NO_WARNINGS`, `_CRT_NONSTDC_NO_DEPRECATE` | get rid of tons of warnings about "unsafe" `strcpy` etc. |
| `_USE_32BIT_TIME_T` | 32-bit `time_t`, as in VC6 (otherwise structure sizes change) |
| `/wd4068`, `/wd4530` | noise: `#pragma clang` for the linter and unused code from `<ostream>` |
| `/fp:precise` (the default, kept on purpose) | see "Floating point" below |

Removed switches that no longer exist: `/G5`, `/G6`. For the linker, the obsolete
`/PDBTYPE:SEPT`, `/MAPINFO:LINES` were replaced, subsystem 4.0 → 5.01. The load
address is the same `0x400000`, no ASLR (`/FIXED /DYNAMICBASE:NO`), no DEP/SafeSEH.
`/MANIFEST:NO`: the original Wiz8.exe has no manifest, and Windows applies the
"legacy" UAC mode to it: writes to the install folder (Program Files) or to
HKLM are silently redirected to VirtualStore. LINK 14 embeds an `asInvoker`
manifest by default, which turns this mode off, and such writes would fail
with "access denied". `/TSAWARE:NO`: the original's DLL characteristics field
is 0, now it is 0 too. The file name is different (`Wiz8Runtime.exe`), so
compatibility settings that Windows/GOG assign by exe name do not
apply to it; keep this in mind when testing.

#### Floating point

- VC6 inlined `sin`, `cos`, `tan`, `atan2`, `sqrt` directly into the code as
  FPU instructions (`fsin`, `fcos`, `fptan`+`fstp st(0)`, `fpatan`, `fsqrt`; the retail exe has
  113 `fsin`, 99 `fcos`, 308 `fsqrt` and no imports of these functions), while
  it called `pow`, `acos`, `asin` from `MSVCRT.dll` (`_CIpow`, `_CIacos`,
  `_CIasin`). The new compiler instead calls `__CIsin` etc. from the
  static UCRT, and on any modern CPU that picks SSE2 versions with
  different rounding.
- Now `src\msvc2022_compat\msvcrt_crt_bridge.c` replaces these functions:
  `_CIsin/_CIcos/_CItan/_CIatan2/_CIsqrt` consist of exactly the same FPU
  instructions VC6 put into the code, and `_CIpow/_CIacos/_CIasin` and `atof` jump to
  `MSVCRT.dll`, as in the original. So the results of these functions are the same as
  in retail on the same Windows (checked with a small program: sin, cos, atan2, pow,
  acos, sqrt return correct values, the atan2 argument order is right).
- `/fp:precise` is kept on purpose. VC6 (`/O2` without `/Op`) did not round
  intermediate `float` values in registers; `/fp:precise` rounds them on
  assignment; `/fp:fast` is closer to VC6 on this point but allows
  reordering of operations. Matching VC6 bit for bit is impossible either way:
  a different compiler distributes values between registers and the stack differently.
  FPU precision (53 bits, `_PC_53`) is set by both the old and the new startup code.
  Saves are not affected (the data layout is the same). Differences in the
  last bit are possible for `float` formulas; if that matters somewhere (comparison with
  a threshold, truncation to an integer), it can only be checked by comparing with retail
  in-game.
- Remaining: `sscanf`/`swscanf` (parsing `%f` in monster data) still come from
  UCRT: they are inline in the headers and cannot be replaced without changing hundreds of calls.
  For short decimal numbers UCRT and MSVCRT give the same result;
  a difference is possible only for pathologically long strings.

`CMAKE_BUILD_TYPE` is empty and without `/EHsc`, as in the original build: all flags
are set by the project.

### 3. Small header changes

- `include\wiz8\compat\compiler.h`: for the new MSVC the real
  `static_assert` and `override` are used (previously these were stub macros for VC6).
  **Structure size checks (`W8_ABI_ASSERT`, ~770 of them) are enabled and all
  pass**: so the in-memory class layout matches what
  `sr.dll` expects. It was also verified that the check really fires (a deliberately wrong
  size gives a compile error).
- `include\wiz8\compat\msvc2022.h` (included automatically): `abs()` of an
  unsigned number. VC6 had a single `abs(int)`, modern C++ has several
  overloads, and the compiler cannot choose. Also there: `#define _msize
  w8_msvcrt_msize`: `_msize` from UCRT cannot be replaced (the same object contains
  `_msize_base`, which UCRT itself pulls in), so calls in the game code (currently
  only debug ones, in `MemMan.cpp`, and they are not compiled) go to a wrapper around
  `MSVCRT.dll!_msize`.
- `compiler.h`: the `W8_RETAIL_STALE(v)` macro, see section 7.
- `include\wiz8\compat\modern_msvc\iostream.h`: an empty stub in place of the
  removed `<iostream.h>` (only `src\sgp\Container.cpp` includes it, and it
  uses nothing from it).
- `src\sgp\Mss.h` (Miles Sound System header): `windows.h` is now
  included before `#pragma pack(1)`. The new Windows SDK complains if it is
  included with non-standard alignment. This does not affect the sound structures:
  `mmsystem.h` is itself packed to 1 byte.

### 4. Linking against the real `sr.dll` (the SurRender engine)

The exe calls 461 functions from the original `sr.dll` by their C++ names.
Checked with `dumpbin`: **all 461 imports are in the export table of retail `sr.dll`**
(the original Wiz8.exe has 468; the difference is below).

- `src\wiz8\imports\sr.def` (+9 names): the new compiler sometimes calls a
  function that VC6 inlined (`sGetClassName` of several classes,
  the `srLight` copy constructor, `srGERD::setVertexPointer`). All of them are
  in the retail `sr.dll` exports. On the other hand, VC6 took virtual method tables from the DLL
  (`??_7srMaterial@@6B@` etc.), while the new compiler instead calls the
  exported constructors: the result is the same.
- `src\msvc2022_compat\sr_template_base_imports.cpp`: the new MSVC assumes that
  the methods of the template `srClassSupport<srCamera, ...>` also live in `sr.dll` (the
  so-called propagation of dllimport to the base template). VC6 did not do that, and
  `sr.dll` does not export them. The file contains the same function bodies (a copy of
  the template), and the linker is told: "if you did not find this name, use this one"
  (`/ALTERNATENAME`, only as a fallback).
- `sr-assert-import.lib`: in the sources `srAssertFail` is declared with a fixed
  number of arguments, while in `sr.dll` it is variadic (`...`). A special
  import library maps one name to the other. It is generated by the decompilation's own
  Python script (`tools\wiz8decomp\binary\coff_archive.py`)
  through the wrapper `tools\msvc2022\make_sr_assert_import.py` during configure.
  Verified: the exe imports `?srAssertFail@@YAXPBD0J0ZZ` from SR.dll.

### 5. The C library (CRT) and memory shared with `sr.dll`

**Solution: `/MT`** (static CRT inside the exe) **+ all heap work
(`new/delete` and `malloc/free/calloc/realloc/_wcsdup/_strdup`) → `MSVCRT.dll`**,
that is, exactly where the original Wiz8.exe sent it.

- `/MD` would require `vcruntime140.dll` next to the game or an installed
  VC++ Redistributable. This machine has it in `SysWOW64`, but that is not
  guaranteed for others. With `/MT` the exe depends only on system DLLs
  (KERNEL32, USER32, GDI32, DDRAW, msvcrt) and game DLLs (SR, MSS32, BINKW32).
- The danger: retail `sr.dll` (VC6, `MSVCRT.DLL`) and the static UCRT have
  different heaps. The system `msvcrt.dll` creates its own heap with `HeapCreate`, UCRT
  uses `GetProcessHeap()`. If memory is allocated in one heap and freed in
  the other, that is a crash or silent memory corruption.
- In the original, `operator new` and `malloc` came from `MSVCRT.dll`, that is, from
  ONE heap. So any mixed pairs (`new` + `free`, `malloc` +
  `delete`) that worked in retail must work for us too. The first version
  of the bridge sent only `new/delete` to `MSVCRT.dll`, while `malloc/free`
  stayed in UCRT: a mixed pair would free memory into the wrong heap.
  A code search found no such pairs, but that is not proof, so now
  everything goes to `MSVCRT.dll`.
- What was found in the code:
  - engine classes derived from `srRuntimeClass`, and `srVector*`/`srARGB` arrays
    use their own `operator new/delete` via `srHeap` inside
    `sr.dll`, so the exe's CRT does not matter to them;
  - `src\wiz8\engine_code\game_timer.cpp`: `new srTimer(...)` in the exe, while
    `delete` goes through the virtual destructor from the `sr.dll` table (a real
    boundary crossing);
  - inline code in the SurRender headers (`srIOManager`, `srIStreamOpener`,
    `srTypeRegistry::ChildList`) allocates with plain `new` in whichever module it is
    compiled into, and another module may free it;
  - subclasses of `sr.dll` classes defined in the exe
    (`W8VirtualFileBinIStream`, `W8MaterialMapper` and others) may be deleted
    from inside `sr.dll`.
- How it is done:
  - `tools\msvc2022\make_import_aliases.py` (the same native generator
    `coff_archive.py` as for `srAssertFail`) writes
    `msvcrt-bridge-import.lib` during configure: import table slots with internal names
    `w8crt_*`, which the Windows loader fills with the addresses of `MSVCRT.dll!malloc`,
    `free`, `??2@YAPAXI@Z` etc. The DLL descriptor comes from
    `src\msvc2022_compat\msvcrt.def`.
  - `src\msvc2022_compat\msvcrt_heap_bridge.cpp`: all variants of
    `operator new/delete` (plain, `[]`, `nothrow`, sized) call
    `MSVCRT.dll!??2`/`??3`. As in VC6, when out of memory `new` returns
    NULL instead of throwing an exception.
  - `src\msvc2022_compat\msvcrt_crt_bridge.c`: `malloc`, `free`, `calloc`,
    `realloc`, `_strdup`, `_wcsdup`, `atof` and the FPU functions (see above).
    An object file always wins over a library, so these names replace the
    versions from `libucrt`. UCRT itself calls
    `_malloc_base/_free_base` for its internal needs and does not mix its heap with anything. Checked across
    all 197 linked `libucrt` objects: the public `malloc/free/calloc`
    are called only by `getcwd.obj` (buffer for `_getcwd(NULL, ...)`, allocation and
    freeing are paired; the game passes its own buffer) and `getenv.obj`
    (`_dupenv_s`, the game does not call it). There is no C++ library (`libcpmt`) in the exe.
  - There is no fallback anymore: previously the bridge looked up `msvcrt.dll` via
    `GetProcAddress` and on failure silently switched to the UCRT heap. Now it is
    a normal import: if `msvcrt.dll` were not found, Windows would not start the exe and
    would show a clear error.
- `dumpbin /imports` check: exactly these are imported from `msvcrt.dll`:
  `??2@YAPAXI@Z ??3@YAXPAX@Z malloc free calloc realloc _wcsdup atof _CIpow
  _CIacos _CIasin` (retail Wiz8.exe also imports all these names from MSVCRT.dll). In
  the `.map`, `_malloc`, `_free`, `__CIsin` etc. are defined in
  `msvcrt_crt_bridge.c.obj`, not in `libucrt`.
### 6. What was removed from the build

`srext_jpegimporter`, `srext_unzip` (no IJG jpeg/unzip sources),
`tests\differential`, reccmp and the reconstructed `SURRENDER` (`sr.dll`): the exe
uses the original DLLs. The console test build `WIZ8_RUNTIME_TEST`
is not created in this mode (it needs `SURRENDER`). The old VC6 CMake branch is
untouched: everything new is enabled only when `MSVC_VERSION >= 1900`.

### 7. Reads of uninitialized variables (`W8_RETAIL_STALE`)

In places the decompilation faithfully reproduces a bug of the original: a local variable
gets no value on some path but is read later. With VC6 such a read
sees exactly what VC6 left in that stack slot, i.e. the same as
retail. The new compiler lays out the stack differently and reads something else.
Example: in `CharacterScreen::UpdateDialog` retail always got 1 there
("accept"), while the new build got the high byte of the object's address.

Solution: `W8_RETAIL_STALE(v)` in `include\wiz8\compat\compiler.h`. On MSVC 2015+
it becomes `= v`, where `v` is taken from the retail disassembly; for VC6 and the
clang linter it is empty (their output does not change).

| Location | Retail (address) | What was in the slot | Done |
|---|---|---|---|
| `local_screens\CharacterScreen.cpp`, `accepted` | `0x005B0504` `mov byte ptr [esp+8],1` | always 1 | `W8_RETAIL_STALE(1)` |
| `local_code\PC Item.cpp` `UseItem`, `used` (the "charges/doses ran out" paths) | `0x0051E6EE`, `0x0051E74B` | the `character` argument slot: low byte of the pointer to the character | `W8_RETAIL_STALE((unsigned char)character)` |
| `dialog_code\stListBox.cpp` `TextAreaButtonCallback`, `top` | `0x005CCEDC` | the `reason` argument | `W8_RETAIL_STALE(reason)` |
| `dialog_code\stListBox.cpp` (track), `top`, `bottom` | `0x005CD26D` | both = `reason` (retail then divides by 0) | `W8_RETAIL_STALE(reason)` |

The other places marked in the code were analyzed and left as is:

- unreachable with the calls present in the code: `OctBuildPreTree::UpdateRegionMap`
  (all calls use mode 5 or 6), `TintHighlightedMonster` (called only
  with `NONE`), `LayoutPortraitQuoteBubble` (all calls with background 0), `Trynnie2`
  (the argument is not read), `ArnikaElevatorAdvance` (states only 1..8),
  `OctPath::FindPathCell` (requires a distance to the neighboring cell ≥ 1e7);
- only on an error path (a triggered `srAssertFail`, a corrupted file,
  an unknown target type): `Combat Attack.cpp` (`base`, `secondary`),
  `Health Stamina Mana.cpp`, `MGSTextBox.cpp`, `Cosmic Circle.cpp`,
  `OctPreTree.cpp` (the value is not read), `Video2.cpp` (debug mode),
  `AnimObj`, `ReadLevel`, `ReadMesh`, `Spells`, `Trigger` (a `FileRead` failure);
- `OctPath.cpp` `AdjustFinalPathEndpoint` (a monster target without a model): the radius in
  retail is the bits of a pointer (≈0), and the position is real stack garbage with no
  defined value, so there is nothing to reproduce.

Additionally, a build with `/w14701 /w14703` (MSVC "potentially
uninitialized variable") was made: ~140 places. Almost all of them repeat
the ones listed above or are guarded by a flag/`goto` that MSVC does not track;
the decompilation's clang linter (`-Werror=sometimes-uninitialized`) does not
treat them as errors. Spot-checked (`GroupAttacks`, `Combat Attack:600`,
`MonsterAI:1194`): false positives or only on an error path. Not all 140 were analyzed
by hand: if something in the game behaves "randomly", this is the first place
to look. To repeat: `cmake ... -DCMAKE_CXX_FLAGS="/DWIN32 /D_WINDOWS
/w14701 /w14703"` in a separate build folder.
## Compiler warnings (7 of them, all from the original code)

- `src\wiz8\local_code\Combat Attack.cpp:376` C4804: comparison `bool > 0`, as
  in the original.
- `src\sgp\vsurface.cpp` C4806 ×4: an old SGP bug `!flags & X` (from JA2).
- `src\sgp\soundman.cpp:329` C4477: `%d` for a HANDLE in a debug string.
- `src\sgp\Container.cpp:30` C4005: a repeated `#define STRICT`.

Plus the system D9035 "`/Zc:forScope-` is deprecated" (the script hides it).

## What is not verified yet

- Running the game (not run, per the task). Look first at: window
  creation/DirectDraw, loading `sr.dll`, the `msvcrt.dll` bridge (any crash in
  `free`/`delete`), sound.
- `_AIL_init_sample@4`: the original exe imports the name `_AIL_init_sample@`
  (without a number). This is a decision of the decompilation authors; if `Mss32.dll` does not
  export `_AIL_init_sample@4`, the game will fail to start with an entry point error.
- `WINVER` is not set: Windows 10 SDK definitions are used. For structures with
  a `cbSize` field this is fine, but worth remembering.

## Change log (commits in `decomp`)

1. `Restore include/wiz8/evidence ...`: missing files from `ref\`.
2. `msvc2022: VC6 compatibility headers`: `compiler.h`, `msvc2022.h`,
   `iostream.h`, `Mss.h`.
3. `msvc2022: SR.dll ABI glue`: `sr.def`, `sr_template_base_imports.cpp`,
   `msvcrt_heap_bridge.cpp`.
4. `msvc2022: CMake lane`: `CMakeLists.txt`, `cmake\ModernMsvc.cmake`,
   `cmake\CompileSettings.cmake`, `src\sgp\CMakeLists.txt`,
   `src\wiz8\CMakeLists.txt`, `tests\runtime\targets.cmake`,
   `tools\msvc2022\make_sr_assert_import.py`.
5. `msvc2022: review fixes`: the whole heap and the FPU functions → `MSVCRT.dll` via
   an import with no fallback (`msvcrt_heap_bridge.cpp`,
   `msvcrt_crt_bridge.c`, `msvcrt.def`, `make_import_aliases.py`,
   `ModernMsvc.cmake`, `src\wiz8\CMakeLists.txt`, `msvc2022.h`);
   `/MANIFEST:NO`, `/TSAWARE:NO`; `W8_RETAIL_STALE` in `compiler.h` and in
   `CharacterScreen.cpp`, `PC Item.cpp`, `stListBox.cpp`.

Outside `decomp`: `scripts\build\build-decomp.ps1` (now also works in Windows
PowerShell 5.1).
## Fixing a divergence from the original: lighting (2026-10-11)

The built game rendered 3D darker and more orange than the original. The cause is a bug in the decompilation itself (not in our MSVC 2022 port): `stLight::traverse` (`src/wiz8/engine_code/stLight.cpp`) skipped all light sources without a "definition" (`m_definition == 0`): the sun/time of day, the camera light, static and rank sources. The original (0x0049C7A0) has no such check. Fixed: `else if (m_definition != 0)` → `else`. After the fix the image matches the original on the same save.

Found along the way (not fixed, behaves the same in the original and the build): the time of day after loading a save depends on Windows uptime: the game clock jumps by (uptime × 12), because `g_tick` in `Environment.cpp` is not reset on load.

## Fix: crash when picking up an item in the inventory (2026-10-11)

Symptom: inventory → select another character → pick up an equipped helmet → assert
`VideoObjectManager.cpp line 104 ... LoadVideoObject: ERROR - Add <garbage> failed`.
The cause is a decompilation bug (array size): `g_video_slots` was declared with 494
elements, while the item image cache (`GetOrCreateVideoObject`, 0x0055CE80) writes
slots `0x1EC + n` for n up to 1000, i.e. up to index 1491. In the original the array occupies
0x006448C8..0x00647768 (next variable at 0x00647770) = 1492 slots of 8 bytes:
494 filled + zeros. In our build `g_video_frames` lies right after `g_video_slots`,
so the item slots overwrote the first frame records, and the frame records
(handle/loaded) overwrote the item frame numbers → a garbage frame index. Fixed:
`g_video_slots[W8_VIDEO_SLOT_COUNT]`, where `W8_VIDEO_SLOT_COUNT = 0x1EC + 1000`
(`video_object_catalog.h`, `VideoObjectManager.cpp`).

## Wide 2D canvas: wiz8wide.ini (2026-10-11)

The built exe can draw 2D not on a 640x480 canvas but on a **W x 480** canvas,
where W = 640, 768 or 856. Every game screen stays the same and sits **centered**
on the wide canvas with offset `ox = (W - 640) / 2`; the side bars are black, and in
the in-game view modes 0, 1, 6 the 3D world shows there (Hor+). Details, the list
of changed functions and the live test checklist: `docs\wide-canvas.md`.

### Configuration

The file `wiz8wide.ini` next to `Wiz8Runtime.exe` (sample: `dist\wiz8wide.ini`).
It is read once at video startup (`InitializeVideoManager`); the result
is written to `wiz8wide.log` next to the exe and to `OutputDebugString`:

```ini
[Canvas]
Width=auto        ; auto | 640 | 768 | 856
HorPlus=1         ; 3D to the canvas edges in modes 0, 1, 6
;MouseScale=1     ; map screen pixels to canvas pixels (default: 1 when W > 640, 0 when W = 640)
```

- `auto`: output aspect ratio from `3DVideo.CFG` (lines 2-3; if the file is missing -
  the desktop size): `>= 1.70` (16:9 and wider) -> 856, `>= 1.55` (16:10) ->
  768, otherwise 640. On our machine 2560x1600 = 1.6 -> **768** (the 768x480 canvas
  is exactly 16:10, square pixels).
- Why 856 and not 854: the canvas "dirty" cells are 8x8 pixels, so the width must
  be divisible by 8. Any other number is rounded up to a multiple of 8 and
  clamped to 640..856.
- Without the file: `Width=auto`, `HorPlus=1`, `MouseScale` by width (1 when W > 640).
- `Width=640` (without the `MouseScale` key) = behavior before this change: ox = 0,
  mouse mapping off, all mouse paths are the original code. `MouseScale=1` at
  640 turns mouse scaling on explicitly (UI stretched, mouse across the whole screen).

### How it works (short)

Web analogy: a 640x480 page inserted centered into a wider
`<body>`. The whole game keeps thinking in 640x480 coordinates ("game" coordinates), and
the mapping is handled by one module `include\wiz8\canvas.h` +
`src\wiz8\engine_code\Canvas.cpp` (`g_canvas_w`, `g_canvas_ox`, cell grid,
mouse mapping).

- The DirectDraw surface, `W8ColorSurface` and `stSurface2D` are W wide.
- `LockPrimarySurface` returns a pointer to the start of the **central window**
  (`start + ox*2` bytes, the real row pitch). So all SGP blitters,
  fonts, buttons, Bink movies and screens that write to memory directly
  draw centered without changes. For a full clear there is `LockPrimarySurfaceFull`.
- The "dirty" cell grid is W/8 x 60 (arrays sized 107x60); `InvalidateRegion`
  maps a game rectangle onto the canvas (+ox).
- Renderer: all mappings `x * width / 640` became `(x + ox) * width / W`;
  sprites (radar, formation board, tooltips, cursor) are normalized by 1/W.
- Mouse: screen pixel -> canvas pixel (`x * W / window_width`), the cursor
  is drawn on the canvas, the game gets `x - ox` clamped to 0..639 (in polling,
  in events, and for the wheel). A button press in a side bar is ignored
  (together with its release) so it does not hit portraits at the window edge.
- Hor+ moved from our DLL (`src\hooks_view3d.cpp`) into `SetViewport`.
- Save thumbnails did not change (80x60, same frame, save
  compatibility).

Commits in `decomp`: `wide canvas: canvas module and wiz8wide.ini`,
`wide canvas: video core, renderer mapping, cursor and Hor+ in Video2`,
`wide canvas: SGP input/surfaces and screen call sites`, `wide canvas: review
fixes (mouse default, wheel, side-bar clicks, 639 clamp)`. The patch
`patches\decomp-msvc2022.patch` is updated (`git diff 720e1d8 --output=...`,
byte for byte, with CRLF lines; the root `.gitattributes` has `-text` for patches
so git does not re-encode them).

## Russian translation Wizardry8_rus 1.2.6 (2026-10-12)

The fan translation (`build\rus\Wizardry8_rus(1_2_6)`, its `Data` copied to
`games\ru`) brings its own data and its own `Wiz8.exe`. With the source-built
`Wiz8Runtime.exe` the strings were Russian (cp1251 bytes) but were drawn as
Latin letters with diacritics ("Àåñèêà"). Now the build itself does the same
as the translation's exe, and **only when the Russian data is in place**.

### What the Russian translation changed in the exe (how it was found)

Its `Wiz8.exe` (3 299 840 bytes) is not a patch on the GOG exe but **a different build
from source** with almost the same layout (`.text` from 0x401000, function
shifts 0..0x300, `.data` shifted by 0x400 after the key table). The sections
are merged and unnamed (stripped by the unpacker); `Wiz8.fix` is a packed (`.upx`)
variant of the same exe. The string `Fonts2` does not appear in the exe at all.

The comparison was done per function: for each function marked `// FUNCTION: WIZ8`
the GOG exe bytes (with `.reloc` addresses and `call`/`jmp` targets masked)
were searched for in its exe in order; the non-matching ones (322) were compared line by line
with a disassembler, plus `.data` was compared separately and all strings with
Cyrillic were searched for. The scripts were in a temp folder; the result:

| What | GOG 1.2.4 | Russian translation | Gist |
|---|---|---|---|
| `CreateEnglishTransTable` (sgp/Font.cpp) | 0x407ec0 | 0x407f70 | 252 cells as in GOG, but: cells 93..148 (À..ß) = 0; 184..249 = 0xC0..0xC5, 0xA8, 0xC6..0xE5, 0xB8, 0xE6..0xFF (А..Е Ё Ж..я, ё after е); 250..251 (¿ ¡) = 0. For example, it has `66 C7 00 C0 00` (`mov word [eax],0xC0`) where GOG has `66 C7 00 00 00`. |
| `TranslateKeyToCharacter`, `TranslateCharacterToKey`, `RedirectToString` (sgp/input.cpp) | 0x402780, 0x4027c0, 0x4023b0 | 0x4027b0, 0x402800, 0x4023d0 | the index into `gsKeyTranslationTable` = `layout*512 + key`, the layout is variable 0x6511b8; the table (0x5ffc3c) became 2x512, the second one is ЙЦУКЕН (the Russian JCUKEN keyboard layout) in cp1251. |
| `KeyboardHandler`/`KeyUp` | 0x401b30 | 0x401b30 | on Shift release, if Alt is held: `xor [0x6511b8],1` (Alt+Shift). |
| `IsUppercaseWideChar`, `IsLowercaseWideChar`, `ToUppercaseWideChar`, `ToLowercaseWideChar`, `CompareWideTextIgnoreAsciiCase` | 0x402800.. 0x402920 | 0x402850.. 0x4029b0 | ranges 0xC0..0xDF (uppercase) and 0xE0..0xFF (lowercase) added. |
| strings in `.data` | `kill`/`kills`, `accidentally strikes`, `%s's`, `Front/Right/Rear/Left/Center`, `%dg`, `%4.1f lbs`, ` vs. `, `%s (Pwr %d)`, `%s %dg` | `уб.` ("kill(s)"), `неожиданно бьет` ("unexpectedly strikes"), `%s`, `Фронт/Правый фланг/Тыл/Левый фланг/Центр` ("Front/Right flank/Rear/Left flank/Center"), `%dз` ("%dg"), `%4.1f кг.` ("%4.1f kg."), ` `, `%s (Эн. %d)` ("%s (Pwr %d)"), `%s %dз` ("%s %dg") | everything else comes from `StringData.DAT`. |

It did not change the code that converts text to wide characters (`ConvertStringToWide` = `swprintf
"%S"`, C locale): a cp1251 byte is simply zero-extended
(`0xC0 -> 0x00C0`), so the "encoding" lives only in the font table.
The imports are the same (no `setlocale`/`MultiByteToWideChar`). The other
exe differences are gameplay fixes from the unofficial 1.2.6 patch (combat, magic,
portraits, etc.); they have nothing to do with text and were not ported.

Fonts: in its `DATA.SLF` the `FONTS\` folder is already Russian (10 fonts have 252
cells: Wiz_Text_Font(+Bold, +Monopalette), dialog_font, Font10Arial(+Bold),
Font12Point1, Opt_title_font, Opt_detail_font, SmFnt; Cyrillic in 184..249, Latin with diacritics left in 93..148),
`FONTSEN\` holds the English originals, `FONTS2\` is a draft set the exe does not
read (some of its files are English). So the experiment "load
`Data\Fonts2`" was wrong and was removed: fonts load as in the original from
`Data\Fonts`, and only the character table was missing.

### What was done in the source

- `src/wiz8/russian_text.cpp`, `include/wiz8/russian_text.h` (new):
  `InitializeRussianText()` is called in `InitializeGame` right after
  opening the SLF and loading strings (before `InitializeMenuFonts`). It turns on Russian
  mode if `Data\Fonts\Wiz_Text_Font.sti` has at least 250 cells (English 154,
  Russian 252). It can be set explicitly in `wiz8wide.ini`:

  ```ini
  [Text]
  ; auto (default) | 1 = Russian mode | 0 = English
  Cyrillic=auto
  ```

  The decision is written as a `text: ...` line at the end of `wiz8wide.log`.
  `RussianOr(english, russian)` is for strings hard-coded in the code: in Russian mode
  the Russian string (plain text in the source, converted to cp1251 codes
  once), otherwise the English one. Formation row names are rewritten in place.
- `src/sgp/Font.cpp/.h`: `gfCyrillicText`, `UseCyrillicFontTranslation()` -
  rewrites the already created "character -> cell" table as in its exe.
- `src/sgp/input.cpp`: a second keyboard layout (built from the English table and a
  list of differences taken from its exe), Alt+Shift, Cyrillic case. All under
  `gfCyrillicText`: with English data the behavior is unchanged.
- Strings: `Combat.cpp`, `Combat Attack.cpp`, `character_skills.cpp`,
  `NpcDialog.cpp`, `DialogFactoryDialogs.cpp`, `AssayDialog.cpp`,
  `NPCInteractionSubscreen.cpp`. «кг.» ("kg.") - same as the translators: they changed the label,
  but the number stayed in pounds (weight * 0.1).

### What to check in the game

- `wiz8wide.log` in `games\ru`: the line `text: ... glyphs=252 -> Russian`;
  in the English copy - `glyphs=154 -> English`.
- Main menu and options (`Opt_title_font`, `Opt_detail_font`), party
  creation (`Font10Arial`, `Font12Point1`, `Profession`), the message log
  at the bottom of the screen (`Wiz_Text_Font`, `..._Bold`, `..._Monopalette`), conversation and
  trading with NPCs (`dialog_font`, prices «123з» ("123g")), tooltips,
  item description (Assay: «(Эн. N)» ("(Pwr N)")), level loading screen, combat
  («неожиданно бьет» ("unexpectedly strikes"), «Победа ... уб.» ("Victory ... kill(s)")), changing a formation row («Правый фланг» ("Right flank")).
- Letters Ё/ё and № (code 0xB9 exists only in the keyboard layout; there is no cell for № in the font,
  same as with the translators).
- Input: character name / save name / a word in NPC conversation -
  Alt+Shift switches to Russian, Shift gives uppercase, the first letter of a name
  is capitalized for Cyrillic too.
- Fonts the Russian translation did not touch (LargeFont, SmallFont, ButtonFont,
  Calligraphy*, TinyMonoFont - 93 cells; Engraved, Embossed, Profession -
  144..148) have no Cyrillic in it either: a Russian letter in them would give
  a cell number past the end of the font. If this shows up somewhere (garbage/crash on
  a specific screen) it is the same behavior as its exe, but it is worth reporting.

### Green dashes on spaces in speech bubbles (fixed)

Symptom: in a bubble with an NPC line (Ferro) or a character line (Vi grumbling), on
every space and after a closing quote there is a barely visible dark green
dash; with English data it is not there, and the bottom log (`Wiz_Text_Font`)
is clean.

The cause is in the Russian translation's data, not in the character table. Bubbles are drawn with
the font `FONT12POINT1.sti` (`LayoutPortraitQuoteBubble` 0x5cf6c0 ->
`DrawWrappedText` 0x5d0770 -> `DrawWrappedTextLine` 0x5d0590). Space in the
table is cell 92 both in GOG and in the Russian translation (both have
`mov word [eax],0x20` at the 93rd entry). In the Russian `FONT12POINT1.sti` (252
cells) cell 92, 7 wide, contains a line: row 8 = ETRLE
`81 05 01 01 01 01 01 81 00` (5 pixels of index 1); in GOG (188 cells) it is
empty (`85 00` x 11). Index 1 in fonts is the shadow. `DrawWrappedTextLine`
draws the line twice: `gprintfDirty` (color from the font palette, index 1 =
RGB 0,54,0) and `mprintf` (shadow = `SetFontShadow(0)` = black = not drawn).
The first pass is what gives the green "glow" on letters and the line on spaces. Of all
fonts in `FONTS\`, `Journal\`, `Level Load\` only
`FONT12POINT1` has such a space cell.

In the Russian translation's exe this path matches GOG byte for byte (except for
addresses): `DrawWrappedText` 0x5d0810, `DrawWrappedTextLine` 0x5d0630,
`LayoutPortraitQuoteBubble` 0x5cf760, `gprintfDirty` 0x407880, `mprintf`
0x407310, blitters 0x411240/0x411e90, `CreateObjectPaletteTables` 0x406510,
`InitializeMenuFonts` 0x4e2880. So the translators have exactly the same line on spaces;
our `Font.cpp` (the cell-count safeguard, the table) has nothing to do with it.

The fix (`src/sgp/Font.cpp`, `BlankSpaceGlyph` from `LoadFontFile`, only
with `gfCyrillicText`): if the space cell has opaque pixels, it is
re-encoded in place as fully transparent (`87 00` x 11, same width,
the background is still filled). English fonts are not affected (the cell
is empty, and the code is not called without Russian mode). Check in the game: the
Ferro/Vi bubble without dashes, space width unchanged, the name input field.

## Borderless without a monitor mode switch (2026-10-12)

Port into the source of what our `version.dll` did for the GOG exe
(`src\hooks_video.cpp`, `src\hooks_input.cpp`, `docs\history\phase3-borderless.md`).
The built exe does not use the DLL, so the same behavior is now in the code.
Commit in `decomp`: `Borderless display: no mode switch, Bink through the 2D
canvas, Alt+Tab fix`.

### Configuration

```ini
[Display]
Borderless=1   ; 1 (default, and when the key/file is missing) | 0 = as in the original
```

The value is read on first access (`DisplayBorderlessEnabled()` in
`Canvas.cpp`) - earlier than `CanvasInitialize`, because the `/WINDOW` switch on the
command line is parsed before video starts. `wiz8wide.log` gets the
line `[Display] Borderless=...`. `Borderless=0` is the original code unchanged
(all new branches are under this flag; the only change without the flag is
zeroing `m_target` in the player constructor, see below).

### What changed (in plain words)

| Function | File | Before | Now with Borderless=1 |
|---|---|---|---|
| `OpenRendererWindow` | `Video2.cpp` | a WS_POPUP window over the whole monitor, then `getDisplayMode(3DVideo.CFG)` and `openWindow(mode)` - the monitor switches to that resolution | the same window, but `openWindow(-1)`: SurRender opens output "as in a window" the size of the client area (= monitor), without `SetDisplayMode` (same as the DLL's 7 bytes at 0x422895) |
| `VideoFullScreen` | `Video2.cpp` | changes `g_fullscreen` and recreates the output | only `g_fullscreen = 1`: `/WINDOW`, the in-game toggle and "maximize" (WM_SIZE) do not break the window; the mouse works in screen coordinates (the window starts at 0,0 of the monitor) |
| `InitializeVideoManager` | `Video2.cpp` | — | `g_fullscreen = 1` before the window is created |
| `BeginVideoPresentation` | `Video2.cpp` | closes the renderer, exclusive mode, monitor at 640x480, gives the player the screen surface | returns 0 immediately: the renderer is not touched |
| `FinishVideoPresentation` | `Video2.cpp` | restores the normal mode and reopens the renderer | only `InvalidateCanvas(0)` - the next screen redraws over the last frame |
| `W8BinkVideo::W8BinkVideo` | `Bink.cpp` | `m_target` (+8) not initialized | `m_target(0)`; without a "screen" the player writes the frame into the 2D canvas (`LockPrimarySurface` - the central 640x480 window) and marks the changed rectangles |
| `IntroScreenFrame` | `IntroScreen.cpp` | the movie screen does not draw the frame (frames went straight to video memory) | while `gpVideo` is alive - `RenderFrame()`, the frame is shown through the 2D canvas centered, like any screen |
| `WindowProcedure` | `sgp\sgp.cpp` | — | on `WM_ACTIVATEAPP(TRUE)` and `WM_SETFOCUS` reset `gfShiftState/gfCtrlState/gfAltState` and `gfKeyState[VK_SHIFT/VK_CONTROL/VK_MENU]` (in the GOG exe 0x6F04EA, 0x6F0508, 0x6F051C, 0x6F0530..32) - Alt does not "stick" after Alt+Tab |

### The Russian translation's intro movies (`Data\Flics\Intro`)

Report: "the Sir-Tech logo does not play after the Buka logo". The files were analyzed
(Bink header + frame-by-frame decoding with the same `binkw32.dll` 1.0q as the
game, with the same flags `BinkCopyToBuffer(..., BINKSURFACE555)` and
`BinkGetRects` - a temporary tool in `build\binkprobe`):

| File | Size | Bink | Frames, fps | Length | Contents |
|---|---|---|---|---|---|
| GOG `sirtech.BIK` | 2 330 252 | BIKf, 640x480, audio 44.1 kHz | 486, 30 | 16.2 s | Sir-Tech logo |
| Russian `sirtech.BIK` | 2 097 952 | BIKi, 640x480, audio 44.1 kHz | 302, 10 | 30.2 s | **both logos in one file**: Buka 0–13.5 s, black ~2 s, Sir-Tech 15.5–30 s (the same movie as GOG's, re-encoded at 10 fps) |
| Russian `sirtech0.BIK` | 520 | BIKi, 640x480 | 1, 25 | 0.04 s | a single black frame, a stub |

Neither the Russian translation's exe nor the GOG exe opens `sirtech0.bik` (the translation's
exe has the same movie name table as GOG; there is no `sirtech0` string).
The logo is not skipped: decoding in the game shows both Buka and Sir-Tech (verified
by simulating redraws over the `BinkGetRects` rectangles - after Buka the screen
is cleared and Sir-Tech fades in). So `sirtech0.bik` was **not
added** to the chain (it would be a flash of a black frame). Probable cause of the
observation: a click/Esc during Buka (`AdvanceIntroScreen` skips
the **whole** file, i.e. Sir-Tech too), or the ~2 s black pause after Buka and the dark
fade-in of Sir-Tech at 16–20 s look like the end of the movie. The movie chain was
not changed: `sirtech.bik`, then `Wizardry8.bik` on first launch.

### What to check in the game

- `wiz8wide.log`: the line `[Display] Borderless=1 (...)`.
- `scripts\play\modewatch.ps1` for the whole run: intro, movies, menu, loading, game -
  not a single monitor mode switch.
- Movies (Russian: Buka → Sir-Tech without pressing anything ~30 s; then
  `Wizardry8.bik` on first launch) - centered, no mode switch, no
  garbage at the edges; after the movie the menu is drawn completely.
- Esc/click during a movie - moves on, no black screen.
- Alt+Tab back and forth in the menu and in the game: the picture comes back, Alt/Shift/Ctrl
  do not stick (for example, movement/clicks do not behave as if Ctrl is held).
- `/WINDOW` and the fullscreen toggle key - the window stays borderless.
- `Borderless=0` - behavior as before (the monitor switches to the
  `3DVideo.CFG` resolution, movies in 640x480).

## Fixes from the bug hunt (2026-10-12)

Three commits in `decomp` (8d31107, 714001a, ebcfe07), patch updated.

Differences from the original (decompilation errors):
- `g_monster_special_attack_name_ids` (`Combat Hostility.cpp`): had 12
  elements; the original (0x61EC14) has 30 + two more words that the original
  reads for types 30/31. Now 32 values from the exe. Previously attack type 12
  (Maddening Gazer) crashed the game, types 13+ showed the wrong text - in combat and in
  the "Monster Info" window.
- `g_character_race_records` (`CGSStatsPage.cpp`): 16 rows, as in the original
  (0x64F118); the selection list still has 11 races. Previously for RPC races (Trynnie,
  T'Rang, Umpani, Rapax, Android) the level-up page showed the gender or a placeholder
  in the "Race" line.
- `ApplyCombatEffectSlot` (`Magic Effects.cpp`): `source_character = -1`
  before the source check, as at 0x54CDE9. Previously, for a monster spell, it held
  garbage (the spell number), and writing `character_hate[garbage]` corrupted monster
  memory/the heap.

Wide canvas (our mod; with W = 640 or without layout A nothing changes):
- End of combat: small combat portraits are erased in the LEFT/RIGHT columns
  (previously they stayed at the edges in "radar"/"formation" modes).
- Party death and the ending: the whole canvas is erased before the picture; the fade
  (`BeginScreenFade`, surprise attack) covers the full canvas width.
- Leaving the main menu: the wide background is erased from the side bars
  (`CanvasClearSideBars` + `ResetTransientRenderScenes`).

Russian text:
- Prefixes in NPC conversation («нанять» ("hire"), «где находится» ("where is"), «расскажи о» ("tell about"))
  are compared by the original function 0x4028C0 (`CompareWideTextNIgnoreCase`),
  which with `gfCyrillicText` understands uppercase Cyrillic letters, like the
  Russian translation's exe. Prefix lengths are the original ones (same as in the translation).
- `Font.cpp`: a character's cell number is checked against the font's cell count; if
  the cell does not exist, "?" is drawn (previously - a read past the end of the array). Buttons draw
  text through the same `gprintf`/`mprintf`.
- `CreateMessageBox`: if the font (SmallFont, 93 cells) cannot draw
  Russian text, Wiz_Text_Font (252 cells) is used. These are the "could not
  save/load character" windows. Other places with "short" fonts and
  translated text: only `DrawCampRegenStats` (Calligraphy, unreachable per
  analysis) - it is covered by the check in `Font.cpp`.

### What to check in the game

- A monster with a special attack of type 12+ (Maddening Gazer, Giant Spider, Spore
  Plant, Bitter Wing): the combat log shows the correct attack name, the game does not crash;
  same in the monster info window (monster knowledge 50+).
- An RPC of a non-playable race (RFS-81, Umpani, T'Rang, Rapax) levels up:
  the "Race" line shows its name and icon.
- W = 768/856, radar or formation mode: after combat there are no combat
  mini-portraits at the edges.
- Whole party death / ending with W > 640: fade and picture with no
  HUD leftovers on the sides.
- From the main menu into "New Game", "Load", "Settings", "Credits": the side
  bars are black.
- Russian data: «Нанять» ("Hire") with a capital Н works in NPC conversation.
- Russian data: the character save error window (Saves\CurrentGame.SAV
  read-only, dismiss an RPC) - readable text, no crash.
