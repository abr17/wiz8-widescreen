// Proxy for version.dll.
//
// Why: sr.dll (the game engine) imports version.dll. Windows looks for it first
// in the game folder, so our DLL with the same name is loaded instead of the system one
// at the very start of the process — before the game creates its window. This is our "entry point".
//
// So that the game doesn't break, we forward each of the 17 functions of the real version.dll:
// we load the system DLL from SysWOW64 and for each function keep a
// "trampoline" — a tiny function consisting of one `jmp` instruction to the real
// address. JS analogy: `export const f = (...a) => real.f(...a)`, except without
// copying the arguments — we just transfer control, the stack stays as it was.

#include <windows.h>

#include "proxy_version.h"

// The order must match the numbers in FWD(...) below.
static const char* const kNames[] = {
    "GetFileVersionInfoA",       "GetFileVersionInfoByHandle", "GetFileVersionInfoExA",
    "GetFileVersionInfoExW",     "GetFileVersionInfoSizeA",    "GetFileVersionInfoSizeExA",
    "GetFileVersionInfoSizeExW", "GetFileVersionInfoSizeW",    "GetFileVersionInfoW",
    "VerFindFileA",              "VerFindFileW",               "VerInstallFileA",
    "VerInstallFileW",           "VerLanguageNameA",           "VerLanguageNameW",
    "VerQueryValueA",            "VerQueryValueW",
};
static const int kCount = sizeof(kNames) / sizeof(kNames[0]);

// Addresses of the real functions. extern "C" — so that the assembly below finds the symbol
// by the plain name `_g_real` (without C++ name "decoration").
extern "C" FARPROC g_real[17];
FARPROC g_real[17];

static HMODULE g_realModule;

bool ProxyVersionLoad()
{
    // In a 32-bit process on 64-bit Windows, GetSystemDirectory returns
    // System32, but Windows itself redirects the path to SysWOW64 (32-bit DLLs).
    char path[MAX_PATH];
    UINT n = GetSystemDirectoryA(path, MAX_PATH);
    if (n == 0 || n + 13 >= MAX_PATH) {
        return false;
    }
    lstrcatA(path, "\\version.dll");
    g_realModule = LoadLibraryA(path);
    if (!g_realModule) {
        return false;
    }
    for (int i = 0; i < kCount; ++i) {
        g_real[i] = GetProcAddress(g_realModule, kNames[i]);
    }
    return true;
}

// Trampoline: a function without prologue/epilogue (naked) that does
// `jmp dword ptr [g_real + offset]`. Offset = index * 4 bytes (the size of
// a pointer in 32-bit code). The arguments and the return address stay on the stack
// untouched, so the real function sees exactly the call the game made.
#define FWD(index, offset, name)                                                \
    extern "C" __attribute__((naked)) void fwd_##name()                        \
    {                                                                           \
        __asm__ volatile("jmp *(_g_real + " #offset ")");                       \
    }

FWD(0, 0, GetFileVersionInfoA)
FWD(1, 4, GetFileVersionInfoByHandle)
FWD(2, 8, GetFileVersionInfoExA)
FWD(3, 12, GetFileVersionInfoExW)
FWD(4, 16, GetFileVersionInfoSizeA)
FWD(5, 20, GetFileVersionInfoSizeExA)
FWD(6, 24, GetFileVersionInfoSizeExW)
FWD(7, 28, GetFileVersionInfoSizeW)
FWD(8, 32, GetFileVersionInfoW)
FWD(9, 36, VerFindFileA)
FWD(10, 40, VerFindFileW)
FWD(11, 44, VerInstallFileA)
FWD(12, 48, VerInstallFileW)
FWD(13, 52, VerLanguageNameA)
FWD(14, 56, VerLanguageNameW)
FWD(15, 60, VerQueryValueA)
FWD(16, 64, VerQueryValueW)
