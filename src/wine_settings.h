#pragma once

// Under Wine (Linux, Steam Deck; Proton is Wine): once the patch runs, it notes in the game's
// own Wine prefix that Wiz8.exe takes version.dll from the game folder and keeps Wine's own
// ddraw.dll, so that the next starts need no WINEDLLOVERRIDES launch option. The same values,
// rules and notes as the installer's (src/wine_overrides.h), so the installer's Uninstall takes
// them back; a setting of the player's is never changed. Writes one "wine settings ..." log line.
// ddrawOwn: false when this run did not get Wine's own ddraw.dll but the game folder's DDraw.dll
// (dgVoodoo) or a native one from Wine's system folder.
// Called from EnsureRuntime: outside the loader lock, with the log open, before the game starts
// DirectDraw. Does nothing on Windows.
void WineKeepOverrides(bool ddrawOwn);
