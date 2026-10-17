#pragma once

// A simple log to the file wiz8ws.log next to Wiz8.exe.
// Used like printf: Log("window %dx%d", w, h);
// Do not call from DllMain: "heavy" file system access is not allowed there.
void LogOpen(const char* path);
void Log(const char* fmt, ...) __attribute__((format(printf, 1, 2)));
