#pragma once

// Direct calls into the sr.dll engine (via its exports), bypassing the exe's import table.
// Needed because we partly replace the import slots with our own hooks, and the
// hooks themselves need the "real" functions.
//
// All these functions are C++ methods of the classes srGERD (renderer) and srCamera (camera).
// thiscall convention: the object pointer (this) goes in the ECX register, the other
// arguments go on the stack, and the function cleans the stack itself. In JS this would be
// obj.method(args): obj is ECX.

#include "layout.h"

// Camera view plane: 4 doubles in the order {left, bottom, right, top}.
// Order verified in sr.dll: getHorizontalFOV reads +0 and +16, getVerticalFOV — +8 and +24.
struct SrRect {
    double l, b, r, t;
};
// A "click in 3D" point (pushPick): x, y in -1..1 coordinates relative to the 3D view.
struct SrPick {
    float x, y, z, u0, u1;
};
struct SrColor {
    float r, g, b, a;
};

// Find the exports in the already loaded sr.dll. false — no sr.dll or the names don't match.
// Safe from DllMain (GetModuleHandle/GetProcAddress load nothing).
bool SrApiInit();
// Export address by decorated C++ name (for checking import slots).
void* SrExport(const char* mangled);

// The game's renderer (*g_gerd); nullptr while there is no render window.
void* MainGerd();
// Size of the render buffer and the 4:3 block in it. false — size not known yet.
bool GerdScreenBlock(void* gerd, ScreenBlock* out);

void GerdSetViewPort(void* gerd, const PixelRect& r);
void GerdSetScissor(void* gerd, const PixelRect& r);
void GerdGetClearColor(void* gerd, SrColor* c);
void GerdSetClearColor(void* gerd, const SrColor& c);
void GerdClear(void* gerd, unsigned flags);  // 1 — color, 2 — depth
void GerdPushPick(void* gerd, const SrPick* p);
void CameraSetViewPlane(void* cam, const SrRect& r, double dist);
void CameraGetViewPlane(void* cam, SrRect* r, double* dist);
