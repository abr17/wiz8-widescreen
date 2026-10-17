# Building and releasing

Everything is built on Windows from PowerShell, with portable tools inside `Tools\`
(nothing is installed system-wide except Python 3 and PowerShell 7). The workspace must be
at `C:\dev\wiz8-ws`: several scripts, `Tools\env.ps1` users and `.mcp.json` use that path.
Paths below are relative to it.

## 0. Repository

```powershell
git clone --recursive <repo> C:\dev\wiz8-ws     # or, in an existing clone: git submodule update --init
```

`third_party\minhook` is a submodule and `version.dll` does not build without it.

## 1. Toolchain (`Tools\`, not in git)

| Folder (must contain) | What, where from | Used by |
|---|---|---|
| `Tools\llvm-mingw` (`bin\clang.exe`) | llvm-mingw, ucrt build for x86_64 hosts, clang 23.1 — github.com/mstorsjo/llvm-mingw releases | `version.dll`, installer |
| `Tools\cmake` (`bin\cmake.exe`) | CMake 4.4, Windows x64 zip — cmake.org | `version.dll`, port build |
| `Tools\msvc` (`VC\Tools\MSVC\14.44.35207`, `Windows Kits\10`) | portable MSVC 2022 + Windows SDK 10.0.26100, made by `scripts\build\toolchain\portable-msvc.py` (below) | `wiz8hy.dll`, port, w8diff |
| `Tools\zlib\zlib-1.0.4` | zlib 1.0.4 sources (the game links this old version; upstream decomp `config\build-inputs.yml` has its source and hash) | port build |
| `Tools\git` (`cmd\git.exe`) | MinGit 2.5x — github.com/git-for-windows | everything |
| `Tools\node` (`node.exe`) | Node.js 24, Windows x64 zip — nodejs.org | `rea` |
| `Tools\jdk21` (`bin\java.exe`) | Eclipse Temurin 21 JDK zip — adoptium.net | Ghidra |
| `Tools\ghidra` (`ghidraRun.bat`) | Ghidra 12.1.4 — github.com/NationalSecurityAgency/ghidra releases | `rea` |
| `Tools\rea` | `cd Tools\rea; ..\node\npm install rea-agents@6.4` (static-analysis MCP server, `.mcp.json`) | analysis only |
| `Tools\x64dbg` (`release\x32\x32dbg.exe`) | x64dbg snapshot — x64dbg.com | debugging only |
| `Tools\dgVoodoo2` | dgVoodoo 2.8.7.5 — dege.freeweb.hu; its `DDraw.dll`, `D3DImm.dll` and our `dgVoodoo.conf` are in `assets\` | reference |

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

## 2. Game copies (`games\`, not in git)

* `games\reference`: pristine GOG 1.2.4 install (`Wiz8.exe` SHA-256
  `18A74FF61C65B8A2D4CFA11FFCE82AD7FEF022A94EAF0C2F217E479E981420D2`). Copy the GOG folder,
  then `attrib +R /S games\reference\*`. Never modified (Claude settings also deny writes).
* `games\work`: another copy, the main test copy. One-time setup, then the `-Install`
  switches keep the patch DLLs current:

  ```powershell
  robocopy games\reference games\work /E
  Copy-Item assets\* games\work -Recurse -Force          # wide art, FALCON.STI, dgVoodoo
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
(`src\hooks_hybrid.cpp`). The older stand-alone hooks (`src\hooks_*.cpp`: borderless,
centred HUD, Hor+ 3D) are still compiled in but superseded by the hybrid; `docs\history\`
tells how they came about.

## 4. `wiz8hy.dll` (the hybrid)

```powershell
powershell -File scripts\build\build-decomp.ps1             # once before the first hybrid build (section 5)
powershell -File scripts\hybrid\build_hybrid.ps1            # -> build\hybrid\wiz8hy.dll, wiz8hy_hooks.txt, wiz8hy.map
powershell -File scripts\hybrid\build_hybrid.ps1 -Install   # + copy both files to games\work
```

The source is `decomp\` (the game code with our changes, [decomp-fork.md](decomp-fork.md)).
`scripts\hybrid\transplant_wide.json` (the default config) lists which source files are
compiled (`units`, `auto_units`) and which original functions are replaced (`transplant`,
287 addresses in 1.0.0). Everything else in the DLL is bound to the original exe's own
functions and data. Needs `Tools\msvc` and `build\vc2022\*.lib` from the port build.
Details: [hybrid.md](hybrid.md) (Russian).

### Changing game code

1. Find the function in `decomp\src` (table "Where the code is" in
   [decomp-fork.md](decomp-fork.md)). Every original function has a
   `// FUNCTION: WIZ8 0x<address>` annotation; keep it.
2. Edit, commit in `decomp\`.
3. If the function's address is not yet in `transplant` in `transplant_wide.json`, add it
   (`"0x00xxxxxx": "name"`). **A change to a function that is not listed has no effect on
   `wiz8hy.dll`**: the build succeeds and the game keeps running the original function.
   New functions that have no original address are pulled in automatically when a listed
   function calls them.
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

## 6. `decomp\` (game source, not in git)

A separate git repository with its full history; tag `1.0.0` is the release source. See
[decomp-fork.md](decomp-fork.md) for what is in it and how it relates to upstream. Our
changes alone are kept as `patches\decomp-msvc2022.patch`, which is **not** in the public
repository (it contains code of the unlicensed decompilation; the folder is gitignored and
kept locally). Regenerate it whenever `decomp\` changes for a release:

```powershell
git -C decomp diff --binary --output=..\patches\decomp-msvc2022.patch 720e1d8 <decomp tag>
```

## 7. Installer and package

```powershell
pwsh -File tools_src\setup\build.ps1                 # -> build\setup\Wiz8WideSetup.exe
pwsh -File scripts\build\make-hybrid-package.ps1     # -> build\package\Wiz8Widescreen\ + .zip
```

The package script builds the installer, then assembles `files\` from `build\version.dll`,
`build\hybrid\wiz8hy.dll` + `wiz8hy_hooks.txt`, `dist\wiz8ws.ini`, `dist\wiz8wide.ini` and
everything in `assets\`, and adds `dist\README_*.txt`. The installer
(`tools_src\setup\setup.cpp`) finds GOG/Steam installs, warns on an unknown exe, refuses to
overwrite another mod's `version.dll`, backs up replaced files to `Wiz8Wide.backup\` and
restores them on uninstall.

`assets\` holds the game-derived art (114 wide `.STI`), `Data\OPTIONS\FALCON.STI` (the exit
screen, which the Russian translation's data lacks) and the dgVoodoo files, laid out like the
game folder. It is not in git. If it is ever lost, restore it from a released zip in
`release\`: copy only `files\Data\` and `files\DDraw.dll`, `D3DImm.dll`, `dgVoodoo.conf`
(the DLLs and inis in `files\` are build outputs and would be stale). Scripts that regenerate
some of the art: [scripts/README.md](../scripts/README.md).

## 8. Release checklist

1. Fix, build all pieces (sections 3, 4, 5 as needed, 7), test on clean copies of the GOG
   and Steam game ([testing.md](testing.md): install, play through the screens, uninstall
   restores the folder byte for byte).
2. Verify the package against the previous release: unzip both and compare the file lists
   and the hashes of the non-built files (`Data\`, dgVoodoo, READMEs); the hooks count in
   `wiz8hy_hooks.txt` should match `transplant_wide.json`.
3. Update the version in `tools_src\setup\setup.manifest` and "Current release" in
   `README.md`; write `docs\releases\<version>.md` (contents, SHA-256 of the zip,
   `version.dll`, `wiz8hy.dll`, what was tested).
4. Tag `decomp\` (`git -C decomp tag -a <version>`), regenerate the patch from that tag
   (section 6), commit everything here, then `git tag -a <version>`.
5. Copy `build\package\Wiz8Widescreen.zip` to `release\Wiz8Widescreen-<version>.zip` and
   make it read-only. Builds are not byte-reproducible (timestamps), so this copy is the
   reference for what was published.
