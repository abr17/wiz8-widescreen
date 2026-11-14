// Which copy of the patch runs it, see loader_route.h.

#include "loader_route.h"

#include <windows.h>
#include <tlhelp32.h>

#include <string.h>

#include "log.h"
#include "proxy_version.h"
#include "runtime.h"
#include "wine_overrides.h"

namespace {

const DWORD kPathChars = MAX_PATH * 2;

// Wine's own DLLs carry this text right after the DOS header (as in LogWine, dllmain.cpp).
bool IsWineBuiltin(HMODULE module)
{
    return module && memcmp((const char*)module + 0x40, "Wine builtin DLL", 16) == 0;
}

// Full path of a module; false if it does not fit.
bool ModulePath(HMODULE module, wchar_t* path)
{
    DWORD n = GetModuleFileNameW(module, path, kPathChars);
    return n > 0 && n < kPathChars;
}

// The part of a path after the last '\' or '/'.
wchar_t* FileNamePart(wchar_t* path)
{
    wchar_t* name = path;
    for (wchar_t* p = path; *p; ++p) {
        if (*p == L'\\' || *p == L'/') name = p + 1;
    }
    return name;
}

// Whether two files have exactly the same bytes. Plain reads in small pieces, no hash: this runs
// in DllMain, and Windows' hashing functions (bcrypt) load further DLLs on first use, which
// DllMain must not cause; the files are small (about 400 KB). Any sharing is allowed: one of
// them is the running DLL itself.
bool SameBytes(const wchar_t* a, const wchar_t* b)
{
    const DWORD share = FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE;
    HANDLE fa = CreateFileW(a, GENERIC_READ, share, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    HANDLE fb = CreateFileW(b, GENERIC_READ, share, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    LARGE_INTEGER sa, sb;
    bool same = fa != INVALID_HANDLE_VALUE && fb != INVALID_HANDLE_VALUE && GetFileSizeEx(fa, &sa) &&
                GetFileSizeEx(fb, &sb) && sa.QuadPart == sb.QuadPart;
    char ba[8192], bb[8192];
    while (same) {
        DWORD na = 0, nb = 0;
        if (!ReadFile(fa, ba, sizeof(ba), &na, nullptr) || !ReadFile(fb, bb, sizeof(bb), &nb, nullptr) ||
            na != nb) {
            same = false;
        } else if (na == 0) {
            break;  // both ended
        } else {
            same = memcmp(ba, bb, na) == 0;
        }
    }
    if (fa != INVALID_HANDLE_VALUE) CloseHandle(fa);
    if (fb != INVALID_HANDLE_VALUE) CloseHandle(fb);
    return same;
}

// The file of this module and version.dll in the same folder; false if a path does not fit.
bool OwnAndVersionDll(HMODULE module, wchar_t* own, wchar_t* version)
{
    if (!ModulePath(module, own)) {
        return false;
    }
    lstrcpyW(version, own);
    wchar_t* name = FileNamePart(version);
    if (name - version + 12 >= (int)kPathChars) {
        return false;
    }
    lstrcpyW(name, L"version.dll");
    return true;
}

// Whether the file of this module and version.dll in the same folder have the same bytes.
bool SameAsVersionDll(HMODULE module)
{
    wchar_t own[kPathChars], version[kPathChars];
    return OwnAndVersionDll(module, own, version) && SameBytes(own, version);
}

// Which version.dll sr.dll got, when this copy runs as binkw32.dll (and so loaded none itself,
// unless version.dll is this same file: then sr.dll got this copy, which loaded Wine's own
// itself, as the version.dll copy does): Wine's own, or our copy from the game folder (through
// the launch option, the registry setting or a newer Wine's own rule), which then only passes
// calls on. Two modules named version.dll can be in the process (ours and Wine's, which ours
// loads), so all modules are listed (a "snapshot" of the process: a kernel32 function, used
// outside DllMain only). Our copy without Wine's next to it could not load Wine's: then every
// version call of the game fails, as the version.dll route's "real version.dll: FAILED" says.
const char* VersionDllText(bool sameFile)
{
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, 0);
    if (snapshot == INVALID_HANDLE_VALUE) {
        return "unknown (the module list could not be read)";
    }
    bool ours = false, wines = false;
    MODULEENTRY32W module;
    module.dwSize = sizeof(module);
    for (BOOL ok = Module32FirstW(snapshot, &module); ok; ok = Module32NextW(snapshot, &module)) {
        if (lstrcmpiW(module.szModule, L"version.dll") != 0) {
            continue;
        }
        if (IsWineBuiltin(module.hModule)) {
            wines = true;
        } else {
            ours = true;
        }
    }
    CloseHandle(snapshot);
    if (ours) {
        return wines ? "our copy, forwarding only"
                     : "our copy, which could not load Wine's own version.dll, so the game's "
                       "version calls fail; use WINEDLLOVERRIDES version=n,b, not version=n";
    }
    if (sameFile) {
        return wines ? "this file too (version.dll is a link to binkw32.dll), forwarding to Wine's own"
                     : "this file too (version.dll is a link to binkw32.dll), which could not load "
                       "Wine's own version.dll, so the game's version calls fail; use "
                       "WINEDLLOVERRIDES version=n,b, not version=n";
    }
    return wines ? "Wine's own" : "not loaded";
}

}  // namespace

LoaderRole LoaderRoleOf(HINSTANCE self)
{
    wchar_t path[kPathChars];
    if (!ModulePath(self, path)) {
        return LoaderRole::Version;
    }
    return lstrcmpiW(FileNamePart(path), L"binkw32.dll") == 0 ? LoaderRole::Binkw32 : LoaderRole::Version;
}

const char* LoaderRoleName(LoaderRole role)
{
    return role == LoaderRole::Binkw32 ? "binkw32.dll" : "version.dll";
}

bool VersionDllIsThisFile(HINSTANCE self)
{
    // Wine matches a DLL to a loaded module by its file (the Unix inode), not by its name, and so
    // does Windows (8 and later: by the mapped file; a hard link shares it). The file number is
    // the inode under Wine and the NTFS file index on Windows; the two names are in one folder,
    // so on one drive: the same volume serial number.
    wchar_t own[kPathChars], version[kPathChars];
    DWORD ownVolume = 0, versionVolume = 0;
    ULONGLONG ownNumber = 0, versionNumber = 0;
    return OwnAndVersionDll(self, own, version) && wine::FileNumber(own, &ownVolume, &ownNumber) &&
           wine::FileNumber(version, &versionVolume, &versionNumber) && ownVolume == versionVolume &&
           ownNumber == versionNumber;
}

bool StartHere(HINSTANCE self, LoaderRole role)
{
    // On Windows only one copy ever starts, so it needs no lock: the version.dll copy, exactly as
    // before 1.0.3, or the binkw32.dll copy when version.dll is this very file (then Windows
    // loads no second module for it, and this one is the only copy in the process).
    if (!wine::UnderWine()) {
        return role == LoaderRole::Version || VersionDllIsThisFile(self);
    }
    if (role == LoaderRole::Binkw32 && !SameAsVersionDll(self)) {
        return false;
    }
    // The lock is created only by a copy that is going to start, and never closed: it exists
    // as long as the process does. GetLastError says whether it was there already.
    wchar_t name[64];
    wsprintfW(name, L"Local\\Wiz8Widescreen-%lu", GetCurrentProcessId());
    HANDLE mutex = CreateMutexW(nullptr, FALSE, name);
    if (mutex && GetLastError() == ERROR_ALREADY_EXISTS) {
        CloseHandle(mutex);
        return false;  // the other copy started first
    }
    // Not created at all (cannot happen in practice): version.dll starts as it always did,
    // binkw32.dll leaves it to version.dll.
    return mutex || role == LoaderRole::Version;
}

void LogLoaderRoute(LoaderRole role)
{
    if (role == LoaderRole::Binkw32 && !wine::UnderWine()) {
        // On Windows this copy starts only when version.dll is this very file (StartHere), and
        // it then loaded the real one itself. The module list (VersionDllText) is not read: the
        // system's version.dll has no Wine mark and would count as our copy.
        if (g_runtime.proxyOk) {
            Log("started from binkw32.dll; version.dll: this file too (version.dll is a link to "
                "binkw32.dll), forwarding to the system version.dll");
        } else {
            Log("started from binkw32.dll; version.dll: this file too (version.dll is a link to "
                "binkw32.dll), which could not load the system version.dll (error %lu), so the "
                "game's version calls fail", ProxyVersionError());
        }
        return;
    }
    if (role == LoaderRole::Binkw32) {
        HMODULE self = nullptr;
        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCWSTR)&LogLoaderRoute, &self);
        Log("started from binkw32.dll (no launch option needed); version.dll: %s",
            VersionDllText(self && VersionDllIsThisFile(self)));
        return;
    }
    if (!wine::UnderWine()) {
        return;
    }
    // Our copy as binkw32.dll exports the version.dll functions too; RAD's original does not.
    HMODULE bink = GetModuleHandleW(L"binkw32.dll");
    if (!bink || !GetProcAddress(bink, "VerQueryValueA")) {
        return;
    }
    HMODULE self = nullptr;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCWSTR)&LogLoaderRoute, &self);
    wchar_t own[kPathChars], other[kPathChars];
    bool same = self && ModulePath(self, own) && ModulePath(bink, other) && SameBytes(own, other);
    Log("binkw32.dll: a copy of the patch, forwarding only (%s)",
        same ? "the same file; version.dll started first"
             : "not the same file as version.dll, an older copy: run the installer again");
}
