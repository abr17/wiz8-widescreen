# Research: widescreen through the decompilation (raw multi-agent output, 2026-10-11)

> **History.** This document describes an early stage of the project and may differ from the released 1.0.0 patch (the hybrid, see [docs/hybrid.md](../hybrid.md) and [README](../../README.md)). It is kept to show how we arrived at the current solution. In the end the decompilation was built with portable MSVC 2022, not VC6 ([decomp-port.md](../decomp-port.md)).

######## toolchain: how the decomp builds the runnable Wiz8Runtime.exe, and whether VC6 c
BLOCKERS: VC6 SP5 is not present and must be obtained. The only path the repo automates is a git clone of archaic-msvc/msvc600_sp5: unlicensed Microsoft binaries, legally gray. The legal route is an owned VS6 disc or a subscription download, plus vs6sp5.exe. | Not verified that VC6 cl, link, nmake and rc run correctly on Windows 11 26300 under WOW64. Strong expectation, but untested. Watch for problems with mspdb60.dll / PDB handling (/PDBTYPE:SEPT), and with long paths or paths containing spaces. | Not verified that CMake 4.4.4 still supports MSVC_VERSION 1200 with NMake Makefiles. The repo pins 3.26.6. The fallback is a portable cmake-3.26.6-windows-i386.zip (tens of MB) inside Tools. | Ninja is not usable as-is: VC6 cl has no /showIncludes, so the dependency scan fails. Use VC6's own nmake.exe ('NMake Makefiles') or jom ('NMake Makefiles JOM'). | The Python driver (uv run wiz8) does not run on Windows: it imports fcntl and calls docker. We need our own driver script, including a port of the stdlib-only coff_archive.named_iat_archive to generate sr-assert-import.lib. | The top-level CMakeLists always configures srext_jpegimporter, srext_unzip and tests/differential. Configure needs the IJG jpeg-6 and Info-ZIP 5.4 source trees (small downloads), or a local change that skips those subdirectories (which would modify the decomp copy). | ddraw.lib and dxguid.lib are assumed to be in VC98\Lib. Not confirmed, because the toolchain is not available locally. | Licensing: the decomp has no license file and src/sgp is non-commercial (SFI). That is fine for a personal mod, but it limits redistribution of a rebuilt exe. | Unknown whether the recovered code is complete enough for Wiz8Runtime.exe to link with no unresolved symbols at the current commit. The README claims it does; this cannot be confirmed without building.
REC: Build natively and skip Docker and Wine. Treat VC6 as a portable folder, C:\dev\wiz8-ws\Tools\msvc600, holding VC98 and Common. The owner must decide how to get it; prefer an owned VS6 disc + SP5 over the unlicensed GitHub mirror. Then write a small driver, Tools\vc6env.ps1 plus build-runtime.ps1, that does the following:

(1) Set session-only environment variables:
   PATH = Tools\msvc600\VC98\Bin;Tools\msvc600\Common\MSDev98\Bin;Tools\cmake\bin;%PATH%
   INCLUDE = VC98\Include;VC98\MFC\Include;VC98\ATL\Include
   LIB = VC98\Lib;VC98\MFC\Lib
   TMP and TEMP pointed inside the workspace.

(2) Unpack zlib-1.0.4, plus jpeg-6 and unzip540 with the zcrypt28 crypt.c/.h overlay, under C:\dev\wiz8-ws\build\deps. All are small and sha256-pinned in config/build-inputs.yml.

(3) Generate build\vc6\sr-assert-import.lib with a 1:1 port of tools/wiz8decomp/binary/coff_archive.py. Run it with the system python using -I, or rewrite it in PowerShell.

(4) Configure:
   cmake -S ref\wizardry-8-decomp -B build\vc6 -G "NMake Makefiles" -DCMAKE_BUILD_TYPE= -DZLIB_SOURCE=... -DIJG_JPEG_SOURCE=... -DINFOZIP_SOURCE=...
   Use "NMake Makefiles JOM" with a portable jom 1.1.3 if parallel builds are wanted. Never use Ninja.

(5) Build:
   cmake --build build\vc6 --target WIZ8_RUNTIME
   Optionally also build the target SURRENDER.

(6) Copy Wiz8Runtime.exe (and optionally the rebuilt sr.dll) into games\work. Our version.dll proxy can stay. Run with /WINDOW.

First smoke test once VC6 is in hand: run `cl /?`, `link /?` and `nmake /?` from the portable folder. Then run the configure step with CMake 4.4.4. If configure fails on compiler detection, put a portable CMake 3.26.6 in Tools.

Fallback if VC6 cannot be obtained legally: not viable as-is. Their clang-cl lane is compile-only and still needs the VC6 headers and libs. A clang-cl + lld-link link against VC6 libs is untested, and the build CMake requires MSVC.
EFFORT: 1-2 days to get a native VC6 build of Wiz8Runtime.exe linking, assuming the VC6 SP5 folder is already available and the decomp links cleanly at its current commit. Add 0.5 day if CMake 3.26.6 or jom must be added. Obtaining VC6 itself depends on the owner (licensing decision).

######## alt-compiler
Short answer: you can build the runnable decomp without VC6 using clang-cl with the MSVC ABI. You cannot do it with llvm-mingw's GNU ABI.

1) The compiler is already in Tools. Tools\llvm-mingw\bin\clang-23.exe (clang 23.1.3) accepts --driver-mode=cl --target=i686-pc-windows-msvc. `ld.lld.exe -flavor link` is lld-link. llvm-lib, llvm-dlltool, llvm-rc and llvm-cvtres are also present. Nothing new needs installing for the compiler or linker. I checked this in the scratchpad:
   - clang-cl produced MSVC-mangled `__imp_` references for dllimport thiscall members, including a virtual-base constructor.
   - An MS `__asm { fld / fistp }` block compiled.
   - lld-link linked against llvm-lib import libs made from .def files (sr.def converted with no errors).
   - A test exe that imports msvcrt.dll ran: static constructors fired through _initterm, and 64-bit division went through ntdll's _alldiv.

2) The source already compiles with clang-cl. The decomp has a clang-cl lint lane (cmake/clang-cl-i686.cmake, cmake/Lint.cmake), and CI runs it on every target with -Werror: wiz8_recovered_objects, WIZ8_SGP, surrender and the runtime tests. So VC6 language quirks (for-scope, MS casts, writable strings), __asm, __declspec and pragmas are already handled by flags and local `#pragma clang` (87 sites). The lane is compile-only and points at the real VC6 headers (-imsvc /opt/msvc6-vc98-include). For iostream it uses its own stand-in headers (tools/lint/include/ostream, fstream, iostream, iosfwd), because the VC6 STL does not parse as C++14.

3) The sr.dll ABI fits clang-cl:
   - Wiz8.exe imports 461 symbols from SR.DLL; 458 of them are in src/wiz8/imports/sr.def (902 mangled names). The 3 missing ones are 2 `??_7srLight` vftables and `?pipe@srTriMeshPipeline`.
   - sr.def has no wchar_t mangling (its `_W` hits are `W4` enums), no free functions returning a class by value and no `__int64`. The 8 member functions that return a class are always returned through a hidden pointer, and clang matches that.
   - 4 sr classes use virtual inheritance (srBin*Stream; 4 vbtable exports). Clang implements the MSVC vbptr layout. src/wiz8 references srBin*Stream 4 times.
   - The decomp declares sr classes in include/surrender: 47 headers, 674 SR_DLL_IMPORT declarations (`__declspec(dllimport)` unless SURRENDER_BUILD). There are 789 W8_ABI_ASSERT/static_assert layout checks that catch layout drift at compile time.
   - `std::ostream` only appears by reference in dump() signatures. The mangling `?$basic_ostream@DU?$char_traits@D@std@@@std@@` is the same with any STL or with the shim. src/wiz8 itself uses `std::` in only 2 places (stTextureFile::dump).
   - The 4 MSVCP60 imports (ios_base::Init and _Winit constructor/destructor) are only static-init side effects of the VC6 headers. They disappear with the shim or modern headers, and the game does not need them.

4) llvm-mingw's GNU ABI is a no-go. `--target=i686-w64-windows-gnu` produces Itanium names (`__imp___ZNK6srNode11getLocationEv`), and `-fc++-abi=microsoft` is rejected for that target. Inline asm is not the problem (`-fms-extensions` accepted the `__asm` block); the C++ ABI is, for all 461 sr imports.

5) The real work is headers and the CRT, not the code:
   - (A) VC6 headers and libs (VC98\Include and VC98\Lib from github.com/archaic-msvc/msvc600_sp5, the same tree the Docker image uses) with clang-cl and lld-link is exactly the configuration the lint lane already proves. Very little source changes.
   - (B) Windows SDK plus MSVC CRT headers, downloaded portably (portable-msvc.py or xwin; large, needs the Microsoft licence) links against UCRT. It needs shims:
     - 203 VC6-style 2-argument swprintf/vswprintf calls in 36 files, and 3 two-argument wcstok calls;
     - `/Zc:wchar_t-` with a `typedef unsigned short wchar_t`;
     - removing `<iostream.h>` from src/sgp/Container.cpp:27.
   - (C) mingw-w64 headers in clang-cl mode are unsupported. Even with -D_X86_ and the wchar typedef, the first test still had 21 errors in the intrinsic headers. Use only mingw's import libs, or better your own .def import libs. Caveat: msvcrt.dll has no _alldiv; ntdll does. libmsvcrt-os.a's exit() needs ___guard_check_icall_fptr.

6) If you take option A you have downloaded VC6 anyway. VC6 cl.exe and link.exe are native Win32 programs, so running VC6 directly on Windows with CMake 3.26.x and jom (the Dockerfile pins cmake-3.26.6-windows-i386.zip and jom 1.1.3) avoids Docker and clang ABI risk entirely. Tools\cmake is 4.4.4, and whether it still recognises cl 12.00 is unverified (guess: risky).

7) Runtime risks under clang -O2 (guesses, but grounded). The decomp keeps retail undefined behaviour on purpose: reads of uninitialised locals (8 `uninit-ok` markers, 9 files listed in src/wiz8/CMakeLists.txt), 2 null-`this` tests, and block copies of records holding vfptrs. Use -fno-delete-null-pointer-checks, -fno-strict-aliasing, /GS-, /GR-, no /EH, and /arch:IA32 (x87 floats like VC6). Lowering the optimisation level helps too. Expect some debugging that VC6 would not need.
BLOCKERS: Headers and CRT for linking: Tools has the compiler and linker but no MSVC-compatible C/Win32 headers. Options: VC6 VC98\Include and VC98\Lib from the archaic-msvc git repo (download of unknown size, legal grey zone; it is what the decomp itself uses), Windows SDK plus MSVC CRT via portable-msvc/xwin (large download, user must accept the Microsoft licence), or mingw-w64 headers (do not work in clang-cl mode without hacks: 21 errors on the first test). | The VC6 STL headers do not parse under clang C++14. You need the repo's tools/lint/include iostream stand-ins in the include path (enough, because wiz8 only declares std::ostream&). Under these headers the MSVCP60 static-init imports disappear. | Build glue is VC6/Docker-specific: CMakeLists.txt:12-14 refuses non-MSVC product builds; ProductSupport.cmake calls lib.exe and cvtres.exe; sr-assert-import.lib comes from Python (build.py:341); zlib 1.0.4 source (ZLIB_SOURCE) has to be fetched. All of this needs rewriting for llvm-lib/llvm-rc/lld-link. Easiest fix for srAssertFail: declare it variadic. | With modern (non-VC6) headers: 203 non-ISO swprintf/vswprintf calls, 3 two-argument wcstok calls, <iostream.h> in src/sgp/Container.cpp:27, and the wchar_t typedef (/Zc:wchar_t-) all need a compat shim header. | Runtime behaviour risk: retail UB is preserved on purpose (uninitialised locals, null-this checks, vfptr block copies) and may be miscompiled by clang -O2. x87 vs SSE2 float differences. If using a custom .def CRT: _alldiv/_allmul come from ntdll, and you need your own startup that calls _initterm and defines _fltused. Needs testing in the game, which this research did not do. | 3 SR.DLL imports used by retail Wiz8.exe are not in sr.def (srLight secondary vftables, srTriMeshPipeline::pipe). The recovered code may not need them; if a link error shows up, add them to the .def.
REC: clang-cl with the MSVC ABI is a go; llvm-mingw's GNU ABI is a no-go (Itanium name mangling cannot call sr.dll's 461 MSVC-mangled thiscall imports, and Microsoft ABI is refused on the gnu triple).

Suggested order:
(1) First consider not switching compilers at all. Get the archaic-msvc/msvc600_sp5 tree (pinned commit b0b07e29) into C:\dev\wiz8-ws\Tools\vc6 and run VC6 natively on Windows (Win32 cl/link, no Wine or Docker) with a portable CMake 3.26.6 and jom, as the Dockerfile pins. This is the original toolchain: zero ABI or UB risk, and the decomp's CMake mostly works as written (the Python glue for sr-assert-import.lib and the ZLIB_SOURCE checkout must be redone by hand).
(2) If VC6 is unacceptable, use clang-cl from the existing Tools\llvm-mingw (clang-23 --driver-mode=cl --target=i686-pc-windows-msvc, ld.lld -flavor link, llvm-lib) with the VC6 headers (-imsvc VC98\Include) plus the repo's tools/lint/include shims. That is the configuration CI already compiles, so source changes stay minimal. Turn the existing clang-cl-i686.cmake into a linking toolchain:
- remove the FATAL_ERROR at CMakeLists.txt:12-14;
- replace lib.exe and cvtres.exe with llvm-lib and llvm-rc/llvm-cvtres;
- build import libs from sr.def, mss32.def and binkw32.def with llvm-lib /def;
- link VC6's msvcrt.lib or a hand-written msvcrt.def, with _alldiv and friends from ntdll;
- flags: /GR- /GS- /Zc:wchar_t- -Xclang -fno-wchar -fno-delete-null-pointer-checks -fno-strict-aliasing /arch:IA32.
(3) Use the Windows SDK plus UCRT only as a last resort: the swprintf, wcstok and iostream.h shims are needed, plus a large licensed download.

Do not try to build sr.dll or the srext DLLs; link against the retail sr.dll from games\work.
EFFORT: Native VC6 on Windows (no Docker): 0.5-1.5 days. clang-cl + VC6 headers/libs + lld-link: 2-4 days to a linking Wiz8Runtime.exe, plus 2-5 days of in-game debugging for clang-specific UB/float differences. clang-cl + Windows SDK/UCRT headers: 5-10 days. llvm-mingw GNU ABI: not feasible (would mean rewriting all 461 sr.dll C++ imports behind a C shim).

######## canvas-scope: widening the decomp's 640x480 2D canvas to 768/854(856)x480
The decomp keeps the 640x480 canvas in a fairly small number of places. Almost all of them are in one file, src/wiz8/engine_code/Video2.cpp: 35 literal "640" hits, about 25 hex 0x280/0x1e0/0x27f/0x1df hits, 9 dirty-grid literals (0x50/80/60/0x12c0) and about 21 uses of the normalized scale constants. SGP adds about 20 more sites, and game/screen code has about 60 full-screen literals. Thousands of per-screen 640-space coordinates sit on top of those, but they never need to change for centering.
Main finding: every 2D pixel write reaches the canvas through one function, LockPrimarySurface (Video2.cpp:307), called directly or via LockVideoSurface(FRAME_BUFFER) at vsurface.cpp:222. All the drawing code uses the pitch that lock returns. FontDestPitch and ButtonDestPitch are stored but never used for addressing. So option (a) can work as a "window inside the surface":
- create the DirectDraw surface W wide;
- have LockPrimarySurface return lpSurface + ox*2 with the real pitch, where ox = (W-640)/2.
Then every SGP blitter, font, button, Bink copy and direct-lock user (MGSPortraits, MGSTextBox, RCSItemsPage, Automap, DialogNumericInput, Text_Input) draws centered without being edited. The 640x480 clip rects then clip to the centered window for free.
What still has to be edited by hand:
1. Video core (Video2.cpp): surface size (624-625); stSurface2D 640 -> W (2493/2497). The tiler already copes with partial tiles: 480/128 = 3.75 rows today, so a 7th partial column for 856 is the same case. Dirty grid 80x60 -> (W/8)x60 (0x12c0 arrays and the 0x50 stride at 205/224/1939/1967/1981-1997/2093-2116). InvalidateRegion clamps and the full-redraw test (2018-2044), plus +ox. The full-screen invalidates at 341/402/871/888/938 must cover all of W. Raw DDLockSurface users that take 640-space coordinates: ClearSurfaceRect 2525 and the inspector at 2233.
2. Renderer mapping: every "*width/640" becomes "(x+ox)*width/W" (RenderScene 1018-1021, clear scissor 1150-1152, 1282-1289, 2136-2138, 3696-3698). SetViewport fractions (2169-2176) are where Hor+ goes in. Sprite normalization: g_inverse_screen_width 0.0015625 (2851), g_viewport_x_scale (219), configure2D width*640 (1457), CreateSpriteFromTexture (1468), PositionToolTipNode +ox (2871-2904), square camera view.top 0.75 = 480/640 (2463), g_double_three_quarters (2853/2899), cursor brush 0.2/0.2667 (1894) and 1594.
3. Mouse: SyncSystemCursor clamps 640/480 (1816-1823); PositionMouseCursor /640, /1280, 641/481 (1727-1731); InitializeMouseCursorScene (1905). Game logic needs 640-space input, so subtract ox at input.cpp:174-180, SGPMouseGetPos (1845), GetAtomCursorX (1866) and DispatchRegionInput (RegionManager.cpp:685).
4. SGP: vobject_blitters.cpp ClippingRect (17), hard clip in Blt16BPPTo16BPP (1524-1525), ShadowRect clamp (3093-3095). LineDraw pitch passed as 0x500 at 4 call sites (line.cpp:123-164 uses giImageWidth for addressing, so this is a real bug once the pitch changes). DirectDraw rect-based fill/blt paths (FillSurfaceRect, BltVideoSurfaceToVideoSurface, DirectDraw Calls.cpp:387-461) need +ox when the destination is the frame buffer. FRAME_BUFFER usWidth picks up W automatically (vsurface.cpp:1506-1507). Tooltip clamps (mousesystem.cpp:998-1006, RegionManager.cpp:39/795-802). game_init.cpp:64 clears pitch*480 from the lock pointer and would overrun by ox*2 bytes once the pointer is offset.
Things to keep at 640: save thumbnails (LoadSaveGame.cpp:451-456 and 1680-1685; 80x60 frames stored in the save file, so changing them breaks save compatibility). Bink frames stay 640 wide and are centered by the pointer offset. BeginVideoPresentation SetDisplayMode(640,480) (789) is a legacy fullscreen path.
For (b), redesign, layout is not data-driven. It lives in literals per screen file:
- 220 DrawCatalogImage, 174 gprintf, 176 "new W8*Control", 33 "new Controls", 83 InvalidateRegion and 22 SetRegionBounds call sites in src/wiz8;
- the static region table: 313 regions in 51 sets (RegionManager.cpp:46-470);
- the main-game tables g_viewport_modes[7] and g_main_game_invalidate_rects[23] (MainGameScreen.cpp:4784-4803).
The main HUD is spread over MainGameScreen.cpp (90 layout calls) plus the MGS* modules (Portraits 46, SpellCasting 27, TextBox 24, Buttons 16, UseItemSelect 15, Formation 11). The main menu is small: MainMenuScreen.cpp has about 10 calls and 7 regions (RegionManager.cpp:73-80).
Effort guess, assuming the runtime build already compiles and runs for us (not checked here): about 9-13 working days for (a) at one configurable W, including a test pass over all screens. Then roughly 2-3 days for the main menu and 8-15 days for the main HUD under (b), not counting new art.
BLOCKERS: Everything here assumes a WIZ8_RUNTIME executable we can build and run on this machine. The README's path is MSVC6 SP5 in Docker plus Wine/GE-Proton, which the owner's constraints rule out except as a last resort. Whether it builds with llvm-mingw, or links against the retail sr.dll and middleware natively on Windows, was not checked (separate topic). | Pitch alignment (GUESS): DirectDraw may pad a system-memory surface's pitch beyond W*2. Code must use the lock pitch everywhere; the 4 LineDraw sites with a hard 0x500 pitch and game_init.cpp:64 must be fixed. | 854 is not a multiple of 8, which breaks the 8x8 dirty-cell grid. I recommend a canvas width of 856 (107 cells) for 16:9; 768 divides cleanly (96 cells, 6x128 tiles). | Not verified (GUESS, but the current partial bottom tile row is evidence it is fine): that srColorSurface::blit clips a tile whose right edge (896) runs past the source width (856) in stTexture2D::getMipmapData (surface2d.cpp:40). | Full-width background art (main menu catalog image 0xe8, HUD frame images) has to come from new assets. Asset formats and packing are out of scope here. | Raw mouse coordinates are in output/window pixels (input.cpp:174, SyncSystemCursor). When the renderer resolution (3DVideo.CFG) is not equal to the canvas size, a pixel->canvas scale step is also needed. The retail code assumes 1:1.
REC: Do (a) first as the 'window inside a wide surface' design, controlled by one runtime variable g_canvas_w (768 or 856), with g_canvas_ox = (g_canvas_w-640)/2:
1) Video core: allocate the DD surface, W8ColorSurface and stSurface2D at g_canvas_w x 480. Make the dirty grid g_canvas_w/8 columns (arrays sized for the max of 107*60). In InvalidateRegion, add ox and clamp to W. Add InvalidateScreen() for the 7 full-screen invalidates. LockPrimarySurface returns base + ox*2 with the real pitch; add a LockPrimarySurfaceBase for the full clears (ResetVideoFrameState, ClearPrimarySurface, game_init.cpp:64).
2) Renderer: replace every /640 with /W and add ox in RenderScene, the scissor code and the Set*Viewport functions. Set g_inverse_screen_width and g_viewport_x_scale to 1/W, square camera top to 480/W, cursor brush to 128/W. PositionToolTipNode adds ox and stores position_x in canvas space.
3) Mouse: clamp to W. Keep g_cursor_width/height in canvas space for drawing the cursor, but give game logic 640-space values (subtract ox in input.cpp:174, SGPMouseGetPos, GetAtomCursorX, DispatchRegionInput). Add an output->canvas scale step.
4) SGP: leave ClippingRect at the centered 640 window. Add +ox in the DD rect fill/blt paths when the destination is the frame buffer. Pass the real pitch to the 4 LineDraw sites.
5) Port the Hor+ logic from our DLL into SetViewport (the plane is widened only for modes 0/1/6, which touch the edges).
6) Test pass over all screens, Bink, dialogs and save thumbnails.
Then (b): add a per-screen 'layout offset' (default ox). Redesigned screens set it to 0 and use canvas-space literals. Start with MainMenuScreen.cpp (about 10 draw calls; regions at RegionManager.cpp:73-80; background 0xe8). Then the main HUD: g_viewport_modes, g_main_game_invalidate_rects, the MGS* modules and the main-game region sets. Group elements by anchor (left column portraits +0, right column portraits +2*ox, message log widened via SetTextBoxRegionBounds). Keep the 80x60 save thumbnails at 640x480 so saves stay compatible.
EFFORT: (a) global centering: config/constants 0.5; video core (surface, stSurface2D, dirty grid, InvalidateRegion, lock offset, clears) 2-3; renderer/sprite/overlay normalization 2; mouse plus output->canvas scaling 1-2; SGP clip/pitch/DD-rect fixes 1-2; Hor+ port 1; full screen-by-screen test 2-3. Total about 9-13 days. (b) redesign: per-screen offset mechanism 1; main menu 2-3 (code only); main HUD 8-15 (MainGameScreen plus 6-8 MGS modules plus region tables); each further screen (RCS/inventory, NPC, automap, options) 2-5 each. All of this excludes art production and assumes the runtime build already works locally (GUESS).

######## hud-layout
KEY FACT: the decomp is built against our exact exe. reccmp-project.yml lists the Wiz8.exe sha256 as 18a74ff6...420d2, so every `// FUNCTION: WIZ8 0x...` and `// GLOBAL: WIZ8 0x...` address can be used directly by our DLL. I checked 6 data tables byte-for-byte in ghidra\bin\Wiz8.exe (see evidence).
HOW LAYOUT IS SPECIFIED: no layout data files. The HUD is placed by absolute 640x480 numbers in C++, in three kinds of place: (a) blit calls with fixed x/y (DrawCatalogImage(FRAME_BUFFER, objectId, 0, subImage, x, y)); (b) tables in .data that can be patched at runtime: the static mouse-region table, the viewport-mode rects, the invalidate rects and the button-position arrays; (c) a few per-slot switch statements. The art comes from a catalog: object id -> g_video_slots[id] -> g_video_frames[path] (VideoObjectManager.cpp:24, :688). The HUD sub-images have zero built-in offsets (checked in DATA.SLF), so every position lives in code.
SCREEN MAP (640x480):
- Roof y0-18: main_roof (id 0x85, 640x18) at (0,0); 3 roof buttons at (10,1), (39,1), (68,1); combat progress bar (0x8d, 286x13) at (177,2); spell-icon strip at x413-640.
- Portrait columns y18-358: left x0-128, right x512-640, 4 rows at y 18/103/188/273 (85 px pitch). All set in one switch, GetPartySlotMenuAnchor (MGSPortraits.cpp:439). Compact mode shifts them by 0x69 / 0x269.
- Bottom panel y358-450, left to right: strip (main_bottom_bar sub-image 0, 23x92) at 0; radar (main_radar_back 105x92) at 23; message log (main_textbox_back 384x92) at 128; formation (small_formation_back 105x92) at 512; strip (sub-image 1) at 617.
- Bottom bar y450-480: main_bottom_bar sub-images 2..9 at x 0/30/196/292/343/528/610, plus SGP buttons placed from position tables.
- Radar and formation board are not framebuffer blits. They are 2D sprites drawn by the 3D renderer (Position2DNodeUnsnapped), which matters for our current centering hook.
MESSAGE LOG: text rect (168,366)-(452,442), set by SetTextBoxRegionBounds (Screens.cpp:410). The scroll arrows follow right+5, but their y values (0x16b/0x1ad/0x17b) are fixed. Wrap width = right-left-10, so width is already parametric. Height is NOT: 7 rows and 11 px line height are hard-coded at about 15 sites in MGSTextBox.cpp. Making the log wider is easy; adding lines is medium work.
MOUSE: two systems. (1) The static region table g_regions (RegionManager.cpp:70, 313 entries, 89 with literal bounds, 34 of them on the right side, some are circles). It also contains the main-menu items 1-6, and a few entries are re-placed at runtime by SetRegionBounds. (2) SGP buttons (W8DialogButton::SetPosition -> SetButtonPosition) for the roof, bottom bar and layout arrows; their hit area follows the button position.
MAIN MENU: background intro_bg_text.sti (catalog 0xe8), a 16-bit 640x480 surface drawn at (0,0). 6 items from introtext_{normal,highlight,depressed,unavailable}.sti (346x44 each) at x=152, tops 138/187/235/284/335/423. Hit areas are g_regions[1..6]. Version text sits at x=0x27b-width, y=5.
LIKELY UNUSED LEGACY ART (guess: no literal id found anywhere in the decomp): roof.sti, bottom.sti, bottomB.sti, leftside1-4/rightside1-4, lefttop/righttop, left/rightcorner, left/rightplug, Left/RightStrip, BottomStrip, Left/RightWingTip, and main_compass_back.sti (not even in the catalog).
BLOCKERS: The 2D framebuffer and SGP clip/viewport are 640x480. A real 768/854-wide canvas needs FRAME_BUFFER creation, SetViewport, ClearPrimarySurface, help-tooltip clamps (RegionManager.cpp:39) and Video2.cpp (45 width literals) widened first. That is outside this topic and its prerequisite. | Radar and formation board are drawn by the 3D renderer as 2D sprites (Position2DNodeUnsnapped), not blitted. Moving them needs the renderer-side 2D coordinate space widened too, and our current 4:3-centering hook may treat them differently. | Message-log height is hard-coded (7 rows, 11 px) at about 15 sites in MGSTextBox.cpp. Each must be patched together or scrolling and hit-testing break. | Mouse hit areas live in two independent systems: the g_regions table plus SetRegionBounds calls, and SGP buttons. Both must be moved to match the art. | Bottom-panel subscreens (spell casting MGSSpellCasting.cpp:120-121, NPC dialogue NPCInteractionSubscreen.cpp:717, use-item, lock/trap, party movement) also assume the 23..617 x 358..450 panel. A redesigned bottom panel breaks them unless they are moved too. Not fully audited. | Not verified: whether the game loads loose files from Data\ before DATA.SLF, which is needed to ship new art without repacking SLF. Repointing g_video_frames paths (0x30-char fields) to new filenames inside a repacked or extra SLF is the fallback. | Binary call sites for code literals (push immediates) still have to be located one by one in Ghidra. Only one pattern was searched (2 hits, call sites not identified).
REC: Use the decomp as an exact address map for our version.dll. Do not rebuild the exe. Order of work:
(1) Data-only patches at DLL load, done by writing to .data: g_regions (0x00620048), g_viewport_modes (0x00647d30), g_main_game_invalidate_rects (0x00647DA0), button position tables (0x0064C290..0x0064C518), and g_video_frames paths (0x0062c430) to point at new widescreen STIs.
(2) Small code hooks or immediate patches on the functions that hold blit literals: ApplyMainGameRedrawFlags 0x00562E40, RedrawLayoutArrowButtons 0x00598490, RedrawSubMenuButtons 0x00598810, RedrawOptionsDiskButton 0x00597AF0, RedrawCombatStanceButtons 0x00597D30, DrawSubMenuCharacterAction 0x00596FE0, RedrawRoofButtons 0x00598060, GetPartySlotMenuAnchor 0x0059AA60, RedrawCombatPortraits 0x0059B720, SetTextBoxRegionBounds 0x0058FA90 plus its caller in InitializeMainGameLevelBlock 0x0055F2C0, MGSRadarMap and MGSFormation sprite positions, MainMenuScreenEnter 0x005bc810 / DrawMainMenuItem 0x005bcab0.
Easiest design path: keep the 640-wide element art, move portrait columns to the screen edges (right column x+128 at 768, x+214 at 854) and widen only the message log. That needs new art only for these 5 files: main_textbox_back (384 -> 512/598 wide), main_roof (640x18 -> W), main_bottom_bar sub-image 4 or 6 (bank/caption, stretched), intro_bg_text 640x480 -> Wx480, and optionally main_columns_normal.
Difficulty per element:
- Roof: easy (1 blit + 3-entry table + strip Controls).
- Portrait columns: medium (1 switch + ~34 region entries + 3 combat literals + invalidate rects).
- Radar/formation: medium (3D-sprite positions + circle regions).
- Message log: wider is easy-medium; taller is medium-hard (7/11 literals).
- Bottom bar: easy-medium (7 blits + 5 tables + caption centring).
- Main menu: easy (1 background + 6 x-literals + 6 regions).
- Bottom-panel subscreens: medium-hard if the panel shape changes.
EFFORT: Prerequisite 2D canvas widening is separate (not estimated here). Main menu: 1-2 days. HUD relayout keeping the existing art, columns to the edges plus a wider log: 5-8 days. Taller log (more lines): +2-3 days. Subscreens (spell, NPC, use-item, lock/trap) that share the bottom panel: +4-7 days. New art integration (STI encode, SLF/path redirect): 2-3 days. Total about 2-4 weeks.

######## CRITIQUE
Critic review: Wizardry 8 widescreen, decomp-based options (research only, no files changed)

## 1. What I checked myself

**A. A native Windows build inside C:\dev\wiz8-ws is possible, but nothing proves it has ever been done**
- `ref\wizardry-8-decomp\CMakeLists.txt:11-14`: if the build is not an analysis build and the compiler is not MSVC, configure stops with FATAL_ERROR. Confirmed. VC6 cl counts as MSVC to CMake, so running native VC6 passes this check. clang-cl would need this block removed or WIZ8_ANALYSIS_BUILD set, but then the product targets are not created at all.
- `tests\runtime\targets.cmake:41-53`: WIZ8_RUNTIME links without /FORCE:UNRESOLVED. Confirmed. `src\wiz8\CMakeLists.txt:94`: only the comparison target WIZ8 uses /FORCE:UNRESOLVED.
- **Gap all reports missed: CI never builds WIZ8_RUNTIME.**
  - The `uv run wiz8` steps in `.github\workflows\ci.yml` are: toolchain build (129), prepare (222), check (224), lint (226), ghidra (253/255/329/587), `build match` (= WIZ8, line 321, links with FORCE:UNRESOLVED), analyze (323), `build SURRENDER` (581).
  - No `build runtime` or `runtime-test` step exists.
  - So the claim that the runnable exe links completely at commit 075cbd0 (10 Oct 2026, shallow clone) is not gated by CI.
  - Indirect evidence that it links: `tests\runtime` has about 20 semantic test files (combat, save, NPC, lock, party movement), and WIZ8_RUNTIME_TEST also needs a complete link. That is strong but unverified. The tree has 5381 `// FUNCTION: WIZ8` annotations and 0 STUBs; I did not count the retail functions to compare.
- The decomp's own run path uses a **rebuilt sr.dll** (`docs\targets\wiz8-executable.md:13-25`; it needs `wiz8 build SURRENDER`). Its default video setup is **Glide2x 800x600**, not DirectX7. Our setup (`games\work\3DVideo.CFG`) is DirectX7 at 2560x1600 through dgVoodoo2.
  - So the pairing we would use (Wiz8Runtime.exe + retail sr.dll + DX7 path + dgVoodoo) has never been exercised by upstream. Report 1's "retail sr.dll should work" is a guess.
- Toolchain facts: Tools has cmake 4.4.4 but no cmake 3.x, jom or nmake. `Tools\_downloads` has no VC6 or msvc600 archive. VC6 is not present.
- Our DLL checks the exe version (`src\exe_version.cpp`, `src\signature.cpp`, `src\game_gog124.h`). Its hooks are tied to the retail addresses and will not apply to Wiz8Runtime.exe. **No report pointed this out.**

**B. Widening the canvas is realistic in rebuilt source; patching it into the retail exe is much harder**
- Confirmed in `src\wiz8\engine_code\Video2.cpp`:
  - LockPrimarySurface is at 307 (`0x00421f70`). It returns `description.lpSurface`, not "lpSurface + lPitch" as report 3's evidence line says (cosmetic error; the design idea still holds).
  - The surface is created with `dwHeight=480`, `dwWidth=640` at 624-625, OFFSCREENPLAIN | SYSTEMMEMORY.
  - W8ColorSurface and stSurface2D are created at 640x480 at 2491-2497.
  - The full-redraw test `==0x280 && ==0x1e0` and the cell index `x/8 + (top/8)*0x50` are at 2044 and 2057.
- 41 references to g_tile_dirty_flags / g_surface_nodes / g_page_full_redraw, all in Video2.cpp. The arrays are fixed at 0x12c0 (80x60).
  - Width 856 needs 107x60 = 6420 cells, so the arrays must grow.
  - In source that is a one-line change. In a DLL patch on the retail exe it means moving .bss arrays and rewriting every reference.
- 133 width literals (640/639/0x280/0x27f) across src .c/.cpp. This matches report 4.
- Report 3 and report 4 count Video2.cpp differently (35 + about 25 hex versus 45). That is only a regex difference, but use 133 total as the planning number.

**C. Loose files override DATA.SLF. This answers report 4's blocker (high confidence).**
- `src\sgp\FileMan.cpp:227-300`: FileOpen (`0x00404C80`) first calls FileExistsNoDB and opens the file from disk. It falls back to OpenFileFromLibrary only when the file is not on disk.
- `src\sgp\STCI.cpp:32`: STI images load through FileOpen.
- So new STI art can be dropped into `games\work\Data\...` without repacking the SLF.
- Not yet tested on the game itself, but the function is annotated as matching retail.

**D. Report 4's key fact holds.** reccmp targets sha256 18a74ff6...420d2, which is our exe. Every FUNCTION/GLOBAL address is usable from our DLL right now.

## 2. Contradictions and unverified load-bearing claims

1. **Strategic contradiction.**
   - Report 3 assumes we rebuild the exe and change the source.
   - Report 4 says do not rebuild; use the decomp as an address map for version.dll.
   - Neither weighed the other. My view: the HUD relayout (report 4) is fine as a DLL patch. The canvas widening (report 3) is not, because of the dirty-grid arrays, the immediates across about 150 sites and the normalized float constants.
2. **"VC6 runs natively on Win11."** All reports treat this as a strong guess.
   - Supporting point (from my knowledge, not tested here): the LEGO Island decomp (isledecomp), which this project follows, builds with an MSVC 4.2 git tree natively on Windows CI runners.
   - Still a guess for VC6 SP5 mspdb60.dll with /PDBTYPE:SEPT on build 26300.
3. **CMake 4.4.4 with cl 12.00.** Untested. The repo pins 3.26.6, and `cmake_minimum_required(3.20)` is fine with 4.x. Plan for a portable 3.26.6 (zip of about 40 MB).
4. **Report 2: "clang-cl needs no VC6".** False in practice. Its own recommended option A still needs VC6 VC98\Include and VC98\Lib. So clang-cl does not avoid the licensing question; it only adds ABI and UB risk. Report 2's scratchpad tests (MSVC mangling, lld-link, .def import libs) are real evidence that a fallback exists.
5. **Report 1** says configure needs the jpeg-6 and unzip540 sources. True, because the top-level CMakeLists.txt adds them unconditionally (lines 26-31). The alternative is a build-tree overlay rather than editing `ref\`.
6. **Report 3** puts effort at 9-13 days for (a). That assumes a working runtime. Add a stage 0 (build plus a parity check against retail in our DX7/dgVoodoo setup) of 2-5 days, which nobody estimated.
7. **Save thumbnails.** Report 3 says keep them at 80x60 from a 640x480 source. Agreed; the SHOT chunk is 0x2588 bytes and part of the save format.

## 3. What is missing

- **Licensing decision for VC6** (archaic-msvc mirror is unlicensed, versus an owned VS6 + SP5). Only the owner can decide. Also, a rebuilt exe contains non-commercial SFI SGP code and the decomp has no license, so it cannot be redistributed. The DLL route has neither problem.
- **No test plan for retail parity** of Wiz8Runtime.exe on our setup: DX7, dgVoodoo, borderless, 2560x1600 render, Bink, Miles, save/load of existing saves.
- **Keeping our existing DLL features:** borderless, Hor+, mouse mapping. On a rebuilt exe these must move into source, or the DLL needs a second address table generated from Wiz8Runtime.map.
- **Mouse in a rebuilt wide canvas:** the output-pixel to canvas scale step (render 2560x1600 versus canvas 856x480). Report 3 noted it; it has no owner and no design.
- **Retail function count versus 5381**, to judge completeness. Not done.

## 4. Recommended path: two tracks, decided by one gate

Track A (start now, low risk, no new toolchain): use the decomp as an address map in version.dll.
- Do the HUD relayout, main menu and wider message log inside the centered 4:3 canvas the DLL already draws, extended to the screen edges where it already draws.
- Only for elements already drawn outside the 640 block: the 3D sprites for radar and formation, and the fills.
- This alone does NOT give a wider 2D canvas. Panels can only reach the edges if they are drawn as renderer-side sprites, or if the 2D surface widening is patched.

Track B (gate): get Wiz8Runtime.exe building natively with VC6. If it builds and plays at parity, do the canvas widening (report 3, "window inside a wide surface") and the HUD redesign in source. Our version.dll keeps working on the retail exe in the meantime.

**Next-session steps, in order:**
1. **Ask the owner** to choose the VC6 source (mirror at commit b0b07e29 versus own disc + vs6sp5) and to accept that a rebuilt exe cannot be distributed. Nothing in Track B can start without this.
2. If approved: put VC6 under `Tools\msvc600`, and portable cmake 3.26.6 i386 plus jom 1.1.3 under Tools (sha256 values are in `docker\msvc600\Dockerfile:61-75`). Smoke test `cl /?`, `link /?`, `lib /?` and `nmake /?` with session-only PATH, INCLUDE, LIB and TMP set in a new `Tools\vc6env.ps1`.
3. Fetch the small pinned deps (zlib-1.0.4, jpeg-6, unzip540 + zcrypt28; hashes in `config\build-inputs.yml`) into `build\deps`. Port `tools\wiz8decomp\binary\coff_archive.py` (83 lines, stdlib only) to produce `sr-assert-import.lib`.
4. Configure from a copy (for example `decomp`), not from `ref\`:
   `cmake -G "NMake Makefiles JOM" -DCMAKE_BUILD_TYPE= -DZLIB_SOURCE=... -DIJG_JPEG_SOURCE=... -DINFOZIP_SOURCE=...`
   Then build `--target WIZ8_RUNTIME`.
   - First real gate: does it link with zero unresolved symbols?
   - Then build SURRENDER too, to have the rebuilt sr.dll as a fallback.
5. Copy to a separate test folder (for example `games\runtime`, a copy of work), not over Wiz8.exe. Run with retail sr.dll on DX7 and dgVoodoo:
   - main menu, new game, load an existing save, combat, Bink intro, save/load round trip;
   - compare against retail Wiz8.exe.
6. Only after parity: implement the widening in `Video2.cpp` behind one `g_canvas_w` (768 / 856; 854 breaks the 8-pixel grid).
7. Meanwhile on Track A: a main-menu proof of concept as a loose `Data\...\intro_bg_text.sti` override (confirms point C), and patch g_regions[1..6] at `0x00620048`.

## 5. Biggest risks

1. **Wiz8Runtime may not link or may not run at parity**, because CI never builds it. Upstream runs it only under Wine/Proton with Glide2x and a rebuilt sr.dll. This is the main unknown, and it decides the whole of Track B.
2. **Licensing:** VC6 has no clean free source. A rebuilt exe contains non-commercial SFI code and unlicensed decomp code, so it is personal use only.
3. **Losing our DLL work on a rebuilt exe:** the hash and signature checks would fail. Borderless, Hor+ and mouse must be ported into source.
4. **Canvas widening risks:** pitch padding; the hard-coded 0x500 pitch in LineDraw at 4 call sites; the `game_init.cpp:64` overrun once the pointer is offset; partial 128-pixel tiles at the right edge (unverified); and the mouse scale from render pixels to canvas pixels.
5. **The HUD redesign touches all the subscreens** that share the bottom panel (spell casting, NPC dialogue, use-item, lock/trap). Report 4 put this at +4-7 days, not audited.
6. **The clang-cl fallback** (if VC6 is refused) still needs the VC6 headers. It adds UB and x87 float risk plus 2-5 days of in-game debugging, so it is not a real way around the licensing problem.

## 6. Effort (rough guess)

| Work | Days |
|---|---|
| Track B stage 0 (toolchain + link + parity) | 2-5 |
| Canvas widening (a) | 9-13 |
| Main menu | 2-3 |
| Main HUD | 8-15 |
| Subscreens | 4-7 |
| Art integration (simple, thanks to loose-file override) | 1-2 |

Track A only (DLL, centered canvas, partial edge use): main menu 1-2 days, HUD 5-8 days. It does not give the owner's goal of a truly wide 2D canvas.

Key paths:
- `C:\dev\wiz8-ws\ref\wizardry-8-decomp\CMakeLists.txt`
- `C:\dev\wiz8-ws\ref\wizardry-8-decomp\tests\runtime\targets.cmake`
- `C:\dev\wiz8-ws\ref\wizardry-8-decomp\.github\workflows\ci.yml`
- `C:\dev\wiz8-ws\ref\wizardry-8-decomp\docs\targets\wiz8-executable.md`
- `C:\dev\wiz8-ws\ref\wizardry-8-decomp\src\wiz8\engine_code\Video2.cpp`
- `C:\dev\wiz8-ws\ref\wizardry-8-decomp\src\sgp\FileMan.cpp`
- `C:\dev\wiz8-ws\ref\wizardry-8-decomp\src\sgp\STCI.cpp`
- `C:\dev\wiz8-ws\src\exe_version.cpp`
- `C:\dev\wiz8-ws\games\work\3DVideo.CFG`
