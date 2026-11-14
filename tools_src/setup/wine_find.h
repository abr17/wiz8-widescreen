#pragma once

// Finding Wizardry 8 under Wine (Linux, Steam Deck; Proton is Wine), for the installer
// (setup.cpp), and telling whether the game runs in the Wine prefix the installer runs in.
//
// A Windows program under Wine cannot see the Linux home folder's name in HOME (Wine hides it),
// but Wine gives every program WINEHOMEDIR (the home folder) and WINECONFIGDIR (the prefix the
// program runs in). From the home folder the launchers' own files say where the game is and in
// which prefix it runs: Steam (its libraries, the Steam game 245450, and non-Steam games added
// as shortcuts), Heroic, Lutris, and GOG installers run in other prefixes (their drive_c).
// Those files hold Linux paths ("/home/deck/Games/Wizardry 8"); FromUnix turns them into paths
// this program can open ("Z:\home\deck\Games\Wizardry 8").
//
// Used by setup.cpp only under Wine (UnderWine()); on Windows nothing here is called.

#include <string>
#include <vector>

namespace wine {

/* Where a game folder was found: the "Found by" line of the installer's window. */
enum Source {
    SOURCE_TYPED,    /* typed, pasted, browsed or given on the command line */
    SOURCE_GOG,      /* the GOG installer's registry keys (of the prefix the installer runs in) */
    SOURCE_STEAM,    /* the Steam game (app 245450) in a Steam library */
    SOURCE_SHORTCUT, /* a non-Steam game in Steam (label = the shortcut's name) */
    SOURCE_HEROIC,
    SOURCE_LUTRIS,
    SOURCE_PREFIX    /* a GOG installer run in another Wine prefix: <prefix>\drive_c\GOG Games */
};

/* Whether the game runs in the Wine prefix the installer runs in. Wine's settings for the patch
   (src\wine_overrides.h) belong to one prefix, so the installer writes them only where they
   reach the game. */
enum Verdict {
    VERDICT_UNKNOWN,     /* no prefix is known (a typed folder, a launcher entry without one), or
                            this one and another existing one: it may run in either */
    VERDICT_THIS,        /* this one is the game's only existing prefix */
    VERDICT_OTHER,       /* the game's prefixes are known, and this is none of them */
    VERDICT_NOT_CREATED  /* the same, but no prefix exists yet: the game never started (Steam
                            makes a shortcut's prefix at its first start) */
};

/* One game folder the installer offers. The same folder found by two sources is one candidate
   with both sources' prefixes (the game may run in either). */
struct Candidate {
    std::wstring folder;
    Source source = SOURCE_TYPED;
    std::wstring label;                 /* SOURCE_SHORTCUT: the shortcut's name in Steam */
    std::vector<std::wstring> prefixes; /* the Wine prefix(es) the game runs in, if known */
    Verdict verdict = VERDICT_UNKNOWN;
};

/* A Linux path (UTF-8, as the launchers' files hold it) as a path a Windows program can open:
   the drive letter Wine maps it to ("Z:\home\deck\..." in most prefixes, "X:\..." for the home
   folder in the prefixes umu makes for Heroic and Lutris), or "\\?\unix\home\deck\..." when no
   drive maps it. Any other text (not starting with "/") is returned as it is. */
std::wstring FromUnix(const std::string& path);

/* The Linux home folder (WINEHOMEDIR) and the prefix this program runs in (WINECONFIGDIR), as
   paths this program can open; empty when Wine did not set them. */
std::wstring HomeFolder();
std::wstring ThisPrefix();

/* Every place the launchers say the game is, in this order: Steam shortcuts, Heroic, Lutris,
   GOG folders in other prefixes, the Steam game. Not checked: many of them are guesses (both
   folder names the Steam game may have), and the installer keeps only real game folders. */
void FindWineGames(std::vector<Candidate>* places);

/* The verdict for a game whose prefixes are these. Prefixes are compared by the file system
   (FolderId of the prefix and its drive_c), so a link (umu's pfx -> .) or another drive letter
   of one prefix still matches. A prefix that does not exist (yet) counts only when no listed
   prefix exists: NOT_CREATED. */
Verdict PrefixVerdict(const std::vector<std::wstring>& prefixes);

/* A folder typed or pasted into the folder box, or given on the command line, as a folder
   name: without spaces around it, one pair of quotes (Steam shows its paths in quotes) and a
   final \Wiz8.exe; "~/..." is the home folder; a Linux path ("/home/deck/...", also as a
   file:// address) goes through FromUnix. */
std::wstring NormalizeTypedFolder(const std::wstring& text);

}  // namespace wine
