#pragma once

#include "layout.h"

// Settings from wiz8ws.ini (sits next to Wiz8.exe).
// If the file is missing, the defaults are used.
struct Config {
    bool enabled = true;          // [General] Enabled — 0 turns the patch off completely
    bool borderless = true;       // [Display] Borderless — no change of the monitor resolution
    HudLayout hudLayout = HudLayout::Stretch;  // [Display] HudLayout = Stretch | Centered
    bool horPlus = true;          // [Display] HorPlus — wider 3D field of view (Centered only)
    bool fixMouse = true;         // [Input] FixMouse — recompute mouse coordinates
    bool fixAltTab = true;        // [Input] FixAltTab — reset a stuck Alt
    bool dpiAware = true;         // [Display] DpiAware — no blurring at 125%/150% scaling
    bool logWindowCalls = true;   // [Debug] LogWindowCalls — log window parameters
    bool diffHarness = false;     // [Debug] DiffHarness — comparison harness against the port (w8diff.dll)
    bool hybrid = false;          // [Hybrid] Enabled — port functions from wiz8hy.dll (trial)
};

// Reads the ini. Safe to call even from DllMain (kernel32 only).
Config LoadConfig(const char* iniPath);
