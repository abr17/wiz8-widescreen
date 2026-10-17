// Centered 4:3 interface (HudLayout=Centered).
//
// All of the game's 2D (HUD, menus, inventory, videos, cursor) is drawn by
// RenderScene with one of two 2D cameras and stretched over the current viewport
// (the screen rectangle being drawn into). Normally that is the whole screen — hence
// the stretched interface. We intercept RenderScene and for the 2D cameras set
// viewport/scissor to the central 4:3 block, draw, then ALWAYS
// restore the whole screen (scissor = clipping rectangle, the engine applies it immediately;
// a forgotten scissor would clip everything drawn afterwards).
//
// The 3D world pass (vp == &g_viewport) also comes through here: its rectangle
// is computed by hooks_view3d.cpp (Hor+ at full width or the 4:3 block).
//
// The game does not clear the side bars (in the original the canvas always covered them) — we clear
// them to black ourselves: at the start of each frame and once more before an opaque menu.

#include "hooks_game.h"

#include <windows.h>

#include "game_gog124.h"
#include "layout.h"
#include "log.h"
#include "patch.h"
#include "sr_api.h"
#include "view3d.h"

using namespace gog124;

// RenderScene is an ordinary game function, cdecl: arguments on the stack, the caller cleans up.
// The last argument is a bool, but it takes 4 bytes on the stack; we pass it as int
// so that the original gets all 4 bytes unchanged.
typedef void(__cdecl* RenderScene_t)(void* scene, void* cam, const int* vp640, int preserveFog);
static RenderScene_t g_origRenderScene;

static void SetViewAndScissor(void* g, const PixelRect& r)
{
    GerdSetViewPort(g, r);
    GerdSetScissor(g, r);
}

static void RestoreFullScreen(void* g, const ScreenBlock& b)
{
    SetViewAndScissor(g, {0, 0, b.W, b.H});
}

// Fill both side bars with black. We set the viewport too, not just the scissor:
// in D3D7 a clear is also clipped by the viewport.
static void ClearBars(void* g, const ScreenBlock& b)
{
    SrColor saved;
    GerdGetClearColor(g, &saved);  // the game sets the clear color itself (fog color) — restore it afterwards
    GerdSetClearColor(g, {0.0f, 0.0f, 0.0f, 1.0f});
    const PixelRect bars[2] = {
        {0, 0, b.offX, b.H},
        {b.offX + b.bw, 0, b.W - b.offX - b.bw, b.H},
    };
    for (const PixelRect& r : bars) {
        if (r.w <= 0) continue;
        SetViewAndScissor(g, r);
        GerdClear(g, 1);  // color only; depth is left alone
    }
    GerdSetClearColor(g, saved);
    RestoreFullScreen(g, b);
}

// Were the bars already cleared this frame by the setScissor hook (before the game's 3D-area clear)?
static bool g_barsClearedEarly;

void HudClearBarsBeforeWorldClear(void* g, const ScreenBlock& b)
{
    ClearBars(g, b);
    g_barsClearedEarly = true;
}

// The canvas is opaque (menu, inventory) — the alpha-test bit is off.
static bool CanvasOpaque()
{
    uint8_t* node = *(uint8_t**)Va(g_surfaceNode);
    return node && (*(uint32_t*)(node + SurfaceNode_ShaderBits) & ShaderBit_AlphaTest) == 0;
}

static void __cdecl HookRenderScene(void* scene, void* cam, const int* vp, int preserveFog)
{
    // RenderScene always draws through the main renderer g_gerd (it reads it itself),
    // so save thumbnails (a second renderer) never come through here.
    void* g = MainGerd();
    ScreenBlock b;
    bool haveSize = g && GerdScreenBlock(g, &b);

    // The return address is the place in RenderFrame we were called from.
    // MinHook jumps into the hook via jmp, so the return address is the same as the original's.
    void* ret = __builtin_return_address(0);
    bool firstOfFrame = ret == Va(Ret_RenderFrame_FirstRenderScene);
    bool clearedEarly = g_barsClearedEarly;
    if (firstOfFrame) {
        g_barsClearedEarly = false;           // the flag lives for one frame
        if (haveSize) View3dSyncPlane(b);     // did the screen size change? (before the 4:3 check)
    }

    if (!haveSize || b.bw >= b.W) {
        // Screen is 4:3 or narrower — no bars, change nothing.
        g_origRenderScene(scene, cam, vp, preserveFog);
        return;
    }

    // Once per frame, before the world and before the 2D — if the game didn't clear the 3D area
    // this frame (it skips that when the sky is drawn) and the bars are not filled yet.
    if (firstOfFrame && !clearedEarly) ClearBars(g, b);

    bool is2d = cam && (cam == *(void**)Va(g_overlayCamera) || cam == *(void**)Va(g_squareCamera));
    bool isWorld = vp && vp == (const int*)Va(g_viewport);

    // Before an opaque canvas, clear the bars once more: the world widened by Hor+ must not
    // stick out at the sides of an opaque menu.
    if (is2d && scene && scene == *(void**)Va(g_sceneOverlay0) && CanvasOpaque()) {
        ClearBars(g, b);
    }

    if (!is2d && !isWorld) {
        g_origRenderScene(scene, cam, vp, preserveFog);
        return;
    }

    PixelRect r = is2d ? BlockRect(b, vp) : View3dWorldRect(b, vp);
    SetViewAndScissor(g, r);
    // World in a narrow rectangle while the plane is widened — for the duration of the pass
    // restore the normal plane (otherwise the picture gets squashed horizontally).
    View3dPlaneSwap swap;
    bool swapped = !is2d && View3dNarrowBegin(cam, &swap);
    // vp = NULL: with it the original leaves the viewport alone and draws into our rectangle.
    g_origRenderScene(scene, cam, nullptr, preserveFog);
    if (swapped) View3dNarrowEnd(swap);
    // Always restore the whole screen — even if the original returned at once (empty scene).
    RestoreFullScreen(g, b);
}

// Bytes at the start of RenderScene: sub esp,18h; mov ecx,[g_gerd]; push ebx/ebp/edi.
static const uint8_t kRenderSceneStart[] = {0x83, 0xEC, 0x18, 0x8B, 0x0D, 0x34, 0x96, 0x65, 0x00, 0x53, 0x55, 0x57};
// First RenderScene call in RenderFrame: call RenderScene (rel32 = 0x00000E11).
static const uint8_t kFirstCall[] = {0xE8, 0x11, 0x0E, 0x00, 0x00};

bool InstallHudHooks(HookReport* r)
{
    r->hud = BytesMatch(RenderScene, kRenderSceneStart, sizeof(kRenderSceneStart)) &&
             BytesMatch(Call_RenderFrame_FirstRenderScene, kFirstCall, sizeof(kFirstCall)) &&
             HookGameFunction(RenderScene, (void*)&HookRenderScene, (void**)&g_origRenderScene);
    return r->hud;
}
