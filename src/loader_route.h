#pragma once

#include <windows.h>

// Which file this copy of the patch was loaded as, and whether this copy runs the patch.
//
// The same DLL can sit in the game folder under two names:
//   - version.dll: the usual way. sr.dll (the game engine) imports version.dll, so Windows
//     loads ours from the game folder. Wine and Proton take their own version.dll instead
//     unless the launch option or the registry setting says otherwise (docs/loader.md).
//   - binkw32.dll: under Wine only, the installer also puts a copy of version.dll in place of
//     RAD's binkw32.dll (the game's video player, imported by Wiz8.exe itself) and renames the
//     original to binkw32_wiz8wide.dll. Wine has no binkw32.dll of its own, so it always loads
//     the game folder's file: the patch starts with no launch option and no setting. The 83
//     Bink functions of this DLL only point Wine at the original (version.def).
// Both copies can be loaded into one process (the binkw32.dll copy, plus version.dll through the
// launch option, the registry setting or the rule of Wine 11.7 and later), and only one of
// them may hook the game: the first one that starts creates a named mutex,
// "Local\Wiz8Widescreen-<process id>", which works like a lock that every module of the
// process can see. A copy that finds it already there only passes calls on: no hooks, no log.

enum class LoaderRole {
    Version,  // loaded as version.dll (or under any name other than binkw32.dll)
    Binkw32,  // loaded as binkw32.dll
};

// The role from this DLL's own file name, in any letter case (Wine reports the name the way
// the importer wrote it, "BINKW32.DLL" for Wiz8.exe). Safe in DllMain (kernel32 only).
LoaderRole LoaderRoleOf(HINSTANCE self);
// "version.dll" or "binkw32.dll", for the log.
const char* LoaderRoleName(LoaderRole role);

// For the copy loaded as binkw32.dll: whether version.dll next to it is this very file (a hard
// link or a symbolic link, as a tool that merges identical files makes them). Wine, and Windows
// too, then load no second module for version.dll and give sr.dll this one, so this copy has to
// load the real version.dll too. Safe in DllMain (kernel32 only).
bool VersionDllIsThisFile(HINSTANCE self);

// Called from DllMain: whether this copy starts the patch.
//   - as version.dll: yes, unless another copy already did (checked under Wine only; on
//     Windows it always starts, as before);
//   - as binkw32.dll: under Wine only when version.dll next to it has exactly the same bytes
//     (an older copy left behind must not run old code against a newer wiz8hy.dll, and
//     deleting version.dll still turns the patch off), and only if no other copy started
//     first; on Windows only when version.dll is this very file (VersionDllIsThisFile: then it
//     is the only copy in the process), otherwise the version.dll copy starts it, as before.
// Safe in DllMain: file reads and kernel32 calls only, no DLL is loaded.
bool StartHere(HINSTANCE self, LoaderRole role);

// From EnsureRuntime (not from DllMain): the log line(s) about the other copy. Started as
// binkw32.dll: "started from binkw32.dll (no launch option needed); version.dll: ..." (Wine's own,
// or our copy, which then only passes calls on); on Windows "started from binkw32.dll;
// version.dll: this file too (...)". Started as version.dll under Wine, with our copy as
// binkw32.dll in the folder: why that one did not start. Nothing otherwise (Windows).
void LogLoaderRoute(LoaderRole role);
