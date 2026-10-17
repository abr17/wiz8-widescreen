#pragma once

#include <string>

#include "config.h"
#include "exe_version.h"
#include "hooks_game.h"

// Shared state of the patch.
struct Runtime {
    char gameDir[260] = {};   // folder of Wiz8.exe with a trailing '\'
    Config config;
    ExeVersion exe = ExeVersion::Unknown;
    std::string exeSha256;
    bool proxyOk = false;     // whether the real version.dll was loaded
    bool hooksInstalled = false;
    HookReport game;          // hooks inside the game (installed only for GOG 1.2.4)
    bool active = false;      // true if the exe version is known and the patch is enabled
};

extern Runtime g_runtime;

// Deferred initialization (log, exe hash). Safe to call repeatedly;
// the real work is done once and NOT from DllMain.
void EnsureRuntime();
