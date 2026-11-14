#pragma once

// What was installed successfully (written to the log).
struct HookReport {
    bool signature = false;     // exe bytes matched the expected ones (that exact build)
    bool dpiAware = false;
    bool modePatch = false;
    bool videoFullScreen = false;
    bool bink = false;
    bool mouse = false;
    bool altTab = false;
    bool hud = false;           // 2D in a 4:3 block (RenderScene hook)
    bool hudFallback = false;   // Centered was requested but the hook didn't go in -> fell back to Stretch
    bool view3dClear = false;   // clearing the 3D area under Centered (setScissor slot)
    bool horPlus = false;       // Hor+: widened camera plane
    bool horPlusPick = false;   // Hor+: recomputing 3D clicks
    bool horPlusThumbs = false; // Hor+: save thumbnails without distortion
    bool diff = false;          // comparison harness against the port (RenderFrame hook)
    bool hybrid = false;        // hybrid: WinMain hook for wiz8hy.dll
    int fileNames = -2;         // UTF-8 file names (filenames.h): -2 off, -1 not needed, else imports redirected
    bool w8x = false;           // srDD_D3D11's extension API: the sr.dll hooks of hooks_w8x.cpp
    bool w8xOtherSr = false;    // those hooks left out: sr.dll is not the build they are written for
    unsigned w8xSrStamp = 0;    // the TimeDateStamp of that sr.dll, for the log line
};

// Checks that the code in memory really is GOG 1.2.4 (header + bytes at the hook points).
bool CheckGameSignature();

// Each function installs its own group of hooks; called from DllMain after CheckGameSignature.
bool InstallVideoHooks(HookReport* r);
bool InstallMouseHooks(HookReport* r);
bool InstallInputHooks(HookReport* r);
// Centered 4:3 interface and Hor+ (only with HudLayout=Centered; SrApiInit must succeed first).
bool InstallHudHooks(HookReport* r);
// horPlus=false — only clearing the 3D area; true — Hor+ as well.
bool InstallView3dHooks(HookReport* r, bool horPlus);

// Comparison harness against the port ([Debug] DiffHarness=1 with [Hybrid] Enabled=0):
// RenderFrame hook -> w8diff.dll.
bool InstallDiffHooks();

// [D3D11] Extensions=1: camera.view, OPAQUE_DONE and the water tag for srDD_D3D11 (hooks_w8x.cpp).
// Hooks in sr.dll only; with another render driver they pass everything on. Sets r->w8x, or
// r->w8xOtherSr with r->w8xSrStamp when sr.dll is another build, and returns r->w8x.
bool InstallW8xHooks(HookReport* r);

// Hybrid ([Hybrid] Enabled=1): the WinMain hook loads wiz8hy.dll before the game initializes.
bool InstallHybridHook();
extern int g_hybridHooks;
