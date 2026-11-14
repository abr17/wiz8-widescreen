# Building and releasing

The package is built on Windows from PowerShell, with portable tools inside `Tools\`
(nothing is installed system-wide except Python 3 and PowerShell 7; the Linux test bench of
`scripts\linux\` also needs Docker Desktop with WSL2, [testing.md](testing.md)). The render
driver is a project of its own, which also has a Linux build for its tests (section 7).

The build, package, test and art scripts find the workspace from their own location, not from
a fixed path; paths below are relative to it. So far the workspace has only lived in a short
path without spaces or non-ASCII characters.

## 0. Repository

```powershell
git clone --recursive <repo>     # or, in an existing clone: git submodule update --init
```

The submodules are `third_party\minhook` (`version.dll` does not build without it), `decomp\`
(the game source, section 6) and `drivers\srdd_d3d11` (the render driver, section 7).

## 1. Toolchain (`Tools\`, not in git)

| Folder (must contain) | What, where from | Used by |
|---|---|---|
| `Tools\llvm-mingw` (`bin\clang.exe`) | llvm-mingw, ucrt build for x86_64 hosts, clang 23.1 — github.com/mstorsjo/llvm-mingw releases | `version.dll` and its export check (`bin\llvm-readobj.exe`), installer, the render driver's ABI check (`bin\llvm-objdump.exe`) |
| `Tools\cmake` (`bin\cmake.exe`) | CMake 4.4, Windows x64 zip — cmake.org | `version.dll`, port build |
| `Tools\msvc` (`VC\Tools\MSVC\14.44.35207`, `Windows Kits\10`) | portable MSVC 2022 + Windows SDK 10.0.26100, made by `scripts\build\toolchain\portable-msvc.py` (below) | `wiz8hy.dll`, port, w8diff, the render driver |
| `Tools\zlib\zlib-1.0.4` | zlib 1.0.4 sources (the game links this old version; upstream decomp `config\build-inputs.yml` has its source and hash) | port build |
| `Tools\git` (`cmd\git.exe`) | MinGit 2.5x — github.com/git-for-windows | everything |
| `Tools\node` (`node.exe`) | Node.js 24, Windows x64 zip — nodejs.org | `rea` |
| `Tools\jdk21` (`bin\java.exe`) | Eclipse Temurin 21 JDK zip — adoptium.net | Ghidra |
| `Tools\ghidra` (`ghidraRun.bat`) | Ghidra 12.1.4 — github.com/NationalSecurityAgency/ghidra releases | `rea` |
| `Tools\rea` | `cd Tools\rea; ..\node\npm install rea-agents@6.4` (static-analysis MCP server; set-up below) | analysis only |
| `Tools\x64dbg` (`release\x32\x32dbg.exe`) | x64dbg snapshot — x64dbg.com | debugging only |
| `Tools\dgVoodoo2` | dgVoodoo 2.8.7.5 — dege.freeweb.hu (the packages up to 1.0.2 carried its `DDraw.dll`, `D3DImm.dll` and our `dgVoodoo.conf`) | comparisons with the render driver only |

Unpack each archive so that the file in the first column exists (flatten the archive's top
folder). Then copy `scripts\build\toolchain\env.ps1` and `msvcenv.ps1` into `Tools\` and fetch
MSVC (the script writes into the current folder and asks to accept Microsoft's licence):

```powershell
cd Tools
python ..\scripts\build\toolchain\portable-msvc.py --vs 2022 --target x86 --host x64 --msvc-version 14.44 --sdk-version 26100
Remove-Item downloads -Recurse; cd ..
```

Also needed: **Python 3** (3.13 used; standard library only) and **PowerShell 7** (`pwsh`,
used by the package and test scripts) on `PATH`.

Each shell: `. .\Tools\env.ps1` (git, CMake, llvm-mingw, node, Java on `PATH` for this
session only). The MSVC scripts load `Tools\msvcenv.ps1` themselves.

### Set-up for AI agents (optional, not in git)

[CLAUDE.md](../CLAUDE.md) holds the project's rules for AI agents. What depends on the machine
or on the person stays out of git (`.gitignore`): `.mcp.json`, `.claude\` and
`CLAUDE.local.md` (personal preferences). To use the `rea` static-analysis server with Claude
Code, put a `.mcp.json` like this into the workspace root, with `<workspace>` replaced by the
full path of the clone, each backslash of it written twice as JSON needs
(`D:\\src\\wiz8-widescreen`):

```json
{
  "mcpServers": {
    "rea": {
      "command": "<workspace>\\Tools\\node\\node.exe",
      "args": ["<workspace>\\Tools\\rea\\node_modules\\rea-agents\\scripts\\rea.mjs", "--mcp"],
      "env": {
        "JAVA_HOME": "<workspace>\\Tools\\jdk21",
        "GHIDRA_INSTALL_DIR": "<workspace>\\Tools\\ghidra",
        "REA_GHIDRA_STARTUP_TIMEOUT_MS": "1800000",
        "REA_ANALYSIS_PROVIDER": "ghidra",
        "PATH": "<workspace>\\Tools\\jdk21\\bin;<workspace>\\Tools\\node;C:\\Windows\\System32;C:\\Windows"
      }
    }
  }
}
```

A `.claude\settings.json` like this keeps an agent from changing the reference copy of the
game (in Claude Code's rules a path with one leading slash starts at the workspace root, and
an `Edit` rule covers every tool that edits files):

```json
{
  "permissions": {
    "deny": ["Edit(/games/reference/**)"]
  }
}
```

## 2. Game copies (`games\`, not in git)

* `games\reference`: pristine GOG 1.2.4 install (`Wiz8.exe` SHA-256
  `18A74FF61C65B8A2D4CFA11FFCE82AD7FEF022A94EAF0C2F217E479E981420D2`). Copy the GOG folder,
  then `attrib +R /S games\reference\*`. Never modified.
* `games\work`: another copy, the main test copy. One-time setup, then the `-Install`
  switches keep the patch DLLs current:

  ```powershell
  robocopy games\reference games\work /E
  Copy-Item assets\* games\work -Recurse -Force          # wide art, FALCON.STI
  Copy-Item drivers\srdd_d3d11\out\srDD_D3D11.dll games\work\Dll   # the render driver (section 7)
  Copy-Item dist\wiz8ws.ini, dist\wiz8wide.ini games\work
  ```
* `games\ru`: like `games\work`, plus the `Data` folder of the Russian translation
  (Wizardry8_rus 1.2.6, a fan translation) copied over it; keep the GOG `Wiz8.exe`.

A fresh copy has no saves; make a party (`scripts\play\play_create.ps1`, `Start-QuickParty`)
and save, or copy your own saves into `Saves\`.

## 3. `version.dll` (proxy loader)

```powershell
.\build.ps1             # -> build\version.dll   (CMake + llvm-mingw, Release, i686)
.\build.ps1 -Install    # + copy to games\work (and dist\wiz8ws.ini if the copy has none)
.\build.ps1 -Uninstall  # remove the patch DLLs and logs from games\work (inis stay)
```

Source: `src\`. It loads the real system `version.dll`, checks `Wiz8.exe` (SHA-256 and a
code signature, `src\exe_version.cpp`, `src\signature.cpp`), reads `wiz8ws.ini`
(`src\config.cpp`), and from a hook on the game's `WinMain` loads `wiz8hy.dll`
(`src\hooks_hybrid.cpp`). The older stand-alone hooks (`src\hooks_video.cpp`,
`hooks_mouse.cpp`, `hooks_input.cpp`, `hooks_hud.cpp`, `hooks_view3d.cpp`: borderless, mouse,
Alt+Tab, centred HUD, Hor+ 3D) are still compiled in but superseded by the hybrid: they run
only with `[Hybrid] Enabled=0`, which is not supported ([hybrid.md](hybrid.md), "How it is
enabled"). `docs\history\` describes them.

The Wine part (Linux; [loader.md](loader.md), "Wine and Proton"):
`src\loader_route.cpp` (which file the DLL was loaded as, `version.dll` or the game's
`binkw32.dll`, and which copy starts the patch), `src\wine_settings.cpp` (the patch's own Wine
setting in the prefix's registry, hence the `advapi32` link; `sr.dll` imports it anyway) and
`src\wine_overrides.h` (the registry names and the rules, shared with the installer). Besides
the `version.dll` functions, `src\version.def` lists the 83 functions of RAD's `binkw32.dll`
as forwarders to `binkw32_wiz8wide.<name>`: under Wine the installer puts a copy of
`version.dll` in place of `binkw32.dll` and renames the original to `binkw32_wiz8wide.dll`.

After the link `build.ps1` checks those exports with `Tools\llvm-mingw\bin\llvm-readobj.exe
--coff-exports`: exactly 83 forwarders, each one `binkw32_wiz8wide.<name>`. Anything else stops
the build with `export check: <path>\version.dll has N forwarders (83 expected), M not starting
with binkw32_wiz8wide. (<the first wrong one>)`, and `llvm-readobj failed on <path>` when the
tool fails. An older lld (Ubuntu's LLVM 18, for one) writes `_binkw32_wiz8wide.<name>` there:
the DLL builds, but under Wine there is no DLL of that name and the game dies at its first
video. So build `version.dll` with llvm-mingw only. `make-hybrid-package.ps1` repeats the
check before it packages `build\version.dll`, with the function `Assert-BinkForwarders` of
`scripts\build\forwarders.ps1` (`<path>\build\version.dll has N Bink forwarders (83 expected),
...: rebuild it with build.ps1`).

## 4. `wiz8hy.dll` (the hybrid)

```powershell
powershell -File scripts\build\build-decomp.ps1             # once before the first hybrid build (section 5)
powershell -File scripts\hybrid\build_hybrid.ps1            # -> build\hybrid\wiz8hy.dll, wiz8hy_hooks.txt, wiz8hy.map
powershell -File scripts\hybrid\build_hybrid.ps1 -Install   # + copy both files to games\work
```

The source is `decomp\` (the game code with our changes, [decomp-fork.md](decomp-fork.md)).
`scripts\hybrid\transplant_wide.json` (the default config) lists which source files are
compiled (`units`, `auto_units`) and which original functions are replaced (`transplant`,
290 addresses in 1.0.3, 289 in 1.0.2, 287 in 1.0.0-1.0.1). Everything else in the DLL is bound
to the original exe's own functions and data. Needs `Tools\msvc` and `build\vc2022\*.lib` from the port build.
Details: [hybrid.md](hybrid.md).

### Changing game code

1. Find the function in `decomp\src` (table "Where the code is" in
   [decomp-fork.md](decomp-fork.md)). Every original function has a
   `// FUNCTION: WIZ8 0x<address>` annotation; keep it.
2. Edit, commit in `decomp\`.
3. If the function's address is not yet in `transplant` in `transplant_wide.json`, add it
   (`"0x00xxxxxx": "name"`). **A change to a function that is not listed has no effect on
   `wiz8hy.dll`**: the game keeps running the original function. When the change carries a
   "Mod" comment, as the fork's edits do, the build stops and names the function (the Mod
   check, [hybrid.md](hybrid.md), "How to change a game function"); without the comment the
   build succeeds and says nothing.
   New functions that have no original address are pulled in automatically when a listed
   function calls them. A call to an `sr.dll` function that the game itself never imported
   also needs that function's name in `decomp\src\wiz8\imports\sr.def` (its last block holds
   such names, `srCamera::sGetClassName()` for one). After any change there run
   `build-decomp.ps1` before `build_hybrid.ps1`: the hybrid links `build\vc2022\wiz8_sr.lib`,
   which the port build makes from that file. With a stale lib the hybrid cannot bind the
   call: the link fails, or the build pulls in `sr.dll`'s own source for it (`auto-added
   units:` lists `surrender\gerd.cpp`); neither is right.
   Original variables keep their `// GLOBAL: WIZ8 0x<address>` annotation directly above the
   declaration: the build binds them to the original's variable and fails ("binding guard")
   when one would get a second copy inside the DLL ([hybrid.md](hybrid.md), "Game variables").
4. Build with `-Install`, run the game, check `wiz8ws.log` (`wiz8hy.dll: N functions
   replaced`, N = number of `transplant` entries) and test ([testing.md](testing.md)).
5. Changes in `src\` (the loader) need only `.\build.ps1 -Install`.

## 5. `Wiz8Runtime.exe` (internal port, not shipped)

```powershell
powershell -File scripts\build\build-decomp.ps1          # incremental
powershell -File scripts\build\build-decomp.ps1 -Clean   # from scratch
```

Output `build\vc2022\Wiz8Runtime.exe` (+ `.map`, + the `.lib` files the hybrid links
against). Log: `build\vc2022\build.log`. It runs next to the original `sr.dll` and game data;
used for debugging, for the w8diff harness ([w8diff.md](w8diff.md)) and by older play-test
helpers. Background: [decomp-port.md](decomp-port.md).

## 6. `decomp\` (game source, git submodule)

The git submodule [abr17/wizardry-8-decomp](https://github.com/abr17/wizardry-8-decomp), a
fork of the public decompilation: branch `widescreen`, tags `wiz8-widescreen-<version>` are the
sources of the released `wiz8hy.dll` (one per release). `git submodule update --init` fetches it. See
[decomp-fork.md](decomp-fork.md) for what is in it and how it relates to upstream. Its code is
not under this repository's MIT licence (upstream has no licence file; `src/sgp` is under
Strategy First's non-commercial source licence).

To change game code: commit in `decomp\` on `widescreen`, push the fork, then commit the new
submodule pointer here. For a release, tag the fork (`wiz8-widescreen-<version>`).

## 7. Installer and package

```powershell
pwsh -File tools_src\setup\build.ps1                 # -> build\setup\Wiz8WideSetup.exe
pwsh -File scripts\build\make-hybrid-package.ps1     # -> build\package\Wiz8Widescreen\ + .zip
```

The package script builds the installer, then assembles `files\` from `build\version.dll`,
`build\hybrid\wiz8hy.dll` + `wiz8hy_hooks.txt`, the render driver as `Dll\srDD_D3D11.dll`,
`dist\wiz8ws.ini`, `dist\wiz8wide.ini` and everything in `assets\` (dgVoodoo files still lying
there are left out), and adds `dist\README_*.txt`, `LICENSE` and `THIRD-PARTY-NOTICES.txt` (the
licence of MinHook, which `version.dll` contains, taken unchanged from the submodule's own
licence file; without that file the script stops). The folder and the zip of an earlier run are
deleted first.

The render driver, `srDD_D3D11.dll`, is a project of its own with its own version and releases
(repository [abr17/wiz8-d3d11](https://github.com/abr17/wiz8-d3d11)); the package only carries
it. Here it is the git submodule `drivers\srdd_d3d11`
([its README](../drivers/srdd_d3d11/README.md)). It has two builds of the
same sources: the release build, the DLL that ships, which has the driver's fast path only, and
the reference build, which also has the driver's exact paths and is the one its tests compare
with. The DLL that ships is built with MSVC, from an x86 developer shell (`cl.exe` on PATH):

```powershell
powershell -File drivers\srdd_d3d11\build.ps1              # release build   -> drivers\srdd_d3d11\out\srDD_D3D11.dll
powershell -File drivers\srdd_d3d11\build.ps1 -Reference   # reference build -> drivers\srdd_d3d11\out\ref\srDD_D3D11.dll
```

`build.ps1` compiles the shaders into the DLL (`fxc.exe` of the Windows SDK), so that the driver
needs no `d3dcompiler_47.dll` on a player's Windows (`-NoFxc` leaves them to run-time
compilation; the package scripts refuse such a DLL). It needs Python 3 for the driver's tools,
found as `py -3`, `python` or `python3` (`drivers\srdd_d3d11\tools\find_python.ps1`), and git, on
PATH or in `Tools\git\cmd`, which tells the build which commit the sources are at. It also needs
`llvm-objdump`, on PATH or named by `LLVM_OBJDUMP`, for the check of the driver's ABI (the order
of the 43 methods the game calls, and the bytes each returns with): here that is
`Tools\llvm-mingw\bin\llvm-objdump.exe`, which `Tools\env.ps1` puts on PATH and
`Tools\msvcenv.ps1` names in `LLVM_OBJDUMP`. Without it the build warns that the ABI of class
Driver IS NOT CHECKED and goes on, its build record says `abi: not checked`, and the package
scripts refuse the DLL; with it the build prints `check_abi: ok - 43 slots in order, ...`. Beside
the DLL it writes the build record `srDD_D3D11.build.txt`, which the package scripts demand, and
the link map `srDD_D3D11.map` (kept with a release, not packaged). `sh drivers/srdd_d3d11/build.sh`
(clang-cl, under Linux) makes the same two builds, the reference build with `--reference`; the
driver's Linux test suites need both (`sh build.sh` and `sh build.sh --reference` in the
driver's folder). The driver's version is in `drivers\srdd_d3d11\src\version.h` and stands in
the first line of its log (`srDD_D3D11 1.0.0`, with `(reference build)` after it in the
reference build); `VERSION` of this repository does not reach it. Requirements, both builds and
the tests: [drivers/srdd_d3d11/docs/testing.md](../drivers/srdd_d3d11/docs/testing.md).

The package script takes `drivers\srdd_d3d11\out\srDD_D3D11.dll` or the file given with
`-Driver`, and asks the driver's own checker, `drivers\srdd_d3d11\tools\check_dll.py --package`
(Python 3 and git, found as above), whether it may go into a package. The checker refuses the
DLL unless it is a 32-bit DLL with the driver's exports and no import outside the driver's lists,
the release build, of the version in the driver's `src\version.h`, with exactly the release
build's shaders embedded, compiled from the driver's present sources, and with a build record
that belongs to this very file, says that the build checked the driver's ABI (`abi: checked`) and
names the driver's present commit, without uncommitted changes. The script then stops with the
checker's reason. `-AllowModifiedDriver` makes a trial package with a driver built from
uncommitted changes or from a commit that is not known; it does not excuse a build without the
ABI check.

The installer
(`tools_src\setup\setup.cpp`, compiled together with `wine_find.cpp`, which finds the game
under Wine; both include `src\wine_overrides.h`) finds GOG/Steam installs, warns on an unknown
exe, refuses to overwrite another mod's `version.dll`, refuses a package whose `files\` lacks
`version.dll`, `wiz8hy.dll`, `wiz8hy_hooks.txt`, `wiz8ws.ini` or `Dll\srDD_D3D11.dll` (a
partial unpack, a file taken by an antivirus: the message names the file, and nothing is
changed), backs up replaced files to
`Wiz8Wide.backup\` and restores them on uninstall. It records its version (from `VERSION`) in
`Wiz8Wide.installed.txt` and, over an older version, offers "Update X -> Y" (over a newer one
"Roll back X -> Y", after a question): a quiet uninstall of the old files, then the install,
keeping `wiz8wide.ini` and `wiz8ws.ini`'s `Enabled=0`. Its "Diagnostics mode (for bug reports)"
checkbox sets `[Debug] Diagnostics` of `wiz8ws.ini`: off on a fresh install, over an install it
shows the current value and the install writes whatever the player leaves it at (without the
window: `--install "<folder>" [--diagnostics|--no-diagnostics]`, neither = keep). So there is one
package, with `Diagnostics=0` in `files\wiz8ws.ini`. Its "Report a problem..." button (without
the window: `--report "<folder>" ["<file.zip>"]`) packs the logs, settings and crash dumps of
the game folder and a summary of the system into one zip on the Desktop and offers the bug
report page; the zip is written by `zip_writer.h`, with no library ([loader.md](loader.md),
"The report file"). Nothing is changed while a file of the
folder is in use (the game running). Under Wine (Linux) it also finds the game in
the Linux launchers (a Steam non-Steam game, Heroic, Lutris), puts a copy of `version.dll` in
place of the game's original `binkw32.dll` so that the patch starts without a launch option,
tells Wine to load the patch's `version.dll` and to keep its own `ddraw.dll` (a dgVoodoo
`DDraw.dll` left in the game folder crashes under Wine) for `Wiz8.exe`, but only in a prefix the game may run in, never
writes Wine's `EmulateModeset`, and takes all that back on uninstall ([loader.md](loader.md),
"Wine and Proton"). A full uninstall also removes the logs the patch wrote,
including `Wiz8Logs\` of the diagnostics ([loader.md](loader.md)); an update keeps `Wiz8Logs\`. The manifest rules for future versions (keep it readable
by older installers; `*format=2` when uninstall must change) are in the comment at the top of
`setup.cpp`.

`assets\` holds the game-derived art (121 wide `.STI`, 5 of them the Options art of the
experimental category), `Data\OPTIONS\FALCON.STI` (the exit screen, which the Russian
translation's data lacks), the animated menu video `Data\WIDE\MENU_ANIM.AVI`
([experimental.md](experimental.md)), laid out like the game folder. It is not in git (it is made from the game's art). Fill it from a released zip
(from the release page, or `release\` locally), 1.0.2 or later. Older zips do not give a
complete `assets\`: the 1.0.1 zip lacks 8 files (`Data\WIDE\STRETCH\S0F9_0_4_768.STI` and
`S0F9_0_4_856.STI`, the 5 experimental Options `.STI` and `MENU_ANIM.AVI`) and has the old
AI-painted `Data\WIDE\WIDEFRAME_768.STI` and `WIDEFRAME_856.STI` (1.0.2 has the native marble
ones). The package script stops only when one of the 6 experimental files is missing:

```powershell
pwsh -File scripts\build\import-release.ps1 -Zip Wiz8Widescreen-1.0.2.zip              # assets\ only
pwsh -File scripts\build\import-release.ps1 -Zip Wiz8Widescreen-1.0.2.zip -Binaries    # + prebuilt DLLs
```

It copies `files\Data\` into `assets\` (nothing else: the dgVoodoo files of the zips up to 1.0.2
are not used any more) and never overwrites a file that
differs unless `-Force` is given. `-Binaries` also puts the release's `version.dll`,
`wiz8hy.dll` + `wiz8hy_hooks.txt` into `build\`, for working on the installer, the art or the
package without building the game code. Scripts that regenerate some of the art:
[scripts/README.md](../scripts/README.md).

## 8. Release checklist

1. Set the version in `VERSION` before building (the installer, `version.dll`'s log line,
   the main menu line drawn by `wiz8hy.dll` and the zip name take it from there) and "Current
   release" in `README.md`. The render driver's version is not set here: it is in
   `drivers\srdd_d3d11\src\version.h` and changes with a release of the driver.
2. Build the render driver's release build with `powershell -File drivers\srdd_d3d11\build.ps1`
   (MSVC, shaders embedded, without `-Reference`: section 7) from a commit of the driver's
   repository with no uncommitted changes, and run the driver's checks on that very DLL; the
   commands are in [drivers/srdd_d3d11/docs/testing.md](../drivers/srdd_d3d11/docs/testing.md).
   The file that passed is the one that goes into the package, with the build record beside it:
   do not build it again afterwards.
3. Build the other pieces (sections 3, 4, 5 as needed) and the package (section 7).
4. Test on clean copies of the GOG and Steam game ([testing.md](testing.md): install, play
   through the screens, uninstall restores the folder byte for byte). Test the installer with
   `pwsh -File tools_src\setup\tests\test_all.ps1 -PreviousZip
   release\Wiz8Widescreen-<previous>.zip`: update from the previous release, the game running,
   rollback, a failed copy, a manual install, uninstall byte for byte, the report file, an
   incomplete package.
5. Verify the package against the previous release: unzip both and compare the file lists
   and the hashes of the non-built files (`Data\`, READMEs); the hooks count in
   `wiz8hy_hooks.txt` should match `transplant_wide.json`.
6. Write `docs\releases\<version>.md`: the contents, the SHA-256 of the zip, of `version.dll`,
   `wiz8hy.dll` and `Dll\srDD_D3D11.dll`, the render driver's version, what was tested.
7. Commit and push the render driver's repository and `decomp\`, and tag `decomp\`
   (`git -C decomp tag -a wiz8-widescreen-<version>`). Commit both submodule pointers and
   everything else here, then `git tag -a v<version>`; push the repositories with their tags.
8. Copy `build\package\Wiz8Widescreen-<version>.zip` (it goes on the release page) to `release\`
   and make it read-only. `version.dll`, `wiz8hy.dll` and the installer are not byte-reproducible
   (their linkers write the time of the build into the file), and the zip stores the time of
   every file in it, so this copy is the reference for what was published. Only the render
   driver's DLL is the same byte for byte from the same sources and compiler (it is linked with
   `/Brepro`).
