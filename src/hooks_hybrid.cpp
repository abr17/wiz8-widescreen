// Hybrid ([Hybrid] Enabled=1): the original Wiz8.exe + port functions from wiz8hy.dll.
//
// The transplanted functions must be in place before the game starts initializing
// (InitializeVideoManager is called from WinMain before the window is even created), hence the hook
// on WinMain (0x00401670): by that point all DLLs are loaded and initialized, so it is
// safe to load wiz8hy.dll and call its HybridInstall. Details: docs/hybrid.md.

#include <windows.h>

#include "filenames.h"
#include "patch.h"
#include "runtime.h"

typedef int(WINAPI* WinMainFn)(HINSTANCE, HINSTANCE, LPSTR, int);
static WinMainFn g_origWinMain;
static constexpr uint32_t kWinMain = 0x00401670;

int g_hybridHooks = -2;  // -2: not attempted, -1: DLL failed to load, otherwise the number of replacements

static int WINAPI HookWinMain(HINSTANCE inst, HINSTANCE prev, LPSTR cmd, int show)
{
    char path[MAX_PATH];
    lstrcpyA(path, g_runtime.gameDir);
    lstrcatA(path, "wiz8hy.dll");
    HMODULE dll = LoadLibraryA(path);
    typedef int(__cdecl * InstallFn)(const char*);
    InstallFn install = dll ? (InstallFn)GetProcAddress(dll, "HybridInstall") : nullptr;
    g_hybridHooks = install ? install(g_runtime.gameDir) : -1;
    if (g_runtime.config.utf8FileNames) g_runtime.game.fileNames = InstallFileNameHooks(dll);
    return g_origWinMain(inst, prev, cmd, show);
}

bool InstallHybridHook()
{
    return HookGameFunction(kWinMain, (void*)&HookWinMain, (void**)&g_origWinMain);
}
