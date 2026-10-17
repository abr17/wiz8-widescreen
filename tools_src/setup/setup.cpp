// Wiz8WideSetup.exe - installer of the Wizardry 8 widescreen patch (hybrid).
//
// Next to the exe there is a "files" folder with the patch contents (what goes into the
// game folder). The installer:
//   - finds the game: GOG (registry), Steam (libraryfolders.vdf), or a folder picked by hand;
//   - checks Wiz8.exe by SHA-256 (GOG/Steam 1.2.4); another version only gets a
//     warning (owner's decision: "at your own risk");
//   - does not touch a foreign version.dll (another mod) - warns and exits;
//   - before installing, saves what will be replaced into Wiz8Wide.backup\,
//     the list of installed files into Wiz8Wide.installed.txt; uninstalling returns
//     the game folder to its original state;
//   - asks for administrator rights only if the game folder is not writable
//     (Program Files) - restarts itself via runas.
// Window language follows the Windows language: Russian, German, French, otherwise English.
//
// Build: tools_src\setup\build.ps1 (llvm-mingw, i686, static, no dependencies).

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

#include <string>
#include <vector>
#include <algorithm>

namespace {

const wchar_t kTitle[] = L"Wizardry 8 Widescreen";
const wchar_t kExeSha256[] = L"18A74FF61C65B8A2D4CFA11FFCE82AD7FEF022A94EAF0C2F217E479E981420D2";
const wchar_t kManifest[] = L"Wiz8Wide.installed.txt";
const wchar_t kBackupDir[] = L"Wiz8Wide.backup";
const wchar_t kGogId[] = L"1207659230";

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
    T_STATUS_INSTALLED,
    T_STATUS_NOT_INSTALLED,
    T_STATUS_OK_EXE,
    T_STATUS_OTHER_EXE,
    T_PICK_FOLDER,
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
    L"The widescreen patch is installed.\n\nStart the game as usual. Display mode, resolution and "
    L"view distance are in Options - Video.",
    L"The widescreen patch was removed. The game folder is as it was before.",
    L"The patch is not installed in this folder.",
    L"Could not copy a file:\n%s\n\nNothing was left half-installed; the previous state was restored.",
    L"The \"files\" folder next to the installer is missing. Unpack the whole archive first.",
    L"Status: the patch is installed.",
    L"Status: the patch is not installed.",
    L"Wiz8.exe: version 1.2.4 (tested).",
    L"Wiz8.exe: unknown version (not tested).",
    L"Choose the Wizardry 8 folder (the one with Wiz8.exe):",
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
    L"Широкоэкранный патч установлен.\n\nЗапускайте игру как обычно. Режим экрана, разрешение и "
    L"дальность прорисовки - в Опциях, раздел «Видео».",
    L"Широкоэкранный патч удалён. Папка игры - как была до установки.",
    L"В этой папке патч не установлен.",
    L"Не удалось скопировать файл:\n%s\n\nНичего не осталось наполовину: прежнее состояние "
    L"восстановлено.",
    L"Рядом с установщиком нет папки \"files\". Сначала распакуйте архив целиком.",
    L"Состояние: патч установлен.",
    L"Состояние: патч не установлен.",
    L"Wiz8.exe: версия 1.2.4 (проверена).",
    L"Wiz8.exe: неизвестная версия (не проверялась).",
    L"Выберите папку Wizardry 8 (ту, где лежит Wiz8.exe):",
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
    L"Der Breitbild-Patch ist installiert.\n\nStarten Sie das Spiel wie gewohnt. Anzeigemodus, "
    L"Aufl\x00f6sung und Sichtweite finden Sie unter Optionen - Video.",
    L"Der Breitbild-Patch wurde entfernt. Der Spielordner ist wie vorher.",
    L"Der Patch ist in diesem Ordner nicht installiert.",
    L"Eine Datei konnte nicht kopiert werden:\n%s\n\nEs blieb nichts halb installiert; der "
    L"vorherige Zustand wurde wiederhergestellt.",
    L"Der Ordner \"files\" neben dem Installer fehlt. Bitte zuerst das ganze Archiv entpacken.",
    L"Status: Der Patch ist installiert.",
    L"Status: Der Patch ist nicht installiert.",
    L"Wiz8.exe: Version 1.2.4 (getestet).",
    L"Wiz8.exe: unbekannte Version (nicht getestet).",
    L"W\x00e4hlen Sie den Ordner von Wizardry 8 (mit Wiz8.exe):",
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
    L"Le patch \x00e9" L"cran large est install\x00e9.\n\nLancez le jeu comme d'habitude. Mode "
    L"d'affichage, r\x00e9solution et distance de vue : Options - Vid\x00e9o.",
    L"Le patch \x00e9" L"cran large a \x00e9t\x00e9 retir\x00e9. Le dossier du jeu est comme avant.",
    L"Le patch n'est pas install\x00e9 dans ce dossier.",
    L"Impossible de copier un fichier :\n%s\n\nRien n'est rest\x00e9 \x00e0 moiti\x00e9 install\x00e9 ; "
    L"l'\x00e9tat pr\x00e9" L"c\x00e9" L"dent a \x00e9t\x00e9 restaur\x00e9.",
    L"Le dossier \"files\" est absent \x00e0 c\x00f4t\x00e9 de l'installateur. D\x00e9" L"compressez "
    L"d'abord toute l'archive.",
    L"\x00c9tat : le patch est install\x00e9.",
    L"\x00c9tat : le patch n'est pas install\x00e9.",
    L"Wiz8.exe : version 1.2.4 (test\x00e9" L"e).",
    L"Wiz8.exe : version inconnue (non test\x00e9" L"e).",
    L"Choisissez le dossier de Wizardry 8 (celui avec Wiz8.exe) :",
};

const wchar_t* const* g_text = kEnglish;

const wchar_t* Tr(Text t)
{
    return g_text[t];
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

std::wstring ExeDir()
{
    wchar_t path[MAX_PATH];
    GetModuleFileNameW(0, path, MAX_PATH);
    std::wstring s = path;
    return s.substr(0, s.find_last_of(L'\\'));
}

bool IsGameDir(const std::wstring& dir)
{
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
        buffer[MAX_PATH * 2 - 1] = 0;
        result = buffer;
    }
    RegCloseKey(handle);
    return result;
}

void AddCandidate(std::vector<std::wstring>* out, std::wstring dir)
{
    for (wchar_t& c : dir) {
        if (c == L'/') {
            c = L'\\';
        }
    }
    while (!dir.empty() && dir.back() == L'\\') {
        dir.pop_back();
    }
    if (!IsGameDir(dir)) {
        return;
    }
    for (const std::wstring& known : *out) {
        if (lstrcmpiW(known.c_str(), dir.c_str()) == 0) {
            return;
        }
    }
    out->push_back(dir);
}

/* Steam: steamapps\libraryfolders.vdf - lines "path" "D:\\SteamLibrary". */
void FindSteam(std::vector<std::wstring>* out)
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
        AddCandidate(out, Join(library, L"steamapps\\common\\Wizardry8"));
        AddCandidate(out, Join(library, L"steamapps\\common\\Wizardry 8"));
    }
}

std::vector<std::wstring> FindGames()
{
    std::vector<std::wstring> found;
    std::wstring gog_key = std::wstring(L"SOFTWARE\\GOG.com\\Games\\") + kGogId;
    AddCandidate(&found, RegString(HKEY_LOCAL_MACHINE, gog_key.c_str(), L"path", KEY_WOW64_32KEY));
    AddCandidate(&found, RegString(HKEY_LOCAL_MACHINE, gog_key.c_str(), L"path", KEY_WOW64_64KEY));
    FindSteam(&found);
    return found;
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

bool IsInstalled(const std::wstring& game)
{
    return FileExists(Join(game, kManifest));
}

/* Remove what was installed and restore what was saved (both on uninstall and on rollback). */
void RemoveInstalled(const std::wstring& game, const std::vector<std::wstring>& installed)
{
    std::wstring backup = Join(game, kBackupDir);
    for (const std::wstring& rel : installed) {
        if (rel[0] == L'+') {
            continue; /* folder, see below */
        }
        std::wstring dst = Join(game, rel);
        SetFileAttributesW(dst.c_str(), FILE_ATTRIBUTE_NORMAL);
        DeleteFileW(dst.c_str());
        std::wstring saved = Join(backup, rel);
        if (FileExists(saved)) {
            CreateDirs(dst.substr(0, dst.find_last_of(L'\\')));
            MoveFileExW(saved.c_str(), dst.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_COPY_ALLOWED);
        }
    }
    /* folders: in Wiz8Wide.backup - all of them (they are ours), in the game - only those
       created by the installation ("+folder" in the list) and only if they became empty */
    std::vector<std::wstring> dirs;
    for (const std::wstring& rel : installed) {
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
}

Result Uninstall(HWND owner, const std::wstring& game, bool quiet)
{
    std::vector<std::wstring> installed = ReadLines(Join(game, kManifest));
    if (installed.empty()) {
        if (!quiet) {
            MessageBoxW(owner, Tr(T_NOTHING_TO_UNINSTALL), kTitle, MB_ICONINFORMATION);
        }
        return RES_CANCELLED;
    }
    RemoveInstalled(game, installed);
    DeleteFileW(Join(game, kManifest).c_str());
    /* logs written by the patch itself */
    for (const wchar_t* log : {L"wiz8ws.log", L"wiz8hy.log", L"wiz8wide.log"}) {
        DeleteFileW(Join(game, log).c_str());
    }
    if (!quiet) {
        MessageBoxW(owner, Tr(T_DONE_UNINSTALL), kTitle, MB_ICONINFORMATION);
    }
    return RES_OK;
}


Result Install(HWND owner, const std::wstring& game)
{
    std::wstring files = Join(ExeDir(), L"files");
    if (!DirExists(files)) {
        MessageBoxW(owner, Tr(T_NO_FILES), kTitle, MB_ICONERROR);
        return RES_FAILED;
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
    if (lstrcmpiW(Sha256(Join(game, L"Wiz8.exe")).c_str(), kExeSha256) != 0 &&
        MessageBoxW(owner, Tr(T_UNKNOWN_EXE), kTitle, MB_ICONWARNING | MB_YESNO | MB_DEFBUTTON2) !=
            IDYES) {
        return RES_CANCELLED;
    }

    /* reinstall: first quietly remove the old install (restoring the originals), but
       keep the player's settings */
    std::wstring keep_settings;
    if (IsInstalled(game)) {
        std::wstring ini = Join(game, L"wiz8wide.ini");
        keep_settings = Join(game, L"wiz8wide.ini.keep");
        CopyFileW(ini.c_str(), keep_settings.c_str(), FALSE);
        Uninstall(owner, game, true);
    }

    std::vector<std::wstring> payload;
    ListFiles(files, L"", &payload);
    std::vector<std::wstring> installed;
    std::wstring backup = Join(game, kBackupDir);
    for (const std::wstring& rel : payload) {
        std::wstring src = Join(files, rel);
        std::wstring dst = Join(game, rel);
        if (FileExists(dst)) {
            std::wstring saved = Join(backup, rel);
            CreateDirs(saved.substr(0, saved.find_last_of(L'\\')));
            if (!CopyFileW(dst.c_str(), saved.c_str(), FALSE)) {
                goto failed_file;
            }
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
        if (!CopyFileW(src.c_str(), dst.c_str(), FALSE)) {
            goto failed_file;
        }
        installed.push_back(rel);
        continue;
    failed_file: {
        wchar_t text[1024];
        wsprintfW(text, Tr(T_COPY_FAILED), dst.c_str());
        RemoveInstalled(game, installed);
        MessageBoxW(owner, text, kTitle, MB_ICONERROR);
        return RES_FAILED;
    }
    }
    /* the game rewrites 3DVideo.CFG itself (DirectX7, chosen resolution) -
       save the original so that uninstall restores it */
    std::wstring cfg = Join(game, L"3DVideo.CFG");
    if (FileExists(cfg)) {
        std::wstring saved = Join(backup, L"3DVideo.CFG");
        CreateDirs(backup);
        if (CopyFileW(cfg.c_str(), saved.c_str(), FALSE)) {
            installed.push_back(L"3DVideo.CFG");
        }
    }
    if (!keep_settings.empty()) {
        CopyFileW(keep_settings.c_str(), Join(game, L"wiz8wide.ini").c_str(), FALSE);
        DeleteFileW(keep_settings.c_str());
    }
    if (!WriteLines(Join(game, kManifest), installed)) {
        RemoveInstalled(game, installed);
        wchar_t text[1024];
        wsprintfW(text, Tr(T_COPY_FAILED), Join(game, kManifest).c_str());
        MessageBoxW(owner, text, kTitle, MB_ICONERROR);
        return RES_FAILED;
    }
    MessageBoxW(owner, Tr(T_DONE_INSTALL), kTitle, MB_ICONINFORMATION);
    return RES_OK;
}

/* Restart itself with administrator rights for this folder and action. */
bool RelaunchElevated(HWND owner, const std::wstring& game, const wchar_t* action)
{
    wchar_t exe[MAX_PATH];
    GetModuleFileNameW(0, exe, MAX_PATH);
    std::wstring args = std::wstring(action) + L" \"" + game + L"\"";
    SHELLEXECUTEINFOW info = {};
    info.cbSize = sizeof(info);
    info.fMask = SEE_MASK_NOCLOSEPROCESS;
    info.hwnd = owner;
    info.lpVerb = L"runas";
    info.lpFile = exe;
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

/* ---------------- window ---------------- */

enum {
    ID_FOLDER = 100,
    ID_BROWSE,
    ID_INSTALL,
    ID_UNINSTALL,
    ID_EXIT,
    ID_STATUS
};

HWND g_folder;
HWND g_status;
HWND g_uninstall;
HFONT g_font;
int g_dpi = 96;

int Dpi(int value)
{
    return MulDiv(value, g_dpi, 96);
}

void UpdateStatus()
{
    wchar_t buffer[MAX_PATH * 2];
    GetWindowTextW(g_folder, buffer, MAX_PATH * 2);
    std::wstring game = buffer;
    std::wstring status;
    if (IsGameDir(game)) {
        status = IsInstalled(game) ? Tr(T_STATUS_INSTALLED) : Tr(T_STATUS_NOT_INSTALLED);
        status += L"\r\n";
        status += lstrcmpiW(Sha256(Join(game, L"Wiz8.exe")).c_str(), kExeSha256) == 0
                      ? Tr(T_STATUS_OK_EXE)
                      : Tr(T_STATUS_OTHER_EXE);
    } else if (!game.empty()) {
        status = Tr(T_NOT_GAME);
    } else {
        status = Tr(T_NOT_FOUND);
    }
    SetWindowTextW(g_status, status.c_str());
    EnableWindow(g_uninstall, IsGameDir(game) && IsInstalled(game));
}

std::wstring BrowseFolder(HWND owner)
{
    BROWSEINFOW info = {};
    info.hwndOwner = owner;
    info.lpszTitle = Tr(T_PICK_FOLDER);
    info.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE;
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
    wchar_t buffer[MAX_PATH * 2];
    GetWindowTextW(g_folder, buffer, MAX_PATH * 2);
    std::wstring game = buffer;
    if (!IsGameDir(game)) {
        MessageBoxW(window, Tr(T_NOT_GAME), kTitle, MB_ICONERROR);
        return;
    }
    if (!CanWrite(game)) {
        RelaunchElevated(window, game, install ? L"--install" : L"--uninstall");
    } else if (install) {
        Install(window, game);
    } else {
        Uninstall(window, game, false);
    }
    UpdateStatus();
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
        AddControl(window, L"STATIC", Tr(T_INTRO), 0, 16, 14, 548, 36, 0);
        AddControl(window, L"STATIC", Tr(T_FOLDER), 0, 16, 58, 548, 18, 0);
        g_folder = AddControl(window, L"COMBOBOX", L"", CBS_DROPDOWN | CBS_AUTOHSCROLL | WS_VSCROLL |
                                                          WS_TABSTOP,
                              16, 78, 440, 200, ID_FOLDER);
        AddControl(window, L"BUTTON", Tr(T_BROWSE), BS_PUSHBUTTON | WS_TABSTOP, 464, 77, 100, 26,
                   ID_BROWSE);
        g_status = AddControl(window, L"STATIC", L"", 0, 16, 114, 548, 40, ID_STATUS);
        AddControl(window, L"BUTTON", Tr(T_INSTALL), BS_DEFPUSHBUTTON | WS_TABSTOP, 16, 166, 160,
                   32, ID_INSTALL);
        g_uninstall = AddControl(window, L"BUTTON", Tr(T_UNINSTALL), BS_PUSHBUTTON | WS_TABSTOP,
                                 186, 166, 160, 32, ID_UNINSTALL);
        AddControl(window, L"BUTTON", Tr(T_EXIT), BS_PUSHBUTTON | WS_TABSTOP, 464, 166, 100, 32,
                   ID_EXIT);
        std::vector<std::wstring> games = FindGames();
        for (const std::wstring& game : games) {
            SendMessageW(g_folder, CB_ADDSTRING, 0, (LPARAM)game.c_str());
        }
        if (!games.empty()) {
            SendMessageW(g_folder, CB_SETCURSEL, 0, 0);
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

    /* restart with rights: Wiz8WideSetup.exe --install|--uninstall "folder" */
    int argc = 0;
    LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (argv && argc >= 3) {
        std::wstring action = argv[1];
        std::wstring game = argv[2];
        LocalFree(argv);
        if (action == L"--install") {
            return Install(0, game) == RES_OK ? 0 : 1;
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
    RECT rect = {0, 0, Dpi(580), Dpi(214)};
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
