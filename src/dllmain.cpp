// DLL entry point.
//
// Windows calls DllMain while holding its internal "loader lock". During that
// time nothing heavy may be done: loading other DLLs "in a chain", creating
// windows, waiting for threads — it is easy to get a hang. So only the bare
// minimum happens here:
//   1) load the real version.dll so the game works (not as binkw32.dll, see loader_route.h);
//   2) decide whether this copy runs the patch (StartHere: under Wine a second copy can be
//      loaded as binkw32.dll); a copy that does not only passes calls on and stops here;
//   3) read the ini;
//   4) with [Debug] Diagnostics=1, move the previous session's logs into Wiz8Logs\ (file moves only);
//   5) hook CreateWindowExA and patch the game (InstallGameHooks: the sr.dll hooks of
//      [D3D11] Extensions in every case; with the hybrid, besides them, only the WinMain hook
//      that loads wiz8hy.dll).
// Everything else (log, exe hash, diagnostics, under Wine the patch's own Wine setting) happens
// in EnsureRuntime() when the first window is created.

#include <windows.h>

#include <MinHook.h>

#include <string.h>

#include "diagnostics.h"
#include "filenames.h"
#include "hooks_window.h"
#include "log.h"
#include "proxy_version.h"
#include "runtime.h"
#include "sr_api.h"
#include "wine_settings.h"

Runtime g_runtime;

static INIT_ONCE g_initOnce = INIT_ONCE_STATIC_INIT;

// Under Wine (Linux, Steam Deck; Proton is Wine): which Wine, and whether ddraw.dll is Wine's
// own (as it should be) or dgVoodoo from the game folder, which crashes under Wine right after
// this line. Wine replaces a game-folder DLL by its own unless WINEDLLOVERRIDES (or the
// registry) says otherwise, and then still reports the game-folder path for it; its own DLLs
// carry this text right after the DOS header (docs/loader.md). Wine looks for DDraw.dll in the
// game folder first; when there is none there, a ddraw.dll that is not Wine's own is a native
// one in Wine's system folder (a winetricks or Bottles component). Returns false when ddraw.dll
// is not Wine's own (true when it is, when it is not loaded, or not under Wine).
static bool LogWine()
{
    typedef const char*(__cdecl * WineVersion_t)();
    auto wineVersion =
        (WineVersion_t)GetProcAddress(GetModuleHandleA("ntdll.dll"), "wine_get_version");
    if (!wineVersion) {
        return true;
    }
    HMODULE ddraw = GetModuleHandleA("ddraw.dll");
    bool own = ddraw && memcmp((const char*)ddraw + 0x40, "Wine builtin DLL", 16) == 0;
    char inFolder[MAX_PATH + 16];
    lstrcpyA(inFolder, g_runtime.gameDir);
    lstrcatA(inFolder, "DDraw.dll");
    DWORD attributes = GetFileAttributesA(inFolder);
    bool folder = attributes != INVALID_FILE_ATTRIBUTES && !(attributes & FILE_ATTRIBUTE_DIRECTORY);
    Log("wine %s: ddraw.dll is %s", wineVersion(),
        !ddraw   ? "not loaded"
        : own    ? "Wine's own (right: a dgVoodoo DDraw.dll left in the game folder would crash "
                   "under Wine)"
        : folder ? "from the game folder (dgVoodoo, which crashes under Wine: ddraw must be b, "
                   "see the README)"
                 : "a native one from Wine's system folder (if it is dgVoodoo, it crashes under "
                   "Wine: ddraw must be b, see the README)");
    return !ddraw || own;
}

static BOOL CALLBACK DoRuntimeInit(PINIT_ONCE, PVOID, PVOID*)
{
    char path[MAX_PATH];
    lstrcpyA(path, g_runtime.gameDir);
    lstrcatA(path, "wiz8ws.log");
    LogOpen(path);
    Log("Wizardry 8 Widescreen " WIZ8WS_VERSION " (wiz8ws, loaded as %s proxy)",
        LoaderRoleName(g_runtime.role));
    Log("game dir: %s", g_runtime.gameDir);
    // As binkw32.dll the real version.dll is not loaded; LogLoaderRoute says which one sr.dll got.
    if (g_runtime.role == LoaderRole::Version) {
        if (g_runtime.proxyOk) {
            Log("real version.dll: loaded");
        } else {
            Log("real version.dll: FAILED (error %lu); its functions report failure. Under Wine use "
                "WINEDLLOVERRIDES version=n,b, not version=n", ProxyVersionError());
        }
    }
    LogLoaderRoute(g_runtime.role);
    bool ddrawOwn = LogWine();
    // Under Wine: note the setting in this prefix, so the next starts need no launch option.
    WineKeepOverrides(ddrawOwn);

    char exePath[MAX_PATH];
    GetModuleFileNameA(nullptr, exePath, MAX_PATH);
    g_runtime.exeSha256 = Sha256File(exePath);
    g_runtime.exe = IdentifyExe(g_runtime.exeSha256);
    Log("exe: %s", exePath);
    Log("exe sha256: %s -> %s", g_runtime.exeSha256.c_str(), ExeVersionName(g_runtime.exe));
    Log("config: Enabled=%d LogWindowCalls=%d", g_runtime.config.enabled,
        g_runtime.config.logWindowCalls);
    Log("hooks installed: %s", g_runtime.hooksInstalled ? "yes" : "no");
    const HookReport& r = g_runtime.game;
    Log("game signature: %s; dpiAware=%d borderless(modePatch=%d videoFullScreen=%d bink=%d) "
        "mouse=%d altTab=%d hudLayout=%s",
        r.signature ? "GOG 1.2.4 OK" : "MISMATCH (game hooks skipped)", r.dpiAware, r.modePatch,
        r.videoFullScreen, r.bink, r.mouse, r.altTab,
        g_runtime.config.hudLayout == HudLayout::Centered ? "Centered" : "Stretch");
    Log("hud layout: hud=%d view3dClear=%d horPlus=%d (ini %d) pick=%d thumbs=%d", r.hud,
        r.view3dClear, r.horPlus, g_runtime.config.horPlus, r.horPlusPick, r.horPlusThumbs);
    if (r.hudFallback) Log("hud layout: HUD hook NOT installed -> HudLayout falls back to Stretch (mouse too)");
    if (g_runtime.config.diffHarness && g_runtime.config.hybrid) {
        Log("diff harness: RenderFrame hook not installed: the diff harness needs [Hybrid] Enabled=0");
    } else if (g_runtime.config.diffHarness) {
        Log("diff harness: RenderFrame hook %s", r.diff ? "installed" : "FAILED");
    }
    if (!g_runtime.config.w8x) {
        Log("w8x (srDD_D3D11 extensions): off ([D3D11] Extensions=0)");
    } else if (r.w8xOtherSr) {
        Log("w8x (srDD_D3D11 extensions): sr.dll hooks not installed: sr.dll is another build "
            "(time stamp 0x%08X)", r.w8xSrStamp);
    } else {
        Log("w8x (srDD_D3D11 extensions): sr.dll hooks %s", r.w8x ? "installed" : "FAILED");
    }

    if (g_runtime.config.hybrid) Log("hybrid: WinMain hook %s, wiz8hy.dll: %d functions replaced (-1 = not loaded)", r.hybrid ? "installed" : "FAILED", g_hybridHooks);
    if (r.fileNames >= 0) {
        Log("file names: system code page is UTF-8; %d file imports redirected, game names read as code page %u",
            r.fileNames, FileNameCodePage());
    } else if (r.fileNames == -1) {
        Log("file names: system code page %u, nothing to do", GetACP());
    } else {
        Log("file names: off (Utf8FileNames=0 or no hybrid)");
    }

    // Project rule: on an unknown exe version we change nothing, we only pass calls through.
    g_runtime.active = g_runtime.config.enabled && g_runtime.exe != ExeVersion::Unknown;
    if (!g_runtime.active) {
        Log("patch inactive (%s); passing everything through unchanged",
            g_runtime.config.enabled ? "unknown exe" : "disabled in ini");
    }
    // Exit trace, crash minidumps, memory heartbeat (diagnostics.h), with [Debug] Diagnostics=1.
    // They only observe, so they run on an unknown exe too (the game's own globals are then not read).
    if (g_runtime.config.diagnostics) {
        DiagStart();
    } else {
        Log("diagnostics: off ([Debug] Diagnostics=0)");
    }
    return TRUE;
}

// Hooks inside the game itself. Installed in DllMain because the game creates its window
// and asks for the screen size right after start — later would be too late.
// Everything here is only memory writes and kernel32/user32 calls that load no DLLs.
static void InstallGameHooks()
{
    HookReport& r = g_runtime.game;
    r.signature = CheckGameSignature();
    if (!r.signature) {
        return;  // unknown build: touch nothing in the game
    }
    const Config& c = g_runtime.config;
    if (c.dpiAware) {
        // Without this, at 150% scaling Windows shows the game a 1707x1067 "screen"
        // and stretches the picture — it gets blurry and mouse coordinates are distorted.
        typedef BOOL(WINAPI * SetCtx_t)(HANDLE);
        auto setCtx = (SetCtx_t)GetProcAddress(GetModuleHandleA("user32.dll"),
                                               "SetProcessDpiAwarenessContext");
        r.dpiAware = setCtx ? setCtx((HANDLE)-4 /* PER_MONITOR_AWARE_V2 */) != FALSE
                            : SetProcessDPIAware() != FALSE;
    }
    // sr.dll's own functions, the same with or without the hybrid.
    if (c.w8x) InstallW8xHooks(&r);
    if (c.hybrid) {
        // Hybrid: the window, mouse, HUD and Hor+ are handled by port code from wiz8hy.dll;
        // the patch's own hooks are not installed here (they would conflict with the transplanted functions).
        r.hybrid = InstallHybridHook();
        return;
    }
    SetHudLayout(c.hudLayout);
    if (c.borderless) InstallVideoHooks(&r);
    if (c.fixMouse) InstallMouseHooks(&r);
    if (c.fixAltTab) InstallInputHooks(&r);
    // Centered 4:3 interface and Hor+. Needs sr.dll functions (it is already in
    // memory: it is sr.dll, not Wiz8.exe, that imports VERSION.dll — so sr.dll is what
    // loaded us; as binkw32.dll Wiz8.exe did, and sr.dll, imported after it, is mapped by then
    // too; its own DllMain has not run yet, so we only read export addresses and
    // call nothing in it). Hor+ is installed only if the 2D hook went in: without it
    // the world with the widened plane would be stretched incorrectly.
    if (c.hudLayout == HudLayout::Centered && SrApiInit() && InstallHudHooks(&r)) {
        InstallView3dHooks(&r, c.horPlus);
    }
    if (c.hudLayout == HudLayout::Centered && !r.hud) {
        // Centering the 2D failed — so the game draws it stretched. The mouse then
        // must also map over the whole screen, otherwise clicks would land off target.
        SetHudLayout(HudLayout::Stretch);
        r.hudFallback = true;  // logged later (writing to a file from DllMain is not allowed)
    }
    if (c.diffHarness) r.diff = InstallDiffHooks();
}

void EnsureRuntime()
{
    InitOnceExecuteOnce(&g_initOnce, DoRuntimeInit, nullptr, nullptr);
}

BOOL WINAPI DllMain(HINSTANCE self, DWORD reason, LPVOID reserved)
{
    if (reason == DLL_PROCESS_ATTACH) {
        // We don't need notifications about every new game thread.
        DisableThreadLibraryCalls(self);

        // Game folder = this DLL's folder (we sit next to Wiz8.exe).
        GetModuleFileNameA(self, g_runtime.gameDir, sizeof(g_runtime.gameDir));
        char* slash = g_runtime.gameDir;
        for (char* p = g_runtime.gameDir; *p; ++p) {
            if (*p == '\\') slash = p + 1;
        }
        *slash = '\0';

        // Loaded as version.dll or as binkw32.dll (loader_route.h). Only the version.dll copy
        // loads the real version.dll: sr.dll imports it from that copy, never from binkw32.dll,
        // unless version.dll is this very file (VersionDllIsThisFile).
        g_runtime.role = LoaderRoleOf(self);
        g_runtime.proxyOk =
            ProxyVersionLoad(g_runtime.role == LoaderRole::Version || VersionDllIsThisFile(self));
        // One copy per process runs the patch; the other one only passes calls on: no ini,
        // no hooks, no log (the log file cannot be opened twice anyway).
        if (!StartHere(self, g_runtime.role)) {
            return TRUE;
        }

        char ini[MAX_PATH];
        lstrcpyA(ini, g_runtime.gameDir);
        lstrcatA(ini, "wiz8ws.ini");
        g_runtime.config = LoadConfig(ini);

        // Keep the previous session's logs (only file moves, safe in DllMain).
        if (g_runtime.config.enabled && g_runtime.config.diagnostics) DiagRotateLogs(g_runtime.gameDir);

        if (g_runtime.config.enabled && MH_Initialize() == MH_OK) {
            g_runtime.hooksInstalled = InstallWindowHooks();
            InstallGameHooks();
        }
    } else if (reason == DLL_PROCESS_DETACH) {
        // reserved != nullptr — the whole process is exiting: removing the hooks is pointless
        // and unsafe (other threads are already killed). Remove them only on FreeLibrary.
        if (g_runtime.hooksInstalled && reserved == nullptr) {
            MH_Uninitialize();
        }
    }
    return TRUE;
}
