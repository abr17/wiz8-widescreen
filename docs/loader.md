# What `version.dll` does at run time

`version.dll` (built from `src\`, see [building.md](building.md)) is the patch's loader: the game's
`sr.dll` loads it in place of the Windows DLL of the same name, it passes the real
`version.dll` calls through, checks the exe, hooks `WinMain` and loads `wiz8hy.dll`
([hybrid.md](hybrid.md)). Besides that it has two features of its own, which do not depend on
the widescreen code. Like everything in the loader they need `[General] Enabled=1`: with
`Enabled=0` `version.dll` only passes calls through and writes no log at all.

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
again and send `wiz8ws.log`, `wiz8hy.log`, `wiz8wide.log` from the game folder and the whole
`Wiz8Logs\` folder (the READMEs say the same).

The installer (1.0.2 and later) sets the switch with its "Diagnostics mode" checkbox (or
`--diagnostics` / `--no-diagnostics` after the folder on its command line): off on a fresh
install; over an install the checkbox shows the current value, and an update or reinstall never
changes it unless the player does. An update, reinstall or rollback also keeps `Wiz8Logs\` and,
when it exists, moves the logs of the last session into it first; a full uninstall (by the 1.0.2 installer or later)
removes the patch's files from it (`20*\` session folders with the three logs, `crash-*.dmp`) and
the folder if nothing else is left.

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
