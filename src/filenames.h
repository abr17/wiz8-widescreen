#pragma once

#include <windows.h>

// File names when Windows uses UTF-8 as the system code page.
//
// The game keeps names of characters and saves as single-byte text (with the Russian data
// these are cp1251 codes) and passes them to the "A" (ANSI) file functions, for example
// CreateFileA("Saves\\Characters\\<nickname>.CHR"). Windows reads such a name in the system
// code page. With the beta option "Use Unicode UTF-8 for worldwide language support" that
// code page is UTF-8, where a lone non-English byte is invalid and becomes U+FFFD: every
// nickname of the same length gets the same file name ("a character with this nickname
// already exists") and the save list shows garbage.
//
// Only in that case (GetACP() == CP_UTF8) the game's file functions are redirected to
// wrappers that call the "W" (Unicode) functions with the name read in the code page Windows
// would use without the option (the system locale's ANSI code page). So the files are named
// as the game names them with the option off (with one rare exception, see filenames.cpp),
// and older files keep working.

// Called from the WinMain hook (all DLLs are loaded by then): redirects the file imports of
// Wiz8.exe and, if loaded, wiz8hy.dll. Returns the number of redirected imports, or -1 when
// nothing is needed (the system code page is not UTF-8).
int InstallFileNameHooks(HMODULE hybrid);

// The code page used for the game's names (valid after InstallFileNameHooks returned >= 0).
UINT FileNameCodePage();

#ifdef WIZ8WS_TESTING
// test_filenames only: behave as on a system with another ANSI code page (1251, 932, ...).
void SetFileNameCodePage(UINT cp);
#endif
