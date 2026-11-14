// The patch keeps its own Wine setting, see wine_settings.h.
//
// Wine reads HKCU\Software\Wine\AppDefaults\Wiz8.exe\DllOverrides once, when Wiz8.exe starts
// (docs/loader.md), so what is written here counts from the next start: this run already got
// its version.dll and ddraw.dll. The rules, for each of "*version" = "native,builtin" and
// "*ddraw" = "builtin":
//   - a value already there under the "*" name or the plain one ("version", "ddraw") is left
//     as it is, whoever wrote it;
//   - a value that HKCU\Software\Wiz8Wide\Wine says was written before but is gone now was
//     deleted by the player: it is not written again (running the installer writes it, which
//     is an explicit choice);
//   - "*ddraw" is not written when the launch option asks for another ddraw (WINEDLLOVERRIDES
//     "ddraw=n,b": the player wants dgVoodoo for this start); Wine looks "*ddraw" up before
//     "ddraw", so ours would silently win over theirs from the next start;
//   - in a 32-bit prefix the plain "ddraw" = "builtin" is written (and noted) with "*ddraw"
//     (wine::PlainDdrawToo): there Wine reads that name first for its own ddraw.dll. For a
//     ddraw.dll in Wine's system folder it then comes before a WINEDLLOVERRIDES "*ddraw" as
//     well, so a dgVoodoo or D7VK put there needs the launch option "ddraw=n,b";
//   - only for Wiz8.exe: another program that loads this DLL (3DSetup.exe in the GOG folder,
//     a tool) would write the setting under the wrong name.
// The game folder is listed in HKCU\Software\Wiz8Wide\Wine\Folders like the installer lists
// it, unless it is listed already, under this name or another one (X: and Z:, see
// wine::SameFolder). One entry per folder is kept: the name this run sees if it is listed,
// otherwise the first one; further names of the same folder are removed from the list.

#include "wine_settings.h"

#include <windows.h>

#include <string>
#include <vector>

#include "log.h"
#include "runtime.h"
#include "wine_overrides.h"

using namespace wine;  // kWineKey, ReadUserValue, ... (src/wine_overrides.h)

namespace {

// Text from the registry (UTF-16) as UTF-8 for the log.
std::string Utf8(const std::wstring& text)
{
    int n = WideCharToMultiByte(CP_UTF8, 0, text.c_str(), (int)text.size(), nullptr, 0, nullptr, nullptr);
    std::string out(n > 0 ? n : 0, '\0');
    if (n > 0) WideCharToMultiByte(CP_UTF8, 0, text.c_str(), (int)text.size(), &out[0], n, nullptr, nullptr);
    return out;
}

// The file name of the running program (Wiz8.exe, 3DSetup.exe, ...).
std::wstring MainExeName()
{
    wchar_t path[MAX_PATH * 2];
    DWORD n = GetModuleFileNameW(nullptr, path, MAX_PATH * 2);
    if (n == 0 || n >= MAX_PATH * 2) {
        return std::wstring();
    }
    std::wstring name = path;
    return name.substr(name.find_last_of(L"\\/") + 1);
}

// The folder of this DLL (the game folder), without the file name.
std::wstring DllFolder()
{
    HMODULE self = nullptr;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCWSTR)&DllFolder, &self);
    wchar_t path[MAX_PATH * 2];
    DWORD n = GetModuleFileNameW(self, path, MAX_PATH * 2);
    if (n == 0 || n >= MAX_PATH * 2) {
        return std::wstring();
    }
    std::wstring folder = path;
    return folder.substr(0, folder.find_last_of(L"\\/"));
}

// One of the two values: what was found or done, for the log line. folder: the game folder.
std::string KeepOne(const WineDll& dll, bool ddrawOwn, const std::wstring& folder)
{
    const wchar_t* plain = dll.name + 1;
    bool ddraw = lstrcmpW(plain, L"ddraw") == 0;
    std::wstring value;
    if (ReadUserValue(kWineKey, dll.name, &value)) {
        return Utf8(dll.name) + " already set (" + Utf8(value) + ")";
    }
    if (ReadUserValue(kWineKey, plain, &value)) {
        return Utf8(plain) + " already set (" + Utf8(value) + ")";
    }
    std::string name = Utf8(dll.name);
    // The note under either name: an uninstall that kept a DDraw.dll may have dropped only one.
    if (ReadUserValue(kOwnKey, dll.name, nullptr) || ReadUserValue(kOwnKey, plain, nullptr)) {
        return name + " removed since it was written, not written again";
    }
    // As Wine looks it up for the game folder's file: "*ddraw" first, then "ddraw".
    std::wstring asked;
    if (ddraw && (WineEnvOrder(L"*ddraw", &asked) || WineEnvOrder(L"ddraw", &asked)) &&
        WineOrderLetters(asked).compare(0, 1, L"b") != 0) {
        return name + " not written: WINEDLLOVERRIDES asks for ddraw=" + Utf8(asked);
    }
    if (!WriteUserValue(kWineKey, dll.name, dll.order)) {
        DWORD error = GetLastError();  // the registry's error code (WriteUserValue sets it)
        return name + " could not be written (error " + std::to_string(error) + ")";
    }
    bool noted = WriteUserValue(kOwnKey, dll.name, dll.order);  // the note, as the installer writes it
    std::string written = name + " written (" + Utf8(dll.order);
    // The plain one only with both notes, so that an uninstall finds and removes it.
    if (PlainDdrawToo(dll) && noted) {
        if (!WriteUserValue(kWineKey, plain, dll.order)) {
            DWORD error = GetLastError();
            written += "; plain " + Utf8(plain) + " could not be written (error " + std::to_string(error) + ")";
        } else if (!WriteUserValue(kOwnKey, plain, dll.order)) {
            DWORD error = GetLastError();
            DeleteUserValue(kWineKey, plain);
            written += "; plain " + Utf8(plain) + " not kept, its note could not be written (error " +
                       std::to_string(error) + ")";
        } else {
            written += "; plain " + Utf8(plain) + " too, which a 32-bit prefix reads first";
        }
    }
    // Not Wine's own this time: the game folder's DDraw.dll, which "*ddraw" keeps out from the
    // next start, or else a native one from Wine's system folder, found through a global
    // "ddraw" or "*ddraw" (from the next start the per-program "*ddraw" comes first in a 64-bit
    // prefix, the plain "ddraw" just written in a 32-bit one; the result below says otherwise
    // only if that could not be written).
    if (ddraw && !ddrawOwn) {
        written += DllInFolder(folder, dll)
                       ? "; ddraw.dll came from the game folder this time, Wine's own from the next start"
                       : "; ddraw.dll was a native one from Wine's system folder this time";
    }
    return written + ")";
}

// Lists the game folder in kFoldersKey (see the top of this file) and logs only what changed.
void ListFolder()
{
    std::wstring folder = DllFolder();
    if (folder.empty()) {
        return;  // its path did not fit (cannot happen with a game folder)
    }
    folder = WineFolderName(folder);
    std::vector<std::wstring> names;  // the entries that are this folder, under any name
    for (const std::wstring& entry : UserValueNames(kFoldersKey)) {
        if (SameFolder(entry, folder)) {
            names.push_back(entry);
        }
    }
    if (names.empty()) {
        if (WriteUserValue(kFoldersKey, folder.c_str(), L"")) {
            Log("wine settings: game folder listed in HKCU\\Software\\Wiz8Wide\\Wine\\Folders as %s",
                Utf8(folder).c_str());
        } else {
            Log("wine settings: game folder could not be listed in HKCU\\Software\\Wiz8Wide\\Wine\\Folders "
                "(error %lu)", GetLastError());
        }
        return;
    }
    // One entry is enough: the name this run sees if it is there (it works for the game), else
    // the first one; the others go.
    std::wstring keep = names[0];
    for (const std::wstring& name : names) {
        if (lstrcmpiW(name.c_str(), folder.c_str()) == 0) keep = name;
    }
    for (const std::wstring& name : names) {
        if (name != keep) DeleteUserValue(kFoldersKey, name.c_str());
    }
    if (names.size() > 1) {
        Log("wine settings: %d more name(s) of this game folder removed from HKCU\\Software\\Wiz8Wide\\Wine\\Folders",
            (int)names.size() - 1);
    }
}

}  // namespace

void WineKeepOverrides(bool ddrawOwn)
{
    if (!UnderWine()) {
        return;
    }
    if (lstrcmpiW(MainExeName().c_str(), L"Wiz8.exe") != 0) {
        Log("wine settings: not Wiz8.exe, nothing written");
        return;
    }
    std::wstring folder = DllFolder();
    std::string report;
    for (const WineDll& dll : kWineDlls) {
        report += (report.empty() ? "" : ", ") + KeepOne(dll, ddrawOwn, folder);
    }
    // Whether a start with no launch option gets what the patch needs (as the installer checks),
    // each value on its own: version.dll decides whether the patch starts, ddraw.dll whether the
    // game survives (dgVoodoo crashes under Wine).
    std::string result;
    if (!WineOrderOk(kWineDlls[0], folder)) {
        result = g_runtime.role == LoaderRole::Binkw32
                     ? "a setting in this prefix keeps version.dll from starting the patch without "
                       "WINEDLLOVERRIDES (left as it is; binkw32.dll starts it)"
                     : "a setting in this prefix keeps the patch from starting without "
                       "WINEDLLOVERRIDES (left as it is)";
    }
    if (!WineOrderOk(kWineDlls[1], folder)) {
        result += std::string(result.empty() ? "" : "; ") +
                  (DllInFolder(folder, kWineDlls[1])
                       ? "a setting in this prefix gives Wiz8.exe the game folder's ddraw.dll (dgVoodoo, "
                         "which crashes under Wine; left as it is)"
                       : "a setting in this prefix gives Wiz8.exe a native ddraw.dll from Wine's system "
                         "folder instead of Wine's own (without one there the game does not start; left "
                         "as it is)");
    }
    if (result.empty()) {
        result = "the patch starts without WINEDLLOVERRIDES in this prefix";
    }
    Log("wine settings (HKCU\\Software\\Wine\\AppDefaults\\Wiz8.exe\\DllOverrides): %s; %s", report.c_str(),
        result.c_str());
    ListFolder();
}
