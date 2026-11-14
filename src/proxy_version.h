#pragma once

#include <windows.h>

// Loads the system version.dll and remembers the addresses of its functions
// so that our trampoline exports can jump to them. false = it could not be loaded
// (its functions then report failure); ProxyVersionError() gives the Windows error code.
// load = false (the copy loaded as binkw32.dll, see loader_route.h): nothing is loaded, every
// function reports failure; nobody imports them from binkw32.dll. (When version.dll is a link
// to that same file, Wine or Windows gives sr.dll that copy, which then passes true:
// VersionDllIsThisFile.)
bool ProxyVersionLoad(bool load);
DWORD ProxyVersionError();
