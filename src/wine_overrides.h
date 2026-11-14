#pragma once

// The patch's Wine settings (Linux, Steam Deck; Proton is Wine), shared by the installer
// (tools_src/setup/setup.cpp) and the patch DLL, so that both read and write the same values and
// notes in the same format: one program's notes must be understood by the other.
//
// Wine, and Proton (Valve's Wine), load their own version.dll and ddraw.dll instead of the files
// in the game folder unless told otherwise, so the patch would silently not start
// (docs/loader.md). The setting that tells Wine, for Wiz8.exe only, is
// HKCU\Software\Wine\AppDefaults\Wiz8.exe\DllOverrides: "*version" = "native,builtin" (game
// folder first, then Wine's own) and "*ddraw" = "builtin": dgVoodoo's DDraw.dll crashes under
// Wine, so Wine's own ddraw must stay even when a global setting (a Bottles component) says
// otherwise. For a game-folder DLL Wine reads the "*" names before the plain ones, also before
// those of the global DllOverrides key, where winecfg and winetricks write theirs. For a DLL
// that it takes from its own system folder (ddraw.dll when the game folder has no DDraw.dll, as
// after an install under Wine) a 32-bit prefix reads the plain name first, so there a global
// "ddraw" would win over the per-program "*ddraw": in a 32-bit prefix a per-program plain
// "ddraw" = "builtin" is written too (PlainDdrawToo), which Wine reads before the global one
// (and before a "*ddraw" in WINEDLLOVERRIDES, so an experiment with a ddraw.dll in that folder
// then needs "ddraw=n,b"). A setting of the player's that keeps the patch from working is
// reported, not changed (WineOrderOk).
// These keys belong to one Wine prefix (the one the program runs in), and Wine reads them when a
// program starts, so a value written now counts from the next start of Wiz8.exe.
//
// One prefix can hold several patched game folders (GOG and Steam, a copy), and all of them use
// the same values, so the notes are kept in the prefix, not in a folder's manifest:
// HKCU\Software\Wiz8Wide\Wine lists the values that were created (value name = the name written,
// data = the text written), ...\Wine\Folders the game folders that use them (one empty value per
// folder, named by WineFolderName). The values are removed only when no listed folder needs them
// any more, and only if they are still as they were written. A value that was already there and
// not created this way (the player's own setting) is never changed.
//
// Header only: every function is "inline", which lets each .cpp file that includes this one use
// it without another .cpp to compile and link. The names live in "namespace wine": a file uses
// them as wine::UnderWine(), or writes "using namespace wine;" once and then UnderWine(). On
// Windows nothing here changes anything: callers check UnderWine() before they write.

#include <windows.h>

#include <initializer_list>
#include <string>
#include <vector>

namespace wine {

constexpr wchar_t kWineKey[] = L"Software\\Wine\\AppDefaults\\Wiz8.exe\\DllOverrides";
constexpr wchar_t kWineAppKey[] = L"Software\\Wine\\AppDefaults\\Wiz8.exe";
constexpr wchar_t kWineGlobalKey[] = L"Software\\Wine\\DllOverrides";
constexpr wchar_t kOwnRoot[] = L"Software\\Wiz8Wide";
constexpr wchar_t kOwnKey[] = L"Software\\Wiz8Wide\\Wine";
constexpr wchar_t kFoldersKey[] = L"Software\\Wiz8Wide\\Wine\\Folders";
struct WineDll {
    const wchar_t* name; /* the "*" form */
    const wchar_t* order;
};
constexpr WineDll kWineDlls[] = {{L"*version", L"native,builtin"}, {L"*ddraw", L"builtin"}};

/* Wine (and Proton) exports wine_get_version from its ntdll.dll; Windows does not. */
inline bool UnderWine()
{
    HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");
    return ntdll && GetProcAddress(ntdll, "wine_get_version");
}

/* Whether this 32-bit program runs in a 32-bit Wine prefix (WINEARCH=win32); in a 64-bit one,
   and in Proton's, it runs under WOW64. The prefix is the one the program runs in, so the one
   whose keys it writes. */
inline bool Prefix32()
{
    BOOL wow64 = FALSE;
    IsWow64Process(GetCurrentProcess(), &wow64);
    return !wow64;
}

/* Whether the plain name of this DLL is written as well, with the same order: only "ddraw", and
   only in a 32-bit prefix, where Wine looks its own system ddraw.dll up as plain "ddraw" first
   (WineOrderOk), so that a global "ddraw" (winetricks, winecfg's Libraries page) does not win
   over Wine's own. It is written and noted together with the "*" name, under the same rule
   (neither name was there for Wiz8.exe), and only once the "*" one's note is written; one whose
   own note cannot be written is deleted again. So an uninstall finds it and removes it with the
   other values, and a note under either name says the player deleted them (KeepOne). */
inline bool PlainDdrawToo(const WineDll& dll)
{
    return lstrcmpW(dll.name + 1, L"ddraw") == 0 && Prefix32();
}

/* A value of HKCU\key, as text ("" for another type); false if there is none. */
inline bool ReadUserValue(const wchar_t* key, const wchar_t* name, std::wstring* out)
{
    HKEY handle;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, key, 0, KEY_READ, &handle) != ERROR_SUCCESS) {
        return false;
    }
    wchar_t buffer[MAX_PATH * 2] = {};
    DWORD size = sizeof(buffer) - sizeof(wchar_t);
    DWORD type = 0;
    LONG status = RegQueryValueExW(handle, name, 0, &type, (BYTE*)buffer, &size);
    RegCloseKey(handle);
    if (status != ERROR_SUCCESS && status != ERROR_MORE_DATA) {
        return false;
    }
    if (out) {
        *out = status == ERROR_SUCCESS && (type == REG_SZ || type == REG_EXPAND_SZ) ? buffer : L"";
    }
    return true;
}

/* Writes a text value into HKCU\key, creating the key if needed. false if that failed;
   GetLastError() then gives the registry's error code. */
inline bool WriteUserValue(const wchar_t* key, const wchar_t* name, const wchar_t* data)
{
    HKEY handle;
    LONG status = RegCreateKeyExW(HKEY_CURRENT_USER, key, 0, 0, 0, KEY_WRITE, 0, &handle, 0);
    if (status == ERROR_SUCCESS) {
        status = RegSetValueExW(handle, name, 0, REG_SZ, (const BYTE*)data,
                                (lstrlenW(data) + 1) * sizeof(wchar_t));
        RegCloseKey(handle);
    }
    SetLastError(status);
    return status == ERROR_SUCCESS;
}

inline void DeleteUserValue(const wchar_t* key, const wchar_t* name)
{
    HKEY handle;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, key, 0, KEY_SET_VALUE, &handle) == ERROR_SUCCESS) {
        RegDeleteValueW(handle, name);
        RegCloseKey(handle);
    }
}

/* The names of all values of HKCU\key (none if there is no such key). */
inline std::vector<std::wstring> UserValueNames(const wchar_t* key)
{
    std::vector<std::wstring> names;
    HKEY handle;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, key, 0, KEY_READ, &handle) != ERROR_SUCCESS) {
        return names;
    }
    wchar_t name[MAX_PATH * 2];
    for (DWORD i = 0;; ++i) {
        DWORD length = MAX_PATH * 2;
        if (RegEnumValueW(handle, i, name, &length, 0, 0, 0, 0) != ERROR_SUCCESS) {
            break;
        }
        names.push_back(name);
    }
    RegCloseKey(handle);
    return names;
}

/* Deletes a key of HKCU that has neither values nor subkeys. */
inline void DeleteKeyIfEmpty(const wchar_t* path)
{
    HKEY key;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, path, 0, KEY_READ, &key) != ERROR_SUCCESS) {
        return;
    }
    DWORD subkeys = 1, values = 1;
    RegQueryInfoKeyW(key, 0, 0, 0, &subkeys, 0, 0, &values, 0, 0, 0, 0);
    RegCloseKey(key);
    if (subkeys == 0 && values == 0) {
        RegDeleteKeyW(HKEY_CURRENT_USER, path);
    }
}

/* A load order as Wine reads it (parse_load_order in its ntdll\loadorder.c): the letters n
   (native, the game folder's file) and b (builtin, Wine's own) in order, "nb" for
   "native,builtin" or "n,b"; "" = the DLL is disabled. */
inline std::wstring WineOrderLetters(const std::wstring& value)
{
    std::wstring letters;
    for (size_t i = value.find_first_not_of(L", \t"); i != std::wstring::npos && letters.size() < 2;
         i = value.find_first_not_of(L", \t", value.find_first_of(L", \t", i))) {
        wchar_t c = value[i] | 0x20;
        if ((c == L'n' || c == L'b') && letters.find(c) == std::wstring::npos) {
            letters += c;
        }
    }
    return letters;
}

/* The load order Wine takes from the registry for Wiz8.exe: for each name in turn, Wiz8.exe's
   own key, then the global one; "?" when neither has any of the names (Wine's default). */
inline std::wstring WineRegistryOrder(std::initializer_list<const wchar_t*> names)
{
    for (const wchar_t* name : names) {
        std::wstring value;
        if (ReadUserValue(kWineKey, name, &value) || ReadUserValue(kWineGlobalKey, name, &value)) {
            return WineOrderLetters(value);
        }
    }
    return L"?";
}

/* Whether the game folder has a file of this DLL ("DDraw.dll" for "*ddraw", in any letter
   case). Wine looks for a DLL there before its own system folder, and which of the two it finds
   decides the names it then looks up (WineOrderOk). */
inline bool DllInFolder(const std::wstring& game, const WineDll& dll)
{
    std::wstring path = game;
    if (!path.empty() && path.back() != L'\\' && path.back() != L'/') {
        path += L'\\';
    }
    path += dll.name + 1; /* the name without its "*" */
    path += L".dll";
    DWORD attributes = GetFileAttributesW(path.c_str());
    return attributes != INVALID_FILE_ATTRIBUTES && !(attributes & FILE_ATTRIBUTE_DIRECTORY);
}

/* Whether the registry gives Wiz8.exe the load order the patch needs for this DLL; game: the
   game folder. Wine looks a DLL that it finds in the game folder up as "*version", then
   "version". One that it takes from its own system folder it looks up the same way in a 64-bit
   prefix (where this 32-bit program runs under WOW64), but plain "version" first in a 32-bit
   one: there Wine drops the system folder from the path and first asks for the name as it is
   left, so a plain value, also the global one, wins over the per-program "*" one (hence the
   per-program plain "ddraw" written there, PlainDdrawToo).
   version.dll must come from the game folder, and the patch then loads Wine's own system copy,
   so builtin has to follow in that copy's order. ddraw.dll must be Wine's own (builtin first,
   or Wine's default) in the order of the file Wine finds first: the game folder's DDraw.dll if
   there is one (the player's own: an install under Wine copies none), otherwise Wine's own in
   its system folder. */
inline bool WineOrderOk(const WineDll& dll, const std::wstring& game)
{
    const wchar_t* plain = dll.name + 1;
    std::wstring folder = WineRegistryOrder({dll.name, plain});
    std::wstring system = Prefix32() ? WineRegistryOrder({plain, dll.name}) : folder;
    if (lstrcmpW(plain, L"version") == 0) {
        return folder == L"nb" && (system == L"?" || system.find(L'b') != std::wstring::npos);
    }
    std::wstring order = DllInFolder(game, dll) ? folder : system;
    return order == L"?" || order[0] == L'b';
}

/* A module name as Wine compares it: without a final ".dll" (in any letter case), so
   "DDRAW.DLL" -> "DDRAW" (remove_dll_ext in its ntdll\loadorder.c). */
inline std::wstring WineModuleName(std::wstring name)
{
    size_t dot = name.find_last_of(L'.');
    if (dot != std::wstring::npos && lstrcmpiW(name.c_str() + dot, L".dll") == 0) {
        name.resize(dot);
    }
    return name;
}

/* The load order the WINEDLLOVERRIDES variable gives one module name ("*ddraw", "ddraw" or
   "ddraw.dll"), read the way Wine reads it at the start of a program (init_load_order in its
   ntdll\loadorder.c; the same from Wine 9 to 11 and in Proton 10): entries are split at ';', each
   is "name[,name...]=order" (the names are also split at spaces and tabs), ".dll" is dropped
   from a name, letter case does not matter, and the last entry for a name wins. "*ddraw" and
   "ddraw" are two different names to Wine: for a game-folder DLL it looks "*ddraw" up first (in
   this variable, then in the registry) and only then "ddraw", so a caller asks for each name it
   cares about. order gets the text after '=' as written (WineOrderLetters reads it); false when
   no entry names the module, or the variable is not set. */
inline bool WineEnvOrder(const wchar_t* name, std::wstring* order)
{
    DWORD size = GetEnvironmentVariableW(L"WINEDLLOVERRIDES", 0, 0);
    if (size == 0) {
        return false;
    }
    std::wstring all(size, L'\0');
    DWORD length = GetEnvironmentVariableW(L"WINEDLLOVERRIDES", &all[0], size);
    if (length == 0 || length >= size) {
        return false;
    }
    all.resize(length);
    std::wstring wanted = WineModuleName(name);
    bool found = false;
    for (size_t start = 0; start < all.size();) {
        size_t end = all.find(L';', start);
        if (end == std::wstring::npos) {
            end = all.size();
        }
        std::wstring entry = all.substr(start, end - start);
        start = end + 1;
        size_t equals = entry.find(L'=');
        if (equals == std::wstring::npos) {
            continue; /* Wine skips an entry without '=' */
        }
        std::wstring names = entry.substr(0, equals);
        for (size_t first = names.find_first_not_of(L", \t"); first != std::wstring::npos;) {
            size_t last = names.find_first_of(L", \t", first);
            std::wstring module = names.substr(first, last == std::wstring::npos ? last : last - first);
            if (lstrcmpiW(WineModuleName(module).c_str(), wanted.c_str()) == 0) {
                if (order) {
                    *order = entry.substr(equals + 1);
                }
                found = true; /* a later entry for it replaces this one */
            }
            first = last == std::wstring::npos ? last : names.find_first_not_of(L", \t", last);
        }
    }
    return found;
}

/* "D:\Games\Wizardry 8\" -> "D:\Games\Wizardry 8" (a drive root keeps its slash). A trailing
   backslash would also break the quoted folder argument of the elevated restart: \" is read
   as an escaped quote. */
inline std::wstring TrimSlashes(std::wstring dir)
{
    while (dir.size() > 3 && (dir.back() == L'\\' || dir.back() == L'/')) {
        dir.pop_back();
    }
    return dir;
}

/* The game folder as listed in kFoldersKey: its full path, so that "/home/deck/Wiz8",
   "Z:/home/deck/Wiz8" and "Z:\home\deck\Wiz8" (all valid under Wine) are one entry. */
inline std::wstring WineFolderName(const std::wstring& game)
{
    wchar_t full[MAX_PATH * 2];
    DWORD n = GetFullPathNameW(game.c_str(), MAX_PATH * 2, full, 0);
    return n && n < MAX_PATH * 2 ? TrimSlashes(full) : game;
}

/* Who a game folder is, whatever name it is reached by. Under Wine one folder often has several
   names: "Z:\home\deck\Games\Wizardry 8", "X:\Games\Wizardry 8" (umu, used by Heroic and Lutris
   with Proton, maps the home folder to X:), a "\\?\unix\..." path, a link; their texts differ,
   so they are compared by the numbers the file system gives the folder and one file in it
   (Wiz8.exe). Under Wine that number is the Unix inode. An inode alone can repeat on another
   disk (an SD card next to the internal one), so both numbers are kept. */
struct FolderIdentity {
    DWORD volume = 0;     /* volume serial number of the folder; compared on Windows only (under
                             Wine it differs per drive letter, also for one folder) */
    ULONGLONG folder = 0; /* the folder's file number */
    ULONGLONG file = 0;   /* the file number of the file inside it */
};

/* The file number and volume of a file or folder; false if it cannot be opened. No rights are
   asked for but reading the attributes, and any sharing is allowed, so this works on a running
   Wiz8.exe too; FILE_FLAG_BACKUP_SEMANTICS is what lets CreateFileW open a folder. */
inline bool FileNumber(const std::wstring& path, DWORD* volume, ULONGLONG* number)
{
    HANDLE handle = CreateFileW(path.c_str(), FILE_READ_ATTRIBUTES,
                                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, 0,
                                OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, 0);
    if (handle == INVALID_HANDLE_VALUE) {
        return false;
    }
    BY_HANDLE_FILE_INFORMATION info;
    BOOL ok = GetFileInformationByHandle(handle, &info);
    CloseHandle(handle);
    if (!ok) {
        return false;
    }
    *volume = info.dwVolumeSerialNumber;
    *number = (ULONGLONG)info.nFileIndexHigh << 32 | info.nFileIndexLow;
    return true;
}

/* The identity of a folder and of the file (or folder) "inside" in it: Wiz8.exe for a game
   folder; another name for other uses (drive_c for a Wine prefix). false when either cannot be
   opened: the folder is not there now (an SD card that is out), or it has no such file. */
inline bool FolderId(const std::wstring& folder, FolderIdentity* id,
                     const wchar_t* inside = L"Wiz8.exe")
{
    std::wstring child = folder;
    if (!child.empty() && child.back() != L'\\' && child.back() != L'/') {
        child += L'\\';
    }
    child += inside;
    DWORD volume = 0;
    return FileNumber(folder, &id->volume, &id->folder) && FileNumber(child, &volume, &id->file);
}

/* Whether two names lead to the same folder: by FolderId when both can be read, otherwise (a
   folder that is not there now, or has no Wiz8.exe) by comparing their WineFolderName forms,
   in any letter case. */
inline bool SameFolder(const std::wstring& a, const std::wstring& b,
                       const wchar_t* inside = L"Wiz8.exe")
{
    FolderIdentity x, y;
    if (FolderId(a, &x, inside) && FolderId(b, &y, inside)) {
        return x.folder == y.folder && x.file == y.file && (UnderWine() || x.volume == y.volume);
    }
    return lstrcmpiW(WineFolderName(a).c_str(), WineFolderName(b).c_str()) == 0;
}

}  // namespace wine
