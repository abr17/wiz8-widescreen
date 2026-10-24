// Crash and exit diagnostics, see diagnostics.h.
//
// How the exit trace works: a process that ends itself normally goes through
// ntdll!RtlExitUserProcess (ExitProcess, the C runtime's exit()) or TerminateProcess.
// MinHook redirects both to our functions, which write to the log who called them (the
// return addresses found on the stack) before letting the process end. A normal quit from
// the menu shows up there too; the stack and the game's error message tell them apart.
// Exceptions go to CrashRecord: fatal ones in the game's code when they are raised
// (FirstChanceCrash, below), unhandled ones from the unhandled-exception filter. Not seen (the log just stops): fail-fast
// (__fastfail, /GS failures, abort() of a modern C runtime), a direct NtTerminateProcess, a
// kill from another process (Task Manager, a launcher, an antivirus).

#include "diagnostics.h"

#include <windows.h>
#include <dbghelp.h>
#include <psapi.h>  // types only; the function comes from kernel32 at run time

#include <MinHook.h>

#include <stdio.h>
#include <string.h>

#include "log.h"
#include "runtime.h"

namespace {

const int kKeepSessions = 10;
const int kKeepDumps = 3;
const DWORD kHeartbeatMs = 60 * 1000;

// Globals of the retail Wiz8.exe (GOG/Steam 1.2.4), read only when that exe is identified.
const ULONG_PTR kGameErrorMessage = 0x006505ac;  // gzErrorMsg[2048] (sgp.cpp): text of a fatal error
const ULONG_PTR kCombatMode = 0x00683f94;        // gXStatus.fCombatMode

char g_logDir[MAX_PATH];  // <game>\Wiz8Logs\ (with the trailing '\')
DWORD g_startTick;
unsigned g_peakUsedMb;
LONG g_exitLogged;

/* ---------------- Wiz8Logs\ folder ---------------- */

// Names in Wiz8Logs\ matching the pattern, sorted oldest first (names start with the date).
int ListNames(const char* pattern, bool directories, char names[][64], int max)
{
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s%s", g_logDir, pattern);
    WIN32_FIND_DATAA data;
    HANDLE find = FindFirstFileA(path, &data);
    if (find == INVALID_HANDLE_VALUE) {
        return 0;
    }
    int count = 0;
    do {
        bool isDir = (data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
        if (isDir != directories || data.cFileName[0] == '.' || count >= max) {
            continue;
        }
        lstrcpynA(names[count++], data.cFileName, 64);
    } while (FindNextFileA(find, &data));
    FindClose(find);
    for (int i = 1; i < count; ++i) {  // insertion sort, a handful of names
        for (int j = i; j > 0 && lstrcmpA(names[j - 1], names[j]) > 0; --j) {
            char t[64];
            lstrcpyA(t, names[j]);
            lstrcpyA(names[j], names[j - 1]);
            lstrcpyA(names[j - 1], t);
        }
    }
    return count;
}

void DeleteFolder(const char* name)
{
    char pattern[MAX_PATH];
    snprintf(pattern, sizeof(pattern), "%s%s\\*", g_logDir, name);
    WIN32_FIND_DATAA data;
    HANDLE find = FindFirstFileA(pattern, &data);
    if (find != INVALID_HANDLE_VALUE) {
        do {
            if (!(data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) {
                char file[MAX_PATH];
                snprintf(file, sizeof(file), "%s%s\\%s", g_logDir, name, data.cFileName);
                DeleteFileA(file);
            }
        } while (FindNextFileA(find, &data));
        FindClose(find);
    }
    char dir[MAX_PATH];
    snprintf(dir, sizeof(dir), "%s%s", g_logDir, name);
    RemoveDirectoryA(dir);
}

void PruneOldest(const char* pattern, bool directories, int keep)
{
    static char names[64][64];
    int count = ListNames(pattern, directories, names, 64);
    for (int i = 0; i < count - keep; ++i) {
        if (directories) {
            DeleteFolder(names[i]);
        } else {
            char file[MAX_PATH];
            snprintf(file, sizeof(file), "%s%s", g_logDir, names[i]);
            DeleteFileA(file);
        }
    }
}

void LocalTimeName(char* out, size_t n, const SYSTEMTIME& t)
{
    snprintf(out, n, "%04d-%02d-%02d_%02d-%02d-%02d", t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute,
             t.wSecond);
}

/* ---------------- memory ---------------- */

struct MemInfo {
    unsigned privateMb;      // memory the game allocated
    unsigned usedMb;         // address space in use (of totalMb, 2048 for this 32-bit exe)
    unsigned totalMb;
    unsigned largestFreeMb;  // biggest free block: big allocations fail when this gets small
};

MemInfo ReadMemory()
{
    MemInfo r = {};
    typedef BOOL(WINAPI * GetMemInfo_t)(HANDLE, PROCESS_MEMORY_COUNTERS*, DWORD);
    static GetMemInfo_t getMemInfo =
        (GetMemInfo_t)GetProcAddress(GetModuleHandleA("kernel32.dll"), "K32GetProcessMemoryInfo");
    PROCESS_MEMORY_COUNTERS_EX counters = {};
    counters.cb = sizeof(counters);
    if (getMemInfo &&
        getMemInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS*)&counters, sizeof(counters))) {
        r.privateMb = (unsigned)(counters.PrivateUsage >> 20);
    }
    MEMORYSTATUSEX status = {};
    status.dwLength = sizeof(status);
    if (GlobalMemoryStatusEx(&status)) {
        r.totalMb = (unsigned)(status.ullTotalVirtual >> 20);
        r.usedMb = (unsigned)((status.ullTotalVirtual - status.ullAvailVirtual) >> 20);
    }
    SYSTEM_INFO info;
    GetSystemInfo(&info);
    ULONG_PTR address = (ULONG_PTR)info.lpMinimumApplicationAddress;
    SIZE_T largest = 0;
    MEMORY_BASIC_INFORMATION region;
    while (address < (ULONG_PTR)info.lpMaximumApplicationAddress &&
           VirtualQuery((void*)address, &region, sizeof(region))) {
        if (region.State == MEM_FREE && region.RegionSize > largest) {
            largest = region.RegionSize;
        }
        address = (ULONG_PTR)region.BaseAddress + region.RegionSize;
    }
    r.largestFreeMb = (unsigned)(largest >> 20);
    if (r.usedMb > g_peakUsedMb) {
        g_peakUsedMb = r.usedMb;
    }
    return r;
}

int CombatFlag()
{
    if (g_runtime.exe != ExeVersion::Gog124 || IsBadReadPtr((void*)kCombatMode, 1)) {
        return -1;
    }
    return *(volatile unsigned char*)kCombatMode;
}

DWORD WINAPI Heartbeat(LPVOID)
{
    for (;;) {
        MemInfo m = ReadMemory();
        Log("mem: private %u MB, address space %u of %u MB used, largest free block %u MB, "
            "combat=%d",
            m.privateMb, m.usedMb, m.totalMb, m.largestFreeMb, CombatFlag());
        Sleep(kHeartbeatMs);
    }
}

/* ---------------- call stacks ---------------- */

// Module (exe or DLL) whose executable code contains the address.
bool CodeModule(ULONG_PTR address, char* name, size_t n, ULONG_PTR* base)
{
    MEMORY_BASIC_INFORMATION region;
    if (!VirtualQuery((void*)address, &region, sizeof(region)) || region.State != MEM_COMMIT ||
        region.Type != MEM_IMAGE) {
        return false;
    }
    const DWORD exec =
        PAGE_EXECUTE | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY;
    if (!(region.Protect & exec)) {
        return false;
    }
    char path[MAX_PATH];
    if (!GetModuleFileNameA((HMODULE)region.AllocationBase, path, MAX_PATH)) {
        return false;
    }
    const char* file = path;
    for (const char* p = path; *p; ++p) {
        if (*p == '\\' || *p == '/') {
            file = p + 1;
        }
    }
    lstrcpynA(name, file, (int)n);
    *base = (ULONG_PTR)region.AllocationBase;
    return true;
}

// Is the instruction right before this address a call (so the address is a return address)?
bool FollowsCall(ULONG_PTR address)
{
    if (IsBadReadPtr((void*)(address - 7), 7)) {
        return false;
    }
    const unsigned char* p = (const unsigned char*)address;
    if (p[-5] == 0xE8) {
        return true;  // call rel32
    }
    // call through memory or a register: FF /2 with 0, 1, 4 or 5 more bytes
    const int lengths[] = {2, 3, 4, 6, 7};
    for (int len : lengths) {
        if (p[-len] == 0xFF && ((p[-len + 1] >> 3) & 7) == 2) {
            return true;
        }
    }
    return false;
}

// Return addresses found on the stack from `from` up: the chain of calls that led here.
// With skipOwnFrames the scan starts after the first return into this DLL (the exit hook's
// caller), so stale values in our own logging frames do not clutter the trace.
void LogStack(const void* from, bool skipOwnFrames)
{
    HMODULE self = nullptr;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                           GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)&FollowsCall, &self);
    bool started = !skipOwnFrames;
    const NT_TIB* tib = (const NT_TIB*)NtCurrentTeb();
    const ULONG_PTR* sp = (const ULONG_PTR*)from;
    const ULONG_PTR* end = (const ULONG_PTR*)tib->StackBase;
    if (end > sp + 8192) {
        end = sp + 8192;  // 32 KB is plenty
    }
    int shown = 0;
    for (; sp < end && shown < 40; ++sp) {
        ULONG_PTR value = *sp;
        char name[64];
        ULONG_PTR base;
        if (value < 0x10000 || !CodeModule(value, name, sizeof(name), &base) ||
            !FollowsCall(value)) {
            continue;
        }
        if (!started) {
            started = base == (ULONG_PTR)self;
            continue;
        }
        Log("  +%04x %s+%06x (%08x)", (unsigned)((const char*)sp - (const char*)from), name,
            (unsigned)(value - base), (unsigned)value);
        ++shown;
    }
}

/* ---------------- process exit ---------------- */

typedef void(NTAPI* RtlExitUserProcess_t)(LONG);
typedef BOOL(WINAPI* TerminateProcess_t)(HANDLE, UINT);
RtlExitUserProcess_t g_origExit;
TerminateProcess_t g_origTerminate;

void LogExit(const char* via, unsigned code)
{
    if (InterlockedExchange(&g_exitLogged, 1)) {
        return;  // the first exit path explains it; ExitProcess may call TerminateProcess
    }
    unsigned seconds = (GetTickCount() - g_startTick) / 1000;
    Log("process exit via %s, code %u (0x%08x), after %u min %u s, combat=%d", via, code, code,
        seconds / 60, seconds % 60, CombatFlag());
    if (g_runtime.exe == ExeVersion::Gog124 && !IsBadReadPtr((void*)kGameErrorMessage, 1)) {
        char message[700];
        lstrcpynA(message, (const char*)kGameErrorMessage, sizeof(message));
        for (char* p = message; *p; ++p) {
            if (*p == '\r' || *p == '\n') {
                *p = ' ';
            }
        }
        if (message[0] != '\0') {
            Log("game error message: %s", message);
        }
    }
    MemInfo m = ReadMemory();
    Log("mem at exit: private %u MB, address space %u of %u MB used (peak %u), largest free "
        "block %u MB",
        m.privateMb, m.usedMb, m.totalMb, g_peakUsedMb, m.largestFreeMb);
    Log("exit call stack (return addresses; for Wiz8.exe the address is 0x400000 + offset):");
    int marker = 0;
    LogStack(&marker, true);
}

void NTAPI HookExit(LONG code)
{
    LogExit("ExitProcess", (unsigned)code);
    g_origExit(code);
}

BOOL WINAPI HookTerminate(HANDLE process, UINT code)
{
    if (process == GetCurrentProcess() || GetProcessId(process) == GetCurrentProcessId()) {
        LogExit("TerminateProcess", code);
    }
    return g_origTerminate(process, code);
}

/* ---------------- crash ---------------- */

void WriteMinidump(EXCEPTION_POINTERS* info, DWORD crashedThread)
{
    typedef BOOL(WINAPI * MiniDumpWriteDump_t)(HANDLE, DWORD, HANDLE, MINIDUMP_TYPE,
                                               PMINIDUMP_EXCEPTION_INFORMATION,
                                               PMINIDUMP_USER_STREAM_INFORMATION,
                                               PMINIDUMP_CALLBACK_INFORMATION);
    HMODULE dbghelp = LoadLibraryA("dbghelp.dll");
    MiniDumpWriteDump_t write =
        dbghelp ? (MiniDumpWriteDump_t)GetProcAddress(dbghelp, "MiniDumpWriteDump") : nullptr;
    if (!write) {
        Log("minidump: dbghelp.dll not available");
        return;
    }
    SYSTEMTIME t;
    GetLocalTime(&t);
    char stamp[32];
    LocalTimeName(stamp, sizeof(stamp), t);
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%scrash-%s.dmp", g_logDir, stamp);
    CreateDirectoryA(g_logDir, nullptr);
    HANDLE file = CreateFileA(path, GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL,
                              nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        Log("minidump: cannot create %s", path);
        return;
    }
    MINIDUMP_EXCEPTION_INFORMATION exception = {crashedThread, info, FALSE};
    BOOL ok = write(GetCurrentProcess(), GetCurrentProcessId(), file,
                    (MINIDUMP_TYPE)(MiniDumpWithDataSegs | MiniDumpWithIndirectlyReferencedMemory),
                    &exception, nullptr, nullptr);
    CloseHandle(file);
    Log("minidump: %s %s", ok ? "written" : "FAILED", path);
    PruneOldest("crash-*.dmp", false, kKeepDumps);
}

struct DumpRequest {
    EXCEPTION_POINTERS* info;
    DWORD thread;
};

// The thread writing a crash down right now (0: none).
volatile LONG g_crashWriter;
// The crashing thread stopped waiting for its dump (30 s): the dump thread frees the writer.
volatile LONG g_dumpOrphaned;

DWORD WINAPI DumpThread(LPVOID param)
{
    DumpRequest* request = (DumpRequest*)param;
    WriteMinidump(request->info, request->thread);
    if (InterlockedExchange(&g_dumpOrphaned, 0)) InterlockedExchange(&g_crashWriter, 0);
    return 0;
}

/* The last exception written down (by the first-chance handler or the unhandled-exception
   filter), so the same one reaching both is recorded once. */
const EXCEPTION_RECORD* volatile g_crashRecord;
volatile DWORD g_crashCode;
void* volatile g_crashAddress;
volatile DWORD g_crashThread;

// firstChance: called by the vectored handler when the exception is raised, before any
// __except of the code had its say, so the code may still handle it and go on.
LONG CrashRecord(EXCEPTION_POINTERS* info, bool firstChance)
{
    const EXCEPTION_RECORD* record = info->ExceptionRecord;
    const DWORD self = GetCurrentThreadId();
    // The same exception a second time (the first-chance handler wrote it, then the dispatch
    // reached the unhandled-exception filter): already recorded.
    if (g_crashRecord == record && g_crashCode == record->ExceptionCode &&
        g_crashAddress == record->ExceptionAddress && g_crashThread == self) {
        return EXCEPTION_CONTINUE_SEARCH;
    }
    // A fault inside the writing itself (this thread is already writing a crash down): do not
    // write again, let Windows go on with it.
    if ((DWORD)g_crashWriter == self) {
        return EXCEPTION_CONTINUE_SEARCH;
    }
    // One crash at a time: another thread that faults meanwhile waits until the first crash is
    // written down, so the process does not end (and leave an empty dump) in the middle of it.
    while (InterlockedCompareExchange(&g_crashWriter, (LONG)self, 0) != 0) {
        Sleep(50);
    }
    g_crashRecord = record;
    g_crashCode = record->ExceptionCode;
    g_crashAddress = record->ExceptionAddress;
    g_crashThread = self;
    ULONG_PTR at = (ULONG_PTR)record->ExceptionAddress;
    char name[64] = "?";
    ULONG_PTR base = 0;
    CodeModule(at, name, sizeof(name), &base);
    Log("CRASH%s: exception 0x%08x at %s+%06x (%08x), combat=%d",
        firstChance ? " (first chance: harmless if the game goes on after it)" : "",
        (unsigned)record->ExceptionCode, name, (unsigned)(at - base), (unsigned)at, CombatFlag());
    if (record->ExceptionCode == EXCEPTION_ACCESS_VIOLATION && record->NumberParameters >= 2) {
        Log("  %s address %08x", record->ExceptionInformation[0] == 1 ? "writing" : "reading",
            (unsigned)record->ExceptionInformation[1]);
    }
    MemInfo m = ReadMemory();
    Log("mem at crash: private %u MB, address space %u of %u MB used, largest free block %u MB",
        m.privateMb, m.usedMb, m.totalMb, m.largestFreeMb);
    Log("crash call stack:");
    LogStack((const void*)(ULONG_PTR)info->ContextRecord->Esp, false);
    // The dump is written by a new thread: after a stack overflow the crashing thread has
    // almost no stack left, and loading dbghelp and writing the dump need a lot of it. The
    // wait is limited in case the crash happened while Windows' loader lock was held (the new
    // thread could not start then).
    DumpRequest request = {info, GetCurrentThreadId()};
    HANDLE thread = CreateThread(nullptr, 0, DumpThread, &request, 0, nullptr);
    if (!thread) {
        Log("minidump: cannot start the dump thread");
    } else {
        if (WaitForSingleObject(thread, 30000) != WAIT_OBJECT_0) {
            // dbghelp is not thread-safe: the writer stays set until the dump thread is done
            // (it frees it), so a later crash waits instead of starting a second dump.
            Log("minidump: not finished in 30 s");
            InterlockedExchange(&g_dumpOrphaned, 1);
            if (WaitForSingleObject(thread, 0) == WAIT_OBJECT_0 && InterlockedExchange(&g_dumpOrphaned, 0)) {
                InterlockedExchange(&g_crashWriter, 0);  // it finished just now
            }
            CloseHandle(thread);
            return EXCEPTION_CONTINUE_SEARCH;
        }
        CloseHandle(thread);
    }
    InterlockedExchange(&g_crashWriter, 0);
    return EXCEPTION_CONTINUE_SEARCH;  // then Windows handles it as usual
}

LONG WINAPI CrashFilter(EXCEPTION_POINTERS* info)
{
    return CrashRecord(info, false);
}

bool HookApi(LPCWSTR module, LPCSTR name, LPVOID detour, LPVOID* original)
{
    LPVOID target = nullptr;
    return MH_CreateHookApiEx(module, name, detour, original, &target) == MH_OK &&
           MH_EnableHook(target) == MH_OK;
}

}  // namespace

void DiagRotateLogs(const char* gameDir)
{
    snprintf(g_logDir, sizeof(g_logDir), "%sWiz8Logs\\", gameDir);
    static const char* const kLogs[] = {"wiz8ws.log", "wiz8hy.log", "wiz8wide.log"};
    // The previous session is named after the last time one of its logs was written.
    FILETIME newest = {};
    bool any = false;
    for (const char* log : kLogs) {
        char path[MAX_PATH];
        snprintf(path, sizeof(path), "%s%s", gameDir, log);
        WIN32_FILE_ATTRIBUTE_DATA data;
        if (GetFileAttributesExA(path, GetFileExInfoStandard, &data)) {
            any = true;
            if (CompareFileTime(&data.ftLastWriteTime, &newest) > 0) {
                newest = data.ftLastWriteTime;
            }
        }
    }
    if (!any) {
        return;
    }
    FILETIME local;
    SYSTEMTIME t;
    FileTimeToLocalFileTime(&newest, &local);
    FileTimeToSystemTime(&local, &t);
    char stamp[32];
    LocalTimeName(stamp, sizeof(stamp), t);
    char session[MAX_PATH];
    snprintf(session, sizeof(session), "%s%s\\", g_logDir, stamp);
    CreateDirectoryA(g_logDir, nullptr);
    CreateDirectoryA(session, nullptr);
    for (const char* log : kLogs) {
        char from[MAX_PATH];
        char to[MAX_PATH];
        snprintf(from, sizeof(from), "%s%s", gameDir, log);
        snprintf(to, sizeof(to), "%s%s", session, log);
        MoveFileExA(from, to, MOVEFILE_REPLACE_EXISTING | MOVEFILE_COPY_ALLOWED);
    }
    PruneOldest("20*", true, kKeepSessions);
}

namespace {

bool InModule(HMODULE module, ULONG_PTR at)
{
    if (!module) return false;
    const IMAGE_DOS_HEADER* dos = (const IMAGE_DOS_HEADER*)module;
    const IMAGE_NT_HEADERS* nt = (const IMAGE_NT_HEADERS*)((const char*)module + dos->e_lfanew);
    ULONG_PTR base = (ULONG_PTR)module;
    return at >= base && at < base + nt->OptionalHeader.SizeOfImage;
}

// A crash in the game's own code (Wiz8.exe, wiz8hy.dll) on the main thread never reaches the
// unhandled-exception filter: the exe's CRT start-up frame (_except_handler3 with its scope
// table in a writable section) is rejected by today's msvcrt, and the kernel ends the process
// with no user-mode code running - the silent Arnika Road crash (2026-10-22). So a fatal
// exception code there is written down when it is raised (first chance), marked as such: the
// retail game handles none of these in its code (its only __try frames are the CRT ones), but
// wiz8hy.dll may (the experimental menu animation's video decoder catches a fault in zlib and
// goes on without the video), so a first-chance record is a crash only if the log ends there.
// This handler never handles anything itself: the game goes on or ends as without it.
LONG CALLBACK FirstChanceCrash(EXCEPTION_POINTERS* info)
{
    const DWORD code = info->ExceptionRecord->ExceptionCode;
    const bool fatal = code == EXCEPTION_ACCESS_VIOLATION || code == EXCEPTION_ILLEGAL_INSTRUCTION ||
                       code == EXCEPTION_PRIV_INSTRUCTION || code == EXCEPTION_INT_DIVIDE_BY_ZERO ||
                       code == EXCEPTION_STACK_OVERFLOW || code == EXCEPTION_ARRAY_BOUNDS_EXCEEDED;
    if (!fatal) return EXCEPTION_CONTINUE_SEARCH;
    const ULONG_PTR at = (ULONG_PTR)info->ExceptionRecord->ExceptionAddress;
    if (!InModule(GetModuleHandleA(nullptr), at) && !InModule(GetModuleHandleA("wiz8hy.dll"), at)) {
        return EXCEPTION_CONTINUE_SEARCH;
    }
    return CrashRecord(info, true);
}

}  // namespace

void DiagStart()
{
    g_startTick = GetTickCount();
    AddVectoredExceptionHandler(0, FirstChanceCrash);  // last in line: after dgVoodoo and the like
    bool exitHook = HookApi(L"ntdll", "RtlExitUserProcess", (LPVOID)&HookExit, (LPVOID*)&g_origExit);
    // kernelbase holds the real TerminateProcess (kernel32's export only jumps there).
    bool terminateHook =
        HookApi(L"kernelbase", "TerminateProcess", (LPVOID)&HookTerminate, (LPVOID*)&g_origTerminate) ||
        HookApi(L"kernel32", "TerminateProcess", (LPVOID)&HookTerminate, (LPVOID*)&g_origTerminate);
    SetUnhandledExceptionFilter(CrashFilter);
    HANDLE thread = CreateThread(nullptr, 0, Heartbeat, nullptr, 0, nullptr);
    if (thread) {
        CloseHandle(thread);
    }
    Log("diagnostics: earlier sessions' logs in Wiz8Logs\\; exit trace %s/%s; crash minidumps; "
        "memory every %u s",
        exitHook ? "on" : "FAILED", terminateHook ? "on" : "FAILED", (unsigned)(kHeartbeatMs / 1000));
}
