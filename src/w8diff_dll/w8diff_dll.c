/* w8diff.dll: the differential harness core for the retail Wiz8.exe.
   version.dll loads it when wiz8ws.ini has [Debug] DiffHarness=1 and calls
   W8DiffRetailPoll from its RenderFrame hook on the game thread. The core is
   the same file the rebuilt Wiz8Runtime.exe compiles
   (decomp/src/w8diff/w8diff_core.c). */
#include <windows.h>
#include <string.h>

#include "w8diff_core.h"

typedef void(__cdecl* SrandFn)(unsigned int);
static SrandFn g_srand;

/* The retail game calls rand() from the MSVCRT.DLL next to Wiz8.exe, so the
   seed has to go to that CRT, not to this DLL's own static one. */
static void __cdecl SeedRetailRandom(unsigned int seed)
{
    if (g_srand) {
        g_srand(seed);
    }
}

__declspec(dllexport) int __cdecl W8DiffRetailPoll(const char* game_dir)
{
    static W8DiffHost host;
    static char dir[MAX_PATH];
    if (host.name == 0) {
        HMODULE crt = GetModuleHandleA("msvcrt.dll");
        g_srand = crt ? (SrandFn)GetProcAddress(crt, "srand") : 0;
        lstrcpynA(dir, game_dir, MAX_PATH);
        host.name = "retail";
        host.dir = dir;
        host.seed = SeedRetailRandom;
    }
    return W8DiffPoll(&host);
}
