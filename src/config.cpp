#include "config.h"

#include <windows.h>

Config LoadConfig(const char* iniPath)
{
    Config c;
    // GetPrivateProfileInt/String — the standard Windows way to read an ini: section, key,
    // default value, path. Like parse_ini_file() in PHP, but one key at a time.
    c.enabled = GetPrivateProfileIntA("General", "Enabled", 1, iniPath) != 0;
    c.borderless = GetPrivateProfileIntA("Display", "Borderless", 1, iniPath) != 0;
    c.dpiAware = GetPrivateProfileIntA("Display", "DpiAware", 1, iniPath) != 0;
    char layout[32];
    GetPrivateProfileStringA("Display", "HudLayout", "Stretch", layout, sizeof(layout), iniPath);
    c.hudLayout = lstrcmpiA(layout, "Centered") == 0 ? HudLayout::Centered : HudLayout::Stretch;
    c.horPlus = GetPrivateProfileIntA("Display", "HorPlus", 1, iniPath) != 0;
    c.fixMouse = GetPrivateProfileIntA("Input", "FixMouse", 1, iniPath) != 0;
    c.fixAltTab = GetPrivateProfileIntA("Input", "FixAltTab", 1, iniPath) != 0;
    c.logWindowCalls = GetPrivateProfileIntA("Debug", "LogWindowCalls", 1, iniPath) != 0;
    c.diffHarness = GetPrivateProfileIntA("Debug", "DiffHarness", 0, iniPath) != 0;
    c.diagnostics = GetPrivateProfileIntA("Debug", "Diagnostics", 0, iniPath) != 0;
    c.hybrid = GetPrivateProfileIntA("Hybrid", "Enabled", 0, iniPath) != 0;
    c.utf8FileNames = GetPrivateProfileIntA("General", "Utf8FileNames", 1, iniPath) != 0;
    return c;
}
