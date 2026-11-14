// Wiz8WideSetup.exe - installer of the Wizardry 8 widescreen patch (hybrid).
//
// Next to the exe there is a "files" folder with the patch contents (what goes into the
// game folder). The installer:
//   - finds the game: GOG (registry), Steam (libraryfolders.vdf), or a folder picked by hand;
//   - checks Wiz8.exe by SHA-256 (GOG/Steam 1.2.4); another version only gets a
//     warning (owner's decision: "at your own risk");
//   - does not touch a foreign version.dll (another mod) - warns and exits;
//   - refuses a "files" folder that lacks a file an install must have (kRequiredFiles):
//     names the file and changes nothing;
//   - before installing, saves what will be replaced into Wiz8Wide.backup\,
//     the list of installed files into Wiz8Wide.installed.txt; uninstalling returns
//     the game folder to its original state;
//   - asks for administrator rights only if the game folder is not writable
//     (Program Files) - restarts itself via runas;
//   - knows its own version (the VERSION file) and writes it into Wiz8Wide.installed.txt
//     (line "*version=X"; the list of 1.0.0 has no such line). Over an older version the
//     install button becomes "Update X -> Y", over the same one "Reinstall", over a newer
//     one "Roll back X -> Y" (asks first): all of them quietly uninstall the old files first
//     and keep the player's wiz8wide.ini and wiz8ws.ini's Enabled=0, also through a failure;
//   - changes nothing while a file of the folder is in use (the game running);
//   - a "Diagnostics mode" checkbox sets [Debug] Diagnostics of wiz8ws.ini (docs\loader.md):
//     off on a fresh install, over an install it shows the current value and the install
//     writes whatever the player leaves it at; without the window --diagnostics or
//     --no-diagnostics after the folder, neither = keep the current value;
//   - a "Report a problem..." button packs the logs, the settings and the crash dumps of the
//     game folder with a summary of the system into one zip on the Desktop and offers the bug
//     report page (see "report" below; without the window --report "folder" ["file.zip"]);
//   - installs the patch's render driver, Dll\srDD_D3D11.dll, next to the game's own drivers
//     (it is part of files\ like everything else; the game's drivers are not touched). Since
//     1.0.3 the package has no dgVoodoo: an update removes the dgVoodoo files an older version
//     installed (they are in its list) and puts back what they replaced, and dgVoodoo files
//     left in files\ by an older package unpacked into the same folder are not installed
//     (IsDgVoodoo);
//   - under Wine (Linux, Steam Deck: Proton is Wine) tells Wine to load the patch's version.dll
//     from the game folder for Wiz8.exe (by default Wine takes its own and the patch silently
//     does not start) and to keep its own ddraw.dll (a dgVoodoo DDraw.dll left in the game
//     folder crashes under Wine), and takes that back on uninstall. The patch itself writes
//     the same values, with the same notes, when it starts under Wine (src\wine_overrides.h),
//     so the uninstall takes back either. Wine's EmulateModeset value is never written: Valve's
//     Proton 10 and 11 read it the other way round (docs\loader.md);
//   - under Wine also finds the game in the Linux launchers' files (Steam libraries and
//     non-Steam shortcuts, Heroic, Lutris, GOG installers in other prefixes: wine_find.cpp),
//     tells whether it runs in the Wine prefix the installer runs in (the "Found by" line), and
//     sets the Wine values only where they reach the game; otherwise the final message gives
//     the launch option, also on the clipboard;
//   - under Wine also makes the patch start with no setting at all: the game's binkw32.dll
//     becomes a copy of the patch's version.dll (which also carries binkw32's functions) and
//     the original moves to binkw32_wiz8wide.dll (see "binkw32.dll" below).
// Wiz8Wide.installed.txt must stay readable by older installers, because any of them may be
// run over a newer install: one line per file that uninstall removes (relative path): an
// installed file, or one the patched game writes itself (the render driver's logs, 3DVideo.CFG;
// such a file need not exist), "+folder" for a folder the install created, and lines starting
// with '*' for everything else ('*' cannot be in a file name; 1.0.0 treats such a line as a
// missing file, later installers skip it). For each file line every installer deletes the file
// and then puts back its saved original from Wiz8Wide.backup\, if there is one.
// Uninstalling follows this list, not the payload, so an older installer removes exactly what
// a newer one installed. If a future installer ever needs uninstall to do more, it writes
// "*format=2" (or higher): installers that know a lower format then refuse to touch the folder.
// Window language follows the Windows language: Russian, German, French, otherwise English.
//
// Build: tools_src\setup\build.ps1 (llvm-mingw, i686, static, no dependencies; setup.cpp and
// wine_find.cpp; zip_writer.h, the report file's archive writer, is a header).

#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <shlobj.h>
#include <bcrypt.h>
#include <commctrl.h>

#include <cstddef>
#include <cstring>
#include <string>
#include <vector>
#include <algorithm>

#include "setup_version.h" /* WIZ8WIDE_VERSION, generated by build.ps1 from VERSION */
#include "../../src/wine_overrides.h" /* the Wine settings, shared with the patch DLL */
#include "wine_find.h"                /* finding the game under Wine */
#include "zip_writer.h"               /* the report file ("Report a problem...") */

namespace {

using namespace wine; /* UnderWine, ReadUserValue, kWineKey, ... (src/wine_overrides.h),
                         Candidate, FindWineGames, ... (wine_find.h) */

const wchar_t kVersion[] = WIZ8WIDE_VERSION;
const wchar_t kTitle[] = L"Wizardry 8 Widescreen " WIZ8WIDE_VERSION;
const wchar_t kExeSha256[] = L"18A74FF61C65B8A2D4CFA11FFCE82AD7FEF022A94EAF0C2F217E479E981420D2";
const wchar_t kManifest[] = L"Wiz8Wide.installed.txt";
/* first line of the manifest; '*' cannot be in a file name, so an older installer that
   treats it as a path just fails to delete it */
const wchar_t kVersionLine[] = L"*version=";
/* manifest format this installer can undo; no "*format=" line = 1 (1.0.0 and later) */
const wchar_t kFormatLine[] = L"*format=";
const int kFormat = 1;
const wchar_t kBackupDir[] = L"Wiz8Wide.backup";
const wchar_t kGogId[] = L"1207659230";
/* the binkw32 route under Wine (see "binkw32.dll" below): the game's file, its renamed original,
   and the SHA-256 of RAD's binkw32.dll 1.0q that GOG and Steam 1.2.4 ship (docs\history\recon.md) */
const wchar_t kBink[] = L"binkw32.dll";
const wchar_t kBinkOriginal[] = L"binkw32_wiz8wide.dll";
const wchar_t kBinkSha256[] = L"1FD7EF7873C8A3BE7E2F127B306D0D24D7D88E20CF9188894EFF87B5AF0D495F";
/* dgVoodoo 2, which the packages up to 1.0.2 had at the root of files\ (the game's DirectX 7
   driver needed it on modern Windows). Since 1.0.3 the patch brings its own Direct3D 11 render
   driver instead (Dll\srDD_D3D11.dll) and these are never installed (see IsDgVoodoo) */
const wchar_t* const kDgVoodoo[] = {L"DDraw.dll", L"D3DImm.dll", L"dgVoodoo.conf"};
/* the logs the patch's render driver, Dll\srDD_D3D11.dll of the package, writes next to itself
   (the patched game names that driver in 3DVideo.CFG at every start). An install lists them in
   the manifest, so that any uninstall removes them, also one by an older installer */
const wchar_t* const kDriverLogs[] = {L"Dll\\srDD_D3D11.log", L"Dll\\srDD_D3D11.log.old"};
/* the files of files\ an install is refused without. Without the loader (version.dll), the
   widescreen engine (wiz8hy.dll) or the engine's hook list (wiz8hy_hooks.txt) the game starts
   unpatched: with no list the engine replaces none of the game's functions (and with the list
   of another build, which a copy made by hand may have left in the game folder, the game
   crashes at start-up). Without the render driver it does not start at all: the engine names
   that driver in 3DVideo.CFG at every start and the patched game uses no other. The loader's
   settings (wiz8ws.ini) are not needed for the start, since the loader's built-in defaults are
   the values of the packaged file. They are required because the installer writes the player's
   "[General] Enabled=0" and the diagnostics switch into the installed copy: a wiz8ws.ini that
   those writes had to create would not be in the manifest, and uninstall would leave it behind.
   The rest of the package may be missing: the engine has a default for every setting of
   wiz8wide.ini and draws the original art where the wide art is not there */
const wchar_t* const kRequiredFiles[] = {L"version.dll", L"wiz8hy.dll", L"wiz8hy_hooks.txt",
                                         L"wiz8ws.ini", L"Dll\\srDD_D3D11.dll"};
/* the launch option the final message gives under Wine (and puts on the clipboard); always
   passed to Tr() as a %s argument: as a format text its "%c" would be read as a character */
const wchar_t kLaunchOption[] = L"WINEDLLOVERRIDES=\"version=n,b;ddraw=b\" %command%";

/* ---------------- texts ---------------- */

enum Text {
    T_INTRO,
    T_FOLDER,
    T_BROWSE,
    T_INSTALL,
    T_UNINSTALL,
    T_EXIT,
    T_NOT_FOUND,
    T_NOT_GAME,
    T_UNKNOWN_EXE,
    T_FOREIGN_DLL,
    T_DONE_INSTALL,
    T_DONE_UNINSTALL,
    T_NOTHING_TO_UNINSTALL,
    T_COPY_FAILED,
    T_NO_FILES,
    T_FILE_MISSING,
    T_STATUS_INSTALLED,
    T_STATUS_NOT_INSTALLED,
    T_STATUS_OK_EXE,
    T_STATUS_OTHER_EXE,
    T_PICK_FOLDER,
    T_REINSTALL,
    T_UPDATE,
    T_DONE_UPDATE,
    T_ROLLBACK,
    T_ASK_ROLLBACK,
    T_DONE_ROLLBACK,
    T_STATUS_NEWER,
    T_STATUS_NEWER_FORMAT,
    T_NEWER_FORMAT,
    T_IN_USE,
    T_UNINSTALL_INCOMPLETE,
    T_UPDATE_FAILED,
    T_DIAGNOSTICS,
    T_WINE_NOTE,
    T_WINE_OWN,
    /* under Wine only (see WineAfterInstall, UpdateStatus) */
    T_WINE_THIS,
    T_WINE_OTHER,
    T_WINE_AUTO,
    T_NOT_FOUND_WINE,
    T_FOUND_BY,
    T_SOURCE_GOG,
    T_SOURCE_STEAM,
    T_SOURCE_SHORTCUT,
    T_SOURCE_HEROIC,
    T_SOURCE_LUTRIS,
    T_SOURCE_PREFIX,
    T_VERDICT_THIS,
    T_VERDICT_OTHER,
    T_VERDICT_NOT_CREATED,
    T_VERDICT_UNKNOWN,
    T_STATUS_RESTORED,
    /* "Report a problem..." (see "report" below) */
    T_REPORT,
    T_REPORT_DONE,
    T_REPORT_PARTLY, /* the second %s of T_REPORT_DONE when not everything went into the file */
    T_REPORT_FAILED,
    T_REPORT_PAGE,
    T_COUNT
};

const wchar_t* const kEnglish[T_COUNT] = {
    L"Native widescreen for Wizardry 8 (GOG and Steam). Choose the game folder:",
    L"Game folder:",
    L"Browse...",
    L"Install",
    L"Uninstall",
    L"Exit",
    L"Wizardry 8 was not found automatically. Please choose the game folder.",
    L"This folder does not contain Wizardry 8 (Wiz8.exe and Data are missing).",
    L"This Wiz8.exe is not the tested version.\n\nThe patch was tested only with Wizardry 8 1.2.4 "
    L"(GOG and Steam). It may not work with this version - install at your own risk.\n\n"
    L"If the game code differs, the patch switches itself off at start-up and the game runs "
    L"as the original.\n\nInstall anyway?",
    L"The game folder already contains a version.dll that does not belong to this patch "
    L"(probably another mod). It was not changed.\n\nRemove or rename that mod first, then run "
    L"the installer again.",
    L"The widescreen patch %s is installed.\n\nStart the game as usual. Display mode, resolution and "
    L"view distance are in Options - Video.",
    L"The widescreen patch was removed. The game folder is as it was before.",
    L"The patch is not installed in this folder.",
    L"Could not copy a file:\n%s\n\nNothing was left half-installed; the previous state was restored.",
    L"The \"files\" folder next to the installer is missing. Unpack the whole archive first.",
    L"A file of the patch is missing from the \"files\" folder next to the installer:\n%s\n\n"
    L"Unpack the whole archive again (an antivirus program may have removed the file). Nothing "
    L"was changed.",
    L"Status: version %s of the patch is installed.",
    L"Status: the patch is not installed.",
    L"Wiz8.exe: version 1.2.4 (tested).",
    L"Wiz8.exe: unknown version (not tested).",
    L"Choose the Wizardry 8 folder (the one with Wiz8.exe):",
    L"Reinstall",
    L"Update %s \x2192 %s",
    L"The widescreen patch was updated from %s to %s. Your settings were kept.\n\nStart the game "
    L"as usual.",
    L"Roll back %s \x2192 %s",
    L"This folder has a newer version of the patch: %s. This installer is version %s.\n\n"
    L"Roll back to the older version? Your settings will be kept.",
    L"The widescreen patch was rolled back from %s to %s. Your settings were kept.\n\nStart the "
    L"game as usual.",
    L"Status: version %s of the patch is installed (newer than this installer, %s).",
    L"Status: version %s of the patch comes from a newer installer; use the installer of "
    L"version %s or newer.",
    L"Version %s of the patch in this folder was installed by a newer installer, and this one "
    L"cannot safely change it. Nothing was changed.\n\nUse the installer of version %s or newer.",
    L"A file in the game folder is in use:\n%s\n\nClose Wizardry 8 (and any program that has its "
    L"files open) and try again. Nothing was changed.",
    L"Some files could not be removed, for example:\n%s\n\nClose Wizardry 8 (and any program that "
    L"has its files open) and run Uninstall again.",
    L"Could not copy a file:\n%s\n\nThe patch is not installed now: the old version had already "
    L"been removed, and the game folder is back to the original. Your settings are kept for the "
    L"next install.",
    L"Diagnostics mode (for bug reports)",
    L"\n\nLinux (Wine/Proton): in this Wine prefix Wiz8.exe now loads the patch's version.dll "
    L"from the game folder, together with Wine's own ddraw.dll (a dgVoodoo DDraw.dll left in the "
    L"game folder would crash under Wine). If the main menu still shows only v1.2.4, the game "
    L"runs in another Wine prefix: add this to its launch options (Steam: Properties - General - "
    L"Launch Options); it is on the clipboard:\n%s\n"
    L"After one start with it the patch remembers this, and later starts work without it. "
    L"(Heroic, Lutris, Bottles, plain Wine: see the Linux section of the README.)",
    L"\n\nLinux (Wine/Proton): a setting in this Wine prefix keeps the patch from starting "
    L"(HKCU\\Software\\Wine\\AppDefaults\\Wiz8.exe\\DllOverrides or "
    L"HKCU\\Software\\Wine\\DllOverrides); it was left as it is. For the patch, version "
    L"should be native,builtin and ddraw builtin (a dgVoodoo DDraw.dll left in the game folder "
    L"would crash under Wine).",
    L"\n\nLinux (Wine/Proton): the game's own Wine prefix is now set up for the patch; nothing "
    L"else to do.",
    L"\n\nLinux (Wine/Proton): the game (found by: %s) runs in another Wine prefix than this "
    L"installer, so nothing was set up for it here. Add this to the game's launch options once; "
    L"it is on the clipboard:\n%s\n"
    L"Steam: Properties - General - Launch Options (a non-Steam game: Shortcut - Launch "
    L"Options). Heroic, Lutris: see the Linux section of the README. After one start with it the "
    L"patch sets up the game's Wine prefix itself, and later starts work without it.",
    L"\n\nLinux (Wine/Proton): the patch starts by itself under Wine and Proton, in any Wine "
    L"prefix; no launch option is needed. If Steam, GOG Galaxy or Heroic checks or repairs the "
    L"game's files, run this installer again.",
    L"Wizardry 8 was not found automatically. Choose the game folder, or paste its Linux path, "
    L"for example /home/deck/Games/Wizardry 8.",
    L"Found by: %s - %s",
    L"GOG",
    L"Steam",
    L"Steam shortcut \"%s\"",
    L"Heroic",
    L"Lutris",
    L"Wine prefix",
    L"runs in this Wine prefix",
    L"runs in another Wine prefix",
    L"its Wine prefix appears at the first start",
    L"Wine prefix not known",
    L"Status: version %s is installed, but a file check replaced its Linux start file with the "
    L"game's original: install again.",
    L"Report a problem...",
    L"The report file was saved:\n%s\n(its path is on the clipboard)\n\n"
    L"It holds the patch's logs and settings and the crash dumps, if there are any. They contain "
    L"folder names, so also your user name.%s\n\n"
    L"Open the bug report page on GitHub now? Describe there what happened and add this file. "
    L"Reports there are public.",
    L" Not everything fit into the file: its report.txt says what was left out or shortened.",
    L"Could not save the report file:\n%s",
    L"The browser did not open. The bug report page:\n%s",
};

const wchar_t* const kRussian[T_COUNT] = {
    L"Нативный широкий экран для Wizardry 8 (GOG и Steam). Выберите папку игры:",
    L"Папка игры:",
    L"Обзор...",
    L"Установить",
    L"Удалить",
    L"Выход",
    L"Wizardry 8 не найдена автоматически. Выберите папку с игрой.",
    L"В этой папке нет Wizardry 8 (нет Wiz8.exe и Data).",
    L"Этот Wiz8.exe - не проверенная версия.\n\nПатч проверялся только на Wizardry 8 1.2.4 "
    L"(GOG и Steam). С этой версией он может не работать - ставьте на свой страх и риск.\n\n"
    L"Если код игры отличается, патч при запуске сам выключится, и игра пойдёт как оригинал.\n\n"
    L"Всё равно установить?",
    L"В папке игры уже есть version.dll, который не относится к этому патчу (вероятно, другой "
    L"мод). Он не тронут.\n\nСначала удалите или переименуйте тот мод, потом запустите "
    L"установщик ещё раз.",
    L"Широкоэкранный патч %s установлен.\n\nЗапускайте игру как обычно. Режим экрана, разрешение и "
    L"дальность прорисовки - в Опциях, раздел «Видео».",
    L"Широкоэкранный патч удалён. Папка игры - как была до установки.",
    L"В этой папке патч не установлен.",
    L"Не удалось скопировать файл:\n%s\n\nНичего не осталось наполовину: прежнее состояние "
    L"восстановлено.",
    L"Рядом с установщиком нет папки \"files\". Сначала распакуйте архив целиком.",
    L"В папке \"files\" рядом с установщиком не хватает файла патча:\n%s\n\n"
    L"Распакуйте архив целиком ещё раз (файл мог удалить антивирус). Ничего не изменено.",
    L"Состояние: установлен патч версии %s.",
    L"Состояние: патч не установлен.",
    L"Wiz8.exe: версия 1.2.4 (проверена).",
    L"Wiz8.exe: неизвестная версия (не проверялась).",
    L"Выберите папку Wizardry 8 (ту, где лежит Wiz8.exe):",
    L"Переустановить",
    L"Обновить %s \x2192 %s",
    L"Широкоэкранный патч обновлён с %s до %s. Ваши настройки сохранены.\n\nЗапускайте игру "
    L"как обычно.",
    L"Откатить %s \x2192 %s",
    L"В этой папке стоит более новая версия патча: %s. Этот установщик - версии %s.\n\n"
    L"Откатить на старую версию? Ваши настройки сохранятся.",
    L"Широкоэкранный патч откачен с %s на %s. Ваши настройки сохранены.\n\nЗапускайте игру "
    L"как обычно.",
    L"Состояние: установлен патч версии %s (новее этого установщика, %s).",
    L"Состояние: патч версии %s ставил более новый установщик; используйте установщик "
    L"версии %s или новее.",
    L"Версию патча %s в этой папке ставил более новый установщик, и этот не может безопасно её "
    L"изменить. Ничего не изменено.\n\nИспользуйте установщик версии %s или новее.",
    L"Файл в папке игры занят:\n%s\n\nЗакройте Wizardry 8 (и программы, открывшие её файлы) и "
    L"попробуйте ещё раз. Ничего не изменено.",
    L"Не удалось удалить некоторые файлы, например:\n%s\n\nЗакройте Wizardry 8 (и программы, "
    L"открывшие её файлы) и снова нажмите «Удалить».",
    L"Не удалось скопировать файл:\n%s\n\nСейчас патч не установлен: старая версия уже была "
    L"удалена, папка игры вернулась к оригиналу. Ваши настройки сохранены для следующей "
    L"установки.",
    L"Режим диагностики (для сообщений об ошибках)",
    L"\n\nLinux (Wine/Proton): в этом префиксе Wine игра Wiz8.exe теперь берёт version.dll "
    L"патча из папки игры, а ddraw.dll встроенную в Wine (оставшаяся в папке игры DDraw.dll от "
    L"dgVoodoo под Wine вызвала бы сбой). Если в главном меню по-прежнему только v1.2.4, игра "
    L"запускается в другом префиксе Wine: добавьте в её параметры запуска (Steam: Свойства - "
    L"Общие - Параметры запуска); это уже в буфере обмена:\n%s\n"
    L"После одного запуска с ним патч это запомнит, и дальше игра пойдёт и без него. "
    L"(Heroic, Lutris, Bottles, просто Wine: см. раздел Linux в README.)",
    L"\n\nLinux (Wine/Proton): настройка в этом префиксе Wine не даёт патчу запуститься "
    L"(HKCU\\Software\\Wine\\AppDefaults\\Wiz8.exe\\DllOverrides или "
    L"HKCU\\Software\\Wine\\DllOverrides); она не тронута. Для патча нужно version = "
    L"native,builtin и ddraw = builtin (оставшаяся в папке игры DDraw.dll от dgVoodoo под Wine "
    L"вызвала бы сбой).",
    L"\n\nLinux (Wine/Proton): собственный префикс Wine игры настроен для патча; больше ничего "
    L"делать не нужно.",
    L"\n\nLinux (Wine/Proton): игра (найдена через: %s) запускается в другом префиксе Wine, "
    L"не в том, где работает установщик, поэтому здесь для неё ничего не настроено. Один раз "
    L"добавьте в параметры запуска игры (это уже в буфере обмена):\n%s\n"
    L"Steam: Свойства - Общие - Параметры запуска (сторонняя игра: Ярлык - Параметры запуска). "
    L"Heroic, Lutris: см. раздел Linux в README. После одного запуска с ним патч сам настроит "
    L"префикс Wine игры, и дальше игра пойдёт и без него.",
    L"\n\nLinux (Wine/Proton): патч запускается сам под Wine и Proton, в любом префиксе Wine; "
    L"параметры запуска не нужны. Если Steam, GOG Galaxy или Heroic проверит или восстановит "
    L"файлы игры, запустите этот установщик ещё раз.",
    L"Wizardry 8 не найдена автоматически. Выберите папку с игрой или вставьте её путь в Linux, "
    L"например /home/deck/Games/Wizardry 8.",
    L"Найдена через: %s - %s",
    L"GOG",
    L"Steam",
    L"ярлык Steam «%s»",
    L"Heroic",
    L"Lutris",
    L"префикс Wine",
    L"запускается в этом префиксе Wine",
    L"запускается в другом префиксе Wine",
    L"её префикс Wine появится при первом запуске",
    L"префикс Wine неизвестен",
    L"Состояние: установлена версия %s, но проверка файлов заменила файл запуска для Linux "
    L"оригиналом игры: установите ещё раз.",
    L"Сообщить об ошибке...",
    L"Файл отчёта сохранён:\n%s\n(путь к нему скопирован в буфер обмена)\n\n"
    L"В нём журналы и настройки патча и дампы сбоев, если они есть. В них есть имена папок, а "
    L"значит и ваше имя пользователя.%s\n\n"
    L"Открыть страницу отчёта об ошибке на GitHub? Опишите там, что произошло, и приложите этот "
    L"файл. Отчёты там видны всем.",
    L" В файл поместилось не всё: в его report.txt сказано, что пропущено или сокращено.",
    L"Не удалось сохранить файл отчёта:\n%s",
    L"Браузер не открылся. Страница отчётов об ошибках:\n%s",
};

const wchar_t* const kGerman[T_COUNT] = {
    L"Natives Breitbild f\x00fcr Wizardry 8 (GOG und Steam). W\x00e4hlen Sie den Spielordner:",
    L"Spielordner:",
    L"Durchsuchen...",
    L"Installieren",
    L"Entfernen",
    L"Beenden",
    L"Wizardry 8 wurde nicht automatisch gefunden. Bitte w\x00e4hlen Sie den Spielordner.",
    L"Dieser Ordner enth\x00e4lt kein Wizardry 8 (Wiz8.exe und Data fehlen).",
    L"Diese Wiz8.exe ist nicht die getestete Version.\n\nDer Patch wurde nur mit Wizardry 8 "
    L"1.2.4 (GOG und Steam) getestet. Mit dieser Version funktioniert er m\x00f6glicherweise "
    L"nicht - Installation auf eigene Gefahr.\n\nWeicht der Spielcode ab, schaltet sich der "
    L"Patch beim Start selbst ab und das Spiel l\x00e4uft wie das Original.\n\nTrotzdem "
    L"installieren?",
    L"Im Spielordner liegt bereits eine version.dll, die nicht zu diesem Patch geh\x00f6rt "
    L"(vermutlich ein anderer Mod). Sie wurde nicht ver\x00e4ndert.\n\nEntfernen oder "
    L"umbenennen Sie zuerst diesen Mod und starten Sie den Installer erneut.",
    L"Der Breitbild-Patch %s ist installiert.\n\nStarten Sie das Spiel wie gewohnt. Anzeigemodus, "
    L"Aufl\x00f6sung und Sichtweite finden Sie unter Optionen - Video.",
    L"Der Breitbild-Patch wurde entfernt. Der Spielordner ist wie vorher.",
    L"Der Patch ist in diesem Ordner nicht installiert.",
    L"Eine Datei konnte nicht kopiert werden:\n%s\n\nEs blieb nichts halb installiert; der "
    L"vorherige Zustand wurde wiederhergestellt.",
    L"Der Ordner \"files\" neben dem Installer fehlt. Bitte zuerst das ganze Archiv entpacken.",
    L"Im Ordner \"files\" neben dem Installer fehlt eine Datei des Patches:\n%s\n\n"
    L"Entpacken Sie das ganze Archiv erneut (ein Antivirenprogramm hat die Datei "
    L"m\x00f6glicherweise entfernt). Es wurde nichts ver\x00e4ndert.",
    L"Status: Version %s des Patches ist installiert.",
    L"Status: Der Patch ist nicht installiert.",
    L"Wiz8.exe: Version 1.2.4 (getestet).",
    L"Wiz8.exe: unbekannte Version (nicht getestet).",
    L"W\x00e4hlen Sie den Ordner von Wizardry 8 (mit Wiz8.exe):",
    L"Neu installieren",
    L"%s \x2192 %s aktualisieren",
    L"Der Breitbild-Patch wurde von %s auf %s aktualisiert. Ihre Einstellungen wurden "
    L"beibehalten.\n\nStarten Sie das Spiel wie gewohnt.",
    L"%s \x2192 %s zur\x00fc" L"ckstufen",
    L"In diesem Ordner ist eine neuere Version des Patches installiert: %s. Dieser Installer hat "
    L"die Version %s.\n\nAuf die \x00e4ltere Version zur\x00fc" L"ckstufen? Ihre Einstellungen "
    L"bleiben erhalten.",
    L"Der Breitbild-Patch wurde von %s auf %s zur\x00fc" L"ckgestuft. Ihre Einstellungen wurden "
    L"beibehalten.\n\nStarten Sie das Spiel wie gewohnt.",
    L"Status: Version %s des Patches ist installiert (neuer als dieser Installer, %s).",
    L"Status: Version %s des Patches stammt von einem neueren Installer; verwenden Sie den "
    L"Installer der Version %s oder neuer.",
    L"Version %s des Patches in diesem Ordner wurde von einem neueren Installer installiert, "
    L"und dieser kann sie nicht sicher \x00e4ndern. Es wurde nichts ver\x00e4ndert.\n\n"
    L"Verwenden Sie den Installer der Version %s oder neuer.",
    L"Eine Datei im Spielordner wird gerade verwendet:\n%s\n\nBeenden Sie Wizardry 8 (und "
    L"Programme, die seine Dateien ge\x00f6" L"ffnet haben) und versuchen Sie es erneut. Es wurde "
    L"nichts ver\x00e4ndert.",
    L"Einige Dateien konnten nicht entfernt werden, zum Beispiel:\n%s\n\nBeenden Sie Wizardry 8 "
    L"(und Programme, die seine Dateien ge\x00f6" L"ffnet haben) und w\x00e4hlen Sie erneut "
    L"\"Entfernen\".",
    L"Eine Datei konnte nicht kopiert werden:\n%s\n\nDer Patch ist jetzt nicht installiert: Die "
    L"alte Version war bereits entfernt, der Spielordner ist wieder im Originalzustand. Ihre "
    L"Einstellungen bleiben f\x00fcr die n\x00e4" L"chste Installation erhalten.",
    L"Diagnosemodus (f\x00fcr Fehlerberichte)",
    L"\n\nLinux (Wine/Proton): In diesem Wine-Pr\x00e4" L"fix l\x00e4" L"dt Wiz8.exe jetzt "
    L"version.dll des Patches aus dem Spielordner, dazu Wines eigene ddraw.dll (eine im "
    L"Spielordner verbliebene DDraw.dll von dgVoodoo w\x00fcrde unter Wine abst\x00fcrzen). Zeigt "
    L"das Hauptmen\x00fc weiter nur v1.2.4, l\x00e4uft das Spiel in einem anderen "
    L"Wine-Pr\x00e4" L"fix: tragen Sie in dessen Startoptionen ein (Steam: Eigenschaften - "
    L"Allgemein - Startoptionen); es steht schon in der Zwischenablage:\n%s\n"
    L"Nach einem Start damit merkt sich der Patch das, und sp\x00e4tere Starts gehen auch ohne. "
    L"(Heroic, Lutris, Bottles, Wine direkt: siehe den Abschnitt Linux in der README.)",
    L"\n\nLinux (Wine/Proton): Eine Einstellung in diesem Wine-Pr\x00e4" L"fix verhindert den "
    L"Start des Patches (HKCU\\Software\\Wine\\AppDefaults\\Wiz8.exe\\DllOverrides oder "
    L"HKCU\\Software\\Wine\\DllOverrides); sie wurde nicht ge\x00e4ndert. F\x00fcr den Patch "
    L"sollte version native,builtin sein und ddraw builtin (eine im Spielordner verbliebene "
    L"DDraw.dll von dgVoodoo w\x00fcrde unter Wine abst\x00fcrzen).",
    L"\n\nLinux (Wine/Proton): Das eigene Wine-Pr\x00e4" L"fix des Spiels ist jetzt f\x00fcr den "
    L"Patch eingerichtet; sonst ist nichts zu tun.",
    L"\n\nLinux (Wine/Proton): Das Spiel (gefunden \x00fc" L"ber: %s) l\x00e4uft in einem anderen "
    L"Wine-Pr\x00e4" L"fix als dieser Installer, daher wurde hier nichts daf\x00fcr eingerichtet. "
    L"Tragen Sie einmal in die Startoptionen des Spiels ein (es steht schon in der "
    L"Zwischenablage):\n%s\n"
    L"Steam: Eigenschaften - Allgemein - Startoptionen (Nicht-Steam-Spiel: Verkn\x00fcpfung - "
    L"Startoptionen). Heroic, Lutris: siehe den Abschnitt Linux in der README. Nach einem Start "
    L"damit richtet der Patch das Wine-Pr\x00e4" L"fix des Spiels selbst ein, und sp\x00e4tere "
    L"Starts gehen auch ohne.",
    L"\n\nLinux (Wine/Proton): Der Patch startet unter Wine und Proton von selbst, in jedem "
    L"Wine-Pr\x00e4" L"fix; keine Startoption ist n\x00f6tig. Pr\x00fc" L"ft oder repariert Steam, "
    L"GOG Galaxy oder Heroic die Dateien des Spiels, starten Sie diesen Installer erneut.",
    L"Wizardry 8 wurde nicht automatisch gefunden. W\x00e4hlen Sie den Spielordner oder "
    L"f\x00fcgen Sie seinen Linux-Pfad ein, z. B. /home/deck/Games/Wizardry 8.",
    L"Gefunden \x00fc" L"ber: %s - %s",
    L"GOG",
    L"Steam",
    L"Steam-Verkn\x00fcpfung \x201e%s\x201c",
    L"Heroic",
    L"Lutris",
    L"Wine-Pr\x00e4" L"fix",
    L"l\x00e4uft in diesem Wine-Pr\x00e4" L"fix",
    L"l\x00e4uft in einem anderen Wine-Pr\x00e4" L"fix",
    L"sein Wine-Pr\x00e4" L"fix entsteht beim ersten Start",
    L"Wine-Pr\x00e4" L"fix unbekannt",
    L"Status: Version %s ist installiert, aber eine Dateipr\x00fc" L"fung hat die Linux-Startdatei "
    L"durch das Original des Spiels ersetzt: erneut installieren.",
    L"Problem melden...",
    L"Die Berichtsdatei wurde gespeichert:\n%s\n(ihr Pfad liegt in der Zwischenablage)\n\n"
    L"Sie enth\x00e4lt die Protokolle und Einstellungen des Patches und die Absturzabbilder, falls es "
    L"welche gibt. Darin stehen Ordnernamen, also auch Ihr Benutzername.%s\n\n"
    L"Jetzt die Seite f\x00fcr Fehlerberichte auf GitHub \x00f6" L"ffnen? Beschreiben Sie dort, was passiert "
    L"ist, und f\x00fcgen Sie diese Datei hinzu. Berichte dort sind \x00f6" L"ffentlich.",
    L" Nicht alles hat in die Datei gepasst: Die report.txt darin nennt, was weggelassen oder "
    L"gek\x00fcrzt wurde.",
    L"Die Berichtsdatei konnte nicht gespeichert werden:\n%s",
    L"Der Browser wurde nicht ge\x00f6" L"ffnet. Die Seite f\x00fcr Fehlerberichte:\n%s",
};

const wchar_t* const kFrench[T_COUNT] = {
    L"\x00c9" L"cran large natif pour Wizardry 8 (GOG et Steam). Choisissez le dossier du jeu :",
    L"Dossier du jeu :",
    L"Parcourir...",
    L"Installer",
    L"D\x00e9sinstaller",
    L"Quitter",
    L"Wizardry 8 n'a pas \x00e9t\x00e9 trouv\x00e9 automatiquement. Choisissez le dossier du jeu.",
    L"Ce dossier ne contient pas Wizardry 8 (Wiz8.exe et Data manquent).",
    L"Ce Wiz8.exe n'est pas la version test\x00e9" L"e.\n\nLe patch n'a \x00e9t\x00e9 test\x00e9 "
    L"qu'avec Wizardry 8 1.2.4 (GOG et Steam). Il peut ne pas fonctionner avec cette version - "
    L"installation \x00e0 vos risques.\n\nSi le code du jeu diff\x00e8re, le patch se d\x00e9sactive "
    L"au d\x00e9marrage et le jeu tourne comme l'original.\n\nInstaller quand m\x00eame ?",
    L"Le dossier du jeu contient d\x00e9j\x00e0 un version.dll qui n'appartient pas \x00e0 ce patch "
    L"(sans doute un autre mod). Il n'a pas \x00e9t\x00e9 modifi\x00e9.\n\nRetirez ou renommez "
    L"d'abord ce mod, puis relancez l'installateur.",
    L"Le patch \x00e9" L"cran large %s est install\x00e9.\n\nLancez le jeu comme d'habitude. Mode "
    L"d'affichage, r\x00e9solution et distance de vue : Options - Vid\x00e9o.",
    L"Le patch \x00e9" L"cran large a \x00e9t\x00e9 retir\x00e9. Le dossier du jeu est comme avant.",
    L"Le patch n'est pas install\x00e9 dans ce dossier.",
    L"Impossible de copier un fichier :\n%s\n\nRien n'est rest\x00e9 \x00e0 moiti\x00e9 install\x00e9 ; "
    L"l'\x00e9tat pr\x00e9" L"c\x00e9" L"dent a \x00e9t\x00e9 restaur\x00e9.",
    L"Le dossier \"files\" est absent \x00e0 c\x00f4t\x00e9 de l'installateur. D\x00e9" L"compressez "
    L"d'abord toute l'archive.",
    L"Un fichier du patch manque dans le dossier \"files\" \x00e0 c\x00f4t\x00e9 de "
    L"l'installateur :\n%s\n\nD\x00e9" L"compressez de nouveau toute l'archive (un antivirus a "
    L"peut-\x00ea" L"tre supprim\x00e9 le fichier). Rien n'a \x00e9t\x00e9 modifi\x00e9.",
    L"\x00c9tat : la version %s du patch est install\x00e9" L"e.",
    L"\x00c9tat : le patch n'est pas install\x00e9.",
    L"Wiz8.exe : version 1.2.4 (test\x00e9" L"e).",
    L"Wiz8.exe : version inconnue (non test\x00e9" L"e).",
    L"Choisissez le dossier de Wizardry 8 (celui avec Wiz8.exe) :",
    L"R\x00e9installer",
    L"Mettre \x00e0 jour %s \x2192 %s",
    L"Le patch \x00e9" L"cran large a \x00e9t\x00e9 mis \x00e0 jour de %s vers %s. Vos r\x00e9glages "
    L"ont \x00e9t\x00e9 conserv\x00e9s.\n\nLancez le jeu comme d'habitude.",
    L"R\x00e9trograder %s \x2192 %s",
    L"Ce dossier contient une version plus r\x00e9" L"cente du patch : %s. Cet installateur est "
    L"en version %s.\n\nRevenir \x00e0 l'ancienne version ? Vos r\x00e9glages seront conserv\x00e9s.",
    L"Le patch \x00e9" L"cran large est revenu de %s \x00e0 %s. Vos r\x00e9glages ont \x00e9t\x00e9 "
    L"conserv\x00e9s.\n\nLancez le jeu comme d'habitude.",
    L"\x00c9tat : la version %s du patch est install\x00e9" L"e (plus r\x00e9" L"cente que cet "
    L"installateur, %s).",
    L"\x00c9tat : la version %s du patch vient d'un installateur plus r\x00e9" L"cent ; utilisez "
    L"celui de la version %s ou plus r\x00e9" L"cente.",
    L"La version %s du patch dans ce dossier a \x00e9t\x00e9 install\x00e9" L"e par un installateur "
    L"plus r\x00e9" L"cent, que celui-ci ne peut pas modifier sans risque. Rien n'a \x00e9t\x00e9 "
    L"modifi\x00e9.\n\nUtilisez l'installateur de la version %s ou plus r\x00e9" L"cente.",
    L"Un fichier du dossier du jeu est en cours d'utilisation :\n%s\n\nFermez Wizardry 8 (et tout "
    L"programme qui a ouvert ses fichiers) puis r\x00e9" L"essayez. Rien n'a \x00e9t\x00e9 "
    L"modifi\x00e9.",
    L"Certains fichiers n'ont pas pu \x00ea" L"tre retir\x00e9s, par exemple :\n%s\n\nFermez "
    L"Wizardry 8 (et tout programme qui a ouvert ses fichiers) puis cliquez de nouveau sur "
    L"\x00ab D\x00e9sinstaller \x00bb.",
    L"Impossible de copier un fichier :\n%s\n\nLe patch n'est plus install\x00e9 : l'ancienne "
    L"version avait d\x00e9j\x00e0 \x00e9t\x00e9 retir\x00e9" L"e et le dossier du jeu est revenu "
    L"\x00e0 l'original. Vos r\x00e9glages sont conserv\x00e9s pour la prochaine installation.",
    L"Mode diagnostic (pour les rapports de bug)",
    L"\n\nLinux (Wine/Proton) : dans ce pr\x00e9" L"fixe Wine, Wiz8.exe charge d\x00e9sormais "
    L"le version.dll du patch depuis le dossier du jeu, avec le ddraw.dll propre \x00e0 Wine "
    L"(un DDraw.dll de dgVoodoo rest\x00e9 dans le dossier du jeu planterait sous Wine). Si le "
    L"menu principal affiche encore seulement v1.2.4, le jeu tourne dans un autre pr\x00e9" L"fixe "
    L"Wine : ajoutez \x00e0 ses options de lancement (Steam : Propri\x00e9t\x00e9s - "
    L"G\x00e9n\x00e9ral - Options de lancement) ; c'est d\x00e9j\x00e0 dans le presse-papiers :\n%s\n"
    L"Apr\x00e8s un lancement avec cette option, le patch s'en souvient, et les lancements "
    L"suivants marchent sans. (Heroic, Lutris, Bottles, Wine seul : voir la section Linux du "
    L"README.)",
    L"\n\nLinux (Wine/Proton) : un r\x00e9glage de ce pr\x00e9" L"fixe Wine emp\x00ea" L"che le "
    L"patch de d\x00e9marrer (HKCU\\Software\\Wine\\AppDefaults\\Wiz8.exe\\DllOverrides ou "
    L"HKCU\\Software\\Wine\\DllOverrides) ; il n'a pas \x00e9t\x00e9 modifi\x00e9. Pour le "
    L"patch, version doit \x00ea" L"tre native,builtin et ddraw builtin (un DDraw.dll de dgVoodoo "
    L"rest\x00e9 dans le dossier du jeu planterait sous Wine).",
    L"\n\nLinux (Wine/Proton) : le pr\x00e9" L"fixe Wine propre au jeu est maintenant configur\x00e9 "
    L"pour le patch ; rien d'autre \x00e0 faire.",
    L"\n\nLinux (Wine/Proton) : le jeu (trouv\x00e9 via : %s) tourne dans un autre pr\x00e9" L"fixe "
    L"Wine que cet installateur, rien n'a donc \x00e9t\x00e9 configur\x00e9 ici pour lui. Ajoutez "
    L"une fois aux options de lancement du jeu (c'est d\x00e9j\x00e0 dans le presse-papiers) :\n%s\n"
    L"Steam : Propri\x00e9t\x00e9s - G\x00e9n\x00e9ral - Options de lancement (jeu non-Steam : "
    L"Raccourci - Options de lancement). Heroic, Lutris : voir la section Linux du README. "
    L"Apr\x00e8s un lancement avec cette option, le patch configure lui-m\x00eame le pr\x00e9" L"fixe "
    L"Wine du jeu, et les lancements suivants marchent sans.",
    L"\n\nLinux (Wine/Proton) : le patch d\x00e9marre tout seul sous Wine et Proton, dans "
    L"n'importe quel pr\x00e9" L"fixe Wine ; aucune option de lancement n'est n\x00e9" L"cessaire. "
    L"Si Steam, GOG Galaxy ou Heroic v\x00e9rifie ou r\x00e9pare les fichiers du jeu, relancez cet "
    L"installateur.",
    L"Wizardry 8 n'a pas \x00e9t\x00e9 trouv\x00e9 automatiquement. Choisissez le dossier du jeu "
    L"ou collez son chemin Linux, par exemple /home/deck/Games/Wizardry 8.",
    L"Trouv\x00e9 via : %s - %s",
    L"GOG",
    L"Steam",
    L"raccourci Steam \x00ab %s \x00bb",
    L"Heroic",
    L"Lutris",
    L"pr\x00e9" L"fixe Wine",
    L"tourne dans ce pr\x00e9" L"fixe Wine",
    L"tourne dans un autre pr\x00e9" L"fixe Wine",
    L"son pr\x00e9" L"fixe Wine appara\x00eetra au premier lancement",
    L"pr\x00e9" L"fixe Wine inconnu",
    L"\x00c9tat : la version %s est install\x00e9" L"e, mais une v\x00e9rification des fichiers a "
    L"remplac\x00e9 son fichier de d\x00e9marrage Linux par l'original du jeu : relancez "
    L"l'installation.",
    L"Signaler un probl\x00e8me...",
    L"Le fichier de rapport a \x00e9t\x00e9 enregistr\x00e9 :\n%s\n(son chemin est dans le presse-papiers)\n\n"
    L"Il contient les journaux et les r\x00e9glages du patch et les images m\x00e9moire des plantages, "
    L"s'il y en a. Ils contiennent des noms de dossiers, donc aussi votre nom d'utilisateur.%s\n\n"
    L"Ouvrir maintenant la page de rapport de bug sur GitHub ? D\x00e9" L"crivez-y ce qui s'est pass\x00e9 et "
    L"ajoutez ce fichier. Les rapports y sont publics.",
    L" Tout n'a pas pu entrer dans le fichier : son report.txt indique ce qui a \x00e9t\x00e9 "
    L"omis ou raccourci.",
    L"Impossible d'enregistrer le fichier de rapport :\n%s",
    L"Le navigateur ne s'est pas ouvert. La page des rapports de bug :\n%s",
};

const wchar_t* const* g_text = kEnglish;

const wchar_t* Tr(Text t)
{
    return g_text[t];
}

/* A text with up to two %s filled in. */
std::wstring Tr(Text t, const std::wstring& a, const std::wstring& b = std::wstring())
{
    wchar_t buffer[1024];
    wsprintfW(buffer, g_text[t], a.c_str(), b.c_str());
    return buffer;
}

void PickLanguage()
{
    /* Windows UI language (not the regional settings) */
    LANGID lang = PRIMARYLANGID(GetUserDefaultUILanguage());
    switch (lang) {
    case LANG_RUSSIAN:
    case LANG_UKRAINIAN:
    case LANG_BELARUSIAN:
        g_text = kRussian;
        break;
    case LANG_GERMAN:
        g_text = kGerman;
        break;
    case LANG_FRENCH:
        g_text = kFrench;
        break;
    default:
        g_text = kEnglish;
        break;
    }
}

/* ---------------- files ---------------- */

std::wstring Join(const std::wstring& a, const std::wstring& b)
{
    if (a.empty()) {
        return b;
    }
    if (a.back() == L'\\' || a.back() == L'/') {
        return a + b;
    }
    return a + L"\\" + b;
}

/* The file name of a relative path: "Dll\srDD_D3D11.log" -> "srDD_D3D11.log" */
std::wstring FileName(const std::wstring& rel)
{
    size_t slash = rel.find_last_of(L'\\');
    return slash == std::wstring::npos ? rel : rel.substr(slash + 1);
}

bool FileExists(const std::wstring& path)
{
    DWORD attr = GetFileAttributesW(path.c_str());
    return attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY);
}

bool DirExists(const std::wstring& path)
{
    DWORD attr = GetFileAttributesW(path.c_str());
    return attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY);
}

/* This program's own file. Wine, when it was started from a folder no drive letter maps (a
   prefix without Z:), names it "unix\home\..." (its NT name without the "\??\" in front); the
   name that works is "\\?\unix\home\...". */
std::wstring ExePath()
{
    wchar_t path[MAX_PATH];
    GetModuleFileNameW(0, path, MAX_PATH);
    std::wstring s = path;
    if (UnderWine() && s.compare(0, 5, L"unix\\") == 0) {
        s = L"\\\\?\\" + s;
    }
    return s;
}

std::wstring ExeDir()
{
    std::wstring s = ExePath();
    return s.substr(0, s.find_last_of(L'\\'));
}

/* Whether a folder name is a full path: "D:\..." or "\\..." ("\\?\unix\...", a network folder),
   not one that is read against the current folder or drive ("", "Games\Wizardry 8", "\Games").
   A drive alone ("G:") counts as its root, as it always has here: it is what a game at a drive
   root ("G:\" in the GOG key) becomes once AddCandidate trims the backslash, and Join puts the
   backslash back ("G:" + "Wiz8.exe" = "G:\Wiz8.exe"). */
bool IsFullPath(const std::wstring& dir)
{
    auto slash = [&](size_t i) { return i < dir.size() && (dir[i] == L'\\' || dir[i] == L'/'); };
    wchar_t drive = dir.empty() ? 0 : (wchar_t)(dir[0] | 0x20);
    bool drive_path = drive >= L'a' && drive <= L'z' && dir.size() > 1 && dir[1] == L':';
    return (drive_path && (dir.size() == 2 || slash(2))) || (slash(0) && slash(1));
}

/* Only a full path counts, on Windows and under Wine. The installer is often started from the
   game folder (the archive unpacked into it and the exe double-clicked; under Wine also a Steam
   shortcut, which starts it in its own folder, or "wine Wiz8WideSetup.exe" typed in it), and an
   empty or relative name (a registry value that is not there, a typed one) would then find the
   game in the current folder, where the install's own paths are no longer folder + file: a
   file at the root of the package ("" + "version.dll") is a file name without a folder, which
   CreateDirs would make a folder of, and every later install into that folder would fail. A
   relative folder given on the command line is made a full path first (CommandLineFolder); one
   typed into the folder box is not. */
bool IsGameDir(const std::wstring& dir)
{
    if (!IsFullPath(dir)) {
        return false;
    }
    return FileExists(Join(dir, L"Wiz8.exe")) && DirExists(Join(dir, L"Data"));
}

void CreateDirs(const std::wstring& dir)
{
    if (dir.empty() || DirExists(dir)) {
        return;
    }
    size_t slash = dir.find_last_of(L'\\');
    if (slash != std::wstring::npos) {
        CreateDirs(dir.substr(0, slash));
    }
    CreateDirectoryW(dir.c_str(), 0);
}

/* All files under root, paths relative to root. */
void ListFiles(const std::wstring& root, const std::wstring& rel, std::vector<std::wstring>* out)
{
    WIN32_FIND_DATAW data;
    HANDLE find = FindFirstFileW(Join(Join(root, rel), L"*").c_str(), &data);
    if (find == INVALID_HANDLE_VALUE) {
        return;
    }
    do {
        std::wstring name = data.cFileName;
        if (name == L"." || name == L"..") {
            continue;
        }
        std::wstring child = rel.empty() ? name : Join(rel, name);
        if (data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            ListFiles(root, child, out);
        } else {
            out->push_back(child);
        }
    } while (FindNextFileW(find, &data));
    FindClose(find);
}

std::vector<std::wstring> ReadLines(const std::wstring& path)
{
    std::vector<std::wstring> lines;
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, 0, OPEN_EXISTING, 0, 0);
    if (file == INVALID_HANDLE_VALUE) {
        return lines;
    }
    DWORD size = GetFileSize(file, 0);
    std::string bytes(size, '\0');
    DWORD read = 0;
    ReadFile(file, &bytes[0], size, &read, 0);
    CloseHandle(file);
    int wide = MultiByteToWideChar(CP_UTF8, 0, bytes.data(), (int)read, 0, 0);
    std::wstring text(wide, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, bytes.data(), (int)read, &text[0], wide);
    size_t start = 0;
    while (start < text.size()) {
        size_t end = text.find(L'\n', start);
        if (end == std::wstring::npos) {
            end = text.size();
        }
        std::wstring line = text.substr(start, end - start);
        while (!line.empty() && (line.back() == L'\r' || line.back() == L' ')) {
            line.pop_back();
        }
        if (!line.empty()) {
            lines.push_back(line);
        }
        start = end + 1;
    }
    return lines;
}

bool WriteLines(const std::wstring& path, const std::vector<std::wstring>& lines)
{
    std::wstring text;
    for (const std::wstring& line : lines) {
        text += line + L"\r\n";
    }
    int size = WideCharToMultiByte(CP_UTF8, 0, text.data(), (int)text.size(), 0, 0, 0, 0);
    std::string bytes(size, '\0');
    WideCharToMultiByte(CP_UTF8, 0, text.data(), (int)text.size(), &bytes[0], size, 0, 0);
    HANDLE file = CreateFileW(path.c_str(), GENERIC_WRITE, 0, 0, CREATE_ALWAYS, 0, 0);
    if (file == INVALID_HANDLE_VALUE) {
        return false;
    }
    DWORD written = 0;
    BOOL ok = WriteFile(file, bytes.data(), (DWORD)bytes.size(), &written, 0);
    CloseHandle(file);
    return ok && written == bytes.size();
}

/* SHA-256 of a file (BCrypt), upper-case hex. */
std::wstring Sha256(const std::wstring& path)
{
    std::wstring result;
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, 0, OPEN_EXISTING, 0, 0);
    if (file == INVALID_HANDLE_VALUE) {
        return result;
    }
    BCRYPT_ALG_HANDLE alg = 0;
    BCRYPT_HASH_HANDLE hash = 0;
    if (BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA256_ALGORITHM, 0, 0) == 0 &&
        BCryptCreateHash(alg, &hash, 0, 0, 0, 0, 0) == 0) {
        std::vector<unsigned char> buffer(1 << 16);
        DWORD read = 0;
        while (ReadFile(file, buffer.data(), (DWORD)buffer.size(), &read, 0) && read > 0) {
            BCryptHashData(hash, buffer.data(), read, 0);
        }
        unsigned char digest[32];
        if (BCryptFinishHash(hash, digest, sizeof(digest), 0) == 0) {
            wchar_t hex[3];
            for (unsigned char b : digest) {
                wsprintfW(hex, L"%02X", b);
                result += hex;
            }
        }
    }
    if (hash) {
        BCryptDestroyHash(hash);
    }
    if (alg) {
        BCryptCloseAlgorithmProvider(alg, 0);
    }
    CloseHandle(file);
    return result;
}

/* Is version.dll ours: it contains the string "wiz8ws". */
bool IsOurVersionDll(const std::wstring& path)
{
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, 0, OPEN_EXISTING, 0, 0);
    if (file == INVALID_HANDLE_VALUE) {
        return false;
    }
    DWORD size = GetFileSize(file, 0);
    std::string bytes(size, '\0');
    DWORD read = 0;
    ReadFile(file, &bytes[0], size, &read, 0);
    CloseHandle(file);
    return bytes.find("wiz8ws") != std::string::npos;
}

/* ---------------- binkw32.dll (the Wine start route) ---------------- */

/* Under Wine the patch can start with no setting in any Wine prefix. Wine has no binkw32.dll of
   its own, so for binkw32.dll (the game's video library, which Wiz8.exe imports) it always loads
   the game folder's file, while for version.dll it takes its own unless told otherwise. The
   patch's version.dll also carries binkw32's functions, each passed on to
   binkw32_wiz8wide.dll ("forwarded"), and under Wine a copy of it named binkw32.dll starts the
   patch. So under Wine the installer renames the game's binkw32.dll to binkw32_wiz8wide.dll
   (as a copy; the original also goes into Wiz8Wide.backup like any replaced file) and puts a
   copy of version.dll in its place. On Windows nothing of this happens, and a folder installed
   this way still starts there through version.dll as before (the binkw32 copy only passes the
   calls on). Both files are ordinary lines of the manifest, binkw32.dll first: any uninstall,
   also by an older installer, puts the original back before it deletes the renamed copy. */

/* What the game folder's binkw32.dll is */
enum BinkKind {
    BINK_MISSING,
    BINK_OURS,     /* a copy of the patch's version.dll (contains "wiz8ws") */
    BINK_ORIGINAL, /* RAD's file as the game ships it */
    BINK_FOREIGN   /* anything else, most likely another mod's: left alone */
};

/* A struct of the PE file format (windows.h) read from the file's bytes at an offset; false if
   the file is too short there. */
template <class T>
bool ReadAt(const std::string& bytes, size_t offset, T* out)
{
    if (offset > bytes.size() || bytes.size() - offset < sizeof(T)) {
        return false;
    }
    memcpy(out, bytes.data() + offset, sizeof(T));
    return true;
}

/* The tables of a 32-bit program or DLL (PE file): the section list, which says where each part
   of the loaded image is in the file, and the export and import directories. */
struct PeTables {
    std::vector<IMAGE_SECTION_HEADER> sections;
    IMAGE_DATA_DIRECTORY exports = {};
    IMAGE_DATA_DIRECTORY imports = {};
};

bool ReadPeTables(const std::string& bytes, PeTables* pe)
{
    IMAGE_DOS_HEADER dos;
    IMAGE_NT_HEADERS32 nt;
    if (!ReadAt(bytes, 0, &dos) || dos.e_magic != IMAGE_DOS_SIGNATURE || dos.e_lfanew < 0 ||
        !ReadAt(bytes, dos.e_lfanew, &nt) || nt.Signature != IMAGE_NT_SIGNATURE ||
        nt.OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR32_MAGIC ||
        nt.OptionalHeader.NumberOfRvaAndSizes <= IMAGE_DIRECTORY_ENTRY_IMPORT) {
        return false;
    }
    pe->exports = nt.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT];
    pe->imports = nt.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    size_t first = dos.e_lfanew + offsetof(IMAGE_NT_HEADERS32, OptionalHeader) +
                   nt.FileHeader.SizeOfOptionalHeader;
    for (int i = 0; i < nt.FileHeader.NumberOfSections; ++i) {
        IMAGE_SECTION_HEADER section;
        if (!ReadAt(bytes, first + i * sizeof(section), &section)) {
            return false;
        }
        pe->sections.push_back(section);
    }
    return true;
}

/* Where an address of the loaded image (an "RVA") is in the file; npos if in none */
size_t FileOffset(const PeTables& pe, DWORD rva)
{
    for (const IMAGE_SECTION_HEADER& section : pe.sections) {
        if (rva >= section.VirtualAddress && rva - section.VirtualAddress < section.SizeOfRawData) {
            return rva - section.VirtualAddress + section.PointerToRawData;
        }
    }
    return std::string::npos;
}

/* A 0-terminated name at an RVA ("" if there is none) */
std::string PeName(const std::string& bytes, const PeTables& pe, DWORD rva)
{
    size_t offset = FileOffset(pe, rva);
    if (offset >= bytes.size()) {
        return std::string();
    }
    size_t end = bytes.find('\0', offset);
    return bytes.substr(offset, (end == std::string::npos ? bytes.size() : end) - offset);
}

bool ReadWholeFile(const std::wstring& path, std::string* bytes)
{
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, 0, OPEN_EXISTING, 0, 0);
    if (file == INVALID_HANDLE_VALUE) {
        return false;
    }
    DWORD size = GetFileSize(file, 0);
    DWORD read = 0;
    bool ok = size != INVALID_FILE_SIZE && size <= (64u << 20);
    if (ok) {
        bytes->assign(size, '\0');
        ok = size > 0 && ReadFile(file, &(*bytes)[0], size, &read, 0) && read == size;
    }
    CloseHandle(file);
    return ok;
}

/* The names a program imports from one DLL (Wiz8.exe from binkw32.dll: 12 functions such as
   _BinkOpen@8). Empty if it imports nothing from it, or anything only by number. */
std::vector<std::string> ImportedNames(const std::wstring& exe, const char* dll)
{
    std::vector<std::string> names;
    std::string bytes;
    PeTables pe;
    if (!ReadWholeFile(exe, &bytes) || !ReadPeTables(bytes, &pe) || pe.imports.VirtualAddress == 0) {
        return names;
    }
    size_t offset = FileOffset(pe, pe.imports.VirtualAddress);
    IMAGE_IMPORT_DESCRIPTOR entry;
    for (; offset != std::string::npos && ReadAt(bytes, offset, &entry) && entry.Name != 0;
         offset += sizeof(entry)) {
        if (lstrcmpiA(PeName(bytes, pe, entry.Name).c_str(), dll) != 0) {
            continue;
        }
        size_t thunks = FileOffset(pe, entry.OriginalFirstThunk ? entry.OriginalFirstThunk : entry.FirstThunk);
        DWORD thunk = 0;
        for (; thunks != std::string::npos && ReadAt(bytes, thunks, &thunk) && thunk != 0; thunks += 4) {
            if (thunk & IMAGE_ORDINAL_FLAG32) {
                return std::vector<std::string>(); /* by number: cannot be checked by name */
            }
            names.push_back(PeName(bytes, pe, thunk + 2)); /* after the 2-byte "hint" */
        }
    }
    return names;
}

/* Whether the file holds every section the section list names: one cut off by a full disk still
   has its headers and maybe its export table, at the start, but not all of its code. */
bool HasAllSections(const std::string& bytes, const PeTables& pe)
{
    for (const IMAGE_SECTION_HEADER& section : pe.sections) {
        if (section.SizeOfRawData > 0 && (section.PointerToRawData > bytes.size() ||
                                          bytes.size() - section.PointerToRawData < section.SizeOfRawData)) {
            return false;
        }
    }
    return true;
}

/* The exports of a DLL by name: for each, the text it is forwarded to ("binkw32_wiz8wide._BinkOpen@8"),
   or "" for a function of its own (code). false if the file is not a whole 32-bit DLL with
   exports. */
bool ReadExports(const std::wstring& path, std::vector<std::pair<std::string, std::string>>* out)
{
    std::string bytes;
    PeTables pe;
    IMAGE_EXPORT_DIRECTORY dir;
    if (!ReadWholeFile(path, &bytes) || !ReadPeTables(bytes, &pe) || !HasAllSections(bytes, pe) ||
        pe.exports.VirtualAddress == 0 || !ReadAt(bytes, FileOffset(pe, pe.exports.VirtualAddress), &dir)) {
        return false;
    }
    size_t names = FileOffset(pe, dir.AddressOfNames);
    size_t numbers = FileOffset(pe, dir.AddressOfNameOrdinals);
    size_t functions = FileOffset(pe, dir.AddressOfFunctions);
    for (DWORD i = 0; i < dir.NumberOfNames && i < 65536; ++i) {
        DWORD name = 0, function = 0;
        WORD number = 0;
        if (names == std::string::npos || numbers == std::string::npos || functions == std::string::npos ||
            !ReadAt(bytes, names + 4 * i, &name) || !ReadAt(bytes, numbers + 2 * i, &number) ||
            number >= dir.NumberOfFunctions || !ReadAt(bytes, functions + 4 * number, &function)) {
            return false;
        }
        /* an export whose address lies inside the export directory is a forwarder: the address
           is that of its text "dll.function" */
        bool forwarded = function >= pe.exports.VirtualAddress &&
                         function - pe.exports.VirtualAddress < pe.exports.Size;
        out->push_back({PeName(bytes, pe, name), forwarded ? PeName(bytes, pe, function) : std::string()});
    }
    return true;
}

/* Whether a binkw32.dll is the game's original by its contents: it has its own code for every
   function Wiz8.exe imports from binkw32.dll, and forwards nothing (RAD's file has 83 functions
   and no forwarders). For a binkw32.dll other than GOG/Steam 1.2.4's (its SHA-256 is checked
   first). */
bool HasBinkCode(const std::wstring& game, const std::wstring& path)
{
    std::vector<std::string> wanted = ImportedNames(Join(game, L"Wiz8.exe"), "binkw32.dll");
    std::vector<std::pair<std::string, std::string>> exports;
    if (wanted.empty() || !ReadExports(path, &exports)) {
        return false;
    }
    for (const auto& item : exports) {
        if (!item.second.empty()) {
            return false;
        }
    }
    for (const std::string& name : wanted) {
        bool found = false;
        for (const auto& item : exports) {
            found = found || item.first == name;
        }
        if (!found) {
            return false;
        }
    }
    return true;
}

/* Whether the package's version.dll forwards every function Wiz8.exe imports from binkw32.dll
   to binkw32_wiz8wide.dll: otherwise a copy of it as binkw32.dll would keep the game from
   starting at all (a package built without them). */
bool CarriesBinkForwarders(const std::wstring& game, const std::wstring& dll)
{
    std::vector<std::string> wanted = ImportedNames(Join(game, L"Wiz8.exe"), "binkw32.dll");
    std::vector<std::pair<std::string, std::string>> exports;
    if (wanted.empty() || !ReadExports(dll, &exports)) {
        return false;
    }
    for (const std::string& name : wanted) {
        bool found = false;
        for (const auto& item : exports) {
            found = found || (item.first == name &&
                              lstrcmpiA(item.second.c_str(), ("binkw32_wiz8wide." + name).c_str()) == 0);
        }
        if (!found) {
            return false;
        }
    }
    return true;
}

BinkKind ClassifyBink(const std::wstring& game, const std::wstring& path)
{
    if (!FileExists(path)) {
        return BINK_MISSING;
    }
    if (IsOurVersionDll(path)) {
        return BINK_OURS;
    }
    if (lstrcmpiW(Sha256(path).c_str(), kBinkSha256) == 0 || HasBinkCode(game, path)) {
        return BINK_ORIGINAL;
    }
    return BINK_FOREIGN;
}

/* ---------------- finding the game ---------------- */

std::wstring RegString(HKEY root, const wchar_t* key, const wchar_t* value, REGSAM view)
{
    HKEY handle;
    std::wstring result;
    if (RegOpenKeyExW(root, key, 0, KEY_READ | view, &handle) != ERROR_SUCCESS) {
        return result;
    }
    wchar_t buffer[MAX_PATH * 2];
    DWORD size = sizeof(buffer);
    DWORD type = 0;
    if (RegQueryValueExW(handle, value, 0, &type, (BYTE*)buffer, &size) == ERROR_SUCCESS &&
        (type == REG_SZ || type == REG_EXPAND_SZ)) {
        /* a text may be stored without its closing 0: it ends where the data read ends */
        buffer[std::min<size_t>(size / sizeof(wchar_t), MAX_PATH * 2 - 1)] = 0;
        result = buffer;
    }
    RegCloseKey(handle);
    return result;
}

/* A folder from Windows' registry or a Windows libraryfolders.vdf, where "/" may stand for "\"
   (Steam writes "c:/program files (x86)/steam"). Not for Linux paths: "/home/deck" would become
   "\home\deck", a folder on the current drive (wine_find.h's FromUnix turns those into paths). */
std::wstring Backslashes(std::wstring dir)
{
    for (wchar_t& c : dir) {
        if (c == L'/') {
            c = L'\\';
        }
    }
    return dir;
}

/* Adds a game folder to the list, if it is one and not listed yet. On Windows the same folder
   is the same text (in any letter case). Under Wine one folder often has several names (Z:\ and
   X:\, a link), so there the file system decides (SameFolder), and a second source's prefixes
   join the first's: the game may run in either. */
void AddCandidate(std::vector<Candidate>* out, std::wstring dir, Source source,
                  const std::vector<std::wstring>& prefixes = {},
                  const std::wstring& label = std::wstring())
{
    while (!dir.empty() && dir.back() == L'\\') {
        dir.pop_back();
    }
    if (!IsGameDir(dir)) {
        return;
    }
    bool wine = UnderWine();
    for (Candidate& known : *out) {
        if (wine ? SameFolder(known.folder, dir) : lstrcmpiW(known.folder.c_str(), dir.c_str()) == 0) {
            for (const std::wstring& prefix : prefixes) {
                if (std::find(known.prefixes.begin(), known.prefixes.end(), prefix) == known.prefixes.end()) {
                    known.prefixes.push_back(prefix);
                }
            }
            return;
        }
    }
    Candidate found;
    found.folder = dir;
    found.source = source;
    found.label = label;
    found.prefixes = prefixes;
    out->push_back(found);
}

/* Steam on Windows: steamapps\libraryfolders.vdf - lines "path" "D:\\SteamLibrary". (Under Wine
   the Linux Steam is read instead: wine_find.cpp.) */
void FindSteam(std::vector<Candidate>* out)
{
    std::wstring steam = RegString(HKEY_CURRENT_USER, L"Software\\Valve\\Steam", L"SteamPath", 0);
    if (steam.empty()) {
        steam = RegString(HKEY_LOCAL_MACHINE, L"SOFTWARE\\Valve\\Steam", L"InstallPath",
                          KEY_WOW64_32KEY);
    }
    if (steam.empty()) {
        return;
    }
    std::vector<std::wstring> libraries;
    libraries.push_back(steam);
    std::vector<std::wstring> lines = ReadLines(Join(steam, L"steamapps\\libraryfolders.vdf"));
    for (const std::wstring& line : lines) {
        size_t key = line.find(L"\"path\"");
        if (key == std::wstring::npos) {
            continue;
        }
        size_t open = line.find(L'"', key + 6);
        size_t close = open == std::wstring::npos ? open : line.find(L'"', open + 1);
        if (open == std::wstring::npos || close == std::wstring::npos) {
            continue;
        }
        std::wstring path = line.substr(open + 1, close - open - 1);
        std::wstring unescaped;
        for (size_t i = 0; i < path.size(); ++i) {
            if (path[i] == L'\\' && i + 1 < path.size() && path[i + 1] == L'\\') {
                ++i;
            }
            unescaped += path[i];
        }
        libraries.push_back(unescaped);
    }
    for (const std::wstring& library : libraries) {
        AddCandidate(out, Backslashes(Join(library, L"steamapps\\common\\Wizardry8")), SOURCE_STEAM);
        AddCandidate(out, Backslashes(Join(library, L"steamapps\\common\\Wizardry 8")), SOURCE_STEAM);
    }
}

/* The game folders found, in the order the folder list shows them. On Windows: GOG (registry),
   then Steam. Under Wine: GOG's registry keys of this prefix (a GOG installer run in it, so the
   game runs in this prefix), then what the Linux launchers' files say (wine_find.h), each with
   its verdict. */
std::vector<Candidate> FindGames()
{
    std::vector<Candidate> found;
    bool wine = UnderWine();
    std::vector<std::wstring> here;
    if (wine && !ThisPrefix().empty()) {
        here.push_back(ThisPrefix());
    }
    std::wstring gog_key = std::wstring(L"SOFTWARE\\GOG.com\\Games\\") + kGogId;
    AddCandidate(&found, Backslashes(RegString(HKEY_LOCAL_MACHINE, gog_key.c_str(), L"path", KEY_WOW64_32KEY)),
                 SOURCE_GOG, here);
    AddCandidate(&found, Backslashes(RegString(HKEY_LOCAL_MACHINE, gog_key.c_str(), L"path", KEY_WOW64_64KEY)),
                 SOURCE_GOG, here);
    if (!wine) {
        FindSteam(&found);
        return found;
    }
    /* the GOG installer's script also writes the game's own key (default value = the folder) */
    for (REGSAM view : {KEY_WOW64_32KEY, KEY_WOW64_64KEY}) {
        AddCandidate(&found, Backslashes(RegString(HKEY_LOCAL_MACHINE, L"SOFTWARE\\Sirtech\\Wizardry 8\\Path",
                                                   L"", view)),
                     SOURCE_GOG, here);
    }
    std::vector<Candidate> places;
    FindWineGames(&places);
    for (const Candidate& place : places) {
        AddCandidate(&found, place.folder, place.source, place.prefixes, place.label);
    }
    for (Candidate& game : found) {
        game.verdict = PrefixVerdict(game.prefixes);
    }
    return found;
}

/* The found game this folder is (any of its names), or the folder alone with an unknown
   verdict: typed, browsed, or not found by any launcher. */
Candidate FindCandidate(const std::vector<Candidate>& games, const std::wstring& game)
{
    for (const Candidate& known : games) {
        if (lstrcmpiW(known.folder.c_str(), game.c_str()) == 0 || SameFolder(known.folder, game)) {
            return known;
        }
    }
    Candidate typed;
    typed.folder = game;
    return typed;
}

/* ---------------- installation ---------------- */

enum Result { RES_OK, RES_CANCELLED, RES_FAILED };

/* Is the folder writable (otherwise a restart with administrator rights is needed). */
bool CanWrite(const std::wstring& dir)
{
    std::wstring probe = Join(dir, L"Wiz8Wide.write-test");
    HANDLE file = CreateFileW(probe.c_str(), GENERIC_WRITE, 0, 0, CREATE_ALWAYS,
                              FILE_FLAG_DELETE_ON_CLOSE, 0);
    if (file == INVALID_HANDLE_VALUE) {
        return false;
    }
    CloseHandle(file);
    return true;
}

/* Is this existing file in use, so that it cannot be replaced or deleted now: a DLL loaded by
   the running game, or a file another program opened without delete sharing. (Checked on
   Windows 11: both make this open fail, a plain file does not.) */
bool IsBusy(const std::wstring& path)
{
    DWORD attr = GetFileAttributesW(path.c_str());
    if (attr == INVALID_FILE_ATTRIBUTES || (attr & FILE_ATTRIBUTE_DIRECTORY)) {
        return false;
    }
    /* a read-only file cannot be opened for writing at all, and opening a loaded DLL only
       for deleting succeeds: so the flag is cleared for the test (uninstall clears it anyway
       before deleting) and put back */
    bool read_only = (attr & FILE_ATTRIBUTE_READONLY) != 0;
    if (read_only && !SetFileAttributesW(path.c_str(), attr & ~FILE_ATTRIBUTE_READONLY)) {
        return true;
    }
    HANDLE file = CreateFileW(path.c_str(), GENERIC_WRITE | DELETE,
                              FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, 0,
                              OPEN_EXISTING, 0, 0);
    bool busy = file == INVALID_HANDLE_VALUE;
    if (!busy) {
        CloseHandle(file);
    }
    if (read_only) {
        SetFileAttributesW(path.c_str(), attr);
    }
    return busy;
}

/* The first of these files (relative to the game folder) that is in use; empty if none.
   Manifest lines that are not files ('+' folders, '*' values) are skipped. Under Wine also the
   two files of the binkw32 route, which an install may replace (see "binkw32.dll" above). */
std::wstring FindBusyFile(const std::wstring& game, std::vector<std::wstring> rels)
{
    if (UnderWine()) {
        rels.push_back(kBink);
        rels.push_back(kBinkOriginal);
    }
    for (const std::wstring& rel : rels) {
        if (rel[0] != L'+' && rel[0] != L'*' && IsBusy(Join(game, rel))) {
            return Join(game, rel);
        }
    }
    return std::wstring();
}

/* Files that only this patch puts into a game folder. Found there without a manifest (a
   manual install, or what an interrupted one left), they are not originals and must not be
   saved into Wiz8Wide.backup, or uninstall would put them back. */
bool IsPatchFile(const std::wstring& game, const std::wstring& rel)
{
    for (const wchar_t* name : {L"wiz8wide.ini", L"wiz8ws.ini", L"wiz8hy.dll", L"wiz8hy_hooks.txt"}) {
        if (lstrcmpiW(rel.c_str(), name) == 0) {
            return true;
        }
    }
    if (lstrcmpiW(rel.c_str(), L"version.dll") == 0) {
        return IsOurVersionDll(Join(game, rel));
    }
    /* the binkw32 route under Wine: the renamed original is the patch's (uninstall deletes it,
       the original itself is in Wiz8Wide.backup), binkw32.dll only when it is a copy of ours */
    if (lstrcmpiW(rel.c_str(), kBinkOriginal) == 0) {
        return true;
    }
    if (lstrcmpiW(rel.c_str(), kBink) == 0) {
        return IsOurVersionDll(Join(game, rel));
    }
    /* the wide art: Data\WIDE\, and the wide copies of game screens (..._768.STI,
       ..._856.STI); the original game has neither. The render driver (Dll\srDD_D3D11.dll) and
       FALCON.STI are not here: a player may have had them before (the driver is also released
       on its own), and uninstall must give them back. */
    std::wstring tail = rel.size() > 8 ? rel.substr(rel.size() - 8) : std::wstring();
    return lstrcmpiW(rel.substr(0, 10).c_str(), L"Data\\WIDE\\") == 0 ||
           lstrcmpiW(tail.c_str(), L"_768.STI") == 0 || lstrcmpiW(tail.c_str(), L"_856.STI") == 0;
}

/* Whether a file of the package (relative to files\) is dgVoodoo's (kDgVoodoo), in any letter
   case. The package has had none since 1.0.3, but a files\ folder may still hold them: a new
   package unpacked over an older one. They are never installed, on Windows or under Wine: not
   copied, not saved as originals, not listed in the manifest and not checked for being in use;
   a DDraw.dll the game folder already has (the player's own) stays as it is. With the patch's
   Direct3D 11 driver nothing needs dgVoodoo, and under Wine its DDraw.dll crashes the game at
   its first surface (2.8.7.5; Wiz8.exe imports DDRAW.DLL for its 2D surfaces whatever the render
   driver). An install that has them (made by 1.0.0-1.0.2 on Windows, or under Wine by 1.0.2)
   lists them, so the quiet uninstall of an update removes them and puts back what they
   replaced. Under Wine the patch runs with Wine's own ddraw.dll ("*ddraw" = "builtin", written
   by this installer and by the patch itself): Wine 11.6 and later take a DDraw.dll that is not
   Microsoft's from the game folder when nothing says otherwise (any Wine does with a global
   "ddraw=native"). With no DDraw.dll in the game folder Wine takes ddraw.dll from its own
   system folder, and a 32-bit prefix looks that one up as plain "ddraw" first: there a global
   "ddraw=native" (winetricks, say) would win over "*ddraw", so a plain "ddraw" = "builtin" for
   Wiz8.exe is written there too (PlainDdrawToo), only together with "*ddraw". A "*ddraw" or
   plain "ddraw" of the player's for Wiz8.exe stays as it is, and then neither is written:
   WineOrderOk reads the order Wine takes in the prefix the installer runs in, and when that is
   not Wine's own the final message says that a setting there keeps the patch from working
   (T_WINE_OWN). */
bool IsDgVoodoo(const std::wstring& rel)
{
    for (const wchar_t* name : kDgVoodoo) {
        if (lstrcmpiW(rel.c_str(), name) == 0) {
            return true;
        }
    }
    return false;
}

/* Copies src to dst, which must not exist yet (false with ERROR_FILE_EXISTS if it does). A copy
   that fails halfway (a full disk) leaves no part of dst: Windows' CopyFileW deletes it itself,
   Wine's leaves it, and a cut-off file in Wiz8Wide.backup would later count as the original. */
bool CopyToNewFile(const std::wstring& src, const std::wstring& dst)
{
    if (CopyFileW(src.c_str(), dst.c_str(), TRUE)) {
        return true;
    }
    DWORD error = GetLastError();
    if (error != ERROR_FILE_EXISTS) {
        SetFileAttributesW(dst.c_str(), FILE_ATTRIBUTE_NORMAL);
        DeleteFileW(dst.c_str());
    }
    SetLastError(error);
    return false;
}

/* Save an original file into Wiz8Wide.backup before it is replaced. A copy that is already
   there (left by an interrupted install) is older, so more likely the real original: kept. */
bool SaveOriginal(const std::wstring& game, const std::wstring& rel)
{
    std::wstring saved = Join(Join(game, kBackupDir), rel);
    CreateDirs(saved.substr(0, saved.find_last_of(L'\\')));
    return CopyToNewFile(Join(game, rel), saved) || GetLastError() == ERROR_FILE_EXISTS;
}

bool IsInstalled(const std::wstring& game)
{
    return FileExists(Join(game, kManifest));
}

/* Value of a "*key=value" line of the manifest; empty if there is no such line. */
std::wstring ManifestValue(const std::wstring& game, const wchar_t* tag)
{
    size_t length = lstrlenW(tag);
    for (const std::wstring& line : ReadLines(Join(game, kManifest))) {
        if (line.compare(0, length, tag) == 0) {
            return line.substr(length);
        }
    }
    return std::wstring();
}

/* Version of the installed patch, from its manifest; empty = not installed (no manifest, or
   one that lists no file). 1.0.0 did not write a version line. */
std::wstring InstalledVersion(const std::wstring& game)
{
    bool any_file = false;
    for (const std::wstring& line : ReadLines(Join(game, kManifest))) {
        any_file = any_file || (line[0] != L'*' && line[0] != L'+');
    }
    if (!any_file) {
        return std::wstring();
    }
    std::wstring version = ManifestValue(game, kVersionLine);
    return version.empty() ? L"1.0.0" : version;
}

/* Number at the start of text ("2" -> 2, "" or "x" -> 0). */
int LeadingNumber(const std::wstring& text, size_t* pos)
{
    int value = 0;
    for (; *pos < text.size() && text[*pos] >= L'0' && text[*pos] <= L'9'; ++*pos) {
        value = value * 10 + (text[*pos] - L'0');
    }
    return value;
}

/* Is the install in this folder made by an installer that knows more than this one
   ("*format=" higher than kFormat)? Then neither install nor uninstall may touch it. */
bool IsNewerFormat(const std::wstring& game)
{
    size_t pos = 0;
    return IsInstalled(game) && LeadingNumber(ManifestValue(game, kFormatLine), &pos) > kFormat;
}

/* Compares "1.0.1"-style versions number by number: <0, 0, >0. Anything after the digits
   of a part ("2-beta") is ignored. */
int CompareVersions(const std::wstring& a, const std::wstring& b)
{
    size_t i = 0, j = 0;
    while (i < a.size() || j < b.size()) {
        int x = LeadingNumber(a, &i);
        int y = LeadingNumber(b, &j);
        if (x != y) {
            return x < y ? -1 : 1;
        }
        i = a.find(L'.', i);
        j = b.find(L'.', j);
        i = i == std::wstring::npos ? a.size() : i + 1;
        j = j == std::wstring::npos ? b.size() : j + 1;
    }
    return 0;
}

/* ---------------- Wine (Linux, Steam Deck) ---------------- */

/* Wine, and Proton (Valve's Wine), load their own version.dll and ddraw.dll instead of the
   files in the game folder unless told otherwise, so the patch would silently not start
   (docs\loader.md). Under Wine the installer tells it, for Wiz8.exe only, with the values and
   notes described in src\wine_overrides.h ("*version" = "native,builtin", "*ddraw" = "builtin",
   in a 32-bit prefix also "ddraw" = "builtin"). These keys belong to the Wine prefix the
   installer runs in, so they are written only when the game runs in it or nobody knows
   (Verdict, wine_find.h); a game started in another prefix needs the WINEDLLOVERRIDES launch
   option once instead (the final message says so and puts it on the clipboard): at that start
   the patch writes the same values and notes in the game's own prefix. Uninstalling the last
   listed folder removes the values (if they are still as they were written) and the notes,
   whether the installer or the patch created them. A value that was already there (the player's
   own setting) is never changed. Wine's EmulateModeset is never written: Valve's Proton 10 and
   11 read it the other way round. */

/* After an install under Wine: sets the missing values and lists this folder. Returns whether
   Wiz8.exe now gets the load order the patch needs (false: a setting of the player's, for
   Wiz8.exe or for all programs, says otherwise; it is left as it is). */
bool AddWineOverrides(const std::wstring& game)
{
    bool ok = true;
    for (const WineDll& dll : kWineDlls) {
        const wchar_t* plain = dll.name + 1;
        if (!ReadUserValue(kWineKey, dll.name, 0) && !ReadUserValue(kWineKey, plain, 0) &&
            WriteUserValue(kWineKey, dll.name, dll.order)) {
            /* in a 32-bit prefix also the plain "ddraw", which Wine reads first there; only
               with both notes, so that an uninstall finds and removes it */
            if (WriteUserValue(kOwnKey, dll.name, dll.order) && PlainDdrawToo(dll) &&
                WriteUserValue(kWineKey, plain, dll.order) && !WriteUserValue(kOwnKey, plain, dll.order)) {
                DeleteUserValue(kWineKey, plain);
            }
        }
        ok = WineOrderOk(dll, game) && ok;
    }
    WriteUserValue(kFoldersKey, WineFolderName(game).c_str(), L"");
    return ok;
}

/* After an uninstall under Wine: this folder no longer needs the values; when no folder of this
   prefix does, the values created by the installer or the patch are removed (if still as they
   were written), with the notes and the keys left empty. This folder may be listed under
   another of its names (Z:\ and X:\, see SameFolder): every such entry goes. A listed folder
   still needs the values while it has the patch: installed by an installer (its manifest) or by
   hand (our version.dll, which the patch listed itself). One whose parent folder is missing too
   may be on a drive that is not there right now (an SD card): it still counts. A DDraw.dll that
   is still in this folder (one it had before the install, the package's dgVoodoo copied by
   hand, say: an install under Wine leaves it alone, the uninstall of one made on Windows puts
   it back from Wiz8Wide.backup) keeps "*ddraw" (and the plain "ddraw" of a 32-bit prefix):
   Wine 11.6 and later load a dgVoodoo DDraw.dll from the game folder when nothing says
   otherwise (and any Wine does with a global "ddraw=native"), which crashes the game at every
   start, and Wine's own ddraw is what kept it from doing so. Their notes go, so that the values
   are the player's from now on, and no later uninstall removes them either. */
void RemoveWineOverrides(const std::wstring& game)
{
    for (const std::wstring& folder : UserValueNames(kFoldersKey)) {
        if (SameFolder(folder, game)) {
            DeleteUserValue(kFoldersKey, folder.c_str());
        }
    }
    for (const wchar_t* name : {kWineDlls[1].name, kWineDlls[1].name + 1}) { /* "*ddraw", "ddraw" */
        std::wstring value, wrote;
        if (FileExists(Join(game, L"DDraw.dll")) && ReadUserValue(kWineKey, name, &value) &&
            ReadUserValue(kOwnKey, name, &wrote) && value == wrote) {
            DeleteUserValue(kOwnKey, name);
        }
    }
    for (const std::wstring& folder : UserValueNames(kFoldersKey)) {
        std::wstring parent = folder.substr(0, folder.find_last_of(L"\\/") + 1);
        if (IsInstalled(folder) || IsOurVersionDll(Join(folder, L"version.dll")) || !DirExists(parent)) {
            return; /* still used there */
        }
        DeleteUserValue(kFoldersKey, folder.c_str()); /* uninstalled elsewhere or deleted by hand */
    }
    for (const std::wstring& dll : UserValueNames(kOwnKey)) {
        std::wstring value, wrote;
        if (ReadUserValue(kWineKey, dll.c_str(), &value) &&
            ReadUserValue(kOwnKey, dll.c_str(), &wrote) && value == wrote) {
            DeleteUserValue(kWineKey, dll.c_str());
        }
        DeleteUserValue(kOwnKey, dll.c_str());
    }
    DeleteKeyIfEmpty(kFoldersKey);
    DeleteKeyIfEmpty(kOwnKey);
    DeleteKeyIfEmpty(kOwnRoot);
    DeleteKeyIfEmpty(kWineKey);
    DeleteKeyIfEmpty(kWineAppKey);
}

/* Copies src over dst without writing into dst itself: copied under a temporary name next to it
   and then renamed over it, dst is a new file, and is never left cut off by a copy that fails
   halfway (a full disk; the old dst is then still there). Under Wine this also protects a game
   started from another Wine prefix: Wine sees only the programs of its own prefix (its
   wineserver), so FindBusyFile cannot see that game, which may have dst loaded; CopyFileW over
   it would rewrite the very file under it (the same inode), and the game crashes, while after
   the rename it keeps the old file until it ends. */
bool ReplaceByRename(const std::wstring& src, const std::wstring& dst)
{
    std::wstring temp = dst + L".wiz8wide-new";
    SetFileAttributesW(temp.c_str(), FILE_ATTRIBUTE_NORMAL);
    if (CopyFileW(src.c_str(), temp.c_str(), FALSE) &&
        MoveFileExW(temp.c_str(), dst.c_str(), MOVEFILE_REPLACE_EXISTING)) {
        return true;
    }
    SetFileAttributesW(temp.c_str(), FILE_ATTRIBUTE_NORMAL);
    DeleteFileW(temp.c_str());
    return false;
}

/* Remove what was installed and restore what was saved (both on uninstall and on rollback).
   Returns the entries that could not be removed or restored (normally none: files in use are
   checked before); their saved originals stay in Wiz8Wide.backup for the next attempt. */
std::vector<std::wstring> RemoveInstalled(const std::wstring& game,
                                          const std::vector<std::wstring>& installed)
{
    std::vector<std::wstring> failed;
    std::wstring backup = Join(game, kBackupDir);
    /* binkw32.dll could not be put back: then binkw32_wiz8wide.dll (listed right after it) stays
       too, listed again: ours still forwards to it, and it may be the only original left */
    bool bink_failed = false;
    auto fail = [&](const std::wstring& rel) {
        failed.push_back(rel);
        bink_failed = bink_failed || lstrcmpiW(rel.c_str(), kBink) == 0;
    };
    for (const std::wstring& rel : installed) {
        if (rel[0] == L'+' || rel[0] == L'*') {
            continue; /* folder (see below) or a value line */
        }
        std::wstring dst = Join(game, rel);
        std::wstring saved = Join(backup, rel);
        if (bink_failed && lstrcmpiW(rel.c_str(), kBinkOriginal) == 0) {
            failed.push_back(rel);
            continue;
        }
        /* binkw32.dll whose saved original was deleted by hand, or is not the original (cut off
           by a full disk; only an original is ever saved there) (only a folder installed under
           Wine lists binkw32.dll, so a Windows install never gets here; an uninstall on Windows
           of such a folder does): the game's original is still in its renamed copy (listed
           after binkw32.dll, so not deleted yet), which replaces binkw32.dll by a rename, so
           that binkw32.dll is never a cut-off file. With that gone too and no backup, a
           binkw32.dll that is not ours is the game's own (a store's file check put it back): it
           stays. A damaged backup without that copy (no install leaves one) goes back as usual. */
        if (lstrcmpiW(rel.c_str(), kBink) == 0 && ClassifyBink(game, saved) != BINK_ORIGINAL) {
            std::wstring copy = Join(game, kBinkOriginal);
            if (ClassifyBink(game, copy) == BINK_ORIGINAL) {
                SetFileAttributesW(dst.c_str(), FILE_ATTRIBUTE_NORMAL);
                if (!ReplaceByRename(copy, dst)) {
                    fail(rel);
                } else {
                    SetFileAttributesW(saved.c_str(), FILE_ATTRIBUTE_NORMAL);
                    DeleteFileW(saved.c_str()); /* the one that is not the original, if any */
                }
                continue;
            }
            if (!FileExists(saved) && ClassifyBink(game, dst) != BINK_OURS) {
                continue;
            }
        }
        SetFileAttributesW(dst.c_str(), FILE_ATTRIBUTE_NORMAL);
        if (!DeleteFileW(dst.c_str()) && FileExists(dst)) {
            fail(rel);
            continue;
        }
        if (FileExists(saved)) {
            CreateDirs(dst.substr(0, dst.find_last_of(L'\\')));
            if (!MoveFileExW(saved.c_str(), dst.c_str(),
                             MOVEFILE_REPLACE_EXISTING | MOVEFILE_COPY_ALLOWED)) {
                fail(rel);
            }
        }
    }
    /* folders: in Wiz8Wide.backup - all of them (they are ours), in the game - only those
       created by the installation ("+folder" in the list) and only if they became empty */
    std::vector<std::wstring> dirs;
    for (const std::wstring& rel : installed) {
        if (rel[0] == L'*') {
            continue;
        }
        bool created = rel[0] == L'+';
        std::wstring path = created ? rel.substr(1) : rel;
        for (size_t slash = path.find_last_of(L'\\'); slash != std::wstring::npos && slash > 0;
             slash = path.find_last_of(L'\\', slash - 1)) {
            dirs.push_back(Join(backup, path.substr(0, slash)));
        }
        if (created) {
            dirs.push_back(Join(game, path));
        }
    }
    std::sort(dirs.begin(), dirs.end(),
              [](const std::wstring& a, const std::wstring& b) { return a.size() > b.size(); });
    for (const std::wstring& dir : dirs) {
        RemoveDirectoryW(dir.c_str()); /* only if empty */
    }
    RemoveDirectoryW(backup.c_str());
    return failed;
}

/* Wiz8Logs\ written by the patch's diagnostics ([Debug] Diagnostics=1): session folders
   20*\ with the three logs (and the render driver's two, which an update moves there:
   KeepLastSessionLogs) and crash-*.dmp. Only those are removed; a folder that still holds
   anything else stays. */
void RemoveDiagnosticLogs(const std::wstring& game)
{
    std::wstring logs = Join(game, L"Wiz8Logs");
    std::vector<std::wstring> session_logs = {L"wiz8ws.log", L"wiz8hy.log", L"wiz8wide.log"};
    for (const wchar_t* log : kDriverLogs) {
        session_logs.push_back(FileName(log));
    }
    WIN32_FIND_DATAW found;
    HANDLE search = FindFirstFileW(Join(logs, L"*").c_str(), &found);
    if (search != INVALID_HANDLE_VALUE) {
        do {
            std::wstring name = found.cFileName;
            std::wstring path = Join(logs, name);
            if (found.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) {
                continue; /* a link made by someone else: never follow it */
            }
            if ((found.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && name.compare(0, 2, L"20") == 0) {
                for (const std::wstring& log : session_logs) {
                    std::wstring file = Join(path, log);
                    SetFileAttributesW(file.c_str(), FILE_ATTRIBUTE_NORMAL);
                    DeleteFileW(file.c_str());
                }
                RemoveDirectoryW(path.c_str()); /* only if empty */
            } else if (!(found.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && name.size() > 10 &&
                       name.compare(0, 6, L"crash-") == 0 && name.compare(name.size() - 4, 4, L".dmp") == 0) {
                SetFileAttributesW(path.c_str(), FILE_ATTRIBUTE_NORMAL);
                DeleteFileW(path.c_str());
            }
        } while (FindNextFileW(search, &found));
        FindClose(search);
    }
    RemoveDirectoryW(logs.c_str()); /* only if empty */
}

/* With the diagnostics on (Wiz8Logs\ exists), the logs of the last session move into
   Wiz8Logs\<date_time>\ (the time one of them was last written) as the patch itself does with
   its three at the next start, so an update right after a crash does not lose the exit trace.
   The render driver's logs go there with them, under their file names: the uninstall that
   follows deletes what is left in Dll\. Without Wiz8Logs\ nothing is kept. */
void KeepLastSessionLogs(const std::wstring& game)
{
    std::wstring logs = Join(game, L"Wiz8Logs");
    if (!DirExists(logs)) {
        return;
    }
    std::vector<std::wstring> last = {L"wiz8ws.log", L"wiz8hy.log", L"wiz8wide.log"};
    last.insert(last.end(), std::begin(kDriverLogs), std::end(kDriverLogs));
    FILETIME newest = {};
    bool any = false;
    for (const std::wstring& log : last) {
        WIN32_FILE_ATTRIBUTE_DATA data;
        if (GetFileAttributesExW(Join(game, log).c_str(), GetFileExInfoStandard, &data)) {
            any = true;
            if (CompareFileTime(&data.ftLastWriteTime, &newest) > 0) {
                newest = data.ftLastWriteTime;
            }
        }
    }
    if (!any) {
        return;
    }
    FILETIME local;
    SYSTEMTIME t;
    FileTimeToLocalFileTime(&newest, &local);
    FileTimeToSystemTime(&local, &t);
    wchar_t stamp[32];
    wsprintfW(stamp, L"%04d-%02d-%02d_%02d-%02d-%02d", t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute,
              t.wSecond);
    std::wstring session = Join(logs, stamp);
    CreateDirectoryW(session.c_str(), nullptr);
    for (const std::wstring& log : last) {
        MoveFileExW(Join(game, log).c_str(), Join(session, FileName(log)).c_str(),
                    MOVEFILE_REPLACE_EXISTING | MOVEFILE_COPY_ALLOWED);
    }
}

/* The diagnostics switch of the installed patch: [Debug] Diagnostics of wiz8ws.ini, read as
   the loader reads it (not 0 = on); no file or no line = off. */
bool DiagnosticsOn(const std::wstring& game)
{
    return GetPrivateProfileIntW(L"Debug", L"Diagnostics", 0, Join(game, L"wiz8ws.ini").c_str()) != 0;
}

/* Writes the diagnostics switch into wiz8ws.ini, only when it differs (so a file left as the
   package has it stays byte for byte the package's). */
void SetDiagnostics(const std::wstring& game, bool on)
{
    if (DiagnosticsOn(game) != on) {
        WritePrivateProfileStringW(L"Debug", L"Diagnostics", on ? L"1" : L"0",
                                   Join(game, L"wiz8ws.ini").c_str());
    }
}

Result Uninstall(HWND owner, const std::wstring& game, bool quiet)
{
    if (!IsFullPath(game)) {
        /* see IsGameDir (an install and the window have checked it already) */
        MessageBoxW(owner, Tr(T_NOT_GAME), kTitle, MB_ICONERROR);
        return RES_CANCELLED;
    }
    if (IsNewerFormat(game)) {
        std::wstring version = InstalledVersion(game);
        MessageBoxW(owner, Tr(T_NEWER_FORMAT, version, version).c_str(), kTitle, MB_ICONWARNING);
        return RES_CANCELLED;
    }
    std::wstring manifest = Join(game, kManifest);
    std::vector<std::wstring> installed = ReadLines(manifest);
    if (installed.empty()) {
        /* no list, or an empty one: nothing is known to be installed */
        SetFileAttributesW(manifest.c_str(), FILE_ATTRIBUTE_NORMAL);
        DeleteFileW(manifest.c_str());
        if (!quiet) {
            MessageBoxW(owner, Tr(T_NOTHING_TO_UNINSTALL), kTitle, MB_ICONINFORMATION);
        }
        return quiet ? RES_OK : RES_CANCELLED;
    }
    std::wstring busy = FindBusyFile(game, installed);
    if (!busy.empty()) {
        MessageBoxW(owner, Tr(T_IN_USE, busy).c_str(), kTitle, MB_ICONWARNING);
        return RES_CANCELLED;
    }
    if (quiet) {
        /* before the list is followed: it names the render driver's logs */
        KeepLastSessionLogs(game);
    }
    std::vector<std::wstring> failed = RemoveInstalled(game, installed);
    SetFileAttributesW(manifest.c_str(), FILE_ATTRIBUTE_NORMAL);
    if (!failed.empty()) {
        /* keep the rest in the list, so that Uninstall can simply be run again */
        std::vector<std::wstring> rest;
        for (const std::wstring& line : installed) {
            if (line[0] == L'*' || line[0] == L'+') {
                rest.push_back(line);
            }
        }
        rest.insert(rest.end(), failed.begin(), failed.end());
        WriteLines(manifest, rest);
        MessageBoxW(owner, Tr(T_UNINSTALL_INCOMPLETE, Join(game, failed[0])).c_str(), kTitle,
                    MB_ICONERROR);
        return RES_FAILED;
    }
    DeleteFileW(manifest.c_str());
    if (UnderWine()) {
        RemoveWineOverrides(game);
    }
    /* logs written by the patch itself, and by its render driver next to the driver (the
       driver's are gone already when the list names them; a list written by 1.0.0-1.0.2 does
       not) */
    for (const wchar_t* log : {L"wiz8ws.log", L"wiz8hy.log", L"wiz8wide.log"}) {
        DeleteFileW(Join(game, log).c_str());
    }
    for (const wchar_t* log : kDriverLogs) {
        DeleteFileW(Join(game, log).c_str());
    }
    if (!quiet) {
        /* a settings copy left by a failed install (the quiet uninstall of an update keeps it) */
        std::wstring keep = Join(game, L"wiz8wide.ini.keep");
        SetFileAttributesW(keep.c_str(), FILE_ATTRIBUTE_NORMAL);
        DeleteFileW(keep.c_str());
        /* logs of earlier sessions: an update keeps them, they may be wanted for a report */
        RemoveDiagnosticLogs(game);
        MessageBoxW(owner, Tr(T_DONE_UNINSTALL), kTitle, MB_ICONINFORMATION);
    }
    return RES_OK;
}

/* Install steps after the payload copy, before the manifest is written. Like the payload loop,
   they list each file in installed before changing it, so a failure is undone by the same
   rollback. Returns the file that could not be copied (empty: all went well); bink_route tells
   whether the binkw32 route was set up. Now only that route, under Wine (see "binkw32.dll"
   above): over the game's own binkw32.dll, and only with a version.dll that carries binkw32's
   functions. Another mod's binkw32.dll is left alone, and the patch then starts through the
   Wine settings as before. */
std::wstring ExtraInstallSteps(const std::wstring& game, const std::wstring& files,
                               std::vector<std::wstring>* installed, bool* overwrote_patch,
                               bool* bink_route)
{
    *bink_route = false;
    std::wstring dll = Join(files, L"version.dll");
    if (!UnderWine() || !CarriesBinkForwarders(game, dll)) {
        return std::wstring();
    }
    std::wstring bink = Join(game, kBink);
    std::wstring copy = Join(game, kBinkOriginal);
    std::wstring saved = Join(Join(game, kBackupDir), kBink);
    /* where the game's original binkw32.dll is now: normally binkw32.dll itself; after a manual
       or interrupted install, binkw32.dll is ours and the original is in the backup or, with
       the backup gone, only in the renamed copy */
    std::wstring original;
    if (IsPatchFile(game, kBink)) {
        if (ClassifyBink(game, saved) == BINK_ORIGINAL) {
            original = saved;
        } else if (ClassifyBink(game, copy) == BINK_ORIGINAL) {
            original = copy; /* the backup gone, or not the original (see below) */
        } else {
            return std::wstring(); /* no original known: nothing is changed */
        }
        *overwrote_patch = true;
    } else if (ClassifyBink(game, bink) == BINK_ORIGINAL) {
        original = bink;
    } else {
        return std::wstring(); /* missing, or another mod's */
    }
    /* the original into Wiz8Wide.backup. Only an original is ever saved there, so a different
       file already there is not an older original (as SaveOriginal assumes for other files) but
       a damaged one (cut off by a full disk): it is replaced. */
    if (original != saved && !FileExists(saved)) {
        CreateDirs(saved.substr(0, saved.find_last_of(L'\\')));
        if (!CopyToNewFile(original, saved)) {
            return bink;
        }
    } else if (original != saved && lstrcmpiW(Sha256(saved).c_str(), Sha256(original).c_str()) != 0) {
        SetFileAttributesW(saved.c_str(), FILE_ATTRIBUTE_NORMAL);
        if (!ReplaceByRename(original, saved)) {
            return bink;
        }
    }
    /* binkw32.dll first: undoing it (here or in any uninstall) restores the original before
       the renamed copy is deleted, so the game never has a binkw32.dll without its original.
       Both are written by a rename (ReplaceByRename): a game running in another Wine prefix may
       have them loaded. */
    installed->push_back(kBink);
    installed->push_back(kBinkOriginal);
    if (original != copy) {
        SetFileAttributesW(copy.c_str(), FILE_ATTRIBUTE_NORMAL);
        if (!ReplaceByRename(original, copy)) {
            return copy;
        }
    }
    SetFileAttributesW(bink.c_str(), FILE_ATTRIBUTE_NORMAL);
    if (!ReplaceByRename(dll, bink)) {
        return bink;
    }
    *bink_route = true;
    return std::wstring();
}

/* Puts a text on the clipboard (under Wine also the Linux desktop's) */
void CopyToClipboard(HWND owner, const std::wstring& text)
{
    if (!OpenClipboard(owner)) {
        return;
    }
    EmptyClipboard();
    size_t size = (text.size() + 1) * sizeof(wchar_t);
    HGLOBAL memory = GlobalAlloc(GMEM_MOVEABLE, size);
    void* data = memory ? GlobalLock(memory) : nullptr;
    if (data) {
        memcpy(data, text.c_str(), size);
        GlobalUnlock(memory);
        if (!SetClipboardData(CF_UNICODETEXT, memory)) {
            GlobalFree(memory); /* still ours: the clipboard did not take it */
        }
    } else if (memory) {
        GlobalFree(memory);
    }
    CloseClipboard();
}

/* What an install under Wine did for starting the patch; selects the final message's Linux
   paragraph. */
enum WineOutcome {
    WINE_OWN_BLOCKS, /* a setting of the player's in this prefix keeps the patch from starting */
    WINE_THIS,       /* set up in the game's own prefix (the installer runs in it) */
    WINE_OTHER,      /* the game runs in another prefix: nothing set here, the launch option once */
    WINE_UNKNOWN,    /* set up here, but whether the game runs here is not known */
    WINE_AUTO        /* the binkw32 route: starts by itself in any prefix */
};

/* The Wine part of an install. The values (AddWineOverrides) go only into a prefix the game
   runs in or may run in (THIS, UNKNOWN); with the binkw32 route they are still written there, as
   a fallback for when a store's file check puts the original binkw32.dll back. Without the route
   the launch option goes on the clipboard whenever it may be needed (OTHER, UNKNOWN). */
WineOutcome WineAfterInstall(HWND owner, const std::wstring& game, Verdict verdict, bool bink_route)
{
    bool here = verdict == VERDICT_THIS || verdict == VERDICT_UNKNOWN;
    bool ok = !here || AddWineOverrides(game);
    if (bink_route) {
        /* only ddraw matters then: binkw32.dll starts the patch whatever version.dll Wine loads */
        return here && !WineOrderOk(kWineDlls[1], game) ? WINE_OWN_BLOCKS : WINE_AUTO;
    }
    if (!ok) {
        return WINE_OWN_BLOCKS;
    }
    if (verdict == VERDICT_THIS) {
        return WINE_THIS;
    }
    CopyToClipboard(owner, kLaunchOption);
    return verdict == VERDICT_UNKNOWN ? WINE_UNKNOWN : WINE_OTHER;
}

/* Where a game was found, as the window names it: "Steam shortcut "Wizardry 8"", "Heroic"... */
std::wstring SourceName(const Candidate& game)
{
    switch (game.source) {
    case SOURCE_GOG:
        return Tr(T_SOURCE_GOG);
    case SOURCE_STEAM:
        return Tr(T_SOURCE_STEAM);
    case SOURCE_SHORTCUT: {
        /* a shortcut's name is the player's text: kept short, so a message stays within Tr's limit */
        std::wstring label = game.label.size() > 64 ? game.label.substr(0, 61) + L"..." : game.label;
        return Tr(T_SOURCE_SHORTCUT, label);
    }
    case SOURCE_HEROIC:
        return Tr(T_SOURCE_HEROIC);
    case SOURCE_LUTRIS:
        return Tr(T_SOURCE_LUTRIS);
    case SOURCE_PREFIX:
        return Tr(T_SOURCE_PREFIX);
    default:
        return std::wstring();
    }
}

/* The final message's Linux paragraph */
std::wstring WineText(WineOutcome outcome, const Candidate& game)
{
    switch (outcome) {
    case WINE_OWN_BLOCKS:
        return Tr(T_WINE_OWN);
    case WINE_THIS:
        return Tr(T_WINE_THIS);
    case WINE_OTHER:
        return Tr(T_WINE_OTHER, SourceName(game), kLaunchOption);
    case WINE_AUTO:
        return Tr(T_WINE_AUTO);
    default:
        return Tr(T_WINE_NOTE, kLaunchOption);
    }
}

/* diagnostics: the "Diagnostics mode" choice - 1 on, 0 off, -1 keep what the installed
   wiz8ws.ini has (off when there is none: a fresh install). where: the game as found (under
   Wine its verdict decides where the Wine values go; a folder no launcher lists has an unknown
   verdict). */
Result Install(HWND owner, const std::wstring& game, int diagnostics, const Candidate& where)
{
    std::wstring files = Join(ExeDir(), L"files");
    if (!DirExists(files)) {
        MessageBoxW(owner, Tr(T_NO_FILES), kTitle, MB_ICONERROR);
        return RES_FAILED;
    }
    /* an incomplete files\ (a partial unpack, a DLL taken by an antivirus) is refused here,
       before anything is changed: an update would first remove the old install, which works */
    for (const wchar_t* rel : kRequiredFiles) {
        if (!FileExists(Join(files, rel))) {
            MessageBoxW(owner, Tr(T_FILE_MISSING, Join(files, rel)).c_str(), kTitle, MB_ICONERROR);
            return RES_FAILED;
        }
    }
    if (!IsGameDir(game)) {
        MessageBoxW(owner, Tr(T_NOT_GAME), kTitle, MB_ICONERROR);
        return RES_FAILED;
    }
    std::wstring dll = Join(game, L"version.dll");
    if (FileExists(dll) && !IsOurVersionDll(dll)) {
        MessageBoxW(owner, Tr(T_FOREIGN_DLL), kTitle, MB_ICONWARNING);
        return RES_CANCELLED;
    }
    /* a newer version is installed: refuse if it is beyond this installer, otherwise
       roll back only if the player confirms */
    std::wstring previous = InstalledVersion(game);
    if (IsNewerFormat(game)) {
        MessageBoxW(owner, Tr(T_NEWER_FORMAT, previous, previous).c_str(), kTitle, MB_ICONWARNING);
        return RES_CANCELLED;
    }
    int order = previous.empty() ? 0 : CompareVersions(previous, kVersion);
    if (order > 0 && MessageBoxW(owner, Tr(T_ASK_ROLLBACK, previous, kVersion).c_str(), kTitle,
                                 MB_ICONWARNING | MB_YESNO | MB_DEFBUTTON2) != IDYES) {
        return RES_CANCELLED;
    }
    if (lstrcmpiW(Sha256(Join(game, L"Wiz8.exe")).c_str(), kExeSha256) != 0 &&
        MessageBoxW(owner, Tr(T_UNKNOWN_EXE), kTitle, MB_ICONWARNING | MB_YESNO | MB_DEFBUTTON2) !=
            IDYES) {
        return RES_CANCELLED;
    }

    std::vector<std::wstring> payload;
    ListFiles(files, L"", &payload);
    /* without dgVoodoo, should files\ still have it from an older package (see IsDgVoodoo) */
    payload.erase(std::remove_if(payload.begin(), payload.end(), IsDgVoodoo), payload.end());
    /* nothing may be in use (the game running, an editor): neither the files of the old
       install nor those that will be replaced; checked before anything is changed */
    std::wstring manifest = Join(game, kManifest);
    std::vector<std::wstring> touched = ReadLines(manifest);
    touched.insert(touched.end(), payload.begin(), payload.end());
    std::wstring busy = FindBusyFile(game, touched);
    if (!busy.empty()) {
        MessageBoxW(owner, Tr(T_IN_USE, busy).c_str(), kTitle, MB_ICONWARNING);
        return RES_CANCELLED;
    }

    /* the player's settings survive any install over the patch (update, reinstall, rollback,
       over a manual install, after a failure): the whole wiz8wide.ini, and the on/off switch
       of wiz8ws.ini (Enabled=0, see the README) */
    std::wstring ini = Join(game, L"wiz8wide.ini");
    std::wstring keep = Join(game, L"wiz8wide.ini.keep");
    std::wstring ws_ini = Join(game, L"wiz8ws.ini");
    bool kept;
    if (FileExists(ini)) {
        SetFileAttributesW(keep.c_str(), FILE_ATTRIBUTE_NORMAL);
        DeleteFileW(keep.c_str());
        kept = CopyFileW(ini.c_str(), keep.c_str(), FALSE) != FALSE;
        if (!kept) {
            MessageBoxW(owner, Tr(T_COPY_FAILED, keep).c_str(), kTitle, MB_ICONERROR);
            return RES_FAILED; /* nothing changed yet */
        }
    } else {
        kept = FileExists(keep); /* the only copy, left by an earlier failed install */
    }
    SetFileAttributesW(keep.c_str(), FILE_ATTRIBUTE_NORMAL);
    bool disabled = GetPrivateProfileIntW(L"General", L"Enabled", 1, ws_ini.c_str()) == 0;
    /* the diagnostics switch as it is now (read before the quiet uninstall removes wiz8ws.ini) */
    bool diagnostics_was = DiagnosticsOn(game);
    bool diagnostics_on = diagnostics < 0 ? diagnostics_was : diagnostics != 0;
    /* installed: the chosen diagnostics value; failed: the previous one, kept for the next
       attempt like Enabled=0 (nothing is written for an off switch, so a failed fresh install
       leaves no wiz8ws.ini behind) */
    auto restore_settings = [&](bool installed_ok) {
        if (kept && CopyFileW(keep.c_str(), ini.c_str(), FALSE)) {
            DeleteFileW(keep.c_str());
        }
        if (disabled) {
            WritePrivateProfileStringW(L"General", L"Enabled", L"0", ws_ini.c_str());
        }
        if (installed_ok) {
            SetDiagnostics(game, diagnostics_on);
        } else if (diagnostics_was) {
            SetDiagnostics(game, true);
        }
    };

    /* update, reinstall or rollback: first quietly remove the old install (restoring the
       originals). If that fails, Uninstall has said why and the list keeps what is left;
       wiz8wide.ini.keep stays for the next attempt. */
    if (!previous.empty() && Uninstall(owner, game, true) != RES_OK) {
        return RES_FAILED;
    }

    std::vector<std::wstring> installed;
    bool overwrote_patch = false; /* patch files found without a manifest, see IsPatchFile */
    /* a failure undoes all that is listed in installed so far, and says which file failed */
    auto failed = [&](const std::wstring& file) {
        RemoveInstalled(game, installed);
        restore_settings(false);
        MessageBoxW(owner, Tr(previous.empty() && !overwrote_patch ? T_COPY_FAILED : T_UPDATE_FAILED, file).c_str(),
                    kTitle, MB_ICONERROR);
        return RES_FAILED;
    };
    /* 1. the payload: the files of the package */
    for (const std::wstring& rel : payload) {
        std::wstring src = Join(files, rel);
        std::wstring dst = Join(game, rel);
        bool exists = FileExists(dst);
        if (exists && IsPatchFile(game, rel)) {
            overwrote_patch = true;
        } else if (exists && !SaveOriginal(game, rel)) {
            return failed(dst);
        }
        /* remember the folders that did not exist in the game (uninstall removes only those) */
        for (std::wstring dir = rel.substr(0, rel.find_last_of(L'\\'));
             rel.find(L'\\') != std::wstring::npos && !DirExists(Join(game, dir));
             dir = dir.substr(0, dir.find_last_of(L'\\'))) {
            installed.push_back(L"+" + dir);
            if (dir.find(L'\\') == std::wstring::npos) {
                break;
            }
        }
        CreateDirs(dst.substr(0, dst.find_last_of(L'\\')));
        SetFileAttributesW(dst.c_str(), FILE_ATTRIBUTE_NORMAL);
        /* listed before copying: a copy that fails halfway deletes dst, and the rollback
           below must then put the saved original back */
        installed.push_back(rel);
        if (!CopyFileW(src.c_str(), dst.c_str(), FALSE)) {
            return failed(dst);
        }
    }
    /* 2. the extra steps (now only the binkw32 route under Wine) */
    bool bink_route = false;
    std::wstring extra_failed = ExtraInstallSteps(game, files, &installed, &overwrote_patch, &bink_route);
    if (!extra_failed.empty()) {
        return failed(extra_failed);
    }
    /* 3. what the patched game writes itself. 3DVideo.CFG at every start (D3D11, the patch's
       render driver, and the chosen resolution): the original is saved, so that uninstall
       restores it; a folder that has none gets the line alone, and uninstall then deletes the
       file the patched game made (it names a driver the original game does not have). Listed
       only once the original is saved: the rollback of a failure deletes what is listed */
    std::wstring video_cfg = L"3DVideo.CFG";
    if (FileExists(Join(game, video_cfg)) && !SaveOriginal(game, video_cfg)) {
        return failed(Join(game, video_cfg));
    }
    installed.push_back(video_cfg);
    /* and the render driver's logs, which have no originals */
    installed.insert(installed.end(), std::begin(kDriverLogs), std::end(kDriverLogs));
    /* 4. the manifest */
    installed.insert(installed.begin(), std::wstring(kVersionLine) + kVersion);
    SetFileAttributesW(manifest.c_str(), FILE_ATTRIBUTE_NORMAL);
    if (!WriteLines(manifest, installed)) {
        DeleteFileW(manifest.c_str());
        return failed(manifest);
    }
    /* the player's settings over the defaults just copied */
    restore_settings(true);
    std::wstring done = order < 0   ? Tr(T_DONE_UPDATE, previous, kVersion)
                        : order > 0 ? Tr(T_DONE_ROLLBACK, previous, kVersion)
                                    : Tr(T_DONE_INSTALL, kVersion);
    /* 5. Wine: its settings, and the paragraph that says what is left to do */
    if (UnderWine()) {
        done += WineText(WineAfterInstall(owner, game, where.verdict, bink_route), where);
    }
    MessageBoxW(owner, done.c_str(), kTitle, MB_ICONINFORMATION);
    return RES_OK;
}

/* The folder of --install and --uninstall as the full path the rest of the installer works with
   (see IsGameDir). A relative one ("." or "Wizardry 8", typed in a console in or next to the game
   folder) is read against the current folder, which is what 1.0.2 did with it on Windows
   (GetFullPathNameW puts the current folder in front and works out "." and "..", without looking
   at the disk); under Wine it may first be a Linux path (NormalizeTypedFolder). Nothing but
   spaces and slashes ("" from a script whose variable was empty) stays empty, and is then
   refused: read against the current folder it would be that folder itself, or the root of its
   drive. */
std::wstring CommandLineFolder(const std::wstring& arg)
{
    if (arg.find_first_not_of(L" \t\r\n\\/") == std::wstring::npos) {
        return std::wstring();
    }
    std::wstring folder = UnderWine() ? NormalizeTypedFolder(arg) : arg;
    if (!folder.empty() && !IsFullPath(folder)) {
        wchar_t full[MAX_PATH * 2];
        DWORD n = GetFullPathNameW(folder.c_str(), MAX_PATH * 2, full, 0);
        if (n && n < MAX_PATH * 2) {
            folder = full;
        }
    }
    return TrimSlashes(folder);
}

/* Restart itself with administrator rights for this folder and action (option: an extra switch
   after the folder, such as --diagnostics, or 0). */
bool RelaunchElevated(HWND owner, const std::wstring& game, const wchar_t* action,
                      const wchar_t* option)
{
    std::wstring exe = ExePath();
    /* Backslashes right before the closing quote are doubled: the command line parser reads
       2n of them + '"' as n backslashes, but "D:\" (a drive root) as D: plus a quote. */
    std::wstring quoted = game;
    for (size_t i = game.size(); i > 0 && game[i - 1] == L'\\'; --i) {
        quoted += L'\\';
    }
    std::wstring args = std::wstring(action) + L" \"" + quoted + L"\"";
    if (option) {
        args += L" ";
        args += option;
    }
    SHELLEXECUTEINFOW info = {};
    info.cbSize = sizeof(info);
    info.fMask = SEE_MASK_NOCLOSEPROCESS;
    info.hwnd = owner;
    info.lpVerb = L"runas";
    info.lpFile = exe.c_str();
    info.lpParameters = args.c_str();
    info.nShow = SW_SHOWNORMAL;
    if (!ShellExecuteExW(&info)) {
        return false; /* UAC declined */
    }
    if (info.hProcess) {
        WaitForSingleObject(info.hProcess, INFINITE);
        CloseHandle(info.hProcess);
    }
    return true;
}

/* ---------------- report ---------------- */

/* "Report a problem...": one zip with what a bug report needs - the patch's and the render
   driver's logs, their settings, the list of installed files, what the diagnostics mode keeps
   in Wiz8Logs\ (the logs of earlier sessions, crash dumps), and report.txt with the versions
   and the system. It is saved to the Desktop (under Wine: the Linux Desktop or home folder,
   because nobody looks into a Wine prefix's own Desktop; if none of them can be written, the
   user's temporary folder), and the page of the patch's bug report form on GitHub is offered,
   with the versions filled in. The installer itself sends nothing anywhere and changes nothing
   in the game folder: the report only reads it.
   Without the window: Wiz8WideSetup.exe --report "folder" ["file.zip"]. */

const wchar_t kReportPage[] = L"https://github.com/abr17/wiz8-widescreen/issues";
const wchar_t kReportForm[] = L"/new?template=bug_report.yml";
/* GitHub takes attachments of up to 25 MB. The files below go in first, then what Wiz8Logs\
   holds, newest first; a file that would take the archive over this is left out (report.txt
   names it). */
const size_t kReportLimit = 24u << 20;
/* a single file larger than this is left out (no dump of the patch comes near it); a log is
   cut instead (kReportLogHead) */
const ULONGLONG kReportFileLimit = 64u << 20;
/* A log larger than these two together goes in as its start and its end, with a line between
   them that says how much is left out. The patch's and the render driver's logs begin with the
   versions, the settings and the graphics device and end with what happened last; the render
   driver's has no size limit, and with LogLevel=3 in Dll\srDD_D3D11.ini it gets a line for
   every call. */
const size_t kReportLogHead = 1u << 20;
const size_t kReportLogTail = 7u << 20;
/* files of the game folder that are in every report when they exist: the settings and the
   installed list first (they are small, and no log may crowd them out), then the logs of the
   last session */
const wchar_t* const kReportFiles[] = {L"wiz8ws.ini",   L"wiz8wide.ini",        L"Dll\\srDD_D3D11.ini",
                                       L"3DVideo.CFG",  kManifest,              L"wiz8ws.log",
                                       L"wiz8hy.log",   L"wiz8wide.log",        L"Dll\\srDD_D3D11.log",
                                       L"Dll\\srDD_D3D11.log.old"};
/* files of the game folder that report.txt only describes (there or not, size, time): the
   programs of the patch, with their SHA-256 for a comparison with a release's files */
const wchar_t* const kReportPrograms[] = {L"Dll\\srDD_D3D11.dll", L"version.dll", L"wiz8hy.dll"};

std::string ToUtf8(const std::wstring& text)
{
    std::string bytes;
    int size = WideCharToMultiByte(CP_UTF8, 0, text.data(), (int)text.size(), 0, 0, 0, 0);
    if (size > 0) {
        bytes.assign(size, '\0');
        WideCharToMultiByte(CP_UTF8, 0, text.data(), (int)text.size(), &bytes[0], size, 0, 0);
    }
    return bytes;
}

std::wstring FromUtf8(const char* text)
{
    std::wstring wide;
    int size = MultiByteToWideChar(CP_UTF8, 0, text, -1, 0, 0);
    if (size > 1) {
        wide.assign(size - 1, L'\0');
        MultiByteToWideChar(CP_UTF8, 0, text, -1, &wide[0], size);
    }
    return wide;
}

std::wstring NumberText(ULONGLONG value)
{
    std::wstring text;
    do {
        text.insert(text.begin(), (wchar_t)(L'0' + value % 10));
        value /= 10;
    } while (value);
    return text;
}

/* Whether a file is a log by its name (".log", or the render driver's ".log.old") */
bool IsLogName(const std::wstring& name)
{
    for (const wchar_t* ending : {L".log", L".log.old"}) {
        size_t length = lstrlenW(ending);
        if (name.size() > length && lstrcmpiW(name.c_str() + name.size() - length, ending) == 0) {
            return true;
        }
    }
    return false;
}

/* Up to size bytes of an open file from offset on, appended to *bytes: fewer when the file ends
   before that (a log the game has cut short meanwhile). */
void ReadPart(HANDLE file, ULONGLONG offset, size_t size, std::string* bytes)
{
    LARGE_INTEGER start;
    start.QuadPart = (LONGLONG)offset;
    if (!SetFilePointerEx(file, start, 0, FILE_BEGIN)) {
        return;
    }
    size_t before = bytes->size();
    bytes->resize(before + size);
    size_t done = 0;
    while (done < size) {
        DWORD want = (DWORD)std::min<size_t>(size - done, 1u << 20);
        DWORD read = 0;
        if (!ReadFile(file, &(*bytes)[before + done], want, &read, 0) || read == 0) {
            break;
        }
        done += read;
    }
    bytes->resize(before + done);
}

/* How ReadForReport read a file */
enum ReportRead {
    READ_WHOLE,
    READ_CUT,       /* a log: its start and its end (see kReportLogHead) */
    READ_TOO_LARGE, /* over kReportFileLimit and not a log: nothing read */
    READ_FAILED     /* it cannot be opened */
};

/* A file as it is now, also one the running game still writes. A log over kReportLogHead +
   kReportLogTail bytes is cut in the middle, both parts at a line end, with one line between
   them that says so; *left_out is then the number of bytes that are not in *bytes. */
ReportRead ReadForReport(const std::wstring& path, bool log, std::string* bytes, ULONGLONG* left_out)
{
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ,
                              FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, 0, OPEN_EXISTING, 0, 0);
    if (file == INVALID_HANDLE_VALUE) {
        return READ_FAILED;
    }
    LARGE_INTEGER size;
    if (!GetFileSizeEx(file, &size)) {
        CloseHandle(file);
        return READ_FAILED;
    }
    ULONGLONG total = (ULONGLONG)size.QuadPart;
    ReportRead result = READ_WHOLE;
    if (log && total > kReportLogHead + kReportLogTail) {
        std::string tail;
        ReadPart(file, 0, kReportLogHead, bytes);
        ReadPart(file, total - kReportLogTail, kReportLogTail, &tail);
        /* whole lines only: the start up to its last line end, the end from its first */
        size_t line_end = bytes->rfind('\n');
        if (line_end != std::string::npos) {
            bytes->resize(line_end + 1);
        }
        line_end = tail.find('\n');
        if (line_end != std::string::npos) {
            tail.erase(0, line_end + 1);
        }
        *left_out = total - std::min<ULONGLONG>(total, bytes->size() + tail.size());
        if (!bytes->empty() && bytes->back() != '\n') {
            *bytes += "\r\n"; /* no line end in the whole start: the note still gets its own line */
        }
        *bytes += "[Wiz8WideSetup: " + ToUtf8(NumberText(*left_out)) +
                  " bytes of this log are left out here; the report holds its start and its end]\r\n" + tail;
        result = READ_CUT;
    } else if (total > kReportFileLimit) {
        result = READ_TOO_LARGE;
    } else {
        ReadPart(file, 0, (size_t)total, bytes);
    }
    CloseHandle(file);
    return result;
}

struct ReportEntry {
    std::wstring rel; /* inside the game folder */
    FILETIME time;
};

/* What the diagnostics mode keeps in Wiz8Logs\: the files of the session folders 20*\ and
   crash-*.dmp (docs\loader.md), newest first. Links are not followed. */
std::vector<ReportEntry> DiagnosticFiles(const std::wstring& game)
{
    std::vector<ReportEntry> files;
    const std::wstring logs = L"Wiz8Logs";
    WIN32_FIND_DATAW found;
    HANDLE search = FindFirstFileW(Join(Join(game, logs), L"*").c_str(), &found);
    if (search != INVALID_HANDLE_VALUE) {
        do {
            std::wstring name = found.cFileName;
            if (found.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) {
                continue;
            }
            if (found.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
                if (name.compare(0, 2, L"20") != 0) {
                    continue;
                }
                WIN32_FIND_DATAW inner;
                HANDLE session = FindFirstFileW(Join(Join(Join(game, logs), name), L"*").c_str(), &inner);
                if (session != INVALID_HANDLE_VALUE) {
                    do {
                        if (!(inner.dwFileAttributes &
                              (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT))) {
                            files.push_back({Join(Join(logs, name), inner.cFileName), inner.ftLastWriteTime});
                        }
                    } while (FindNextFileW(session, &inner));
                    FindClose(session);
                }
            } else if (name.size() > 10 && name.compare(0, 6, L"crash-") == 0 &&
                       name.compare(name.size() - 4, 4, L".dmp") == 0) {
                files.push_back({Join(logs, name), found.ftLastWriteTime});
            }
        } while (FindNextFileW(search, &found) && files.size() < 500);
        FindClose(search);
    }
    std::sort(files.begin(), files.end(), [](const ReportEntry& a, const ReportEntry& b) {
        LONG order = CompareFileTime(&a.time, &b.time);
        return order != 0 ? order > 0 : a.rel < b.rel;
    });
    return files;
}

/* "Windows 10.0.26100 x64", or "Wine 9.0, as Windows 10.0.19043 x64" */
std::wstring SystemText()
{
    HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");
    typedef LONG(WINAPI * VersionFn)(OSVERSIONINFOW*);
    typedef const char*(__cdecl * WineFn)(void);
    VersionFn version = ntdll ? (VersionFn)(void*)GetProcAddress(ntdll, "RtlGetVersion") : nullptr;
    WineFn wine = ntdll ? (WineFn)(void*)GetProcAddress(ntdll, "wine_get_version") : nullptr;
    OSVERSIONINFOW os = {};
    os.dwOSVersionInfoSize = sizeof(os);
    wchar_t buffer[80];
    if (version && version(&os) == 0) {
        wsprintfW(buffer, L"Windows %lu.%lu.%lu", os.dwMajorVersion, os.dwMinorVersion, os.dwBuildNumber);
    } else {
        lstrcpyW(buffer, L"Windows");
    }
    std::wstring text = buffer;
    BOOL wow = FALSE;
    text += IsWow64Process(GetCurrentProcess(), &wow) && wow ? L" x64" : L" x86";
    if (wine) {
        text = L"Wine " + FromUtf8(wine()) + L", as " + text;
    }
    return text;
}

/* The graphics cards Windows lists, the primary one first, each with its driver version when
   the registry has it: "NVIDIA GeForce RTX 4080 Laptop GPU (driver 32.0.15.6094)". */
std::vector<std::wstring> GraphicsCards()
{
    std::vector<std::wstring> cards;
    const std::wstring machine = L"\\Registry\\Machine\\";
    for (DWORD i = 0; i < 32; ++i) {
        DISPLAY_DEVICEW device = {};
        device.cb = sizeof(device);
        if (!EnumDisplayDevicesW(0, i, &device, 0)) {
            break;
        }
        std::wstring name = device.DeviceString;
        if (name.empty() || (device.StateFlags & DISPLAY_DEVICE_MIRRORING_DRIVER)) {
            continue;
        }
        std::wstring key = device.DeviceKey;
        if (key.size() > machine.size() &&
            lstrcmpiW(key.substr(0, machine.size()).c_str(), machine.c_str()) == 0) {
            std::wstring driver = RegString(HKEY_LOCAL_MACHINE, key.c_str() + machine.size(),
                                            L"DriverVersion", KEY_WOW64_64KEY);
            if (!driver.empty()) {
                name += L" (driver " + driver + L")";
            }
        }
        if (std::find(cards.begin(), cards.end(), name) == cards.end()) {
            bool primary = (device.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE) != 0;
            cards.insert(primary ? cards.begin() : cards.end(), name);
        }
    }
    return cards;
}

std::wstring TimeText(const SYSTEMTIME& t)
{
    wchar_t buffer[32];
    wsprintfW(buffer, L"%04d-%02d-%02d %02d:%02d:%02d", t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute,
              t.wSecond);
    return buffer;
}

/* The line of report.txt about a file of the game folder that the report does not hold:
   whether it is there, its size and last change, and with hash its SHA-256. */
std::wstring FileLine(const std::wstring& game, const std::wstring& rel, bool hash)
{
    std::wstring path = Join(game, rel);
    WIN32_FILE_ATTRIBUTE_DATA data;
    if (!GetFileAttributesExW(path.c_str(), GetFileExInfoStandard, &data) ||
        (data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) {
        return L"  " + rel + L"  absent\r\n";
    }
    FILETIME local;
    SYSTEMTIME when = {};
    FileTimeToLocalFileTime(&data.ftLastWriteTime, &local);
    FileTimeToSystemTime(&local, &when);
    std::wstring line = L"  " + rel + L"  " +
                        NumberText(((ULONGLONG)data.nFileSizeHigh << 32) | data.nFileSizeLow) +
                        L" bytes  " + TimeText(when);
    if (hash) {
        std::wstring sha = Sha256(path);
        line += L"  SHA-256 " + (sha.empty() ? std::wstring(L"cannot be read") : sha);
    }
    return line + L"\r\n";
}

/* what RunReport needs to know of a report: the values the bug report form gets filled in
   with, and whether report.txt names anything left out or cut */
struct ReportFacts {
    std::wstring version;
    std::wstring system;
    std::wstring graphics;
    bool partly = false;
};

/* The whole report as the bytes of a zip file. */
bool BuildReport(const std::wstring& game, std::string* archive, ReportFacts* facts)
{
    zipw::Writer zip;
    std::wstring listed;
    std::wstring missing;
    std::wstring left_out;
    auto add = [&](const std::wstring& rel) {
        std::wstring path = Join(game, rel);
        WIN32_FILE_ATTRIBUTE_DATA data;
        if (!GetFileAttributesExW(path.c_str(), GetFileExInfoStandard, &data) ||
            (data.dwFileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT))) {
            missing += (missing.empty() ? L"" : L", ") + rel;
            return;
        }
        ULONGLONG size = ((ULONGLONG)data.nFileSizeHigh << 32) | data.nFileSizeLow;
        FILETIME local;
        SYSTEMTIME when = {};
        WORD date = 0;
        WORD time = 0;
        FileTimeToLocalFileTime(&data.ftLastWriteTime, &local);
        FileTimeToSystemTime(&local, &when);
        if (!FileTimeToDosDateTime(&local, &date, &time)) {
            date = (1 << 5) | 1; /* 1980-01-01 */
            time = 0;
        }
        std::string name = ToUtf8(rel);
        std::replace(name.begin(), name.end(), '\\', '/');
        std::string bytes;
        ULONGLONG cut = 0;
        ReportRead read = ReadForReport(path, IsLogName(rel), &bytes, &cut);
        std::wstring reason;
        if (read == READ_FAILED) {
            reason = L"could not be read";
        } else if (read == READ_TOO_LARGE) {
            reason = L"larger than " + NumberText(kReportFileLimit >> 20) + L" MB";
        } else if (!zip.Add(name, bytes, time, date, kReportLimit)) {
            reason = L"the archive would pass " + NumberText(kReportLimit >> 20) + L" MB";
        }
        if (!reason.empty()) {
            left_out += L"  " + rel + L"  " + NumberText(size) + L" bytes  " + reason + L"\r\n";
            return;
        }
        listed += L"  " + rel + L"  " + NumberText(bytes.size()) + L" bytes  " + TimeText(when);
        if (read == READ_CUT) {
            listed += L"  cut: " + NumberText(cut) + L" bytes of its middle are left out";
            facts->partly = true;
        }
        listed += L"\r\n";
    };
    for (const wchar_t* rel : kReportFiles) {
        add(rel);
    }
    for (const ReportEntry& entry : DiagnosticFiles(game)) {
        add(entry.rel);
    }
    facts->partly = facts->partly || !left_out.empty();

    std::wstring installed = InstalledVersion(game);
    std::wstring exe = Sha256(Join(game, L"Wiz8.exe"));
    std::vector<std::wstring> cards = GraphicsCards();
    facts->version = installed.empty() ? std::wstring(kVersion) + L" (not installed)" : installed;
    facts->system = SystemText();
    facts->graphics = cards.empty() ? std::wstring() : cards[0];

    SYSTEMTIME now;
    GetLocalTime(&now);
    MEMORYSTATUSEX memory = {};
    memory.dwLength = sizeof(memory);
    GlobalMemoryStatusEx(&memory);
    HDC screen = GetDC(0);
    int dpi = screen ? GetDeviceCaps(screen, LOGPIXELSY) : 96;
    if (screen) {
        ReleaseDC(0, screen);
    }
    wchar_t number[64];
    std::wstring text = L"Wizardry 8 Widescreen - problem report\r\n";
    text += L"Made: " + TimeText(now) + L" (local time) by Wiz8WideSetup.exe " + kVersion + L"\r\n\r\n";
    text += L"Patch installed: " + (installed.empty() ? std::wstring(L"no") : installed) + L"\r\n";
    text += L"Wiz8.exe: " +
            (exe.empty() ? std::wstring(L"cannot be read")
             : lstrcmpiW(exe.c_str(), kExeSha256) == 0 ? std::wstring(L"version 1.2.4 (tested)")
                                                       : L"another version, SHA-256 " + exe) +
            L"\r\n";
    text += L"Game folder: " + game + L"\r\n";
    text += std::wstring(L"Diagnostics mode: ") + (DiagnosticsOn(game) ? L"on" : L"off") + L"\r\n";
    text += L"System: " + facts->system + L"\r\n";
    text += L"Processor: " +
            RegString(HKEY_LOCAL_MACHINE, L"HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0",
                      L"ProcessorNameString", KEY_WOW64_64KEY) +
            L"\r\n";
    text += L"Memory: " + NumberText(memory.ullTotalPhys >> 20) + L" MB\r\n";
    text += L"Graphics: ";
    for (size_t i = 0; i < cards.size(); ++i) {
        text += (i ? L"; " : L"") + cards[i];
    }
    text += L"\r\n";
    wsprintfW(number, L"%dx%d at %d %%, screens: %d", GetSystemMetrics(SM_CXSCREEN),
              GetSystemMetrics(SM_CYSCREEN), MulDiv(dpi, 100, 96), GetSystemMetrics(SM_CMONITORS));
    text += std::wstring(L"Primary screen: ") + number + L"\r\n";
    wsprintfW(number, L"0x%04x", GetUserDefaultUILanguage());
    text += std::wstring(L"Windows language: ") + number + L"\r\n\r\n";
    /* which programs the game folder has: those of the patch, binkw32.dll (under Wine a copy of
       the patch's version.dll, see "binkw32.dll" above), and the dgVoodoo files, which decide
       what DirectDraw the game gets when they are there */
    text += L"Program files in the game folder (bytes, last change in local time; not in this "
            L"archive):\r\n";
    for (const wchar_t* rel : kReportPrograms) {
        text += FileLine(game, rel, true);
    }
    text += FileLine(game, kBink, false);
    for (const wchar_t* rel : kDgVoodoo) {
        text += FileLine(game, rel, false);
    }
    text += L"\r\nFiles in this archive (bytes, last change in local time):\r\n" + listed;
    if (!missing.empty()) {
        text += L"\r\nNot in the game folder: " + missing + L"\r\n";
    }
    if (!left_out.empty()) {
        text += L"\r\nLeft out:\r\n" + left_out;
    }
    FILETIME stamp;
    WORD date = 0;
    WORD time = 0;
    SystemTimeToFileTime(&now, &stamp);
    FileTimeToDosDateTime(&stamp, &date, &time);
    if (!zip.Add("report.txt", ToUtf8(text), time, date)) {
        return false;
    }
    *archive = zip.Finish();
    return !archive->empty();
}

bool SaveBytes(const std::wstring& path, const std::string& bytes)
{
    HANDLE file = CreateFileW(path.c_str(), GENERIC_WRITE, 0, 0, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, 0);
    if (file == INVALID_HANDLE_VALUE) {
        return false;
    }
    size_t done = 0;
    bool ok = true;
    while (ok && done < bytes.size()) {
        DWORD want = (DWORD)std::min<size_t>(bytes.size() - done, 1u << 20);
        DWORD written = 0;
        ok = WriteFile(file, bytes.data() + done, want, &written, 0) && written > 0;
        done += written;
    }
    CloseHandle(file);
    if (!ok) {
        DeleteFileW(path.c_str());
    }
    return ok;
}

/* Makes the report of the game folder and saves it. *path: the file to write, or empty: then
   Wiz8Wide-report-<date_time>.zip on the Desktop (under Wine the Linux Desktop or home folder
   first), or in the user's temporary folder if that fails; never in the game folder, which a
   report leaves as it is. On return the file written (or tried last). */
bool SaveReport(const std::wstring& game, std::wstring* path, ReportFacts* facts)
{
    std::string archive;
    if (!IsGameDir(game) || !BuildReport(game, &archive, facts)) {
        return false;
    }
    if (!path->empty()) {
        return SaveBytes(*path, archive);
    }
    std::vector<std::wstring> folders;
    if (UnderWine()) {
        std::wstring home = HomeFolder();
        if (!home.empty()) {
            folders.push_back(Join(home, L"Desktop"));
            folders.push_back(home);
        }
    }
    wchar_t desktop[MAX_PATH];
    if (SHGetFolderPathW(0, CSIDL_DESKTOPDIRECTORY, 0, SHGFP_TYPE_CURRENT, desktop) == S_OK) {
        folders.push_back(desktop);
    }
    wchar_t temp[MAX_PATH + 1];
    DWORD length = GetTempPathW(MAX_PATH + 1, temp);
    if (length > 0 && length <= MAX_PATH) {
        folders.push_back(temp);
    }
    SYSTEMTIME now;
    GetLocalTime(&now);
    wchar_t name[64];
    wsprintfW(name, L"Wiz8Wide-report-%04d-%02d-%02d_%02d-%02d-%02d.zip", now.wYear, now.wMonth, now.wDay,
              now.wHour, now.wMinute, now.wSecond);
    for (const std::wstring& folder : folders) {
        *path = Join(folder, name);
        if (DirExists(folder) && SaveBytes(*path, archive)) {
            return true;
        }
    }
    return false;
}

/* A path as the player knows it: under Wine the Linux path. */
std::wstring ShownPath(const std::wstring& path)
{
    if (UnderWine()) {
        typedef char*(__cdecl * UnixNameFn)(const wchar_t*);
        HMODULE kernel = GetModuleHandleW(L"kernel32.dll");
        UnixNameFn get = kernel ? (UnixNameFn)(void*)GetProcAddress(kernel, "wine_get_unix_file_name") : nullptr;
        char* name = get ? get(path.c_str()) : nullptr;
        if (name) {
            std::wstring text = FromUtf8(name);
            HeapFree(GetProcessHeap(), 0, name);
            if (!text.empty()) {
                return text;
            }
        }
    }
    return path;
}

/* a value of a web address: everything but letters, digits and -_.~ as %XX of its UTF-8 */
std::wstring UrlValue(const std::wstring& text)
{
    static const wchar_t kHex[] = L"0123456789ABCDEF";
    std::wstring out;
    for (unsigned char c : ToUtf8(text)) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' ||
            c == '_' || c == '.' || c == '~') {
            out += (wchar_t)c;
        } else {
            out += L'%';
            out += kHex[c >> 4];
            out += kHex[c & 15];
        }
    }
    return out;
}

/* The "Report a problem..." button. */
void RunReport(HWND window, const std::wstring& game)
{
    if (!IsGameDir(game)) {
        MessageBoxW(window, Tr(T_NOT_GAME), kTitle, MB_ICONERROR);
        return;
    }
    HCURSOR before = SetCursor(LoadCursorW(0, (LPCWSTR)IDC_WAIT));
    std::wstring path;
    ReportFacts facts;
    bool ok = SaveReport(game, &path, &facts);
    SetCursor(before);
    std::wstring shown = ShownPath(path);
    if (!ok) {
        MessageBoxW(window, Tr(T_REPORT_FAILED, shown).c_str(), kTitle, MB_ICONERROR);
        return;
    }
    CopyToClipboard(window, shown);
    std::wstring done = Tr(T_REPORT_DONE, shown, facts.partly ? Tr(T_REPORT_PARTLY) : L"");
    if (MessageBoxW(window, done.c_str(), kTitle, MB_ICONINFORMATION | MB_YESNO) != IDYES) {
        return;
    }
    std::wstring page = std::wstring(kReportPage) + kReportForm + L"&version=" + UrlValue(facts.version) +
                        L"&system=" + UrlValue(facts.system) + L"&graphics=" + UrlValue(facts.graphics);
    if ((INT_PTR)ShellExecuteW(window, L"open", page.c_str(), 0, 0, SW_SHOWNORMAL) <= 32) {
        MessageBoxW(window, Tr(T_REPORT_PAGE, kReportPage).c_str(), kTitle, MB_ICONINFORMATION);
    }
}

/* ---------------- window ---------------- */

enum {
    ID_FOLDER = 100,
    ID_BROWSE,
    ID_INSTALL,
    ID_UNINSTALL,
    ID_EXIT,
    ID_STATUS,
    ID_DIAGNOSTICS,
    ID_REPORT
};

HWND g_folder;
HWND g_status;
HWND g_diagnostics;
HWND g_install;
HWND g_uninstall;
/* the folder the diagnostics checkbox was last read for: the box shows that folder's
   wiz8ws.ini value and is not reset while the player only clicks it */
std::wstring g_diagnostics_folder = L"\x01"; /* never a folder: the first update reads it */
HFONT g_font;
int g_dpi = 96;
/* the game folders found (FindGames), in the folder list's order */
std::vector<Candidate> g_games;

int Dpi(int value)
{
    return MulDiv(value, g_dpi, 96);
}

/* The folder in the folder box. Under Wine also as a player pastes it from Linux: in quotes,
   as a Linux path or "~/...", or the path of Wiz8.exe itself (NormalizeTypedFolder); the box
   keeps the text as typed. */
std::wstring FolderText()
{
    wchar_t buffer[MAX_PATH * 2];
    GetWindowTextW(g_folder, buffer, MAX_PATH * 2);
    return UnderWine() ? NormalizeTypedFolder(buffer) : std::wstring(buffer);
}

/* Under Wine: the manifest lists binkw32.dll (the binkw32 route was set up), but the file is not
   ours any more: a store's file check (Steam, GOG Galaxy, Heroic) put the original back. */
bool BinkRestored(const std::wstring& game)
{
    for (const std::wstring& line : ReadLines(Join(game, kManifest))) {
        if (lstrcmpiW(line.c_str(), kBink) == 0) {
            return !IsOurVersionDll(Join(game, kBink));
        }
    }
    return false;
}

/* The status box's line under Wine: "Found by: <source> - <verdict>" */
std::wstring FoundByText(const Candidate& game)
{
    Text verdict = game.verdict == VERDICT_THIS        ? T_VERDICT_THIS
                   : game.verdict == VERDICT_OTHER       ? T_VERDICT_OTHER
                   : game.verdict == VERDICT_NOT_CREATED ? T_VERDICT_NOT_CREATED
                                                         : T_VERDICT_UNKNOWN;
    return Tr(T_FOUND_BY, SourceName(game), Tr(verdict));
}

/* reread: after an install or uninstall, when the folder's file has changed */
void UpdateStatus(bool reread = false)
{
    bool wine = UnderWine();
    std::wstring game = FolderText();
    /* the diagnostics checkbox shows what the folder has now (off for a fresh install); the
       install keeps whatever the player leaves it at */
    std::wstring trimmed = TrimSlashes(game);
    if (reread || lstrcmpiW(trimmed.c_str(), g_diagnostics_folder.c_str()) != 0) {
        g_diagnostics_folder = trimmed;
        bool on = IsGameDir(trimmed) && DiagnosticsOn(trimmed);
        SendMessageW(g_diagnostics, BM_SETCHECK, on ? BST_CHECKED : BST_UNCHECKED, 0);
    }
    std::wstring status;
    std::wstring installed = IsGameDir(game) ? InstalledVersion(game) : std::wstring();
    int order = installed.empty() ? 0 : CompareVersions(installed, kVersion);
    bool newer_format = !installed.empty() && IsNewerFormat(game);
    if (IsGameDir(game)) {
        status = installed.empty()                 ? Tr(T_STATUS_NOT_INSTALLED)
                 : newer_format                    ? Tr(T_STATUS_NEWER_FORMAT, installed, installed)
                 : order > 0                       ? Tr(T_STATUS_NEWER, installed, kVersion)
                 : wine && BinkRestored(game)      ? Tr(T_STATUS_RESTORED, installed)
                                                   : Tr(T_STATUS_INSTALLED, installed);
        status += L"\r\n";
        status += lstrcmpiW(Sha256(Join(game, L"Wiz8.exe")).c_str(), kExeSha256) == 0
                      ? Tr(T_STATUS_OK_EXE)
                      : Tr(T_STATUS_OTHER_EXE);
        /* under Wine, for a folder found by a launcher: by which, and whether it runs here */
        Candidate where = wine ? FindCandidate(g_games, game) : Candidate();
        if (where.source != SOURCE_TYPED) {
            status += L"\r\n" + FoundByText(where);
        }
    } else if (!game.empty()) {
        status = Tr(T_NOT_GAME);
    } else {
        status = Tr(wine ? T_NOT_FOUND_WINE : T_NOT_FOUND);
    }
    SetWindowTextW(g_status, status.c_str());
    /* over an older version: "Update X -> Y"; the same one: "Reinstall"; a newer one:
       "Roll back X -> Y"; nothing: "Install". An install this installer cannot undo: both
       buttons off, the status line says which installer to use. */
    std::wstring action = Tr(T_INSTALL);
    if (!installed.empty()) {
        action = order == 0 ? std::wstring(Tr(T_REINSTALL))
                 : order < 0 ? Tr(T_UPDATE, installed, kVersion)
                             : Tr(T_ROLLBACK, installed, kVersion);
    }
    SetWindowTextW(g_install, action.c_str());
    EnableWindow(g_install, !newer_format);
    EnableWindow(g_diagnostics, !newer_format);
    EnableWindow(g_uninstall, !installed.empty() && !newer_format);
}

/* The folder dialog's callback: once it is open, it goes to the folder in start (lParam) */
int CALLBACK BrowseStart(HWND dialog, UINT message, LPARAM, LPARAM start)
{
    if (message == BFFM_INITIALIZED && start) {
        SendMessageW(dialog, BFFM_SETSELECTIONW, TRUE, start);
    }
    return 0;
}

std::wstring BrowseFolder(HWND owner)
{
    BROWSEINFOW info = {};
    info.hwndOwner = owner;
    info.lpszTitle = Tr(T_PICK_FOLDER);
    info.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE;
    /* under Wine it starts in the Linux home folder, below which the game usually is (Wine's
       dialog would start at "My Computer", and it does not show hidden folders such as
       ~/.local, so typing or pasting the path is the way there) */
    std::wstring home = UnderWine() ? HomeFolder() : std::wstring();
    if (!home.empty()) {
        info.lpfn = BrowseStart;
        info.lParam = (LPARAM)home.c_str();
    }
    LPITEMIDLIST list = SHBrowseForFolderW(&info);
    std::wstring result;
    if (list) {
        wchar_t path[MAX_PATH];
        if (SHGetPathFromIDListW(list, path)) {
            result = path;
        }
        CoTaskMemFree(list);
    }
    return result;
}

void RunAction(HWND window, bool install)
{
    std::wstring game = TrimSlashes(FolderText());
    if (!IsGameDir(game)) {
        MessageBoxW(window, Tr(T_NOT_GAME), kTitle, MB_ICONERROR);
        return;
    }
    bool diagnostics = SendMessageW(g_diagnostics, BM_GETCHECK, 0, 0) == BST_CHECKED;
    if (!CanWrite(game)) {
        RelaunchElevated(window, game, install ? L"--install" : L"--uninstall",
                         install ? (diagnostics ? L"--diagnostics" : L"--no-diagnostics") : 0);
    } else if (install) {
        Install(window, game, diagnostics ? 1 : 0,
                UnderWine() ? FindCandidate(g_games, game) : Candidate());
    } else {
        Uninstall(window, game, false);
    }
    UpdateStatus(true);
}

HWND AddControl(HWND parent, const wchar_t* cls, const wchar_t* text, DWORD style, int x, int y,
                int w, int h, int id)
{
    HWND control = CreateWindowExW(0, cls, text, WS_CHILD | WS_VISIBLE | style, Dpi(x), Dpi(y), Dpi(w), Dpi(h), parent,
                                   (HMENU)(INT_PTR)id, GetModuleHandleW(0), 0);
    SendMessageW(control, WM_SETFONT, (WPARAM)g_font, TRUE);
    return control;
}

LRESULT CALLBACK WindowProc(HWND window, UINT message, WPARAM wparam, LPARAM lparam)
{
    switch (message) {
    case WM_CREATE: {
        NONCLIENTMETRICSW metrics = {};
        metrics.cbSize = sizeof(metrics);
        SystemParametersInfoW(SPI_GETNONCLIENTMETRICS, sizeof(metrics), &metrics, 0);
        g_font = CreateFontIndirectW(&metrics.lfMessageFont);
        /* under Wine the status box has a third line ("Found by"), and what is below it moves
           down by one line (the window is taller by as much, see wWinMain) */
        int more = UnderWine() ? 16 : 0;
        AddControl(window, L"STATIC", Tr(T_INTRO), 0, 16, 14, 548, 36, 0);
        AddControl(window, L"STATIC", Tr(T_FOLDER), 0, 16, 58, 548, 18, 0);
        g_folder = AddControl(window, L"COMBOBOX", L"", CBS_DROPDOWN | CBS_AUTOHSCROLL | WS_VSCROLL |
                                                          WS_TABSTOP,
                              16, 78, 440, 200, ID_FOLDER);
        AddControl(window, L"BUTTON", Tr(T_BROWSE), BS_PUSHBUTTON | WS_TABSTOP, 464, 77, 100, 26,
                   ID_BROWSE);
        g_status = AddControl(window, L"STATIC", L"", 0, 16, 112, 548, 50 + more, ID_STATUS);
        /* [Debug] Diagnostics of wiz8ws.ini (the README explains it) */
        g_diagnostics = AddControl(window, L"BUTTON", Tr(T_DIAGNOSTICS), BS_AUTOCHECKBOX | WS_TABSTOP,
                                   16, 166 + more, 372, 22, ID_DIAGNOSTICS);
        /* on the same line, at the right: the report file for a bug report (see "report") */
        AddControl(window, L"BUTTON", Tr(T_REPORT), BS_PUSHBUTTON | WS_TABSTOP, 396, 164 + more, 168, 26,
                   ID_REPORT);
        g_install = AddControl(window, L"BUTTON", Tr(T_INSTALL), BS_DEFPUSHBUTTON | WS_TABSTOP, 16,
                               198 + more, 210, 32, ID_INSTALL);
        g_uninstall = AddControl(window, L"BUTTON", Tr(T_UNINSTALL), BS_PUSHBUTTON | WS_TABSTOP,
                                 236, 198 + more, 160, 32, ID_UNINSTALL);
        AddControl(window, L"BUTTON", Tr(T_EXIT), BS_PUSHBUTTON | WS_TABSTOP, 464, 198 + more, 100, 32,
                   ID_EXIT);
        g_games = FindGames();
        /* preselected: the first game that runs in this Wine prefix (where the installer can set
           everything up), otherwise the first found */
        int selected = 0;
        for (size_t i = 0; i < g_games.size(); ++i) {
            SendMessageW(g_folder, CB_ADDSTRING, 0, (LPARAM)g_games[i].folder.c_str());
            if (g_games[i].verdict == VERDICT_THIS && g_games[selected].verdict != VERDICT_THIS) {
                selected = (int)i;
            }
        }
        if (!g_games.empty()) {
            SendMessageW(g_folder, CB_SETCURSEL, selected, 0);
        }
        UpdateStatus();
        return 0;
    }
    case WM_COMMAND:
        switch (LOWORD(wparam)) {
        case ID_FOLDER:
            if (HIWORD(wparam) == CBN_SELCHANGE) {
                int index = (int)SendMessageW(g_folder, CB_GETCURSEL, 0, 0);
                wchar_t text[MAX_PATH * 2];
                SendMessageW(g_folder, CB_GETLBTEXT, index, (LPARAM)text);
                SetWindowTextW(g_folder, text);
                UpdateStatus();
            } else if (HIWORD(wparam) == CBN_EDITCHANGE) {
                UpdateStatus();
            }
            return 0;
        case ID_BROWSE: {
            std::wstring dir = BrowseFolder(window);
            if (!dir.empty()) {
                SetWindowTextW(g_folder, dir.c_str());
                UpdateStatus();
            }
            return 0;
        }
        case ID_INSTALL:
            RunAction(window, true);
            return 0;
        case ID_UNINSTALL:
            RunAction(window, false);
            return 0;
        case ID_REPORT:
            RunReport(window, TrimSlashes(FolderText()));
            return 0;
        case ID_EXIT:
            DestroyWindow(window);
            return 0;
        }
        break;
    case WM_CTLCOLORSTATIC:
        SetBkMode((HDC)wparam, TRANSPARENT);
        return (LRESULT)GetSysColorBrush(COLOR_WINDOW);
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(window, message, wparam, lparam);
}

} // namespace

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int show)
{
    PickLanguage();
    CoInitializeEx(0, COINIT_APARTMENTTHREADED);

    /* restart with rights, or a run without the window:
       Wiz8WideSetup.exe --install|--uninstall "folder" [--diagnostics|--no-diagnostics]
       (the diagnostics switch only matters for --install; without it the installed value is
       kept, a fresh install gets it off), or
       Wiz8WideSetup.exe --report "folder" ["file.zip"] (the report file of "Report a problem...";
       without a file name it goes to the Desktop) */
    int argc = 0;
    LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (argv && argc >= 3) {
        std::wstring action = argv[1];
        /* a full path from here on; under Wine the folder may also be given as a Linux path */
        std::wstring game = CommandLineFolder(argv[2]);
        if (action == L"--report") {
            /* --report "folder" ["file.zip"]: the report file, no window and no question */
            std::wstring file = argc >= 4 ? argv[3] : L"";
            bool extra = argc > 4;
            LocalFree(argv);
            if (extra) {
                return 2;
            }
            if (!file.empty() && file[0] == L'/') {
                file = FromUnix(ToUtf8(file)); /* under Wine also as a Linux path */
            }
            ReportFacts facts;
            return SaveReport(game, &file, &facts) ? 0 : 1;
        }
        int diagnostics = -1;
        bool bad = false;
        for (int i = 3; i < argc; ++i) {
            std::wstring option = argv[i];
            if (option == L"--diagnostics") {
                diagnostics = 1;
            } else if (option == L"--no-diagnostics") {
                diagnostics = 0;
            } else {
                bad = true;
            }
        }
        LocalFree(argv);
        if (bad) {
            return 2;
        }
        if (action == L"--install") {
            /* under Wine a folder the launchers list gets its verdict; any other is unknown */
            Candidate where = UnderWine() ? FindCandidate(FindGames(), game) : Candidate();
            return Install(0, game, diagnostics, where) == RES_OK ? 0 : 1;
        }
        if (action == L"--uninstall") {
            return Uninstall(0, game, false) == RES_OK ? 0 : 1;
        }
        return 2;
    }
    if (argv) {
        LocalFree(argv);
    }

    INITCOMMONCONTROLSEX controls = {sizeof(controls), ICC_STANDARD_CLASSES};
    InitCommonControlsEx(&controls);
    WNDCLASSW cls = {};
    cls.lpfnWndProc = WindowProc;
    cls.hInstance = instance;
    cls.hCursor = LoadCursorW(0, (LPCWSTR)IDC_ARROW);
    cls.hbrBackground = GetSysColorBrush(COLOR_WINDOW);
    cls.hIcon = LoadIconW(instance, MAKEINTRESOURCEW(1));
    cls.lpszClassName = L"Wiz8WideSetup";
    RegisterClassW(&cls);
    HDC screen = GetDC(0);
    g_dpi = GetDeviceCaps(screen, LOGPIXELSY);
    ReleaseDC(0, screen);
    RECT rect = {0, 0, Dpi(580), Dpi(UnderWine() ? 262 : 246)}; /* see WM_CREATE */
    DWORD style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX;
    AdjustWindowRect(&rect, style, FALSE);
    HWND window = CreateWindowW(L"Wiz8WideSetup", kTitle, style, CW_USEDEFAULT, CW_USEDEFAULT,
                                rect.right - rect.left, rect.bottom - rect.top, 0, 0, instance, 0);
    ShowWindow(window, show);
    MSG message;
    while (GetMessageW(&message, 0, 0, 0)) {
        if (!IsDialogMessageW(window, &message)) {
            TranslateMessage(&message);
            DispatchMessageW(&message);
        }
    }
    return 0;
}
