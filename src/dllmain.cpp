// DLL entry point.
//
// Windows calls DllMain while holding its internal "loader lock". During that
// time nothing heavy may be done: loading other DLLs "in a chain", creating
// windows, waiting for threads — it is easy to get a hang. So only the bare
// minimum happens here:
//   1) load the real version.dll so the game works;
//   2) read Enabled from the ini;
//   3) hook CreateWindowExA.
// Everything else (log, exe hash) happens in EnsureRuntime() when the first window is created.

#include <windows.h>

#include <MinHook.h>

#include "hooks_window.h"
#include "log.h"
#include "proxy_version.h"
#include "runtime.h"
#include "sr_api.h"

Runtime g_runtime;

static INIT_ONCE g_initOnce = INIT_ONCE_STATIC_INIT;

static BOOL CALLBACK DoRuntimeInit(PINIT_ONCE, PVOID, PVOID*)
{
    char path[MAX_PATH];
    lstrcpyA(path, g_runtime.gameDir);
    lstrcatA(path, "wiz8ws.log");
    LogOpen(path);
    Log("wiz8ws " WIZ8WS_VERSION " loaded as version.dll proxy");
    Log("game dir: %s", g_runtime.gameDir);
    Log("real version.dll: %s", g_runtime.proxyOk ? "loaded" : "FAILED");

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
    Log("phase4: hud=%d view3dClear=%d horPlus=%d (ini %d) pick=%d thumbs=%d", r.hud, r.view3dClear,
        r.horPlus, g_runtime.config.horPlus, r.horPlusPick, r.horPlusThumbs);
    if (r.hudFallback) Log("phase4: HUD hook NOT installed -> HudLayout falls back to Stretch (mouse too)");
    if (g_runtime.config.diffHarness) Log("diff harness: RenderFrame hook %s", r.diff ? "installed" : "FAILED");

    if (g_runtime.config.hybrid) Log("hybrid: WinMain hook %s, wiz8hy.dll: %d functions replaced (-1 = not loaded)", r.hybrid ? "installed" : "FAILED", g_hybridHooks);

    // Project rule: on an unknown exe version we change nothing, we only pass calls through.
    g_runtime.active = g_runtime.config.enabled && g_runtime.exe != ExeVersion::Unknown;
    if (!g_runtime.active) {
        Log("patch inactive (%s); passing everything through unchanged",
            g_runtime.config.enabled ? "unknown exe" : "disabled in ini");
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
    // Phase 4: centered 4:3 interface and Hor+. Needs sr.dll functions (it is already in
    // memory: it is sr.dll, not Wiz8.exe, that imports VERSION.dll — so sr.dll is what
    // loaded us; its own DllMain has not run yet, so we only read export addresses and
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

        g_runtime.proxyOk = ProxyVersionLoad();

        char ini[MAX_PATH];
        lstrcpyA(ini, g_runtime.gameDir);
        lstrcatA(ini, "wiz8ws.ini");
        g_runtime.config = LoadConfig(ini);

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
