#pragma once

// Link between hooks_hud.cpp (owns the RenderScene hook) and hooks_view3d.cpp (Hor+).

#include "layout.h"
#include "sr_api.h"

// Where to draw the world pass (RenderScene with vp == &g_viewport), in pixels:
//   Hor+ in effect  -> full screen width (x = 0, w = W), height as in the game;
//   otherwise       -> the g_viewport rectangle inside the 4:3 block (like the 2D).
PixelRect View3dWorldRect(const ScreenBlock& b, const int* vp640);

// Is the world currently widened horizontally (the camera plane is widened AND the 3D view
// touches the 4:3 edges). The world rectangle and the click recomputation depend on this.
bool View3dWorldWidened();

// Once per frame (first RenderScene): if the screen size changed since
// SetViewport widened the plane (Alt+Tab, mode change without SetViewport),
// recompute the widened plane for the new size (or restore the normal one at 4:3).
void View3dSyncPlane(const ScreenBlock& b);

// Before the world/sky pass: if the plane is widened but the 3D view does NOT currently
// touch the 4:3 edges (the game changed g_viewport without SetViewport — character
// creation, loading), temporarily give the camera its normal plane back, as in the original.
// Returns true if swapped; then View3dNarrowEnd is mandatory after the pass.
struct View3dPlaneSwap {
    void* cam;
    SrRect saved;  // the widened plane to restore after the pass
    double dist;
};
bool View3dNarrowBegin(void* cam, View3dPlaneSwap* s);
void View3dNarrowEnd(const View3dPlaneSwap& s);

// Fill the side bars with black (hooks_hud.cpp). Called from the setScissor hook BEFORE
// the game clears the 3D area: then the game itself paints the widened world rows
// with the fog color over our black, not the other way round.
void HudClearBarsBeforeWorldClear(void* gerd, const ScreenBlock& b);
