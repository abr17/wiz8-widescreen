# Wizardry 8: native widescreen + undistorted HUD + borderless

> **History.** This document describes an early stage of the project and may differ from the released patch 1.0.0 (the hybrid, see [docs/hybrid.md](../hybrid.md) and [README](../../README.md)). It is kept to show how we arrived at the current solution. Paths like `C:\Games`, `C:\Tools`, Visual Studio and the dinput8/ddraw architecture were not used: everything lives inside `C:\dev\wiz8-ws`, and the tools are portable.

Work spec for Claude Code on a local machine (Windows).
Goal: play Wizardry 8 at 16:9 / 16:10 / 21:9 so that the 3D is Hor+, the interface is not stretched, and the game runs reliably in borderless windowed mode on Windows 10/11.

> **How to use this file.** First set up the environment per section 9. Then put this file in the project working folder (for example `C:\dev\wiz8-ws\SPEC.md`) and tell the local Claude: "We work from SPEC.md, starting with Phase 0. After each phase, stop and show me the verification result". Phases go strictly in order; each one ends with a verifiable result.

---

## 0. What to understand before starting (honestly)

1. **"Source code" is not achievable and not needed.** A decompiler (Ghidra/IDA) produces pseudo-C: no variable or function names, no structures, sometimes wrong types. It cannot simply be rebuilt into a working exe. It is a map for navigation, not source code. Rebuilding the whole game from the decompilation is a multi-year project (that is how the Mario 64 / Zelda decomp projects were done, by teams of enthusiasts).
2. **The real path: a DLL patch on top of the original exe.** We write a small DLL in C/C++ that is loaded along with the game and replaces behavior at a few points (hooks). Reverse engineering is needed to find these points: where the HUD layout is computed, where the window is created, where the 3D viewport is set.
3. **3D has already been solved by others.** There is "Wizardry 8 Extender" (`srVP_Wiz8Extender.dll`, Hor+ in DirectX7 mode, 32-bit) and Fan Patch 1.28 (authors from old-games.ru / VK "Cosmic Forge", automatic FOV). The new work is the **HUD** and **borderless**.
4. **Scope.** Borderless: days. Non-stretched HUD: from a few weeks to a couple of months of evenings, and most of it is research, not code. With AI this is realistic, but the AI will make mistakes interpreting pseudocode, so every hypothesis is verified in the debugger.
5. **Legal.** We work only with our own legally purchased copy (GOG/Steam). We may distribute our own DLL and instructions; we do not distribute a modified exe or game files. We do not touch SafeDisc/DRM (the digital versions do not have it anyway).

### Why the HUD is stretched (hypothesis, verify in Phase 2)
The game draws the 2D interface in "virtual" 4:3 coordinates (probably 800×600 or 640×480) and scales them to the screen **separately in X and Y** (`sx = W/800`, `sy = H/600`). The Extender widened only the 3D projection, while the 2D scale stayed separate, hence the stretching. Fix: a single scale `s = H/600` for 2D and an X offset (`offsetX = (W - 800*s)/2`), plus a decision on which panels to pin to the screen edges.

---

## 1. Glossary for a web developer

| Term | In plain words |
|---|---|
| PE32 / x86 | Exe format and architecture: 32-bit Windows. Our DLL must also be **32-bit** (Win32/x86), otherwise it will not load. |
| Disassembler / decompiler | Ghidra or IDA: they open the exe and show assembly and pseudo-C. Like the DevTools "Sources" tab for a binary without source maps. |
| Debugger | x64dbg (for 32-bit you run `x32dbg.exe`): breakpoints, viewing memory and registers in the live game. Like Xdebug, but for machine code. |
| Hook | Intercepting a function call: we put our function in place of the original one, do our own thing and optionally call the original. Like middleware / monkey-patching in JS. |
| Proxy DLL | A DLL with the name of a system one (for example `ddraw.dll` or `dinput8.dll`) that the game loads from its own folder. It loads the real system DLL and runs our code along the way. A way to "plug in" without editing the exe. |
| MinHook | A small C library for function hooks. Similar to overriding `Function.prototype`, but at the machine-code level. |
| RVA / address | Offset of a function in the exe. We will store addresses and **byte signatures** so we can find functions even in a slightly different exe (GOG vs Steam vs Fan Patch). |
| D3D7 / DirectDraw7 | A 1999 graphics API that the game's DirectX7 mode runs on. |
| dgVoodoo2 | A wrapper that translates D3D7/DDraw/Glide to Direct3D 11/12. Solves many compatibility problems on Win10/11. |

---

## 2. Tools (to install)

**Required:**
- **Visual Studio 2022 Community** with the "Desktop development with C++" workload. Build in the **Win32 (x86)** configuration. Alternative: CMake + MSVC Build Tools.
- **Ghidra** (free, needs JDK 21) with PE32 support. This is the main decompiler.
- **x64dbg** (we use `x32dbg`) + the **ScyllaHide** plugin is not needed (no DRM), but a plugin for exporting/importing labels is useful (x64dbg supports `.dd32` databases).
- **rea MCP**: `npx rea-agents setup` (needs Node.js 22.19+ / 24.11+). Gives Claude access to analysis via Ghidra. Important: according to the repository documentation, **Ghidra support on Windows is marked experimental**, and the MCP tools are mostly **read-only** (binary overview, function analysis, address context); judging by the contract descriptions, renaming functions and writing patches through it is not possible. If rea misbehaves on Windows, fallback options: GhidraMCP (LaurieWired) or ida-pro-mcp (mrexodia, needs IDA Pro). Or run rea in WSL2 on a copy of the exe.
- **MinHook** (add as a git submodule or via vcpkg: `vcpkg install minhook:x86-windows`).
- **Process Monitor** (Sysinternals): see which DLLs and configs the game loads.
- **API Monitor** (rohitab) or **apitrace**: log DirectDraw/D3D7 calls and window WinAPI calls.

**Recommended:**
- **dgVoodoo2** (latest stable): a D3D7 → D3D11 wrapper for compatibility and as a "base layer" for borderless.
- **RenderDoc** works with D3D11, so through dgVoodoo2 you can capture frames and see how the HUD is drawn.
- A clean copy of the game from **GOG or Steam** (already version 1.2.4, without SafeDisc). We keep an **immutable reference copy** and a separate working one.

---

## 3. Solution architecture

```
Wizardry 8\
  Wiz8.exe                  (the original, do not touch)
  dinput8.dll / ddraw.dll   ← our proxy loader (choose in Phase 0)
  wiz8ws.dll                ← our logic: HUD hooks, window, config
  wiz8ws.ini                ← user settings
  Dll\ ...                  (the game's render plugins; the Extender stays here)
  [dgVoodoo2 DLL]           (optional, under our proxy or instead of it)
```

Modules of `wiz8ws.dll`:
1. **Loader / version**: determine which exe is running (SHA-256 hash), choose the address table, otherwise search by signatures; on a mismatch, patch nothing and write to the log.
2. **Window**: borderless windowed (Phase 3).
3. **HUD**: recalculation of 2D coordinates and panel layout (Phase 4).
4. **Mouse**: inverse transform of mouse coordinates for the new layout (without it clicks "miss").
5. **Config + log**: `wiz8ws.ini`, `wiz8ws.log`.

Why not edit the exe directly: the DLL approach is reversible (delete the file and everything is back), works on any copy of the same version and does not require distributing game files.

> **A Phase 0 hypothesis that could simplify everything.** The name `srVP_Wiz8Extender.dll` and the `Dll\` folder suggest that the game's renderers are **plugins in separate DLLs** with a common interface. If the HUD's 2D drawing goes through plugin functions (for example "draw a rectangle/texture at coordinates x,y,w,h"), then the HUD can be fixed **at the exe ↔ plugin boundary** by intercepting these calls and translating the coordinates, barely touching the logic of the exe itself. This is the first thing to check.

---

## 4. Work phases

### Phase 0. Reconnaissance (1–3 evenings)
Tasks:
- **Choose the target version.** There are GOG, Steam and the original Buka ISOs. Compute SHA-256 and size of `Wiz8.exe` and the DLLs from `Dll\` in all three, record them in `docs/history/recon.md` as a table. Main target: **GOG** (no DRM and no Steam client; no launcher needs to be running while debugging). If the Steam exe is byte-identical to GOG, Steam is supported for free. If it differs, check for a Steam DRM wrapper (a `.bind` section in the PE header); we will not debug such a version, its support comes later via signature search. Buka: most likely an early version under disc protection (SafeDisc or similar), which does not work on Windows 10/11 and which we do not remove or bypass. We use it only as a source of Russian texts and resources, not as a patch target.
- Record the version: install path, SHA-256 of `Wiz8.exe` and all DLLs in `Dll\`, size, build date (from the PE header). Write it to `docs/history/recon.md`.
- List the imports of the exe and of each DLL in `Dll\` (`dumpbin /imports`, or Ghidra). Answer: who imports `ddraw.dll`, `d3d*`, `opengl32`, `glide*`; is it the exe or the plugins.
- Process Monitor: which files are read at startup (`3DVideo.CFG`, `.ini`, DLLs from `Dll\`).
- See how the exe chooses and loads the render plugin (`LoadLibrary` + `GetProcAddress` with which export names).
- Decide which proxy DLL to plug in through: `dinput8.dll`/`dsound.dll`/`winmm.dll` (whichever of these the exe actually imports) or `ddraw.dll`.
- Check that the game starts in DirectX7 + 32-bit + Extender at the target resolution, both with and without dgVoodoo2. Screenshots in `docs/screens/baseline/`.

Done when: there is a `docs/history/recon.md` with versions, imports, the renderer loading scheme and the chosen entry point.

### Phase 1. DLL skeleton (1–2 evenings)
- CMake/VS project, Win32 target, `/MT` (static CRT, so no redistributable is required).
- A proxy DLL that forwards all exports of the real system DLL and in `DllMain` (no heavy work in `DllMain`!) starts the initialization of `wiz8ws.dll`.
- File logger, reading `wiz8ws.ini`, exe hash check.
- MinHook initialized, a test hook on `CreateWindowExA` logs the window parameters.

Done when: the game starts with the DLL as usual, the log shows the exe hash and the parameters of the window being created; removing the DLL restores the original behavior.

### Phase 2. Finding the HUD code (the most research-heavy, 1–4 weeks)
Method (confirm every hypothesis in x32dbg, not only from pseudocode):
1. **Find the resolution.** In the debugger, find where the screen width/height are stored in memory (search for values, for example 1920 and 1080, after startup). Set a hardware breakpoint on read: whoever reads these values is doing the scaling.
2. **Find the base 800/600 (or 640/480).** In Ghidra, search for the constants `0x320`/`0x258` (800/600) and `0x280`/`0x1E0` (640/480), and also float `800.0f`/`600.0f`. Functions that divide the resolution by these numbers are candidates for the "2D scale".
3. **Find the 2D drawing.** Via API Monitor or RenderDoc (with dgVoodoo2), find the calls that draw party portraits, panels, text. Walk up the call stack to the exe functions that pass the coordinates.
4. **Find the layout.** There is probably layout data (panel coordinates) in resources or in tables in the exe. Look for strings with screen/panel names and resource files that are read when screens open.
5. **Mouse input.** Find where mouse coordinates are converted from screen to virtual (the inverse of the scale).
6. **Rename** every function found **in Ghidra** (manually or with a Ghidra script in Python/Java, if rea cannot write), add a comment and record it in `docs/functions.md`: address, byte signature, what it does, how it was verified.

How to use Claude + rea here: "show all functions that reference the constant 800.0f", "analyze the function at address X, guess the meaning of the arguments", "compare these two functions". AI answers are hypotheses, verified with a breakpoint.

Done when: found and verified in the debugger (a) the 2D scale function/location, (b) the place where the 3D window viewport is set, (c) the mouse coordinate transform, (d) it is clear whether there are separate drawing modes for the "world" and for full-screen menus (inventory, character creation, map).

### Phase 3. Borderless windowed (2–5 evenings, can be done in parallel with Phase 2)
Option A (simpler, start with it): **dgVoodoo2 in windowed mode at the desktop resolution** + our window hook:
- Hooks on `CreateWindowExA`, `SetWindowLongA`, `SetWindowPos`, `MoveWindow`, `AdjustWindowRect(Ex)`: force `WS_POPUP | WS_VISIBLE`, position and size = the monitor the window is on.
- Hook `ChangeDisplaySettingsA/ExA`: return success but do not change the monitor mode (this is exactly what "messes up" the layout of windows on the desktop).
- If the game uses `IDirectDraw7::SetCooperativeLevel(DDSCL_FULLSCREEN | DDSCL_EXCLUSIVE)` and `SetDisplayMode`, intercept and replace with `DDSCL_NORMAL`, and do the output through the window (dgVoodoo2 partly does this itself).
- Alt+Tab: remove the known bug "movement stops after Alt+Tab" (handle `WM_ACTIVATEAPP`, reset key state).
- DPI: declare DPI awareness (manifest or `SetProcessDpiAwareness`), otherwise Windows scales the window and the image gets blurry.
- Cursor: `ClipCursor` to the window, as an ini option.

Option B (if A does not fit): our own DirectDraw7 interception that copies the frame into the window. This takes longer; do it only if A hits a wall.

Done when: the game at 2560×1440 (or the native resolution) opens without changing the monitor mode, Alt+Tab is instant, desktop windows do not "jump", the mouse hits the elements.

### Phase 4. Undistorted HUD (2–6 weeks)
1. **Single scale.** Hook the 2D scale function: `s = H / baseH`, `offsetX = (W - baseW*s) / 2`. First result: the whole 2D interface in 4:3, centered, not stretched. 3D may for now be covered by panels or shown only in the center.
2. **Full-screen 3D behind the HUD.** Hook the 3D view viewport so the world is drawn across the full width (the Extender already does the Hor+ projection; the output area needs to match the new layout).
3. **Panel layout (anchors).** Add modes to the ini:
   - `HudLayout=Centered` (the whole 4:3 frame centered, with 3D or black bars on the sides);
   - `HudLayout=Anchored` (party portraits pinned to the bottom/edges, compass and buttons to the corners).
   For `Anchored` we need a "panel → anchor" table (left/right/center/top/bottom), found in Phase 2.
4. **Full-screen 2D screens** (inventory, character, map, party creation, main menu): pillarbox (4:3 centered, black or blurred background on the sides).
5. **Mouse.** Inverse coordinate transform with the same formula, otherwise clicks will miss.
6. **Video (Bink).** Check that movies are 4:3 and centered; Fan Patch 1.28 can already stretch Bink to the resolution, so keep compatibility.
7. **Fonts/text.** Check that text is scaled by the same `s`.

Done when: at 16:9, 16:10 and 21:9 the interface is undistorted, all buttons are clickable, the test plan from section 6 passes.

### Phase 5. Compatibility and packaging (1–2 weeks)
- Version support: GOG is primary; Steam (if the exe matches GOG, one address table, otherwise signature search). Russian version: check that the patch works with Russian resources on top of the GOG exe (that is also how it is used with Fan Patch 1.28). We do not support the Buka exe if it is under disc protection. Then decide whether to support the Fan Patch 1.28 exe (it is modified itself, addresses may differ: search by signatures).
- Compatibility with the Extender (do not duplicate its FOV) and with dgVoodoo2.
- `wiz8ws.ini` with comments, `README.md` (installation, removal, common problems), a license for our own code (MIT).
- Release: a zip with only our DLLs + ini + README. No game files.

---

## 5. Milestones

| # | Milestone | Verification |
|---|---|---|
| M0 | Reconnaissance complete | `docs/history/recon.md`, it is clear where rendering is and how it is loaded |
| M1 | DLL loads | log with the exe hash, the game works as before |
| M2 | Borderless works | no monitor mode change, Alt+Tab is instant |
| M3 | 2D scale found | a breakpoint on the function fires while the HUD is drawn; a manual change in the debugger changes the scale |
| M4 | HUD 4:3 centered, not stretched | screenshots at 16:9 and 21:9 |
| M5 | Full-screen 3D + panel anchors | screenshots, the mouse hits |
| M6 | All screens and video checked | test plan passed |
| M7 | Release | clean install on a second machine/copy |

---

## 6. Test plan (for every milestone)
Resolutions: 1920×1080, 2560×1440, 1920×1200, 3440×1440, plus 1024×768 for regression (nothing should change at 4:3).
Check: main menu, party creation, the world (combat, conversation, trading), inventory, spellbook, map, save/load, movies, Alt+Tab, minimizing, changing the resolution in settings, second monitor.
Every time: screenshots in `docs/screens/<milestone>/`, a log without errors, the game survives 30 minutes without a crash.

---

## 7. Rules for Claude Code in this project
- Do not modify `Wiz8.exe` or the files of the reference copy. Work in a copy.
- Record every function address in `docs/functions.md` together with its byte signature and how it was verified.
- Mark assumptions about a function's meaning as a hypothesis until confirmed in the debugger.
- Check the exe hash before every hook; on an unknown version, patch nothing.
- Comment C++ code more than usual: the project owner writes PHP/JS.
- After each phase, stop and show the result and screenshots.

---

## 8. Useful sources
- rea MCP: https://github.com/morluto/rea (tool contracts: `docs/mcp-contracts.md`)
- PCGamingWiki, Wizardry 8 (Extender, renderers, problems on newer Windows): https://www.pcgamingwiki.com/wiki/Wizardry_8
- Fan Patch 1.28 (old-games.ru): https://www.old-games.ru/forum/threads/wizardry-8-fan-patch-1-28.104012/
- dgVoodoo2 and widescreen discussion on GOG: https://www.gog.com/forum/wizardry_series/wizardry_8_cutscenes_and_widescreen_solutions
- MinHook: https://github.com/TsudaKageyu/minhook
- dgVoodoo2: https://dege.freeweb.hu/

**Tip:** before starting Phase 2, it is worth writing to the Fan Patch 1.28 authors (the thread on old-games.ru or the VK group "Cosmic Forge"). They already hook the exe at the assembly level and probably know where the interface code is. Their markup could save weeks.

---

## 9. Setting up the local environment (Windows 11 Pro)

### Decision: everything on native Windows
The game, the x32dbg debugger, building a 32-bit DLL with MSVC and Ghidra with its GUI only work on Windows (or are most convenient there). If Claude Code lived in WSL2, it would constantly have to cross the WSL ↔ Windows boundary: `/mnt/c/...` paths, running `.exe` from Linux, a slow file system. So **Claude Code is installed natively on Windows**, with all the tools next to it.

| What you have | Use it? | Why |
|---|---|---|
| Native Windows | **Yes, the main environment** | Game, x32dbg, MSVC, Ghidra, Claude Code |
| WSL2 Ubuntu | Fallback only | If `rea` does not work with Ghidra on Windows (rea marks this as experimental): then Ghidra + rea in WSL on a **copy** of the exe, for static analysis only |
| Docker Desktop | No | Containers do not run Windows games with a GPU; they give nothing for this task |
| Docker sandbox | No | Same thing: Linux isolation for the agent, while we need Windows processes and a debugger |
| Windows Sandbox | No (at most for one test) | Resets on close, weak GPU, a D3D7 game is unlikely to run properly there. Can be used once to check a "clean install" of the release in Phase 5 |

Instead of a sandbox, isolation is provided like this: a separate project folder, a working copy of the game separate from the reference one, Claude has command confirmations enabled (the default mode), and `.claude/settings.json` forbids writing to the reference copy.

### Step 1. Folder structure
Do not work in `C:\Program Files (x86)\...`: there Windows redirects the game's writes to VirtualStore and requires admin rights, which confuses both debugging and Claude.
```
C:\dev\wiz8-ws\            ← project repository (git), we run claude here
  SPEC.md                  ← this file
  CLAUDE.md                ← rules for Claude (step 7)
  src\  docs\  third_party\
C:\Games\Wiz8-reference\   ← reference copy of the game, read-only
C:\Games\Wiz8-work\        ← working copy, we put our DLLs here and run it
C:\Tools\                  ← ghidra, x64dbg, procmon, etc.
```
Copy the installed **GOG** version into both `C:\Games\...` folders (this is the main target). To compare hashes in Phase 0, put the exe and `Dll\` from Steam and from the Buka ISO next to them in `C:\Games\Wiz8-variants\steam\` and `...\buka\` (files for analysis only, no installation). Set the "read-only" attribute on `Wiz8-reference`:
```powershell
attrib +R C:\Games\Wiz8-reference\* /S
```

### Step 2. Basic programs (PowerShell)
```powershell
winget install --id Git.Git -e                        # needed by Claude Code on Windows (Git Bash)
winget install --id OpenJS.NodeJS.LTS -e              # Node 22.19+ / 24.11+ for rea
winget install --id EclipseAdoptium.Temurin.21.JDK -e # Java 21 for Ghidra
winget install --id Python.Python.3.12 -e             # for helper scripts
winget install --id Kitware.CMake -e
```
Restart the terminal and check: `git --version`, `node -v`, `java -version`, `cmake --version`.

### Step 3. C++ compiler (Visual Studio Community)
- Install Visual Studio 2022 Community (or newer) with the **"Desktop development with C++"** workload. In the components, select: MSVC x86/x64 build tools, Windows SDK, "C++ CMake tools for Windows".
- To build from the terminal, Claude uses the **"x86 Native Tools Command Prompt for VS"** or, in a regular PowerShell:
  ```powershell
  & "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\Launch-VsDevShell.ps1" -Arch x86
  ```
- Check: `cl` prints a version with `for x86`. This matters: the DLL must be 32-bit.

### Step 4. Reverse-engineering tools
- **Ghidra:** download the zip from github.com/NationalSecurityAgency/ghidra/releases, unpack it to `C:\Tools\ghidra`. Launch with `ghidraRun.bat`. Create a project `C:\dev\wiz8-ws\ghidra\`, import `Wiz8.exe` and the DLLs from `Dll\` **from the working copy**, run Auto Analysis.
- **x64dbg:** snapshot zip from x64dbg.com, unpack it to `C:\Tools\x64dbg`. For the game we use `release\x32\x32dbg.exe`.
- **Process Monitor:** `winget install --id Microsoft.Sysinternals.ProcessMonitor -e`.
- **API Monitor** (rohitab.com) and **dgVoodoo2** (dege.freeweb.hu): unpack to `C:\Tools\`.

### Step 5. Claude Code
```powershell
irm https://claude.ai/install.ps1 | iex
```
Then run `claude` in `C:\dev\wiz8-ws` and log in. Check: `claude doctor`.

### Step 6. rea MCP
```powershell
cd C:\dev\wiz8-ws
npx rea-agents setup
```
The wizard will register the MCP server in Claude Code. When it asks about the engine for native binaries, choose **Ghidra** and point it to `C:\Tools\ghidra`. If a Ghidra startup timeout appears, set the variable:
```powershell
setx REA_GHIDRA_STARTUP_TIMEOUT_MS 180000
```
Check: in `claude` run `/mcp` (the rea server is in the connected state), then ask: "via rea, open C:\Games\Wiz8-work\Wiz8.exe and give me a binary_overview".

**If rea does not work on Windows** (Ghidra support on Windows is marked experimental):
1. Try an alternative MCP for Ghidra (for example, GhidraMCP), which runs as a plugin inside the Ghidra GUI.
2. Or the fallback via WSL2: in Ubuntu install Node 22+, JDK 21, Ghidra for Linux, copy `Wiz8.exe` and the DLLs to `~/wiz8-bin/` and run `npx rea-agents setup` there. Analysis in WSL, while building and debugging still happen in Windows. Claude transfers the analysis results (addresses, names) to `docs/functions.md`.

### Step 7. Project settings for Claude
`C:\dev\wiz8-ws\.claude\settings.json`:
```json
{
  "permissions": {
    "deny": [
      "Edit(C:/Games/Wiz8-reference/**)",
      "Write(C:/Games/Wiz8-reference/**)"
    ]
  }
}
```
`C:\dev\wiz8-ws\CLAUDE.md` (short):
```markdown
# Wiz8 widescreen patch
- We work from SPEC.md, phase by phase; after each phase, stop and report.
- Build only Win32 (x86), from VS Dev Shell -Arch x86.
- Game reference copy C:\Games\Wiz8-reference: never modify.
- Test copy C:\Games\Wiz8-work: copy built DLLs here.
- Ghidra project: C:\dev\wiz8-ws\ghidra. Debugger: C:\Tools\x64dbg\release\x32\x32dbg.exe.
- Found addresses: docs/functions.md (address, byte signature, how verified).
- The owner writes PHP/JS: explain C++ and assembly in simple words.
```

### Step 8. Git
```powershell
cd C:\dev\wiz8-ws
git init
git submodule add https://github.com/TsudaKageyu/minhook third_party/minhook
```
In `.gitignore`: `build/`, `ghidra/`, `*.exe`, `*.dll` in the root, game files. Game files and Ghidra databases containing its code do not go into the public repository.

### How the roles are split
- **Claude Code**: reads the decompilation via MCP, writes C++, builds, copies the DLL into the working copy, reads `wiz8ws.log`, maintains `docs/`.
- **You**: run the game and x32dbg when a live breakpoint or a screenshot is needed, and give Claude the result (log text, address, screenshot). The GUI debugger and visual checking of the HUD stay with you: this is the fastest way to confirm the AI's hypotheses.

### Environment readiness checklist
- [ ] `cl` from VS Dev Shell x86 works
- [ ] Ghidra opens and analyzes `Wiz8.exe`
- [ ] `x32dbg` starts the game from `C:\Games\Wiz8-work` and stops at the entry point
- [ ] `claude` in `C:\dev\wiz8-ws`, `/mcp` shows rea (or an alternative) connected
- [ ] Claude produces an overview of `Wiz8.exe` via MCP on request
- [ ] The game from `Wiz8-work` starts in DirectX7 32-bit with the Extender
