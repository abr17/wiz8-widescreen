// Mouse. The game assumes one screen pixel = one unit of its 640x480 screen
// (true on 2001 monitors in 640x480 mode). At 2560x1600 that breaks everything:
// the cursor is locked in the top-left corner. We fix it in the three places where the game
// gets coordinates:
//   1) GetCursorPos (position polled every frame) — convert screen -> logical;
//   2) SetCursorPos (the game moves the cursor itself) — convert logical -> screen;
//   3) MouseHandler (Windows hook for clicks) — convert the click point.
// Formulas are in layout.cpp; the 640x480 block may be stretched or centered.

#include "hooks_game.h"

#include <windows.h>

#include "game_gog124.h"
#include "layout.h"
#include "log.h"
#include "patch.h"

using namespace gog124;

typedef BOOL(WINAPI* GetCursorPos_t)(LPPOINT);
typedef BOOL(WINAPI* SetCursorPos_t)(int, int);
typedef LRESULT(CALLBACK* HookProc_t)(int, WPARAM, LPARAM);

static GetCursorPos_t g_realGetCursorPos;
static SetCursorPos_t g_realSetCursorPos;
static HookProc_t g_origMouseHandler;

static BOOL WINAPI HookGetCursorPos(LPPOINT p)
{
    POINT s;
    if (!g_realGetCursorPos(&s)) return FALSE;
    Block b;
    if (!CurrentBlock(&b)) {
        *p = s;
        return TRUE;
    }
    // No need to clamp: the game clamps the result to 0..640 x 0..480 itself.
    *p = ScreenToLogical(b, s);
    return TRUE;
}

static BOOL WINAPI HookSetCursorPos(int x, int y)
{
    Block b;
    if (!CurrentBlock(&b)) return g_realSetCursorPos(x, y);
    // The game calls SetCursorPos on every position change. If the real cursor
    // is already at that logical point, leave it alone, otherwise it would "snap"
    // to the 640x480 grid and jitter while moving.
    POINT s;
    if (g_realGetCursorPos(&s)) {
        POINT cur = ScreenToLogical(b, s);
        if (cur.x == x && cur.y == y) return TRUE;
    }
    POINT t = LogicalToScreen(b, {x, y});
    return g_realSetCursorPos(t.x, t.y);
}

static LRESULT CALLBACK HookMouseHandler(int code, WPARAM msg, LPARAM lParam)
{
    Block b;
    if (code >= 0 && lParam && CurrentBlock(&b)) {
        // Work on a copy of the structure: don't modify the original Windows structure.
        MOUSEHOOKSTRUCT copy = *(MOUSEHOOKSTRUCT*)lParam;
        POINT l = ScreenToLogical(b, copy.pt);
        // The game stores click coordinates in 16 bits without checks; negative ones
        // (a click in a side bar) would become 65535. We clamp them ourselves.
        if (l.x < 0) l.x = 0;
        if (l.x > 639) l.x = 639;
        if (l.y < 0) l.y = 0;
        if (l.y > 479) l.y = 479;
        copy.pt = l;
        return g_origMouseHandler(code, msg, (LPARAM)&copy);
    }
    return g_origMouseHandler(code, msg, lParam);
}

bool InstallMouseHooks(HookReport* r)
{
    // Take the real functions directly from user32 (not from the exe's slot) so as not
    // to depend on whatever is already in the slot.
    HMODULE user32 = GetModuleHandleA("user32.dll");
    g_realGetCursorPos = (GetCursorPos_t)GetProcAddress(user32, "GetCursorPos");
    g_realSetCursorPos = (SetCursorPos_t)GetProcAddress(user32, "SetCursorPos");
    r->mouse = g_realGetCursorPos && g_realSetCursorPos &&
               PatchIatSlot(Iat_GetCursorPos, (void*)&HookGetCursorPos, nullptr) &&
               PatchIatSlot(Iat_SetCursorPos, (void*)&HookSetCursorPos, nullptr) &&
               HookGameFunction(MouseHandler, (void*)&HookMouseHandler, (void**)&g_origMouseHandler);
    return r->mouse;
}
