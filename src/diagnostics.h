#pragma once

// Crash and exit diagnostics (wiz8ws.log + the Wiz8Logs\ folder next to Wiz8.exe).
//
// Some players see the game close silently, with no error and no Windows crash record.
// That is either an exit call or a crash in the game's own code that the kernel ends with
// no user-mode code running (the Arnika Road crash, diagnostics.cpp), so the patch records
// every exit call with the call stack and the game's own error message if it set one,
// writes down fatal exceptions in the game's code when they are raised (first chance) and
// unhandled ones elsewhere, each with a minidump, and logs the memory use once a minute
// (the game is 32-bit: about 2 GB of address space). All of it runs only with
// [Debug] Diagnostics=1 in wiz8ws.ini.

// Called from DllMain (only file moves): moves the logs of the previous session
// (wiz8ws.log, wiz8hy.log, wiz8wide.log) into Wiz8Logs\<date_time>\ so a restart after
// a crash does not overwrite them; keeps the last 10 sessions.
void DiagRotateLogs(const char* gameDir);

// Called once from EnsureRuntime (after the log is open, MinHook initialized): hooks the
// process exit paths, installs the first-chance (vectored) crash handler and the
// unhandled-exception filter, starts the memory heartbeat.
void DiagStart();
