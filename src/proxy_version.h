#pragma once

// Loads the system version.dll and remembers the addresses of its functions
// so that our trampoline exports can jump to them.
bool ProxyVersionLoad();
