# What `version.dll` does at run time

`version.dll` (built from `src\`, see [building.md](building.md)) is the patch's loader: the game's
`sr.dll` loads it in place of the Windows DLL of the same name, it passes the real
`version.dll` calls through, checks the exe, hooks `WinMain` and loads `wiz8hy.dll`
([hybrid.md](hybrid.md)); under Wine a copy of it can also stand in for the game's
`binkw32.dll` (last section). Besides that it has features of its own, which do not depend on
the widescreen code: two for Windows, and under Wine its own way to start and its own Wine
setting. Like everything in the loader they need `[General] Enabled=1`: with `Enabled=0`
`version.dll` only passes calls through and writes no log at all.

## Crash and exit diagnostics (`src\diagnostics.cpp`)

Players report the game closing silently, with no error and no Windows crash record. That means
the process ended itself rather than crashed, so the loader can record how it ends. It is off
unless `wiz8ws.ini` has `[Debug] Diagnostics=1`; with `0` (the default) nothing below runs and no
`Wiz8Logs\` folder is made.

| What | Where |
|---|---|
| logs of earlier sessions (`wiz8ws.log`, `wiz8hy.log`, `wiz8wide.log`) | moved at the next start into `Wiz8Logs\<date_time>\` next to `Wiz8.exe` (the time of the session's last log line); the last 10 sessions are kept. Until then the session that just ended is in the game folder |
| a process exit through `ExitProcess`/`exit()` (`ntdll!RtlExitUserProcess`) or `TerminateProcess` called inside the game | `wiz8ws.log`: exit code, time since start, combat flag, memory, the call stack as return addresses (`Wiz8.exe+offset`; for `Wiz8.exe` the address is `0x400000 + offset`) and the game's own error text if it set one (`0x006505ac`) |
| memory | `wiz8ws.log`, once a minute: private bytes, used address space of the 2 GB, largest free block |
| a real crash (unhandled exception) | `wiz8ws.log`: exception, address, memory, stack; and a minidump `Wiz8Logs\crash-<date_time>.dmp` (the last 3 are kept), written by a separate thread so that a stack overflow still gets one; open it in WinDbg or Visual Studio with `release\symbols-<version>\` |

A crash in the game's own code on its main thread never reaches the unhandled-exception filter:
the exe's CRT start-up frame (`_except_handler3`, its scope table in a writable section) is
rejected by today's msvcrt and the kernel ends the process with no user-mode code running, no
Windows crash record either (found on the silent Arnika Road crash, 2026-10-22). So a vectored
handler, last in line, writes the same CRASH lines and minidump when a fatal exception code
(access violation, illegal instruction, divide by zero, stack overflow, heap corruption) is
raised in `Wiz8.exe` or `wiz8hy.dll` code; the game handles no such exception in its own code,
and the handler never handles anything, so the game ends as without it. The same exception is
not written twice if it later reaches the filter.

Not seen (the log just stops without an exit line): fail-fast (`__fastfail`, `/GS` failures,
`abort()` of a modern C runtime), a direct `NtTerminateProcess`, and a kill from another process
(Task Manager, a launcher, an antivirus). A log that stops like that points to one of these.

When a player reports a silent close, ask them to run the installer again with "Diagnostics mode
(for bug reports)" ticked (or set `Diagnostics=1` by hand), play until it happens
again and press the installer's "Report a problem..." button (1.0.3 and later, see below). By
hand the same files are `wiz8ws.log`, `wiz8hy.log`, `wiz8wide.log` from the game folder,
`Dll\srDD_D3D11.log` and the whole `Wiz8Logs\` folder (the READMEs say the same).

### The report file ("Report a problem...", `tools_src\setup\setup.cpp`)

The installer packs what a bug report needs into one zip. The button is in its
window, on the line of the "Diagnostics mode" checkbox; without the window it is
`Wiz8WideSetup.exe --report "<game folder>" ["<file.zip>"]` (exit code 0 = written, 1 = not a
game folder or the file could not be written, 2 = wrong arguments).

| In the zip | From |
|---|---|
| `report.txt` | written by the installer: the installed patch version, whether `Wiz8.exe` is the tested 1.2.4 (otherwise its SHA-256), the game folder, the diagnostics switch, the Windows version (under Wine also Wine's), processor, memory, graphics cards with driver versions, the primary screen and its scaling; the block "Program files in the game folder", which describes files the zip does not hold (`Dll\srDD_D3D11.dll`, `version.dll` and `wiz8hy.dll` with size, time and SHA-256; `binkw32.dll`, `DDraw.dll`, `D3DImm.dll` and `dgVoodoo.conf` with size and time; `absent` for one that is not there); and the list of the files below |
| `wiz8ws.ini`, `wiz8wide.ini`, `Dll/srDD_D3D11.ini`, `3DVideo.CFG`, `Wiz8Wide.installed.txt` | the settings and the list of installed files |
| `wiz8ws.log`, `wiz8hy.log`, `wiz8wide.log`, `Dll/srDD_D3D11.log`, `Dll/srDD_D3D11.log.old` | the last session's logs of the patch and of the render driver |
| `Wiz8Logs/<date_time>/*`, `Wiz8Logs/crash-*.dmp` | what the diagnostics mode kept: the logs of earlier sessions and the crash dumps |

Nothing else is taken: no saves, no programs, no files in `Wiz8Logs\` that the patch did not
write. The files go in in the order of the table: the settings and the list of installed
files, then the last session's logs, then the contents of `Wiz8Logs\` newest first. A file
that would take the archive over 24 MB is left out (GitHub takes attachments of up to 25 MB);
a smaller one after it still goes in. A log over 8 MB goes in as its first 1 MB and its last
7 MB, with a line between them that says how many bytes are left out; a file that is not a log
and is over 64 MB is left out. `report.txt` gives the reason for each file left out, marks a
cut log and lists the files that are not in the game folder, and the installer's final message
says when something was left out or cut. The game folder is only read.

The zip goes to the Desktop as `Wiz8Wide-report-<date_time>.zip` (under Wine the Linux Desktop
or home folder is tried first) or, when that cannot be written, to the user's temporary folder
(`%TEMP%`), never to the game folder; its path goes to the clipboard. The
installer then asks whether to open the bug report form of the repository
(`.github\ISSUE_TEMPLATE\bug_report.yml`) in the browser, with the patch version, the system
and the graphics card filled in through the address. It sends nothing itself: the player
describes the problem and adds the file. The form and the question both say that reports are
public and that the logs contain folder names (so the user name).

The archive is written by `tools_src\setup\zip_writer.h` (deflate with the fixed Huffman
codes; no library, because the installer has no dependencies and under Wine there is no
PowerShell or `tar.exe` to lean on). Its test: [testing.md](testing.md).

The installer sets the switch with its "Diagnostics mode" checkbox (or
`--diagnostics` / `--no-diagnostics` after the folder on its command line): off on a fresh
install; over an install the checkbox shows the current value, and an update or reinstall never
changes it unless the player does. An update, reinstall or rollback also keeps `Wiz8Logs\` and,
when it exists, first moves the last session's five logs into a new session folder of it: the
patch's three and, from `Dll\`, the render driver's `srDD_D3D11.log` and `srDD_D3D11.log.old`.
A full uninstall removes the patch's files from `Wiz8Logs\` (those five names in the `20*\`
session folders, `crash-*.dmp`) and the folder if nothing else is left.

## Game file names on UTF-8 Windows (`src\filenames.cpp`)

Windows 10/11 has a beta option, "Use Unicode UTF-8 for worldwide language support" (Region,
Administrative, Change system locale). With it the system code page is UTF-8.

The game keeps names of characters and saves as single-byte text (with the Russian data, cp1251
codes) and passes them to the ANSI file functions (`CreateFileA("Saves\\Characters\\<nickname>.CHR")`,
`FindFirstFileA`, `fopen`, ...). With the option on, a lone non-English byte is invalid UTF-8 and
Windows turns it into U+FFFD, so:

- every nickname of the same length maps to the same file: "a character with this nickname already
  exists" for any new Russian nickname, and the game silently creates files named `����.CHR`;
- Russian names in the save and character lists show as garbage.

The bug is in the original game's code (the patch does not change these functions), but it blocks
the Russian translation on such systems, so the loader fixes it. Only when `GetACP() == CP_UTF8`,
it redirects the file imports of `Wiz8.exe` and `wiz8hy.dll` (`CreateFileA`, `DeleteFileA`,
`MoveFileA`, `CopyFileA`, `Get/SetFileAttributesA`, `CreateDirectoryA`, `GetPrivateProfileIntA`,
`FindFirstFileA`, `FindNextFileA`; msvcrt `fopen`, `_access`, `rename`, `_chmod`, `_chdir`) to
wrappers that call the Unicode functions:

- game to Windows: each path component that is valid UTF-8 is read as UTF-8 (it came from Windows,
  for example the game folder from `GetModuleFileNameA`); any other component is read in the code
  page Windows would use without the option (the system locale's ANSI code page,
  `LOCALE_IDEFAULTANSICODEPAGE`);
- Windows to game (names from `FindFirstFileA`/`FindNextFileA`): in that code page when the name
  fits into it and the bytes can be mistaken neither for UTF-8 nor for a path separator (in
  double-byte code pages such as 932 a `\` byte can be the second half of a character), otherwise
  as UTF-8 (what Windows returns now). So a listed name always opens the same file again.

So files are named as the game names them with the option off (with an English system locale a
Russian nickname is stored as `Èâàí.CHR`, as before), files made before the option was turned on
keep working, and file contents are untouched: saves and characters stay compatible with the
unpatched game. One rare exception: a game name whose bytes happen to be valid UTF-8 as a whole is
read as UTF-8, so it is stored under that meaning and can share a file with another name. "Рё"
is cp1251 D0 B8, which is UTF-8 for "и": with a Russian system locale both nicknames map to
`и.CHR`. It takes a name in which every non-English letter is a capital followed by ё or Ё (Иван,
Пётр, Лёха are not affected). Those same bytes are how a Cyrillic or accented folder name from
Windows looks, so the two cannot be told apart.

Paths with English letters only go to the original functions unchanged; the graphics, sound and
video DLLs are not touched. `[General] Utf8FileNames=0` in `wiz8ws.ini` turns it off. The log says
which code page is used:
`file names: system code page is UTF-8; 18 file imports redirected, game names read as code page 1252`.

Files the unpatched game created with the option on (`���.CHR`) are not recoverable by name; they
still list and load, and the player can delete them.

Test without the game. The test declares UTF-8 as its own code page in its manifest, so it runs on
any Windows 10 1903+; it goes through the game's flows for this system's code page, then as on
cp1251 and cp1252 systems, and checks double-byte names as on cp932:

```
cmake --build build --target test_filenames
build\test_filenames.exe
```

## Wine and Proton (Linux)

Under Linux the patch was tested only on the Linux test bench, a Docker container with software
rendering (GE-Proton10-25 and Ubuntu's Wine 9.0; [testing.md](testing.md), "Linux / Proton
bench"), not on a real Linux PC and not on a Steam Deck.

Wine (and Proton, which is Valve's Wine) has its own `version.dll` and `ddraw.dll`. When the
game folder has a file of the same name, Wine still maps its own one unless told otherwise
(load order "default" = its own first, unless that DLL is built as "prefer native"; checked in
the source of Wine 9.0, 10.0, 11.0 and Valve's proton_10.0/11.0, and in Wine 9.0 and
GE-Proton10-25, 2026-10-25; newer development versions of Wine differ, see "Newer Wine" at the
end). It even names that module with the game-folder path. So by default the patch's
`version.dll` never runs, no `wiz8ws.log` appears and the menu shows only `v1.2.4`. A
`DDraw.dll` in the game folder (dgVoodoo's, which the packages up to 1.0.2 carried) is replaced
by Wine's own as well, and under Wine that is what we want (next section).

Since 1.0.3 the patch starts under Wine in three ways, and all of them run only under Wine
(`ntdll!wine_get_version` exists; Windows sees none of it):

* the installer puts a copy of the patch in place of the game's `binkw32.dll`, a DLL Wine has
  no copy of its own of, so Wine always loads the game folder's file: no setting at all, in
  any Wine prefix ("The patch starts through binkw32.dll");
* a per-program Wine setting, written by the installer into the prefix it runs in when the game
  runs there ("What the installer and the player set", "Finding the game under Wine"), and by
  the patch itself into the game's prefix once it has started there ("The patch keeps its own
  Wine setting");
* the launch option, for a copy of `files\` made by hand: needed for the first start only,
  because the patch then keeps the setting itself.

### Which ddraw: Wine's own, not dgVoodoo

Since 1.0.3 the game's 3D goes through the patch's own render driver, `Dll\srDD_D3D11.dll`
(Direct3D 11: wined3d in Wine, DXVK in Proton; `3DVideo.CFG` line 1 `D3D11`, written by
`wiz8hy.dll` at every start), and the package has no `DDraw.dll`. `Wiz8.exe` itself still
imports `DDRAW.DLL` (its 2D surfaces), whatever the render driver, so Wine loads a ddraw when
the game starts, before the patch runs, and it has to be Wine's own.

Up to 1.0.2 the package carried dgVoodoo 2.8.7.5 (`DDraw.dll`, `D3DImm.dll`, `dgVoodoo.conf`),
which the game's DirectX 7 driver needed on modern Windows, and such files may still lie in a
game folder: an install made by 1.0.0 - 1.0.2, a copy of `files\` made by hand, the player's
own. dgVoodoo does not run under Wine. With the DirectX 7 driver it crashed on its first
`CreateSurface` with a page fault at `DDraw.dll+0x9928`, a call through a bad texture pointer of
its own (`ID3D11Texture2D::GetDesc`); every Direct3D 11 call before it succeeds. Seen with the
real game, with and without the patch, and with a 120-line program that only repeats the
game's video start, under Wine 9.0 and GE-Proton10-25, with every `OutputAPI` (bestavailable
picks Direct3D 11 there: wined3d in Wine, DXVK in Proton), on software rendering and on a real
GPU through WSL (2026-10-25). Other players report the same for dgVoodoo after about 2.81.3
(late 2023), Steam Deck included, and Wine bug 58731; the author does not support Wine. The
`8007000E` values on the stack at the crash are stale, not a real out-of-memory.

The installer never installs dgVoodoo, on Windows or under Wine: `DDraw.dll`, `D3DImm.dll` and
`dgVoodoo.conf` at the root of `files\` (`kDgVoodoo` in `setup.cpp`, matched in any letter case
by `IsDgVoodoo`; there only when a new package was unpacked over an older one) are not copied,
not saved as originals, not listed in the manifest, and not checked for being in use unless the
old manifest lists them. In the game folder they could only do harm under Wine: Wine loads
`DDRAW.DLL` before the patch can write `*ddraw=builtin`, and Wine 11.6 and later take a
`DDraw.dll` that is not Microsoft's from the game folder when nothing says otherwise ("Newer
Wine"; any Wine does with a global `ddraw=native`). In a prefix the installer did not set up
(the game runs in another one) the first start then crashed in dgVoodoo (seen with the real
game, the DirectX 7 driver and a global `ddraw=native`: Wine's crash dialog). What follows:

* An update, reinstall or rollback over an install that has them (made by 1.0.0 - 1.0.2 on
  Windows, or under Wine by the 1.0.2 installer) first runs its quiet uninstall, which removes
  what the old manifest lists and puts back the originals saved in `Wiz8Wide.backup\` (a
  `DDraw.dll` of the player's own comes back); the new install then simply lacks them. The
  binkw32 route is not affected.
* A `DDraw.dll`, `D3DImm.dll` or `dgVoodoo.conf` that the manifest does not list (the player's
  own, or a copy of `files\` made by hand) stays as it is. `*ddraw=builtin`, from the installer
  or from the patch, keeps Wine from loading such a `DDraw.dll`, and the uninstall keeps that
  value while the folder has one ("What the installer and the player set").
* The uninstall of an install made since 1.0.3 has nothing of dgVoodoo's to do: the folder ends
  as it was before the install, byte for byte.
* A folder installed under Wine and then played from Windows (dual boot, a drive or Steam
  library shared with Windows) needs nothing more: the render driver is the same file on both,
  and the patch starts through `version.dll` there ("The patch starts through binkw32.dll").
  An install run on Windows over it has no binkw32 route (its quiet uninstall puts the original
  `binkw32.dll` back); under Linux the patch then starts through the Wine setting that the
  installer or an earlier start of the patch left in the game's prefix ("The patch keeps its
  own Wine setting"), or through the launch option, or after the installer has run under Linux
  again (the READMEs say so).
* A prefix with a global `ddraw=native` (only `native`, as winecfg, winetricks, Bottles or
  Lutris can set it) that the installer did not set up: with no `DDraw.dll` in the game folder,
  Wine finds no native ddraw for the `DDRAW.DLL` import and `Wiz8.exe` does not start at all
  (`import_dll Library ddraw.dll ... not found`, status `c0000135`; mock game under Wine 9.0 and
  GE-Proton10-25), so the patch never runs to write `*ddraw=builtin`. With the dgVoodoo of a
  package up to 1.0.2 in the folder, that crashed once there and the next start had Wine's
  ddraw. The original game does not
  start in such a prefix either, so the setting is the player's to remove; the READMEs say so.
  The launch option once (its `ddraw=b`, after which the patch writes `*ddraw=builtin`) or an
  install run in that prefix also make it start. In a 32-bit prefix (`WINEARCH=win32`) Wine
  takes its own `system32\ddraw.dll` and looks it up as plain `ddraw` first, so the global value
  would win over `*ddraw=builtin` ("What the installer and the player set"): there the installer
  and the patch also write a per-program plain `ddraw=builtin`, which Wine reads before the
  global key, and the game starts the same way (since 2026-10-26; before, only removing the
  setting or the launch option at every start helped). A `*ddraw` or plain `ddraw` already set
  for `Wiz8.exe` stays as it is, and the plain one is then not written (it goes only with
  `*ddraw`). Unless a plain `ddraw` there is `builtin` first (it then wins over the global
  value, and the game starts), an install run in such a prefix then says in its final message
  that a setting keeps the patch from working, and so does the patch's log line. With a
  `DDraw.dll` in the game folder (the package's, up to 1.0.2) Wine looks that file up as `*ddraw`
  first, so there the game starts with Wine's ddraw in any prefix (checked with the mock game
  under Wine 9.0 in a 32-bit prefix; 64-bit prefixes and GE-Proton10-25 take `*ddraw` first for
  Wine's own `ddraw.dll` too).
* The same 32-bit lookup applies when a winetricks or Bottles component has put a native
  `ddraw.dll` (dgVoodoo, say) into the prefix's `system32` and set a global `ddraw=native` or
  `native,builtin`: with no `DDraw.dll` in the game folder a 32-bit prefix would load that DLL
  at every start despite `*ddraw=builtin`; the per-program plain `ddraw=builtin` keeps Wine's
  own there from the start after the one that wrote it (the patch's log names that one start's
  DLL `a native one from Wine's system folder`). A 64-bit prefix keeps Wine's own through
  `*ddraw`.

### What the installer and the player set

What makes Wine take the patch's `version.dll` and keep its own `ddraw.dll` (value names
without `.dll`; `n,b` = game folder first, then Wine's own; `b` = Wine's own only):

* the launch option `WINEDLLOVERRIDES="version=n,b;ddraw=b" %command%` (Steam; Proton keeps it
  and appends its own list after it, which never names `version` or `ddraw` for this game), or
  the same overrides in another launcher: Heroic's environment variables, Bottles' DLL Overrides
  (`*ddraw` there: Bottles refuses a plain `ddraw`, which its D7VK component manages), and in
  Lutris its Runner options - DLL overrides (Lutris replaces a `WINEDLLOVERRIDES` set in its
  System options with its own). `ddraw=b` is Wine's default today; it is there for a global
  `ddraw` setting and for later Wine ("Newer Wine");
* or, per program, the registry of the Wine prefix:
  `HKCU\Software\Wine\AppDefaults\Wiz8.exe\DllOverrides`, `*version` = `native,builtin` and
  `*ddraw` = `builtin`, in a 32-bit prefix also the plain `ddraw` = `builtin`. The `*` form
  matches the DLL from any folder, but for a DLL that Wine takes from its own system folder a
  32-bit prefix reads the plain name first (below).

How Wine picks the entry (`get_load_order` in its `ntdll\loadorder.c`; checked with Wine 9.0 in
a 64-bit and a 32-bit prefix, 2026-10-25): for each name in turn it looks at `WINEDLLOVERRIDES`,
the per-program key, then the global `HKCU\Software\Wine\DllOverrides` (where winecfg and
winetricks write), and the first hit decides. For a DLL in the game folder the names are
`*version`, then `version`, so the per-program `*version` wins over everything in the registry.
The patch also loads Wine's own `system32\version.dll`, which needs `builtin` in the order that
applies to it: a 64-bit prefix (Proton, most launchers) looks it up the same way, but a 32-bit
prefix strips the system folder and looks up the plain `version` first. There a plain
`version=native`, in the per-program key or the global one, makes that load fail even with
`*version=native,builtin` set. The same goes for `ddraw.dll`: Wine finds a `DDraw.dll` in the
game folder first and looks it up as `*ddraw`, then `ddraw`; with none there (the package has
none since 1.0.3) it takes its own `system32\ddraw.dll`, which a 32-bit prefix looks up
as plain `ddraw` first, so there a global `ddraw=native` would win over the per-program
`*ddraw=builtin`, and the per-program plain `ddraw=builtin` is what wins over it ("Which
ddraw"; checked with Wine 9.0 and the mock game, 2026-10-26). Wine
reads the per-program key once, when `Wiz8.exe` starts, so a value written while the game runs
counts from its next start.

The installer (1.0.3 and later), when it runs under Wine, writes `*version` = `native,builtin`
and `*ddraw` = `builtin` in that per-program key of the prefix it runs in, each only when the
key has neither the `*` nor the plain name: a setting the player made stays as it is. With
`*ddraw` it writes, in a 32-bit prefix (`PlainDdrawToo`, which tells it by `IsWow64Process`),
also the plain `ddraw` = `builtin`, with a note of its own. It does so only when the game runs
in that prefix or nobody knows where it runs (the verdicts THIS and UNKNOWN, "Finding the game
under Wine"); a value in another prefix would not reach the game. With the binkw32 route it
still writes them there, as a fallback for when a store's file check puts the original
`binkw32.dll` back. `*ddraw=builtin` keeps Wine's own ddraw even when a global setting (the
winetricks or Bottles dgVoodoo component, say) asks for a native one, in a 64-bit prefix
(Proton, most launchers) and for a `DDraw.dll` in the game folder; in a 32-bit prefix with none
there the plain `ddraw=builtin` does that (above). Since Wine looks for `*ddraw` before `ddraw`
for the game folder's file, these values also win over plain names in `WINEDLLOVERRIDES`: an
experiment with dgVoodoo then needs `*ddraw=n,b` there (checked with Wine 9.0, as `*version=b`
there switches the patch off). For a `ddraw.dll` in the `system32` of a 32-bit prefix Wine asks
for the plain name first, and our per-program plain `ddraw=builtin` comes before a `*ddraw` in
`WINEDLLOVERRIDES`: an experiment with one there needs `ddraw=n,b`. The installer then reads the
registry the way Wine does (`WineOrderOk` in `src\wine_overrides.h`: for `ddraw` the order of
the file Wine will find, the game folder's `DDraw.dll` if there is one, else Wine's own in its
system folder; in a 32-bit prefix, which it tells by `IsWow64Process`, with the plain name first
for a system file) and, when the result would keep the patch from working (`version` not
`native` first with `builtin` after it, `ddraw` not Wine's own), the final window says so
instead of the usual note; with the binkw32 route only `ddraw` counts, since `binkw32.dll`
starts the patch whatever `version.dll` Wine loads. It never writes Wine's `EmulateModeset`
("Full screen under Wine").

The Wine part of the registry belongs to the prefix, not to one game folder, so what was
written is noted in the prefix too, not in `Wiz8Wide.installed.txt` (an older installer
rewrites that file and would drop such lines). The installer and the patch write the same
notes in the same format (`src\wine_overrides.h` is shared by both):

* `HKCU\Software\Wiz8Wide\Wine` - the values the installer or the patch created, with the text
  written;
* `HKCU\Software\Wiz8Wide\Wine\Folders` - one value per game folder that uses them, named by
  its full path (`WineFolderName`).

Uninstall removes its folder from that list, under every name that leads to the same folder
(`Z:\` and `X:\`, a link: compared by file identity, `wine::SameFolder`, "Finding the game under
Wine"). When no listed folder still has the patch, it deletes the values that were created, but
only if they still hold what was written, then the notes and any keys left empty. A listed
folder still has the patch while it has `Wiz8Wide.installed.txt` or our `version.dll` (a copy of
`files\` made by hand, which the patch listed itself). Two game copies in one prefix therefore
keep the values until the last one is uninstalled. A listed folder that is gone is dropped from
the list, unless its parent folder is gone too: then it may be on a drive that is not mounted
right now (an SD card), and it still counts as installed. One exception: when the uninstalled
folder still has a `DDraw.dll` (one it had before the install, the dgVoodoo of a package up to
1.0.2 copied by hand before the installer ran, say: an install leaves it where it is since
1.0.3, and the uninstall of one made by 1.0.0 - 1.0.2 puts it back from
`Wiz8Wide.backup\`), `*ddraw=builtin` (and the plain `ddraw=builtin` of a 32-bit prefix) stays,
each if it still holds what was written, and only the notes go, so the values are the player's
from then on. Without it Wine 11.6 and later (or any Wine with a global `ddraw=native`) would
load that dgVoodoo from the game folder ("Newer Wine") and the unpatched game would crash at
every start, which Wine's own ddraw had kept it from doing. All this happens in the prefix the
installer runs in; values the patch wrote in the game's prefix stay there when the installer
runs in another one, which is harmless ("The patch keeps its own Wine setting").

### The patch starts through binkw32.dll under Wine

Wine has no `binkw32.dll` of its own (checked in the file lists of Wine master 11.20, Valve's
proton_10.0 and proton_11.0, GE-Proton10-25 and Ubuntu's Wine 9.0, 2026-10-25), so for that
name it always loads the game folder's file, with no setting. `Wiz8.exe` imports 12 functions of
RAD's video library `binkw32.dll` 1.0q (286208 bytes, SHA-256 `1FD7EF78...`, the same file in
GOG's and Steam's 1.2.4), all by name; nothing else in the game loads it. Its DllMain only
refuses to run from the Windows folder, so it works under another name in the game folder.

So `src\version.def` also lists all 83 functions of RAD's file as forwarders, each as
`_BinkOpen@8 = binkw32_wiz8wide._BinkOpen@8`: the export table only says "this function is
`_BinkOpen@8` of `binkw32_wiz8wide.dll`", and the loader (Wine's or Windows') looks it up there
when a program imports the name. `Wiz8.exe` therefore gets the original's own addresses (the
`BinkOpenMiles` pointer that the game hands back to `BinkSetSoundSystem` stays the original's).
The copy loaded as `version.dll` never loads `binkw32_wiz8wide.dll`: `sr.dll` imports none of
those names (checked under Wine; on Windows every normal install shows it too: there is no
`binkw32_wiz8wide.dll` in the folder, and the game starts with the patch). The
build checks the forwarder texts ([building.md](building.md), section 3).

The installer, under Wine only (`ExtraInstallSteps` in `setup.cpp`, after the package files and
before the manifest):

1. takes the route only over the game's own `binkw32.dll`: RAD's file by its SHA-256, or a file
   that exports every name `Wiz8.exe` imports from `binkw32.dll` as code and forwards nothing
   (`ClassifyBink`), and only when the package's `version.dll` forwards all of those names to
   `binkw32_wiz8wide.dll` (`CarriesBinkForwarders`). Another mod's `binkw32.dll` is left alone,
   and the patch then starts through the Wine setting as before. A `binkw32.dll` that is
   already ours (a copy made by hand, an interrupted install) is set up again from the original
   in `Wiz8Wide.backup\` or, with that gone or not the original, in `binkw32_wiz8wide.dll`;
2. saves the original into `Wiz8Wide.backup\binkw32.dll` like every file it replaces (a copy
   that fails halfway leaves no part of it, `CopyToNewFile`: Wine's `CopyFileW` keeps a cut-off
   file, Windows' deletes it; and since only an original is ever saved there, a different file
   already there, one cut off by a full disk, is replaced, not kept as an older original), lists
   `binkw32.dll` and then `binkw32_wiz8wide.dll` in the manifest, copies the original to
   `binkw32_wiz8wide.dll` and `files\version.dll` over `binkw32.dll`. Both are copied under a
   temporary name (`<name>.wiz8wide-new`) and then renamed over the old file
   (`ReplaceByRename`): Wine sees only the programs of its own prefix, so `FindBusyFile` misses
   a game started from another prefix, and `CopyFileW` over a DLL that game has loaded rewrites
   the file under it (the same inode; the game crashed, Wine 9.0 and GE-Proton10-25). After a
   rename that game keeps its old file until it ends.

The game folder then has `binkw32.dll` = a copy of `version.dll`, `binkw32_wiz8wide.dll` = the
original, and the original again in `Wiz8Wide.backup\`. Because `binkw32.dll` is listed first,
any uninstall or rollback, by an older installer too, puts the original back before it deletes
the renamed copy: they are two ordinary file lines, so no `*format` change (the 1.0.2 installer
built from `7a0757a` uninstalled such a mock folder byte for byte, 2026-10-26). The new
installer also restores `binkw32.dll` from `binkw32_wiz8wide.dll` when the backup was deleted by
hand or is not the original (cut off), by a rename (`ReplaceByRename`, so `binkw32.dll` is never
a cut-off file), on Windows too (only a folder installed under Wine lists `binkw32.dll`, so a
Windows install never gets there); with neither copy of the original left and no backup, a
`binkw32.dll` that is not ours (a store's file check put the game's own back) stays (a damaged
backup without the renamed copy, which no install leaves behind, is put back like any other
saved file). When `binkw32.dll` cannot be put back, `binkw32_wiz8wide.dll` stays too and both
stay listed for the next Uninstall: ours still forwards to it, and it may be the only original
left. A file cut off inside its sections never counts as the original: `ClassifyBink` also wants
all the sections the file's section list names (`HasAllSections`). `binkw32_wiz8wide.dll` always
counts as a patch file, `binkw32.dll` only when it is a copy of ours (`IsPatchFile`); under Wine
install and uninstall refuse while either file is in use (`FindBusyFile`). The package's
`files\` has no `binkw32.dll`, so a copy made by hand never takes this route. The final message
under Wine then says `Linux (Wine/Proton): the patch starts by itself under Wine and Proton, in
any Wine prefix; no launch option is needed. If Steam, GOG Galaxy or Heroic checks or repairs
the game's files, run this installer again.`

The DLL (`src\loader_route.cpp`, called from DllMain) takes its role from its own file name:
`binkw32.dll` in any letter case, any other name is the `version.dll` role.

* As `binkw32.dll` it loads no real `version.dll` (`ProxyVersionLoad(false)`: its 17 version
  functions report failure, and nobody imports them from there), except when `version.dll` is
  this very file (a hard link or a symbolic link, as a tool that merges identical files makes
  them; `VersionDllIsThisFile` compares the file numbers: the inode under Wine, the NTFS file
  index on Windows): Wine, and Windows too, match a DLL to a loaded module by its file (Wine's
  own conformance test `kernel32/tests/loader.c` checks that on Windows with a hard link), load
  no second module, and give `sr.dll` this one as its `version.dll`, so it loads the real one
  too. Under Wine it starts the patch only when `version.dll` next to it has exactly the same
  bytes (read and compared in 8 KB pieces, no hashing in DllMain: an older copy left by a manual
  update must not run old code against a newer `wiz8hy.dll`, and deleting `version.dll` still
  turns the patch off) and no other copy started first; on Windows only when `version.dll` is
  this very file (then it is the only copy in the process).
* As `version.dll` it starts unless another copy started first.

"First" is a named mutex, `Local\Wiz8Widescreen-<process id>`, a lock every module of the
process can see: the copy that starts creates it and never closes it; a copy that finds it
already there only passes calls on: no ini, no hooks, no log (the log file could not be opened
twice anyway). Both copies are in one process when Wine also loads our `version.dll` (the
launch option, the Wine setting, Wine 11.7 and later); under Wine 9.0 and GE-Proton10-25 the
`binkw32.dll` copy runs its DllMain first (`Wiz8.exe` imports `BINKW32.DLL` before `SR.DLL`,
which imports `version.dll`), so it is the one that starts. Its DllMain runs when `sr.dll` is
already mapped (seen with mocks), so the game hooks can read `sr.dll`'s exports as before.

On Windows the `binkw32.dll` copy never starts while `version.dll` is a file of its own: a
folder installed under Wine and then used from Windows starts through `version.dll` as before,
and its videos go through the forwarders (checked in Windows Sandbox on 2026-10-25, with a folder
laid out that way that still had dgVoodoo and the DirectX 7 driver: the intro videos play and
the menu is wide). Since the render driver is the patch's own on both systems ("Which ddraw"),
such a folder needs no install run on Windows. With
`version.dll` a link to `binkw32.dll` (a tool that merges identical files, on a library shared
by dual boot) Windows loads that one file once, as `BINKW32.DLL` (`Wiz8.exe` imports it before
`SR.DLL`), so it is the copy that starts there; checked under Wine with the DLL's Windows paths
forced, and in Windows Sandbox on 2026-10-25 (the game starts with the patch). What Windows sees new in 1.0.3 is the static
`advapi32` import (already in the process through `sr.dll`) and the 83 forwarders, which resolve
only for a program that imports them; the mutex is made under Wine only.

Log lines (`wiz8ws.log`):

* the header ends in `(wiz8ws, loaded as binkw32.dll proxy)` instead of `(wiz8ws, loaded as
  version.dll proxy)`, there is no `real version.dll` line, and the next line is `started from
  binkw32.dll (no launch option needed); version.dll: Wine's own`, or `...; version.dll: our
  copy, forwarding only` when Wine loaded ours too (read from the module list, because two
  modules named `version.dll` can be loaded: ours and Wine's, which ours loads); `...; our copy,
  which could not load Wine's own version.dll, so the game's version calls fail; use
  WINEDLLOVERRIDES version=n,b, not version=n` when ours is there without Wine's (the option
  `version=n`, say), and for a `version.dll` that is a link to `binkw32.dll`: `this file too
  (version.dll is a link to binkw32.dll), forwarding to Wine's own`, or `..., which could not
  load ...` when the real one failed; on Windows (only with such a link) `started from
  binkw32.dll; version.dll: this file too (version.dll is a link to binkw32.dll), forwarding to
  the system version.dll`, or `..., which could not load the system version.dll (error N), so
  the game's version calls fail`;
* when the `version.dll` copy started and `binkw32.dll` is a copy of the patch: `binkw32.dll: a
  copy of the patch, forwarding only (the same file; version.dll started first)`, or `(not the
  same file as version.dll, an older copy: run the installer again)`.

What turns the route off:

* A store's file check (Steam's "Verify integrity of game files", GOG Galaxy's or Heroic's
  repair) puts the original `binkw32.dll` back (it is in GOG's file list,
  `goggame-galaxyFileList.ini`; such a check is assumed to leave the extra files alone). The
  game then starts through `version.dll` if the patch's Wine setting is in the game's prefix
  (the copy started as `binkw32.dll` writes it too, on purpose), otherwise unpatched. The
  installer's status line under Wine says `Status: version X is installed, but a file check
  replaced its Linux start file with the game's original: install again.`, and its button
  reads Reinstall (or `Update X -> Y` with a newer installer).
* `binkw32_wiz8wide.dll` deleted by hand: the game starts, and its first video ends it (`wine:
  unimplemented function BINKW32.DLL._BinkSetSoundSystem@8, aborting`; seen with a mock game).
* A `version.dll` built with an older lld (Ubuntu's LLVM 18): its forwarder texts read
  `_binkw32_wiz8wide.`, Wine finds no such DLL and the game dies at its first video; the
  export check in the build catches it.

### The patch keeps its own Wine setting

The launch option has to be typed into the launcher, and the installer's values reach only the
prefix it runs in. So since 1.0.3 the patch, once it has started under Wine, writes the
installer's values itself, into the prefix the game runs in: `WineKeepOverrides` in
`src\wine_settings.cpp`, called from `EnsureRuntime` right after the `wine <version>: ddraw.dll
is ...` line. That is the game's first `CreateWindowExA`: on its main thread, outside the loader
lock, with the log open, and before the game starts DirectDraw, so also on a start that is going
to crash in dgVoodoo. The values count from the next start (Wine has read the key already). The
values, notes and folder names are the installer's (`src\wine_overrides.h`), so the installer's
Uninstall takes them back. The rules, for `*version` = `native,builtin` and `*ddraw` =
`builtin` (in a 32-bit prefix written and noted together with the plain `ddraw` = `builtin`,
`PlainDdrawToo`):

* only for `Wiz8.exe` (any letter case): another program that loads the DLL (`3DSetup.exe` in
  the GOG folder, a tool) would write under the wrong name;
* a value already there, under the `*` name or the plain one, is left as it is, whoever wrote
  it, and the log names what it found;
* a value that `HKCU\Software\Wiz8Wide\Wine` notes as written but that is gone now was deleted
  by the player: it is not written again (the installer writes it again: running the installer
  is an explicit act). For `ddraw` a note under either name counts: an uninstall that kept a
  `DDraw.dll` may have dropped only one of them;
* `*ddraw` is not written when `WINEDLLOVERRIDES` gives `*ddraw` (or, without that, `ddraw`) an
  order that does not start with `b`: `ddraw=n,b` means the player wants dgVoodoo for this
  start, and ours would silently win over their plain `ddraw` from the next start. The variable
  is read the way Wine reads it (`WineEnvOrder`: entries split at `;`, `a,b=order`, `.dll`
  dropped, any letter case, the last entry wins);
* when this start got the game folder's `DDraw.dll` anyway (a global `ddraw=native` set by
  winetricks or Bottles, or Wine 11.6 and later), `*ddraw` is written with a note: the game
  crashes in dgVoodoo this once, and its next start gets Wine's own ddraw. With no `DDraw.dll`
  in the game folder such a start got a native `ddraw.dll` from Wine's system folder (a
  winetricks or Bottles component); the note then says that, and the next start gets Wine's own
  too (in a 32-bit prefix through the plain `ddraw=builtin`; the result below says otherwise
  only if that could not be written).

Then it reads both values back the way Wine will (`WineOrderOk`, the installer's check) and
says whether a start without the launch option gets the patch, and lists the game folder in
`...\Wine\Folders` unless that folder is listed already under any of its names; of several
names of one folder it keeps the one this start sees (else the first) and removes the others.
This runs before the exe check, so a `Wiz8.exe` the patch then switches itself off for gets
the values too; with `[General] Enabled=0` nothing is written (no hooks, so `EnsureRuntime`
never runs). The DLL links `advapi32` for the registry; `sr.dll` imports it anyway.

Log lines, one after the `wine <version>: ddraw.dll is ...` line:

* `wine settings (HKCU\Software\Wine\AppDefaults\Wiz8.exe\DllOverrides): <version item>, <ddraw
  item>; <result>`, where an item is one of `*version written (native,builtin)`, `*ddraw written
  (builtin)`, `*ddraw written (builtin; ddraw.dll came from the game folder this time, Wine's
  own from the next start)`, `*ddraw written (builtin; ddraw.dll was a native one from Wine's
  system folder this time)` (in a 32-bit prefix `; plain ddraw too, which a 32-bit prefix reads
  first` follows `builtin` in these three, or `; plain ddraw could not be written (error N)` or
  `; plain ddraw not kept, its note could not be written (error N)`), `<name> already set
  (<value>)` (`*version`, `version`, `*ddraw` or `ddraw`, as found), `<name> removed since it
  was written, not written again`, `*ddraw not written: WINEDLLOVERRIDES asks for
  ddraw=<order>`, `<name> could not be written (error N)`; and the result is `the patch starts
  without WINEDLLOVERRIDES in this prefix`, or, for each value Wine will not take as the patch
  needs it (checked one by one, joined by `; `): `a setting in this prefix keeps the patch from
  starting without WINEDLLOVERRIDES (left as it is)` for `version` (started as `binkw32.dll`:
  `... keeps version.dll from starting the patch without WINEDLLOVERRIDES (left as it is;
  binkw32.dll starts it)`) and `a setting in this prefix gives Wiz8.exe the game folder's
  ddraw.dll (dgVoodoo, which crashes under Wine; left as it is)` for `ddraw` (with no
  `DDraw.dll` in the game folder: `a setting in this prefix gives Wiz8.exe a native ddraw.dll
  from Wine's system folder instead of Wine's own (without one there the game does not start;
  left as it is)`). The normal line from the second start on: `*version already set
  (native,builtin), *ddraw already set (builtin); the patch starts without WINEDLLOVERRIDES in
  this prefix`;
* `wine settings: game folder listed in HKCU\Software\Wiz8Wide\Wine\Folders as <folder>` (or
  `could not be listed ... (error N)`), and `wine settings: N more name(s) of this game folder
  removed from HKCU\Software\Wiz8Wide\Wine\Folders`; nothing when the entry is there already;
* `wine settings: not Wiz8.exe, nothing written`.

When the setting is lost: wineserver saves the registry every 30 s when something changed, when
the prefix's last program ends and on SIGTERM (Wine 9.0's source); a SIGKILL within 30 s of the
write loses it, and the next start through the launch option or `binkw32.dll` writes it again.
A Proton upgrade keeps `AppDefaults`, also when it applies `wine.inf` again (checked); going
back to an older Valve Proton removes the prefix's `user.reg` with its other tracked files
(Valve's source; GE-Proton never takes that path), and so does deleting the game's compatibility
data in Steam: then one start with the launch option, or through `binkw32.dll`, puts it back. In
a read-only prefix or on a full disk the write lands only in wineserver's memory; the log then
says `written` at every start, and the launch option keeps working.

What is left behind: patch files deleted by hand, or an uninstall run in another prefix than the
game's, leave the values and notes in the game's prefix. They are harmless: with no
`version.dll` in the game folder, "game folder first" finds `system32\version.dll`, which is
Wine's own (checked with Wine 9.0 in a 64-bit and a 32-bit prefix), and `*ddraw=builtin` (with
the plain `ddraw=builtin` of a 32-bit prefix) is Wine's default. Only a `version.dll` mod copied
in later would load (as it would on Windows), and a dgVoodoo or D7VK experiment then needs
`*ddraw=n,b` (`ddraw=n,b` for one in the `system32` of a 32-bit prefix). The next uninstall in
that prefix drops the folders that no longer have the patch and then the values.

### Finding the game under Wine

On Windows the installer looks where it always did, with the same window and texts: GOG's
registry key, then Steam's libraries (`SteamPath`, `libraryfolders.vdf`). Under Wine Steam's
registry inside a Proton prefix is a stub (`SteamPath` without `steamapps`), and the games are
in Linux folders that the launchers' own files name (`tools_src\setup\wine_find.cpp`):

* A Windows program under Wine does not see `HOME` (Wine hides it, and from Wine 11 on all
  `XDG_*` variables), but Wine gives every program `WINEHOMEDIR` (the Linux home folder) and
  `WINECONFIGDIR` (the prefix it runs in) as NT paths: `\??\Z:\home\deck`, `\??\X:\` in a
  prefix made by umu (Heroic, Lutris with Proton), `\??\unix\home\deck` when no drive maps the
  folder. The installer opens them as `Z:\home\deck` or `\\?\unix\home\deck`.
* The launchers' files hold Linux paths. `kernel32!wine_get_dos_file_name` (looked up by name:
  only Wine has it) turns one into a path on the drive letter that maps it, or the installer
  uses `\\?\unix\...` when none does. A Linux path never goes through the old `/` to `\` step:
  `\home\deck` would be a folder on the current drive.

Sources, in the order the folder list shows them (each kept only when the folder has
`Wiz8.exe`):

1. GOG's registry key (32- and 64-bit view) and `HKLM\Software\Sirtech\Wizardry 8\Path` (written
   by GOG's installer script; assumed to stay): a GOG installer run in this prefix, so the game
   runs here;
2. Steam's non-Steam games: `userdata\<user>\config\shortcuts.vdf` (Steam's binary format) of
   every Steam folder (`STEAM_COMPAT_CLIENT_INSTALL_PATH`, `~/.local/share/Steam`,
   `~/.steam/steam`, `~/.steam/root`, the flatpak's, the snap's). The game folder is the one of
   `Exe` when that is `Wiz8.exe`, or `StartDir`; a shortcut that starts a launcher (Heroic's
   `heroic://launch/...`) is left to that launcher, and one that starts this installer
   (`Wiz8WideSetup.exe`, or the name it runs under) counts for no game: its `StartDir` is the
   game folder when the package was unpacked there, but its prefix is the installer's. A
   shortcut's prefix is `steamapps\compatdata\<appid as an unsigned number>\pfx` in any
   library (an old shortcut without `appid`: `crc32(Exe + AppName) | 0x80000000`, as
   Protontricks computes it);
3. Heroic (native and flatpak): `gog_store\installed.json` and `sideload_apps\library.json`,
   the prefix from `GamesConfig\<id>.json` (`winePrefix`, and its `pfx`, which umu makes a link
   to the folder itself);
4. Lutris (`~/.config/lutris`, `~/.local/share/lutris`, the flatpak's): `games\*.yml` (`exe`,
   `prefix`, `working_dir`; with no `prefix`, the part of the path before `drive_c`);
5. GOG installers run in other prefixes: `drive_c\GOG Games\Wizardry 8` and GOG Galaxy's game
   folder in Steam's `compatdata\*\pfx`, `~/.wine`, Heroic's and Lutris' default prefix folders
   (`~/Games/Heroic/Prefixes`, `~/Games`) and Bottles' (native and flatpak; Bottles' paths are
   assumed); the source is shown as `Wine prefix`;
6. the Steam game (app 245450): the `installdir` of `steamapps\appmanifest_245450.acf`, then
   `Wizardry 8` and `Wizardry8`, in every library (the Steam folders,
   `steamapps\libraryfolders.vdf`, `STEAM_COMPAT_LIBRARY_PATHS`); its prefix
   `compatdata\245450\pfx`. `SteamAppId=245450` never decides anything: umu reports it for the
   GOG game too.

Identity: under Wine one folder often has several names (`Z:\home\deck\Games\Wizardry 8`,
`X:\Games\Wizardry 8` in a umu prefix, a `\\?\unix` path, a link), so folders are compared by
what the file system says (`wine::SameFolder` in `src\wine_overrides.h`): the file number of the
folder and that of its `Wiz8.exe` (under Wine the Unix inode; two numbers, because one inode can
repeat on an SD card next to the internal disk; the volume serial number is left out under Wine,
where it differs per drive letter even for one folder). When either cannot be opened, the full
paths are compared in any letter case. The same folder from two sources is one entry with both
sources' prefixes. A prefix is identified the same way, by its folder and its `drive_c`.

Verdict, per entry (`PrefixVerdict`), shown as the third status line `Found by: <source> -
<verdict>` (sources `GOG`, `Steam`, `Steam shortcut "<name>"`, `Heroic`, `Lutris`, `Wine
prefix`):

* `runs in this Wine prefix` (THIS): the installer's prefix is the only one of its prefixes
  that exists;
* `runs in another Wine prefix` (OTHER);
* `its Wine prefix appears at the first start` (NOT_CREATED): its prefixes are known but none
  exists yet (Steam makes a shortcut's prefix at its first start);
* `Wine prefix not known` (UNKNOWN): a typed or browsed folder, or a launcher entry without a
  prefix; also the installer's prefix together with another existing one (a game installed with
  `wine setup.exe` into `~/.wine` and played through a Steam shortcut, which runs it in the
  shortcut's own `compatdata` prefix): it may run in either, so the values are written here and
  the launch option goes on the clipboard.

What it changes at the end of an install (`WineAfterInstall`):

| Verdict | with the binkw32 route | without it (another mod's `binkw32.dll`, say) |
|---|---|---|
| THIS | values written here; "starts by itself" | values written here; "the game's own Wine prefix is now set up for the patch; nothing else to do" |
| UNKNOWN | values written here; "starts by itself" | values written here; the note "if the main menu still shows only v1.2.4, add this to its launch options", with the option on the clipboard |
| OTHER, NOT_CREATED | nothing written; "starts by itself" | nothing written; "the game (found by: ...) runs in another Wine prefix ... add this to the game's launch options once", on the clipboard |

A setting of the player's that keeps the patch from starting gives the earlier "a setting in
this Wine prefix keeps the patch from starting" paragraph instead. Nothing is ever written into
another prefix: its `user.reg` may be open in its own wineserver, which would later save over
the change. The clipboard: Wine passes it to the X11 clipboard; the text was still there 6 s
after the installer exited (Wine 9.0, GE-Proton10-25); longer depends on the desktop's
clipboard manager (assumed).

The window, under Wine only (on Windows it stays as it was, byte for byte, apart from the
full-path rule below): the first THIS entry is preselected, else the first one; the status box
has the third line and the window is 16 px taller (262 instead of 246); Browse opens at the home
folder (Wine's folder dialog does not show dot folders such as `~/.local`, so pasting is the way
there); the folder box also takes what a player pastes from Linux: in quotes, `file://...`,
`~/...`, a `/...` path, or the path of `Wiz8.exe` itself (`NormalizeTypedFolder`, also for the
folder after `--install` and `--uninstall`). A folder given on the command line gets the verdict
of the entry it matches, else UNKNOWN, so the bench's `-Install setup` behaves as before. When
nothing is found the status says `Wizardry 8 was not found automatically. Choose the game
folder, or paste its Linux path, for example /home/deck/Games/Wizardry 8.`

A game folder counts only as a full path, `X:\...` or `\\...` (`IsGameDir`; `Uninstall` refuses
any other with the "does not contain Wizardry 8" message, `T_NOT_GAME`), since 1.0.3 on Windows
as well as under Wine. A drive alone (`G:`) still counts as that drive's root, as in 1.0.2: a
game at a drive root has the GOG key `G:\`, the candidate list trims it to `G:`, and every file
path is joined with a backslash. The installer is often started from the game folder: the
archive unpacked into it and the exe double-clicked, a Steam shortcut (which starts it in its
own folder), `wine Wiz8WideSetup.exe` typed in it. An empty name (the GOG key when it is not
there: no GOG installer ran on this Windows or in this prefix) or a relative one would then find
the game in the current folder, where the install's paths are no longer folder and file. The
1.0.2 installer, on Windows and under Wine, listed such an empty entry and preselected it;
Install then joined `""` and `D3DImm.dll` into a bare file name, made a folder of that name in
the game folder, said that nothing was left half-installed, and every later install into that
folder failed until the player deleted it. Now no empty or relative entry is listed, and neither
the window, Install and Uninstall nor `--install` and `--uninstall` act on the current folder; a
relative path typed into the folder box is not a game folder. On the command line a non-empty
relative folder is first made a full path against the current folder (`CommandLineFolder`:
`GetFullPathNameW`, under Wine after `NormalizeTypedFolder`), so `--install .` and `--install
"Wizardry 8"` work as in 1.0.2, on Windows and under Wine; an empty one (`""`, or only spaces
and slashes, as from a script whose variable was empty) stays empty and is refused with that
message and exit code 1, and nothing is created anywhere.

Known limits: Linux paths with non-English letters need a UTF-8 locale (under `LANG=C` Cyrillic
paths from the launchers' files are not found); in a prefix without `Z:` a `WIZ8.EXE` in capitals
is not recognised (`\\?\unix` names are case-sensitive); folder names with `"<>:|?*` cannot be
opened under Wine at all; flatpak launchers see only part of the home folder. Wine 9 names a
program started from a folder no drive maps `unix\home\...`; the installer puts `\\?\` in front
(`ExePath`), or it would not find its `files\` folder.

### Full screen under Wine

What Wine does with a display mode switch (as the game's DirectX 7 driver asked for one:
`getDisplayMode`, then exclusive mode and `SetDisplayMode`), checked 2026-10-25 by source and
with a small program that repeats the game's start:

* Wine's ddraw resizes the window to the mode and clips the cursor to it, so the client area is
  the mode and the mouse maps 1:1.
* Proton 9 (winex11's "fshack") and Proton 10 and 11 (modes emulated in win32u) only pretend to
  switch: they scale the picture to fit with black bars and map the cursor. GE-Proton10-25 on a
  1920x1080 X screen at 1024x768: the picture 1440x1080 at x = 240, the X screen unchanged,
  also on an X server with real RandR and after a kill.
* Steam Deck game mode (gamescope): Proton turns its emulation off but still pretends; gamescope
  then fits the window to the screen (assumed, not checked).
* Plain Wine on X11 (distro Wine, WineHQ, Bottles runners without fshack) really switches the
  monitor through XRandR; after a crash the screen stays at the game's resolution (Wine 9.0;
  Wine 10 and later restore it when the process ends, from the source). On an X server with
  one mode (Xvfb, some VMs) Wine 9.0 lists only the current mode.
* Plain Wine on Wayland through Xwayland: the monitor keeps its mode, but a 4:3 picture on a
  16:9 screen is stretched without bars (from Xwayland's source).

So the patch never asks Wine for a mode change, and since the render driver is the patch's own
(`Dll\srDD_D3D11.dll`), nothing in `wiz8hy.dll` is special for Wine any more. `Mode=fullscreen`
is the same on Windows and under Wine (`OpenRendererWindow` in `Video2.cpp`): the popup window
at the monitor's size, `srGERD::getDisplayMode` for the chosen size and `openWindow(mode)`, as
the original game does. The driver shows a display-mode open without changing the monitor's
mode (`FullscreenPresent=borderless`, its default: `drivers\srdd_d3d11\README.md`,
"Fullscreen"): the render target has the chosen size, and every frame is enlarged into the
window with black bars when the proportions differ. After such an open `NoteFullscreenOutput`
gives `OutputRect` (`Canvas.cpp`) the mode's size (`CanvasSetScaledOutputSize`), and the mouse
code uses the centred rectangle of those proportions, the same arithmetic as the driver's; so a
full screen entered from `Mode=window` (the full-screen key, a maximized window) is letterboxed
too, and there are bars only while the output is open in a display mode. Picture and mouse are
the same on Windows and under Wine, the monitor never switches, and nothing stays switched
after a crash.

A size the driver does not list (`getDisplayMode` gives -1: the ini edited by hand, another
monitor) opens borderless for this launch; the ini is not changed. The driver lists the classic
sizes, every 32-bit mode Windows or Wine reports for the monitor and the desktop size, and the
Options page offers only sizes it lists (`VideoFullscreenSizeSupported`). The lines in
`wiz8wide.log`:

* `[Display] fullscreen 1024x768: scaled into 1440x1080 at (240,0) of the 1920x1080 window`
  after a full-screen open (a 1024x768 picture in a 1280x800 window: `1066x800 at (107,0)`,
  rounded down as the mouse code rounds);
* `[Display] fullscreen 1024x768x32 not supported, using borderless`;
* `[Display] output: borderless, no scaling` (or `window, no scaling`) after every other open,
  on Windows and under Wine alike, so the last of these lines is the picture shown now, also
  after a switch in Options (the bench's `click640` reads it).

The start-up line reads `[Display] Mode=fullscreen: the render driver's full screen at the
chosen resolution, 1024x768`.

Never write `EmulateModeset`. Upstream Wine 10 and 11 have it as an opt-in value
(`HKCU\Software\Wine\AppDefaults\Wiz8.exe\X11 Driver`, `"EmulateModeset"="Y"`) that turns on
emulation like Proton's, but Valve's proton_10.0 and proton_11.0 read it the other way round
(`emulate_modeset = !IS_OPTION_TRUE(...)`): with GE-Proton10-25 `Y` turned the emulation off,
the monitor really switched and stayed switched after a kill; Wine 9.0 ignores it. The installer
never writes it (the comment at the top of `setup.cpp` says so).

### Log lines

Plain `version=n` (no `,b`) is wrong: our DLL loads, but then its `LoadLibrary` of
`system32\version.dll` fails (error 126). That file in the prefix is a copy of (or a link to)
Wine's own DLL, and with `n` alone Wine refuses to load its own DLLs. Since 1.0.3 each forwarded
function then reports failure instead of jumping to address 0 (stubs in `src\proxy_version.cpp`
with the right argument count: 0 and `ERROR_MOD_NOT_FOUND`, `VerFindFile` returns
`VFF_BUFFTOOSMALL`, `VerInstallFile` returns `VIF_CANNOTREADSRC`), and the log says
`real version.dll: FAILED (error 126) ...`. Under Wine the log also has a line
`wine <version>: ddraw.dll is ...`: `Wine's own (right: ...)`, `from the game folder
(dgVoodoo, which crashes under Wine: ...)` or, when the game folder has no `DDraw.dll`, `a
native one from Wine's system folder (if it is dgVoodoo, it crashes under Wine: ...)` (Wine's
own DLLs carry the text `Wine builtin DLL` at offset 0x40 of their image). Wine has no
`GetFileVersionInfoByHandle`; that forwarder stays empty, which is harmless (`sr.dll` imports
only `GetFileVersionInfoSizeA`, `GetFileVersionInfoA` and `VerQueryValueA`). The lines of the
binkw32 route and of the patch's own Wine setting are in their sections above. A start under
Wine therefore begins like this:

```text
Wizardry 8 Widescreen 1.0.3 (wiz8ws, loaded as binkw32.dll proxy)
game dir: Z:\home\deck\Games\gog\Wizardry 8\
started from binkw32.dll (no launch option needed); version.dll: Wine's own
wine 9.0: ddraw.dll is Wine's own (right: a dgVoodoo DDraw.dll left in the game folder would crash under Wine)
wine settings (HKCU\Software\Wine\AppDefaults\Wiz8.exe\DllOverrides): *version written (native,builtin), *ddraw written (builtin); the patch starts without WINEDLLOVERRIDES in this prefix
wine settings: game folder listed in HKCU\Software\Wiz8Wide\Wine\Folders as Z:\home\deck\Games\gog\Wizardry 8
```

### Newer Wine

Upstream Wine changed which game-folder DLL loads with no setting, in steps (Alexandre
Julliard's commits to `dlls/ntdll/unix/loadorder.c`, read at the tags wine-11.5 to wine-11.9,
2026-10-25):

* 11.6 (`a31ec8da`): a DLL whose version resource names a company that does not start with
  "Microsoft" loads from the game folder first (`native,builtin`). dgVoodoo's `DDraw.dll`
  (company `Dégé`) is such a DLL;
* 11.7 (`8cf7a53e`, Wine bug 59658): so does a DLL without a version resource. Our
  `version.dll` has none, so there it loads with no setting; do not give it a version resource
  that names Microsoft;
* 11.9: the same rules, rewritten, plus Wine's own copy only for "Twain Working Group" DLLs
  (bug 59743).

The rule applies only when no override matched, to a file outside the system folder that is
not one of Wine's own. Valve's branches proton_10.0, proton_11.0, experimental_11.0 and
bleeding-edge have none of it, so no Proton has it yet. With such a Wine both of our copies
load, and the mutex lets one of them start ("The patch starts through binkw32.dll"). A dgVoodoo
`DDraw.dll` in the game folder (a copy of `files\` of a package up to 1.0.2 made by hand, an
install made by 1.0.0 - 1.0.2; since 1.0.3 the package has no dgVoodoo, "Which ddraw") loads
too unless `*ddraw=builtin` (or `ddraw=b`) is set: in a prefix where neither the
installer nor an earlier start of the patch wrote it, the first start crashes once, after the
patch wrote `*ddraw=builtin`, and the next start works. That is why the launch option has
`ddraw=b`, both the installer and the patch write `*ddraw=builtin`, and the installer never
installs dgVoodoo.

The test bench for all this is in `scripts\linux\` ([testing.md](testing.md)).
