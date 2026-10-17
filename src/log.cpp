#include "log.h"

#include <windows.h>

#include <stdarg.h>
#include <stdio.h>

static HANDLE g_file = INVALID_HANDLE_VALUE;
// A critical section is like a mutex: it keeps lines from different game threads
// from getting mixed up mid-line.
static CRITICAL_SECTION g_lock;

void LogOpen(const char* path)
{
    InitializeCriticalSection(&g_lock);
    // CREATE_ALWAYS — every run starts the log afresh.
    g_file = CreateFileA(path, GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_ALWAYS,
                         FILE_ATTRIBUTE_NORMAL, nullptr);
}

void Log(const char* fmt, ...)
{
    if (g_file == INVALID_HANDLE_VALUE) {
        return;
    }
    char line[1024];
    SYSTEMTIME t;
    GetLocalTime(&t);
    int n = snprintf(line, sizeof(line), "%02d:%02d:%02d.%03d [%5lu] ", t.wHour, t.wMinute,
                     t.wSecond, t.wMilliseconds, GetCurrentThreadId());
    va_list args;
    va_start(args, fmt);
    n += vsnprintf(line + n, sizeof(line) - n - 2, fmt, args);
    va_end(args);
    if (n > (int)sizeof(line) - 3) {
        n = sizeof(line) - 3;
    }
    line[n++] = '\r';
    line[n++] = '\n';

    EnterCriticalSection(&g_lock);
    DWORD written;
    WriteFile(g_file, line, n, &written, nullptr);
    // Flush to disk right away: if the game crashes, the last line is not lost.
    FlushFileBuffers(g_file);
    LeaveCriticalSection(&g_lock);
}
