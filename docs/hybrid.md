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
  (289 of them in 1.0.2, 287 in 1.0.0-1.0.1);
* `dll_owned_globals` - original variables that deliberately live in the DLL (the enlarged
  arrays of the wide canvas), each with the reason (`"name": "reason"`); see "Game variables" below;
* `glue` - glue code.

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
6. The DLL, `wiz8hy_hooks.txt` and the map are linked and written into `build\hybrid\staging\`
   (same file names). The binding guard (next section) checks them there; only when every check
   passes are they moved into `build\hybrid\` (map, hooks, DLL last; copies of the old three
   are kept in `staging\last-good\` first, and a move that fails puts back the files it already
   replaced, so a locked or read-only target never leaves a mixed pair). Every build writes
   `build\hybrid\GUARD_FAILED` when it starts, and only that move removes it. So whatever stops a
   build (a guard error, a compile, link or trap error, an interruption), nothing replaces the
   last good pair, the file stays with the reason (the guard's errors, or "The build stopped:
   ..."), and `-Install` copies nothing. `scripts\build\make-hybrid-package.ps1` and
   `scripts\hybrid\try_hybrid.ps1` refuse to run while that file exists (the pair in
   `build\hybrid` is older than the sources). The next build that passes removes it, and so does
   `scripts\build\import-release.ps1 -Binaries`, which installs a released pair (and deletes the
   local build's `wiz8hy.map`: a release has none, and the old map would make `symbolize.py`
   name the released DLL's addresses wrongly).

## Game variables: the binding rule and the guard

**Rule.** A variable that exists in the original exists once, at its address in Wiz8.exe. Its
`// GLOBAL: WIZ8 0x<address>` annotation makes the build bind it there, so the DLL's code reads
and writes the original's variable. It must never get its own storage in the DLL: the original
code would keep using the address in the exe, the DLL code its private copy, and the two halves
of the game would see different values. That hung the party-death screen in 1.0.0-1.0.1:
`g_fade_callback` was declared `void (*g_fade_callback)(void);`, the old scanner read no name
from it, the replaced `BeginScreenFade` wrote a copy in the DLL and the original
`UpdateScreenFade` read the exe's variable, which stayed 0.

**How the name is found.** `scan_annotations` (`scripts\w8diff\w8diff\symbols.py`) reads the
declaration right below the annotation; it may span lines, comments and a `// STRING:`
annotation in between are skipped. One variable per declaration in these forms: `T x;`,
`T x = v;`, arrays, function pointers `void (*x)(void)` and arrays of them
`void (*x[16])(void) = {...}`, constructor arguments `W8Vector<T*> x(5);`, `T x{...}`,
templates (also with comparisons in their arguments, `Foo<(1 < 2)> x;`), `__declspec(...)`,
`A::x`, an all-caps name after a type (`static INT32 MAX_X;`). When the name is not certain the
scanner returns none and the build fails instead of binding a wrong name: several declarators
(`int a, b;`, `static INT32 giX, giY = 0;`), a type defined in the declaration
(`struct S { int a; } x;`, also `enum` and `union`: not `S`) and a macro after the name, i.e.
an all-caps word after a type and a name (`int x WIZ8_ALIGNED;`, `int x ALIGN(16);`: not
`WIZ8_ALIGNED`/`ALIGN`) or a macro with arguments that looks like one
(`int x WIZ8_ALIGN(16);`). Split such a declaration so that the annotation sits right above a
single plain one. GLOBAL annotations belong only in `.c`/`.cpp` files, above the definition (a
header or `.inc` file is an error: the catch-all below sees only compiled files).

Names carry their scope, as in the DLL's decorated names. A variable inside a named namespace
reads as `ns::x` (`namespace ns { int x; }`; an anonymous namespace adds nothing). A static
member is annotated on its definition outside the class, `int Owner::s_member;`
(`Owner::s_member`); an annotation on the declaration inside the class body is an error. The
scanner follows the braces of the file for this (comments, literals and preprocessor lines
skipped); in a file whose braces do not balance (a preprocessor branch with braces of its own)
it knows no scopes, and the guard's checks after compiling and linking catch a missing scope.
On the DLL side the variable's name is read from its decorated name (`?x@ns@@3...` is `ns::x`),
not from undname's text; static members of class templates (`?s@?$Tmpl@H@@2HA`) read as
`Tmpl::s`, like the annotations (template arguments dropped).

* Function-local static: keep the annotation inside the function, indented, right above the
  `static` line. It is bound by name plus the enclosing function, like file-scope statics
  through a `__w8r_<address>` symbol. The enclosing function comes from the nearest
  `// FUNCTION` annotation above the function's header (its signature may span lines), or
  from the header itself, skipping keywords (`__declspec(naked) void F()` is `F`, an unindented
  `if (` is not a function) and a template head on the same line
  (`template <class T> void Tmpl(T x)` is `Tmpl`); an operator reads as
  `Owner& Owner::operator=(...)` -> `Owner::operator=`, and template arguments of the class
  are dropped (`Foo<T>::Get` is `Foo::Get`). On the DLL side every local static is recognised
  by its scope marker (`?x@?1??...`), also in constructors (`?x@?1???0Owner@@QAE@XZ@4HA` is in
  `Owner::Owner`), destructors, operators (`??4` is `operator=`, `??H` `operator+`, `??R`
  `operator()`, `??_U` `operator new[]`, ...), template functions and anonymous namespaces. A
  local static of a function defined inside a class body gets no enclosing function from the
  scanner and cannot be bound (the guard fails): define the function outside the class.
* A variable that a system header defines (the DirectDraw GUIDs): the annotation, then a
  comment line with only its name, then an empty line:
  `// GLOBAL: WIZ8 0x005ebb78` / `// IID_IDirectDraw2`. Only GUID names (`IID_`, `CLSID_`,
  `GUID_`) are accepted there; any other one-word comment in that shape is an error.
* `python -I scripts\w8diff\w8diff\symbols.py --selftest` checks examples of every form,
  including the ones that must fail, and the scopes (namespace, in-class declaration, operator
  and template local statics); `python -I scripts\hybrid\build_hybrid.py --selftest` adds the
  guard's own logic (function extents, publishing and `GUARD_FAILED`, the catch-all and the
  scope checks below, on generated object files and a generated map). The build runs both
  first.

**The guard** (`check_annotations`, `check_object_names`, `check_bindings`,
`check_owned_users` in `build_hybrid.py`), every build:

1. Before compiling: a `// GLOBAL` annotation with no certain variable name is an error, so are
   an annotation in a header or `.inc` file and one on a declaration inside a class body;
   `dll_owned_globals` must give a reason for each name, and each name needs exactly one
   annotation.
2. After compiling, the catch-all for a misread declaration: every non-const `// GLOBAL` name
   of a compiled source file must be a variable that file's object file (as compiled) defines,
   with the same qualified name and the same scope (outside any function, or a local static of
   the same function). A name that is not defined there is an error: `int x WIZ8_ALIGNED;` read
   as `WIZ8_ALIGNED`, `extern int g_other; int g_x;` read as `g_other` (the object only refers
   to it), `g_x` when the object has `ns::g_x` or `Owner::g_x` (a scope the scanner missed).
   Only the comment-only GUID form may be a reference. Const objects are skipped: the compiler
   may fold them into their users.
3. After linking, from the staged `wiz8hy.map`: an annotated variable that has storage in the
   DLL (`.data`/`.bss`/`.rdata` of one of our object files) instead of an `<absolute>` symbol at
   its address is an error, unless `dll_owned_globals` lists it. So is a variable bound to an
   address other than its annotation's. For a local static the enclosing function is ignored
   here (either side may have misread it): a DLL local static with the name of an annotated
   variable of its file fails loudly instead of being skipped. A DLL variable whose name ends
   like an annotated one but whose scope differs (`ns::g_x` vs an annotation read as `g_x`, or
   the other way round; same file first) is an error too: nothing could bind it.
4. For every `dll_owned_globals` array: every original function that uses the original array
   (found from the exe's base relocations) must be transplanted, or dead in the hybrid: the DLL
   has no live stub for it, no pointer to it is stored in the exe, and every direct call or
   jump to it comes from a transplanted function. A use or a call is attributed to a function
   only inside that function's real extent (`RetailCode`: from its `// FUNCTION` start, the
   code reachable through fall-through, jumps and switch tables, up to the next annotated
   start; llvm-objdump from `Tools\llvm-mingw` decodes it). Code after the extent belongs to
   no annotated function: compiler-generated dynamic initializers and atexit destructors
   (0x00482250, 0x00482270), scalar deleting destructors, thunks, library code. A use there is
   an error ("unknown retail user at 0x..."), and so is a call from there to a function that
   uses the array: nothing shows that code is dead. The extents were checked against Ghidra
   for every function that touches the two arrays today. The log prints the result; today the
   only dead user is `ReleaseSurfaceNode` 0x00425950 (its callers are all transplanted, the DLL
   has its own inlined copy).

**Declaring variables in `decomp\`.** Keep the annotation directly above the declaration. A
variable that must really live in the DLL (an array enlarged for the wide canvas) goes into
`dll_owned_globals` with the reason, and every original function that touches the original
array has to be transplanted (the guard checks it). The guard knows only annotated variables:
an original variable without a `// GLOBAL` annotation that the DLL defines itself is not
checked.

The 2026-10-22 sweep (scripts and notes in `build\tmp\binding-audit\`) found, besides
`g_fade_callback`, nine original variables with a private copy in the DLL. Only one was used
by both halves: `Reenter`, the re-entry guard of the SGP shutdown, which the DLL's
`ShutdownStandardGamingPlatform` (window closed: X button, Alt+F4) and the original `SGPExit`
must share so the shutdown runs once. It had no visible effect, because the original game
crashes earlier in that exit path. All nine are bound now (`fRestore`, `fResizing`,
`iLastClock`, `Reenter`, `g_message_box_callback`, `g_automap_button_callbacks`,
`g_environment_lights`, `IID_IDirectDraw2`, `IID_IDirectDrawSurface2`). The original's values
match what the copies held: the automap button table points at the same 16 functions, the
GUIDs are byte-identical, the rest start at zero, and no DLL code uses
`g_environment_lights`.

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
   the "Video" pages in the game options (view distance on page 1, display mode and resolution on page 2, the frame rate limit on page 3). Log: `wiz8wide.log`.

Trial run: `powershell -File scripts\hybrid\try_hybrid.ps1 [-Save "444"] [-Off]`.

## How to change a game function

Step by step (in English) - [building.md](building.md), "Changing game code". The key point: a change to a
function in `decomp\` gets into `wiz8hy.dll` only if its address is in `transplant` in
`transplant_wide.json`; otherwise the build succeeds, but the game keeps running the original.

## History

First trial (2026-10-13): 9 draw-distance functions + the frame limit. Then everything widescreen from the port
was moved into the hybrid ([wide-canvas.md](wide-canvas.md)), and it became
the released product instead of `Wiz8Runtime.exe`.
