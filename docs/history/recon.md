# Phase 0 — reconnaissance (draft)

> **History.** This document describes an early stage of the project and may differ from the released 1.0.0 patch (the hybrid, see [docs/hybrid.md](../hybrid.md) and [README](../../README.md)). It is kept to show how we arrived at the current solution. The Steam exe is now identical to GOG (same SHA-256); the packed Steam exe described in this document is no longer encountered.

Date: 2026-10-11. Everything below was obtained statically (reading PE headers and hashes); the game had not been run yet.

## Versions

| Copy | Path | Wiz8.exe SHA-256 | Size | Build date (PE) | Status |
|---|---|---|---|---|---|
| **GOG** (target) | `C:\Program Files (x86)\GOG Galaxy\Games\Wizardry 8` → copied to `C:\dev\wiz8-ws\games\reference` (read-only) and `C:\dev\wiz8-ws\games\work` | `18A74FF61C65B8A2D4CFA11FFCE82AD7FEF022A94EAF0C2F217E479E981420D2` | 3 580 513 | 2001-12-24 | 1.2.4 GOG v1 (GOG registry). Entry point 0x401000 in `.text`; empty SafeDisc sections `stxt774`/`stxt371` remain, but the protection has already been removed — the exe is clean and can be debugged directly. |
| Steam | `C:\Program Files (x86)\Steam\steamapps\common\Wizardry8` | `D54776C1C286802157F738C1E3D2703498D931B4565E1AB0D55C3366C56E6B9C` | 1 232 896 | 2002-03-15 | **Differs from GOG.** Unnamed sections + `.adata`, exactly one function imported from each DLL: the exe is packed/encrypted by an unknown packer (this is not Steam DRM: there is no `.bind` section). Not debugged; support later only via signatures (if at all). |
| Buka | — | — | — | — | ISO not found on disk. |

All renderer and engine DLLs in Steam and GOG are byte-identical, except `Dll\srDD_OpenGL.dll` (Steam has a different build). Steam has no `Dll\srDD_Glide2x.dll`.
Extender (`srVP_Wiz8Extender.dll`) and Fan Patch 1.28 are **not installed** in the GOG copy. Installed: nGlide (`glide*.dll`, 2017) and the official 2001-12-23 patch.

## GOG file hashes (and comparison with Steam)

| File | Size | Build | SHA-256 | Steam |
|---|---|---|---|---|
| `Dll\srDD_DirectX6.dll` | 86096 | 2000-09-17 | `2968987F843F1E1B228B2FF322923E5AC215095A3CB41877B169F01820F8F316` | = GOG |
| `Dll\srDD_DirectX7.dll` | 94283 | 2000-11-23 | `3623F1CB66CD50B7141B49F82100A8FFA1FD3C53DDEBC7093BFDDEB148CBF8E9` | = GOG |
| `Dll\srDD_Glide2x.dll` | 69705 | 2000-09-17 | `E19987FB5BC9ABCCEADF4AD64BF108AC2F95D10B520D8DE294D9B10466CA1D11` | none |
| `Dll\srDD_OpenGL.dll` | 36953 | 2001-01-08 | `A176AA711039AEBBFE33EB5D48E082DCD608835EEEBD2A69EAD9B455400AFC8C` | differs: `A84BD2AF15A5621B…` |
| `Dll\srDD_Software.dll` | 127051 | 2000-09-17 | `8866A254569F61022B857628380171DFF018939376C02965741635421D0C79F8` | = GOG |
| `Dll\srEXT_AVI.dll` | 24650 | 2000-09-17 | `9D27A6698693FB6B244951166D873A1F1A102213F5832D60379234176BD0EB07` | = GOG |
| `Dll\srEXT_default.dll` | 57426 | 2000-09-17 | `E2A9D1E7F11E0927B7BACFE058A7113B234F0ADED92F4C5FECFB23CF86EAD7F8` | = GOG |
| `Dll\srEXT_FLIC.dll` | 28748 | 2000-09-17 | `3CE83B9944F4D26F027C5B322A5DBEA97CFE6339A7298B25914F67F35CCFD281` | = GOG |
| `Dll\srEXT_HTTP.dll` | 24652 | 2000-09-17 | `ADE27CE64A7AF1824AEB5BA65F908BAB56344311CD8F45C0C65EDDE02D1D87AF` | = GOG |
| `Dll\srEXT_Inspector.dll` | 45142 | 2000-09-17 | `6BC2949D6C9BCA35ECC37E8F4F98ED36886A075F00D69AE86687D38F682387A1` | = GOG |
| `Dll\srEXT_JPEGImporter.dll` | 118876 | 2000-09-17 | `0BF545937BD86CE2195C08B6DBF6B70E1A1071A9FCE449CCB9F06DFA384DE490` | = GOG |
| `Dll\srEXT_LWOImporter.dll` | 57434 | 2000-09-17 | `A681095372DECD2639D0EA14BDBADB362B7AEAC04F137DC1558856212479932A` | = GOG |
| `Dll\srEXT_MPEG.dll` | 77900 | 2000-09-17 | `42344E67D5DE0B962652677D70891402DAE16B0F39979693539867F779455ECD` | = GOG |
| `Dll\srEXT_Unzip.dll` | 102400 | 2000-09-17 | `DBA6CDC5741AE57574E019AB8F37935362BC288BEE738BC711460F34D7647F62` | = GOG |
| `Dll\srHXImporter.dll` | 73728 | 2000-09-17 | `DB83029AD30F8DF5DD425E586A1B847193B0EDC38E79EC62A3D2C7D4CB59E7A7` | = GOG |
| `Dll\srVP_486.dll` | 49152 | 2000-09-17 | `E28FD5AD6DA156179910FA59B8D6EF88DA432B1E69B3C44507592D10FDFC8C57` | = GOG |
| `Dll\srVP_AMD3DNow.dll` | 65536 | 2000-09-17 | `42E169C89A01AB620320981D5B6A15A89EA7A6D3FE312A8728E1262B95FAC8F3` | = GOG |
| `Dll\srVP_Generic.dll` | 36864 | 2000-09-17 | `0C4704C920235E58F0FAB852844FC9273CD4683B7B9655C702855BC9335E1474` | = GOG |
| `Dll\srVP_KNI.dll` | 106561 | 2000-09-17 | `895B5FB3F4982F7A70E7BFC518FED1D674587380D708487F57A0A00E0C9669CC` | = GOG |
| `Dll\srVP_Pentium.dll` | 49152 | 2000-09-17 | `9A08CDDB2F75D98D61A3A3BFD644BFFE07610C080840C03660BA9D6D849E14FA` | = GOG |
| `Dll\srVP_PentiumII.dll` | 57421 | 2000-09-17 | `2CADEFD51ED177C762CCBC6BE0181FC70E6E26ECAF04B1B475298F206FED518C` | = GOG |
| `Dll\srVP_PentiumMMX.dll` | 61440 | 2000-09-17 | `BF1A2E932680A71261382115A3AFC4CEB1742814D4C52742FCF8A1D6FB0F5A47` | = GOG |
| `Dll\srVP_PentiumPro.dll` | 57344 | 2000-09-17 | `7F3502649D7CFD151EBDB82AB5472D8F32AB0268D2AC24ADD60490B6B0E4CDD0` | = GOG |
| `Dll\srVP_x86.dll` | 61505 | 2000-09-17 | `BBEC96AA91B6988618FB4EC07696BAED01CA556A3EAB6F3836F9F475B45730C2` | = GOG |
| `3DfxSpl.dll` | 1105408 | 1999-10-16 | `1EE8B2B4963B95F600AC683907778304F75C559AA6831A3F203EFAFC8D67D45A` | = GOG |
| `3DfxSpl2.dll` | 1105408 | 1999-10-16 | `262C70749AC24B4D3691E39767D3E01B5B4957B9B82768186E5FAA58F395CEBA` | = GOG |
| `3DfxSpl3.dll` | 1105408 | 1999-10-16 | `E282BCBA9E04AC9A898AE353F93573FA7F94EB5A4E0BC0C25933C3B702BB269E` | = GOG |
| `3DSetup.exe` | 102454 | 2001-12-11 | `B440EE06A3AA03C4FA301DCABA6875A61488F0DEE3D06386B721F4CBE0C11473` | = GOG |
| `binkw32.dll` | 286208 | 2000-07-11 | `1FD7EF7873C8A3BE7E2F127B306D0D24D7D88E20CF9188894EFF87B5AF0D495F` | = GOG |
| `glide.dll` | 1527808 | 2017-12-17 | `57FD08DE7ADB9268027D79A3C28C49AA29970C752CAB4D50E31425E4D9D089F0` | = GOG |
| `glide2x.dll` | 1617920 | 2017-12-17 | `7FF40975FEE4016E029ABB45732CDD06B54C23E8778C77BCE50806C11C6E23FA` | = GOG |
| `glide3x.dll` | 1712128 | 2017-12-17 | `DB1630A50EB481BC86702A8FCC2E4E5E67F7F4C34F9707AD325424D24ACB1381` | = GOG |
| `Mss32.dll` | 348160 | 2001-10-16 | `2A515199CC7A2E1CCD8D756EFDAAB07CEDD5C3052309EF1C7499C2560E2097BD` | = GOG |
| `MSVCIRT.DLL` | 77878 | 1998-06-17 | `647F7534AAAEDFFA93534E4CB9B24BFCF91524828FF0364D88973BE58139E255` | = GOG |
| `MSVCP60.DLL` | 401462 | 1998-06-17 | `2B6B93C2D66969EB00258E2B5AD6172DECEBADA096E3B1B077A3380C80E4A072` | = GOG |
| `MSVCRT.DLL` | 266293 | 1998-12-04 | `D4287AB5E4988DFE99BD54243D50DBE8744094F11FE5F9809A1A6FB9728C2124` | = GOG |
| `nglide_config.exe` | 348160 | 2017-12-11 | `7445DC0A2A63B8532457E17795CA4F264035B90C49CA457673556BDFC3C31D00` | = GOG |
| `sr.dll` | 688191 | 2000-09-17 | `CEC1CAF85861C34BC4583EF1C69209E96A6930BDFC9AF545C429F7470A8B6165` | = GOG |
| `unins000.exe` | 1343048 | 2018-08-20 | `5761E7789D813626CD68EE1E62429CFEB92BDD814CD29EF12FC4AE9EC1DBAFF3` | none |
| `Wiz8.exe` | 3580513 | 2001-12-24 | `18A74FF61C65B8A2D4CFA11FFCE82AD7FEF022A94EAF0C2F217E479E981420D2` | differs: `D54776C1C2868021…` |

## Imports (GOG)

- **`Wiz8.exe`**: `DDRAW.DLL` (only `DirectDrawCreate`), `USER32` (35, incl. `CreateWindowExA`, `SetWindowLongA`, `SetWindowPos`, `AdjustWindowRect`, `ClipCursor`, `GetSystemMetrics`, `GetCursorPos`/`SetCursorPos`, `ClientToScreen`), `GDI32` (`GetStockObject`), `KERNEL32` (44), `MSVCRT`/`MSVCP60`, `BINKW32` (12, video), `MSS32` (56, Miles sound), `SR.DLL` (461 engine functions).
  No imports of `dinput*`, `dsound`, `winmm`, `d3d*`, `opengl32`, `glide*`. Input apparently goes through window messages.
- **`sr.dll`** (the "sr" engine, C++ with exports, 2059 functions): `LoadLibraryA`/`LoadLibraryExA`/`GetProcAddress`/`FindFirstFileA` — apparently this is the module that enumerates and loads the plugins from `Dll\`. It also creates its own windows (`CreateWindowExA`, `MoveWindow`, `SetWindowLongA`, `AdjustWindowRect`).
- **`Dll\srDD_DirectX7.dll`** (render driver): exports `srDDGetDriverApiVersion`, `srDDGetDriverName`, `srDDGetDeviceCount`, `srDDGetDeviceName`, `srDDConfigureDriver`, `srDDInitDevice`. Imports: `USER32` (`GetClientRect`, `GetWindowRect`, `ClientToScreen`, `SetWindowPos`), `LoadLibraryA`/`GetProcAddress` (so `ddraw.dll` is loaded dynamically, not through the import table).
- **`Dll\srVP_*.dll`** (per-CPU vector processors): exports `srInitVectorProcessor`, `srGetVectorProcessorAPI`, `srGetVectorProcessorID`. This is exactly the kind of module the Extender replaces.

Conclusion: the spec's hypothesis is structurally confirmed. The renderer is a plugin with a narrow C interface (`srDDInitDevice` most likely returns a table of device functions). Hooking 2D drawing at the `sr.dll` ↔ `srDD_*.dll` boundary looks feasible; to be verified in Phase 2.

## Public decompilation

https://github.com/agluszak/wizardry-8-decomp (cloned into `ref\`, not in git) targets exactly our GOG `Wiz8.exe` (same SHA-256 in `reccmp-project.yml`). 17 addresses from it were checked against the bytes of our exe — all land on function starts, and the constants 1/640 and 1/480 are in place. The table is in `docs/functions.md`. The game's virtual 2D space is **640×480**, not 800×600 as the spec assumed.

## Renderer loading sequence (from the decompilation, `Video2.cpp`)

`InitializeVideoDevice` (0x422240) reads `3DVideo.CFG` (device / width / height / depth / sound) → `_chdir("DLL")` → `srInit()` → `sprintf("srDD_%s", device)` → `srGERD::loadDevice` → `createContext(ghWindow)` → `OpenRendererWindow` (0x422800), where in fullscreen mode `getDisplayMode(w,h,depth)` looks for an exact match. The game window has already been created by this point. `srVP_*` modules are enumerated by `srVectorProcessor::loadBest` in `sr.dll`, and `DllMain` runs for each of them.

## Injection point — decision

- `ddraw.dll` — **no**: that slot is taken by dgVoodoo2, without which the game does not start on this machine.
- `srVP_*` — no (competes in the selection of the "best" VP); an `srDD_*` wrapper — is loaded only after the window is created, too late for DPI awareness and for hooking `CreateWindowExA`.
- **Chosen: `version.dll` in the game folder.** It is statically imported by `sr.dll` (3 functions: `GetFileVersionInfoSizeA`, `GetFileVersionInfoA`, `VerQueryValueA`), and `sr.dll` is a static import of `Wiz8.exe`, so our DLL will be loaded at process start, before `WinMain` and before the window is created. `version.dll` is not in KnownDLLs (checked in the registry), so the local copy takes priority. The proxy forwards 17 exports to `SysWOW64\version.dll`. A fallback with the same property is `winmm.dll` (also an import of `sr.dll`, not a KnownDLL).
- Process Monitor was not needed: dgVoodoo2 already proves that a local DLL is picked up from the game folder; we will confirm `version.dll` loading with a log in Phase 1.

## Config

`3DVideo.CFG` (text): `DirectX7`, `1280`, `1024`, `3216`, `Miles Fast 2D Positional Audio` — renderer, width, height, unknown parameter (probably flags/depth), sound.
`Wiz8.CFG` — binary RIFF (`CNFG`, `QLTY`, `KEYM` — settings, quality, key bindings).

## Baseline run (2026-10-11, RTX 4080 Laptop, 2560×1600, 150% scaling)

- Without wrappers: `Video device does not support video resolution.` both with the original `3DVideo.CFG` (DirectX7 1280×1024 "3216") and with 1024×768×16 from 3DSetup. According to the decompilation (`OpenRendererWindow` 0x422800), this means `srGERD::getDisplayMode` finds no exact width/height/depth match in the srDD_DirectX7 driver's mode list.
- With dgVoodoo2 2.87.5 (`DDraw.dll` + `D3DImm.dll` from `MS\x86` in the game folder, watermark off): **the game starts** in DirectX7 1024×768×16.
- 3DSetup offers at most 1280×1024×16, but that is its own list. Manually editing `3DVideo.CFG` to 2560×1600×16 (the screen's native resolution) works with dgVoodoo2: the menu is fullscreen (confirmed by the owner). srDD_DirectX7 + dgVoodoo2 have no width limit at 2560.
- Conclusion: a local `ddraw.dll` in the game folder really is picked up (dgVoodoo proved it). So a proxy named `ddraw.dll` would take dgVoodoo's place — our DLL needs a different name (see below).

## Extender

- Source: PCGamingWiki file 541, `Wiz8Extender.zip` (password `pcgw`, repacked RAR), stored in `Tools\_downloads`, unpacked into `Tools\extender`.
- `srVP_Wiz8Extender.dll` 0.2.2.0 (Dec 2013), 115 712 bytes, SHA-256 `867DF77A30DA63E7958B073EFDAEDFE3BF75BFAF7C44652A1D5ACA40B4C4848A`.
- Packed with **VMProtect** (sections `.vmp0`/`.vmp1`, export encrypted), imports MSVCR100/MSVCP100 (VC++ 2010 x86 is already on the system). We will not reverse it; for us it is a black box we have to coexist with.
- According to the readme: it changes FOV only for 16:9 and 16:10; when it loads successfully, the Sir-Tech logo is not shown. That is the check indicator.
- Installed into `games\work\Dll\`, `3DVideo.CFG` = DirectX7 2560×1600×32.
- **Does not work on this machine:** at startup `srVP_Wiz8Extender.dll` shows "Sorry, this application cannot run under a Virtual Machine." This is VMProtect's anti-VM check: Windows 11 has the hypervisor enabled (`HypervisorPresent=True`, VBS running), so the system itself looks like a virtual machine to it. We will not bypass the protection of someone else's DLL; disabling the hypervisor/VBS is a system setting (it would break WSL2/Docker). The DLL was removed from the working copy.
- Consequence for the plan: we do Hor+ for 3D ourselves in `wiz8ws.dll` (the points are known from the decompilation: `RenderScene` 0x427850 and its neighbours). This also removes the risk of double FOV with the Extender.

## Phase 0 summary

- [x] Versions and hashes (GOG is the target; Steam is packed; no Buka).
- [x] Imports of the exe and DLLs, renderer loading sequence.
- [x] Baseline run: dgVoodoo2 is required; 1024×768 and 2560×1600 work. 1024×768 screenshots in `docs/screens/baseline/`.
- [x] Extender checked: does not work under the Windows 11 hypervisor → we do Hor+ ourselves.
- [x] Injection point: `version.dll`.
- [x] 2560×1600 "before" screenshots: `baseline/main-menu-2560x1600-stretched.jpg` (the in-game one is not kept) (both 3D and HUD stretched 4:3 → 16:10).
- [x] Observation: in fullscreen mode the game accepts clicks in **screen pixels 0..640 × 0..480** regardless of resolution (clicking "Load Game" only worked at coordinates 323,257 on a 2560×1600 screen). This confirms the description of `SyncSystemCursor` from the decompilation and means that the mouse transform must be fixed together with the HUD.
