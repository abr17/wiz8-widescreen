// Alt+Tab: a known bug — after returning to the game it thinks Alt is still pressed
// (its keyboard hook didn't see the key release while the window was inactive).
// We intercept the game's window procedure and, when focus returns, reset
// its Shift/Ctrl/Alt flags.

#include "hooks_game.h"

#include <windows.h>

#include "game_gog124.h"
#include "log.h"
#include "patch.h"

using namespace gog124;

typedef LRESULT(CALLBACK* WndProc_t)(HWND, UINT, WPARAM, LPARAM);
static WndProc_t g_origWndProc;

static void ResetModifierState()
{
    for (uint32_t a : KeyState_Words) {
        *(uint16_t*)Va(a) = 0;
    }
    memset(Va(KeyState_Bytes), 0, 3);
}

static LRESULT CALLBACK HookWindowProcedure(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    if ((msg == WM_ACTIVATEAPP && wp) || msg == WM_SETFOCUS) {
        ResetModifierState();
        Log("focus regained (msg 0x%X): modifier keys reset", msg);
    }
    return g_origWndProc(hwnd, msg, wp, lp);
}

bool InstallInputHooks(HookReport* r)
{
    r->altTab = HookGameFunction(WindowProcedure, (void*)&HookWindowProcedure, (void**)&g_origWndProc);
    return r->altTab;
}
