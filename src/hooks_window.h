#pragma once

// Hooks CreateWindowExA (via MinHook). Called from DllMain,
// so it only installs the hook — no logging, no files.
bool InstallWindowHooks();
