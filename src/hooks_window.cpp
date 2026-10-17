// Hooks on window functions. In Phase 1 — observation only: we log the parameters
// the game (and the sr.dll engine) create windows with, and change nothing.
//
// How a MinHook hook works (like monkey-patching in JS):
//   const orig = user32.CreateWindowExA;
//   user32.CreateWindowExA = (...a) => { log(a); return orig(...a); };
// Except that MinHook rewrites the first bytes of the function itself in user32.dll's memory
// into a jump to our function, and `orig` is a "trampoline" holding the saved bytes.
// That is why calls from ANY module of the process (exe, sr.dll, srDD_*) are intercepted.

#include "hooks_window.h"

#include <windows.h>

#include <MinHook.h>

#include "runtime.h"
#include "log.h"

// Type of CreateWindowExA — needed to call the original through a pointer.
// WINAPI = the stdcall calling convention: the function itself removes the arguments from the stack.
typedef HWND(WINAPI* CreateWindowExA_t)(DWORD, LPCSTR, LPCSTR, DWORD, int, int, int, int, HWND,
                                         HMENU, HINSTANCE, LPVOID);
static CreateWindowExA_t g_origCreateWindowExA;

// The window class name may be not a string but a numeric "atom" (then the pointer is < 0x10000).
static const char* SafeStr(LPCSTR s, char* buf, size_t n)
{
    if (!s) return "(null)";
    if ((ULONG_PTR)s < 0x10000) {
        wsprintfA(buf, "#%u", (unsigned)(ULONG_PTR)s);
        return buf;
    }
    lstrcpynA(buf, s, (int)n);
    return buf;
}

// Who called us: find the module by the return address (exe, sr.dll, etc.).
static const char* CallerModule(void* ret, char* buf, size_t n)
{
    HMODULE m = nullptr;
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                               GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCSTR)ret, &m) &&
        GetModuleFileNameA(m, buf, (DWORD)n)) {
        const char* slash = buf;
        for (const char* p = buf; *p; ++p) {
            if (*p == '\\' || *p == '/') slash = p + 1;
        }
        return slash;
    }
    return "?";
}

static HWND WINAPI HookCreateWindowExA(DWORD exStyle, LPCSTR className, LPCSTR windowName,
                                       DWORD style, int x, int y, int w, int h, HWND parent,
                                       HMENU menu, HINSTANCE inst, LPVOID param)
{
    // The first CreateWindowExA call is no longer inside DllMain, so here we may open the log,
    // compute the hash, etc. EnsureRuntime() does this exactly once.
    EnsureRuntime();

    HWND hwnd = g_origCreateWindowExA(exStyle, className, windowName, style, x, y, w, h, parent,
                                      menu, inst, param);

    if (g_runtime.active && g_runtime.config.logWindowCalls) {
        char cls[128], title[128], caller[MAX_PATH];
        Log("CreateWindowExA from %s: class=\"%s\" title=\"%s\" exStyle=0x%08lX style=0x%08lX "
            "pos=(%d,%d) size=(%d,%d) parent=%p -> hwnd=%p",
            CallerModule(__builtin_return_address(0), caller, sizeof(caller)),
            SafeStr(className, cls, sizeof(cls)), SafeStr(windowName, title, sizeof(title)),
            exStyle, style, x, y, w, h, (void*)parent, (void*)hwnd);
    }
    return hwnd;
}

bool InstallWindowHooks()
{
    if (MH_CreateHookApi(L"user32", "CreateWindowExA", (LPVOID)&HookCreateWindowExA,
                         (LPVOID*)&g_origCreateWindowExA) != MH_OK) {
        return false;
    }
    return MH_EnableHook(MH_ALL_HOOKS) == MH_OK;
}
