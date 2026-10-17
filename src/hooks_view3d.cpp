// Hor+ — wider 3D field of view on a wide screen (ini [Display] HorPlus=1, only with
// HudLayout=Centered).
//
// How the game sets the view: SetViewport 0x426250 builds the camera's "view plane"
// of 85°x71° over the whole 640x480 virtual screen and cuts out a piece of it for the
// 3D view (g_viewport). We replace that piece with a wider one: the same
// "degrees per pixel" scale, but from the left to the right edge of the real screen, not
// just of the 4:3 block. The height (vertical angle) does not change — that is what Hor+ means.
// Then the world pass is drawn at full width (x = 0, w = W) — that is done by
// hooks_hud.cpp via View3dWorldRect().
//
// Hooks here:
//   1) import slot srCamera::setViewPlane(Rect, double) 0x5EB4EC — only calls
//      from SetViewport (return addresses 0x4263A9 world, 0x4263C3 sky);
//   2) import slot srGERD::setScissor 0x5EB640 — only the 3D-area clear in
//      RenderFrame (return address 0x4269E8), only for the main renderer;
//   3) the pushPick call at 0x426BAC (click in 3D) — rewritten to call our thunk;
//   4) RenderWorldToSurface 0x426F80 — save thumbnails are drawn with the normal
//      (non-widened) plane, otherwise the picture gets squashed.
//
// We widen only when the 3D view touches the 4:3 edges (modes 0, 1, 6: left = 23,
// right+1 = 618, and menus 0..641). The narrow modes 2-5 (128..512, between the panels)
// stay inside the 4:3 block.

#include "hooks_game.h"

#include <windows.h>

#include "game_gog124.h"
#include "log.h"
#include "patch.h"
#include "sr_api.h"
#include "view3d.h"

using namespace gog124;

// Types of the "real" methods (thiscall: object in ECX). Our replacements are declared as
// __fastcall(self, edx, ...): fastcall puts the 1st argument in ECX, the 2nd in EDX, and
// the rest on the stack, and cleans the stack itself — from the outside this is indistinguishable from thiscall.
// EDX is then just garbage that we ignore.
typedef void(__attribute__((thiscall))* SetViewPlaneRect_t)(void*, const SrRect*, double);
typedef void(__attribute__((thiscall))* SetScissor_t)(void*, unsigned long, unsigned long, unsigned long, unsigned long);
typedef unsigned char(__cdecl* RenderWorldToSurface_t)(void*, const int*, int);

static SetViewPlaneRect_t g_origSetViewPlaneRect;
static SetScissor_t g_origSetScissor;
static RenderWorldToSurface_t g_origRenderWorldToSurface;

static bool g_horPlus;        // Hor+ is on and the plane hooks are installed
static bool g_planeWidened;   // the last SetViewport widened the world camera's plane
static void* g_widenedCam;    // ...of this camera (new world = new camera = reset)
// The non-widened planes the game wanted: [0] world, [1] sky.
static void* g_planeCam[2];
static SrRect g_origPlane[2];
// Screen size the current widened plane was computed for.
static int g_planeW, g_planeH;

static const int* Viewport640() { return (const int*)Va(g_viewport); }

// Does the 3D view touch the 4:3 edges (left <= 23, right+1 >= 618)?
static bool TouchesEdges(const int* v) { return v[0] <= 23 && v[2] >= 618 && v[2] > v[0]; }

// Camera of the world (i = 0) or of the sky (i = 1), if there is a world.
static void* WorldCamera(int i)
{
    uint8_t* world = *(uint8_t**)Va(i == 0 ? g_world : g_secondaryWorld);
    return world ? *(void**)(world + World_Camera) : nullptr;
}

bool View3dWorldWidened()
{
    return g_horPlus && g_planeWidened && TouchesEdges(Viewport640()) && g_widenedCam &&
           g_widenedCam == WorldCamera(0);
}

PixelRect View3dWorldRect(const ScreenBlock& b, const int* vp)
{
    PixelRect r = BlockRect(b, vp);
    if (View3dWorldWidened()) {
        r.x = 0;
        r.w = b.W;
    }
    return r;
}

// Virtual (in 640 units) coordinates of the left and right screen edges:
// screen pixel p corresponds to virtual (p - offX) / s, where s = bw/640.
static void ScreenEdgesVirtual(const ScreenBlock& b, double* VL, double* VR)
{
    double s = b.bw / 640.0;
    *VL = -b.offX / s;
    *VR = (b.W - b.offX) / s;
}

// Widen the plane piece the game cut out to the screen edges. The game computes:
// plane(x) = pl + k*(x - L) for virtual x (linear), k = (pr - pl)/(R1 - L).
// We simply extend this line to VL and VR.
static bool WidenPlane(const SrRect& in, SrRect* out)
{
    void* g = MainGerd();
    ScreenBlock b;
    if (!g || !GerdScreenBlock(g, &b) || b.bw >= b.W) return false;
    const int* v = Viewport640();  // SetViewport wrote it before calling setViewPlane
    if (!TouchesEdges(v)) return false;
    int L = v[0], R1 = v[2];
    double VL, VR;
    ScreenEdgesVirtual(b, &VL, &VR);
    double k = (in.r - in.l) / (R1 - L);
    *out = in;  // top and bottom (b, t) unchanged — the vertical angle stays the same
    out->l = in.l + k * (VL - L);
    out->r = in.l + k * (VR - L);
    g_planeW = b.W;
    g_planeH = b.H;
    return true;
}

// Give camera i back the game's non-widened plane (dist is taken from the current one).
static void RestoreOrigPlane(int i)
{
    void* cam = g_planeCam[i];
    if (cam && cam == WorldCamera(i)) {
        SrRect cur;
        double dist;
        CameraGetViewPlane(cam, &cur, &dist);
        CameraSetViewPlane(cam, g_origPlane[i], dist);
    }
    g_planeCam[i] = nullptr;
}

void View3dSyncPlane(const ScreenBlock& b)
{
    if (!g_horPlus || !g_planeWidened) return;
    if (b.W == g_planeW && b.H == g_planeH) return;  // the usual case: do nothing
    for (int i = 0; i < 2; ++i) {
        void* cam = g_planeCam[i];
        if (!cam || cam != WorldCamera(i)) continue;
        SrRect wide;
        if (WidenPlane(g_origPlane[i], &wide)) {
            SrRect cur;
            double dist;
            CameraGetViewPlane(cam, &cur, &dist);
            CameraSetViewPlane(cam, wide, dist);
        } else {
            RestoreOrigPlane(i);  // screen became 4:3 (or the 3D view is narrow) — normal plane
            if (i == 0) g_planeWidened = false;
        }
    }
    // Remember the size even if widening failed: don't recompute every frame.
    g_planeW = b.W;
    g_planeH = b.H;
}

bool View3dNarrowBegin(void* cam, View3dPlaneSwap* s)
{
    if (!g_horPlus || !g_planeWidened || !cam || TouchesEdges(Viewport640())) return false;
    for (int i = 0; i < 2; ++i) {
        if (cam == g_planeCam[i] && cam == WorldCamera(i)) {
            s->cam = cam;
            CameraGetViewPlane(cam, &s->saved, &s->dist);
            CameraSetViewPlane(cam, g_origPlane[i], s->dist);
            return true;
        }
    }
    return false;
}

void View3dNarrowEnd(const View3dPlaneSwap& s)
{
    CameraSetViewPlane(s.cam, s.saved, s.dist);
}

// --- 1. setViewPlane(Rect, double): thiscall, retn 0xC (Rect* + double = 12 bytes) ---
static void __fastcall HookSetViewPlaneRect(void* cam, void* /*edx*/, const SrRect* rect, double dist)
{
    void* ret = __builtin_return_address(0);
    int idx = ret == Va(Ret_SetViewport_WorldPlane) ? 0 : (ret == Va(Ret_SetViewport_SkyPlane) ? 1 : -1);
    if (idx < 0) {
        // Someone else's call (2D cameras at start-up, automap). If it is the world camera,
        // our widened plane is no longer in effect. Then the sky also gets
        // its normal plane back, otherwise it would be squashed in a narrow rectangle.
        if (cam && cam == g_widenedCam && g_planeWidened) {
            g_planeWidened = false;
            g_planeCam[0] = nullptr;  // its plane is now set by the game, not by us
            RestoreOrigPlane(1);
        }
        g_origSetViewPlaneRect(cam, rect, dist);
        return;
    }
    SrRect wide;
    if (rect && WidenPlane(*rect, &wide)) {
        g_planeCam[idx] = cam;
        g_origPlane[idx] = *rect;
        if (idx == 0) {
            g_planeWidened = true;
            g_widenedCam = cam;
        }
        g_origSetViewPlaneRect(cam, &wide, dist);
        return;
    }
    g_planeCam[idx] = nullptr;
    if (idx == 0) g_planeWidened = false;
    g_origSetViewPlaneRect(cam, rect, dist);
}

// --- 2. setScissor: thiscall (x, y, w, h), retn 0x10 ---
static void __fastcall HookSetScissor(void* g, void* /*edx*/, unsigned long x, unsigned long y,
                                      unsigned long w, unsigned long h)
{
    // RenderFrame clears the 3D area (color + depth) using g_viewport stretched over
    // the whole screen. We give it the same rectangle where the world is actually drawn.
    // Main renderer only: save thumbnails have their own (second) GERD.
    if (__builtin_return_address(0) == Va(Ret_RenderFrame_ClearScissor) && g && g == MainGerd()) {
        ScreenBlock b;
        if (GerdScreenBlock(g, &b) && b.bw < b.W) {
            // First the bars to black, then the game (right after us) clears the world with the fog
            // color — the widened world rows get fog, not black.
            HudClearBarsBeforeWorldClear(g, b);
            PixelRect r = View3dWorldRect(b, Viewport640());
            x = r.x;
            y = r.y;
            w = r.w;
            h = r.h;
        }
    }
    g_origSetScissor(g, x, y, w, h);
}

// --- 3. click in 3D: thunk instead of call [pushPick] at 0x426BAC ---
// The game converts the cursor to -1..1 coordinates relative to its (narrow) 3D view.
// When the world is widened, -1..1 must cover the whole screen instead — we recompute x.
// y is left alone: vertically the 3D view did not change.
static void __fastcall PickThunk(void* g, void* /*edx*/, const SrPick* p)
{
    ScreenBlock b;
    if (p && View3dWorldWidened() && GerdScreenBlock(g, &b) && b.bw < b.W) {
        const int* v = Viewport640();
        int halfw = (v[2] - v[0]) / 2;  // as in the game: integer division
        if (halfw > 0) {
            // Back to the cursor's virtual x (that is how the game computed it: x = (cx - L - halfw)/halfw).
            double cx = v[0] + halfw * (1.0 + p->x);
            double VL, VR;
            ScreenEdgesVirtual(b, &VL, &VR);
            SrPick q = *p;  // copy: don't modify the game's structure
            q.x = (float)(2.0 * (cx - VL) / (VR - VL) - 1.0);
            GerdPushPick(g, &q);
            return;
        }
    }
    GerdPushPick(g, p);
}

// --- 4. save thumbnails: non-widened plane while the snapshot is taken ---
static unsigned char __cdecl HookRenderWorldToSurface(void* target, const int* rect, int sky)
{
    if (!g_planeWidened) return g_origRenderWorldToSurface(target, rect, sky);
    SrRect saved[2];
    double dist[2];
    bool swapped[2] = {false, false};
    for (int i = 0; i < 2; ++i) {
        void* cam = WorldCamera(i);
        if (cam && cam == g_planeCam[i]) {
            CameraGetViewPlane(cam, &saved[i], &dist[i]);
            CameraSetViewPlane(cam, g_origPlane[i], dist[i]);
            swapped[i] = true;
        }
    }
    unsigned char res = g_origRenderWorldToSurface(target, rect, sky);
    for (int i = 0; i < 2; ++i) {
        if (swapped[i]) CameraSetViewPlane(WorldCamera(i), saved[i], dist[i]);
    }
    return res;
}

// --- installation ---

// Check bytes (GOG 1.2.4).
static const uint8_t kScissorLoad[] = {0x8B, 0x1D, 0x40, 0xB6, 0x5E, 0x00};  // mov ebx,[setScissor]
static const uint8_t kCallEbx[] = {0xFF, 0xD3};                              // call ebx
static const uint8_t kPlaneLoad[] = {0x8B, 0x35, 0xEC, 0xB4, 0x5E, 0x00};    // mov esi,[setViewPlane]
static const uint8_t kCallEsi[] = {0xFF, 0xD6};                              // call esi
static const uint8_t kPushPickCall[] = {0xFF, 0x15, 0x30, 0xB6, 0x5E, 0x00}; // call [pushPick]
static const uint8_t kRwtsStart[] = {0x83, 0xEC, 0x0C, 0x56, 0x8B, 0x35, 0x1C, 0x97, 0x65, 0x00};

// Replace an import slot only if it really holds the expected sr.dll function.
static bool PatchSrSlot(uint32_t slot, const char* mangled, void* hook, void** orig)
{
    void* expected = SrExport(mangled);
    return expected && *(void**)Va(slot) == expected && PatchIatSlot(slot, hook, orig);
}

bool InstallView3dHooks(HookReport* r, bool horPlus)
{
    // Clearing the 3D area: needed with any Centered setup (world in the block or at full width).
    bool clear = BytesMatch(Load_RenderFrame_ScissorPtr, kScissorLoad, sizeof(kScissorLoad)) &&
                 BytesMatch(Call_RenderFrame_ClearScissor, kCallEbx, sizeof(kCallEbx)) &&
                 PatchSrSlot(Iat_srGERD_setScissor, "?setScissor@srGERD@@QAEXKKKK@Z",
                             (void*)&HookSetScissor, (void**)&g_origSetScissor);
    r->view3dClear = clear;
    // Without the clear hook the edges of the widened world would stay uncleared (garbage,
    // depth artifacts) — so Hor+ is not enabled then.
    if (!horPlus || !clear) return clear;

    bool plane = BytesMatch(Load_SetViewport_PlanePtr, kPlaneLoad, sizeof(kPlaneLoad)) &&
                 BytesMatch(Call_SetViewport_WorldPlane, kCallEsi, sizeof(kCallEsi)) &&
                 BytesMatch(Call_SetViewport_SkyPlane, kCallEsi, sizeof(kCallEsi)) &&
                 PatchSrSlot(Iat_srCamera_setViewPlaneRect, "?setViewPlane@srCamera@@QAEXABURect@1@N@Z",
                             (void*)&HookSetViewPlaneRect, (void**)&g_origSetViewPlaneRect);
    if (!plane) return false;  // without the widened plane Hor+ must not be enabled (the picture would stretch)

    // Click in 3D: replace the 6-byte call [mem] with a 5-byte call rel32 to the thunk + nop.
    // rel32 is the distance from the end of the instruction (address + 5) to the target.
    bool pick = false;
    if (BytesMatch(Call_RenderFrame_PushPick, kPushPickCall, sizeof(kPushPickCall)) &&
        *(void**)Va(Iat_srGERD_pushPick) == SrExport("?pushPick@srGERD@@QAEXABUPick@1@@Z")) {
        uintptr_t site = (uintptr_t)Va(Call_RenderFrame_PushPick);
        int32_t rel = (int32_t)((uintptr_t)&PickThunk - (site + 5));
        uint8_t code[6] = {0xE8, 0, 0, 0, 0, 0x90};
        memcpy(code + 1, &rel, 4);
        pick = WriteBytes(Call_RenderFrame_PushPick, code, sizeof(code));
    }

    bool thumbs = BytesMatch(RenderWorldToSurface, kRwtsStart, sizeof(kRwtsStart)) &&
                  HookGameFunction(RenderWorldToSurface, (void*)&HookRenderWorldToSurface,
                                   (void**)&g_origRenderWorldToSurface);

    g_horPlus = true;
    r->horPlus = true;
    r->horPlusPick = pick;
    r->horPlusThumbs = thumbs;
    return clear && pick && thumbs;
}
