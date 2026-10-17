// Comparison harness against the port ([Debug] DiffHarness=1, off by default).
//
// Hook on RenderFrame (once per frame, game thread): on the first frame we load
// w8diff.dll (built by scripts\w8diff\build_dll.ps1 with the same MSVC as the
// port, from the same core) and then call its W8DiffRetailPoll every frame. It
// checks the request file w8diff_retail.req itself and runs the call plan.
// Details: docs/w8diff.md.

#include <windows.h>

#include "game_gog124.h"
#include "hooks_game.h"
#include "patch.h"
#include "runtime.h"

using namespace gog124;

typedef void (*VoidFn)();
typedef int(__cdecl* PollFn)(const char*);

static VoidFn g_origRenderFrame;
static PollFn g_poll;
static bool g_tried;

static void HookRenderFrame()
{
    if (!g_tried) {
        g_tried = true;
        char path[MAX_PATH];
        lstrcpyA(path, g_runtime.gameDir);
        lstrcatA(path, "w8diff.dll");
        HMODULE dll = LoadLibraryA(path);
        g_poll = dll ? (PollFn)GetProcAddress(dll, "W8DiffRetailPoll") : nullptr;
    }
    if (g_poll) {
        g_poll(g_runtime.gameDir);
    }
    g_origRenderFrame();
}

bool InstallDiffHooks()
{
    return HookGameFunction(RenderFrame, (void*)&HookRenderFrame, (void**)&g_origRenderFrame);
}
