// Hybrid (trial, 2026-10-13): the original Wiz8.exe + port functions.
//
// wiz8hy.dll is built by scripts\hybrid\build_hybrid.ps1 from the port sources: everything
// that exists in the original is bound to its addresses, while the functions from scripts\hybrid\transplant_wide.json are ours.
// With [Hybrid] Enabled=1, version.dll loads the DLL when the game window is created and calls
// HybridInstall: each transplanted function of the original gets a jmp at its start to
// the port's version (table wiz8hy_hooks.txt: original address, RVA in the DLL). Plus a frame
// rate cap: a wrapper around the original RenderFrame.

#include <windows.h>
#include <stdio.h>
#include <string.h>

#include "wiz8/canvas.h"

static FILE* g_log;

static void HyLog(const char* fmt, ...)
{
    if (!g_log) {
        return;
    }
    va_list args;
    va_start(args, fmt);
    vfprintf(g_log, fmt, args);
    va_end(args);
    fputc('\n', g_log);
    fflush(g_log);
}

static bool WriteCode(unsigned addr, const unsigned char* bytes, unsigned len)
{
    DWORD old;
    if (!VirtualProtect((void*)(UINT_PTR)addr, len, PAGE_EXECUTE_READWRITE, &old)) {
        return false;
    }
    memcpy((void*)(UINT_PTR)addr, bytes, len);
    VirtualProtect((void*)(UINT_PTR)addr, len, old, &old);
    FlushInstructionCache(GetCurrentProcess(), (void*)(UINT_PTR)addr, len);
    return true;
}

static bool PatchJump(unsigned from, unsigned to)
{
    unsigned char code[5];
    int rel = (int)(to - (from + 5));
    code[0] = 0xE9;
    memcpy(code + 1, &rel, 4);
    return WriteCode(from, code, 5);
}

// --- frame rate cap: the original RenderFrame (cdecl void(), 0x00426790) ---
// The first 7 bytes (sub esp,3Ch; lea ecx,[esp+10h]) are moved into the trampoline.
typedef void (*VoidFn)(void);
static const unsigned kRenderFrame = 0x00426790;
static const unsigned char kRenderFrameHead[7] = {0x83, 0xEC, 0x3C, 0x8D, 0x4C, 0x24, 0x10};
static unsigned char* g_renderTrampoline;

static void HybridRenderFrame(void)
{
    CanvasCountFrame();
    CanvasLimitFrameRate();
    ((VoidFn)(void*)g_renderTrampoline)();
}

static bool InstallFrameCap(void)
{
    if (memcmp((void*)(UINT_PTR)kRenderFrame, kRenderFrameHead, sizeof(kRenderFrameHead)) != 0) {
        HyLog("frame cap: RenderFrame bytes differ (already hooked?), skipped");
        return false;
    }
    g_renderTrampoline = (unsigned char*)VirtualAlloc(0, 32, MEM_COMMIT | MEM_RESERVE,
                                                      PAGE_EXECUTE_READWRITE);
    if (!g_renderTrampoline) {
        return false;
    }
    memcpy(g_renderTrampoline, kRenderFrameHead, sizeof(kRenderFrameHead));
    g_renderTrampoline[7] = 0xE9;
    int rel = (int)((kRenderFrame + 7) - ((unsigned)(UINT_PTR)g_renderTrampoline + 12));
    memcpy(g_renderTrampoline + 8, &rel, 4);
    return PatchJump(kRenderFrame, (unsigned)(UINT_PTR)&HybridRenderFrame);
}

// --- crash log: address and stack of the first access violations (symbolize.py) ---
static LONG g_crashLogged;

static LONG CALLBACK HybridCrashLogger(EXCEPTION_POINTERS* info)
{
    DWORD code = info->ExceptionRecord->ExceptionCode;
    if (code != EXCEPTION_ACCESS_VIOLATION && code != EXCEPTION_ILLEGAL_INSTRUCTION &&
        code != EXCEPTION_PRIV_INSTRUCTION && code != EXCEPTION_INT_DIVIDE_BY_ZERO) {
        return EXCEPTION_CONTINUE_SEARCH;
    }
    if (InterlockedIncrement(&g_crashLogged) > 8) {
        return EXCEPTION_CONTINUE_SEARCH;
    }
    CONTEXT* c = info->ContextRecord;
    HyLog("exception %08x at %08x (first chance; the game may still handle it)", code, c->Eip);
    HyLog("  eax=%08x ebx=%08x ecx=%08x edx=%08x esi=%08x edi=%08x ebp=%08x esp=%08x", c->Eax,
          c->Ebx, c->Ecx, c->Edx, c->Esi, c->Edi, c->Ebp, c->Esp);
    const unsigned* sp = (const unsigned*)(UINT_PTR)c->Esp;
    for (int i = 0; i < 96; i += 8) {
        if (IsBadReadPtr(sp + i, 32)) {
            break;
        }
        HyLog("  stack %08x %08x %08x %08x %08x %08x %08x %08x", sp[i], sp[i + 1], sp[i + 2],
              sp[i + 3], sp[i + 4], sp[i + 5], sp[i + 6], sp[i + 7]);
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

extern "C" __declspec(dllexport) int __cdecl HybridInstall(const char* dir)
{
    AddVectoredExceptionHandler(0, HybridCrashLogger);
    char path[MAX_PATH];
    _snprintf(path, sizeof(path), "%swiz8hy.log", dir);
    g_log = fopen(path, "w");
    HMODULE self = 0;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                           GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)&HybridInstall, &self);
    unsigned base = (unsigned)(UINT_PTR)self;
    HyLog("wiz8hy loaded at %08x", base);

    _snprintf(path, sizeof(path), "%swiz8hy_hooks.txt", dir);
    FILE* f = fopen(path, "r");
    int count = 0;
    if (!f) {
        HyLog("no %s", path);
        return 0;
    }
    char line[512];
    while (fgets(line, sizeof(line), f)) {
        unsigned retail = 0, rva = 0;
        char name[400] = "";
        if (sscanf(line, "%x %x %399s", &retail, &rva, name) < 2) {
            continue;
        }
        bool ok = PatchJump(retail, base + rva);
        HyLog("%s %08x -> %08x %s", ok ? "hook" : "FAIL", retail, base + rva, name);
        count += ok;
    }
    fclose(f);
    HyLog("frame cap: %s (MaxFps=%d), ViewDistance=%.2f", InstallFrameCap() ? "on" : "off",
          DisplayMaxFps(), DisplayViewDistanceScale());
    return count;
}
