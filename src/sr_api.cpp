#include "sr_api.h"

#include <windows.h>

#include "game_gog124.h"
#include "patch.h"

// Method pointer types. __attribute__((thiscall)) tells the compiler:
// put the first argument in ECX, the rest on the stack.
#define SR_THISCALL __attribute__((thiscall))
typedef long(SR_THISCALL* GetDim_t)(void*);
typedef void(SR_THISCALL* SetRect_t)(void*, unsigned long, unsigned long, unsigned long, unsigned long);
typedef void(SR_THISCALL* GetColor_t)(void*, SrColor*);
typedef void(SR_THISCALL* SetColor_t)(void*, const SrColor*);
typedef void(SR_THISCALL* Clear_t)(void*, const unsigned*);  // srFlags by reference = pointer to a DWORD
typedef void(SR_THISCALL* PushPick_t)(void*, const SrPick*);
typedef void(SR_THISCALL* SetPlane_t)(void*, const SrRect*, double);
typedef void(SR_THISCALL* GetPlane_t)(void*, SrRect*, double*);

static HMODULE g_sr;
static GetDim_t g_getWidth, g_getHeight;
static SetRect_t g_setViewPort, g_setScissor;
static GetColor_t g_getClearColor;
static SetColor_t g_setClearColor;
static Clear_t g_clear;
static PushPick_t g_pushPick;
static SetPlane_t g_setViewPlane;
static GetPlane_t g_getViewPlane;

void* SrExport(const char* mangled)
{
    return g_sr ? (void*)GetProcAddress(g_sr, mangled) : nullptr;
}

bool SrApiInit()
{
    g_sr = GetModuleHandleA("sr.dll");
    if (!g_sr) return false;
    // Decorated C++ names — as they are written in sr.dll's export table.
    g_getWidth = (GetDim_t)SrExport("?getWidth@srGERD@@QBEJXZ");
    g_getHeight = (GetDim_t)SrExport("?getHeight@srGERD@@QBEJXZ");
    g_setViewPort = (SetRect_t)SrExport("?setViewPort@srGERD@@QAEXKKKK@Z");
    g_setScissor = (SetRect_t)SrExport("?setScissor@srGERD@@QAEXKKKK@Z");
    g_getClearColor = (GetColor_t)SrExport("?getClearColor@srGERD@@QBEXAAV?$srVector4T@M@@@Z");
    g_setClearColor = (SetColor_t)SrExport("?setClearColor@srGERD@@QAEXABV?$srVector4T@M@@@Z");
    g_clear = (Clear_t)SrExport("?clear@srGERD@@QAEXABV?$srFlags@W4e_buffer@srGERD@@@@@Z");
    g_pushPick = (PushPick_t)SrExport("?pushPick@srGERD@@QAEXABUPick@1@@Z");
    g_setViewPlane = (SetPlane_t)SrExport("?setViewPlane@srCamera@@QAEXABURect@1@N@Z");
    g_getViewPlane = (GetPlane_t)SrExport("?getViewPlane@srCamera@@QBEXAAURect@1@AAN@Z");
    return g_getWidth && g_getHeight && g_setViewPort && g_setScissor && g_getClearColor &&
           g_setClearColor && g_clear && g_pushPick && g_setViewPlane && g_getViewPlane;
}

void* MainGerd()
{
    return *(void**)Va(gog124::g_gerd);
}

bool GerdScreenBlock(void* gerd, ScreenBlock* out)
{
    if (!gerd) return false;
    int W = (int)g_getWidth(gerd), H = (int)g_getHeight(gerd);
    if (W <= 0 || H <= 0) return false;
    *out = MakeScreenBlock(W, H);
    return true;
}

void GerdSetViewPort(void* gerd, const PixelRect& r)
{
    g_setViewPort(gerd, r.x, r.y, r.w, r.h);
}

void GerdSetScissor(void* gerd, const PixelRect& r)
{
    g_setScissor(gerd, r.x, r.y, r.w, r.h);
}

void GerdGetClearColor(void* gerd, SrColor* c) { g_getClearColor(gerd, c); }
void GerdSetClearColor(void* gerd, const SrColor& c) { g_setClearColor(gerd, &c); }

void GerdClear(void* gerd, unsigned flags)
{
    g_clear(gerd, &flags);
}

void GerdPushPick(void* gerd, const SrPick* p) { g_pushPick(gerd, p); }
void CameraSetViewPlane(void* cam, const SrRect& r, double dist) { g_setViewPlane(cam, &r, dist); }
void CameraGetViewPlane(void* cam, SrRect* r, double* dist) { g_getViewPlane(cam, r, dist); }
