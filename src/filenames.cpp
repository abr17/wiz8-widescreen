// File names when Windows uses UTF-8 as the system code page (see filenames.h).
//
// How a path is converted (game -> Windows), one component between '\' or '/' at a time:
//   - a component that is valid UTF-8 is read as UTF-8: it came from Windows itself, for
//     example the game folder from GetModuleFileNameA, or a name returned below;
//   - any other component is read in the code page Windows would use without the UTF-8
//     option: it is one of the game's own single-byte names.
// File names found on disk (Windows -> game, FindFirstFileA/FindNextFileA) go back in that
// code page when they fit into it and the result cannot be mistaken for UTF-8 or for a path
// separator, otherwise as UTF-8 (as Windows returns them now). So a name the game found on
// disk always opens the same file again. The other way round there is one ambiguity: a game
// name whose bytes happen to be valid UTF-8 as a whole (e.g. "Рё" = D0 B8, which is UTF-8 for
// "и") is read as UTF-8 and may share a file with another name. Such names need every
// non-English letter to be a capital followed by ё/Ё; the same bytes are also how a Cyrillic
// or accented folder name from Windows looks, so they cannot be told apart.
//
// The redirection is a change of the import table ("IAT": the list of addresses through
// which a module calls functions of other DLLs), only in Wiz8.exe and wiz8hy.dll; the
// graphics, sound and video DLLs are not touched. Paths with English letters only are
// passed to the original functions unchanged. wiz8hy.dll links its C runtime statically, so
// its own fopen/_access/rename calls do not go through msvcrt and are not redirected; today it
// opens game files only through kernel32 (CreateFileA, DeleteFileA, the PrivateProfile calls).

#include "filenames.h"

namespace {

constexpr int kMaxPath = 1024;  // wide characters; the game's own paths are under MAX_PATH

UINT g_codePage = 1252;

// The original functions, for paths that need no conversion.
HANDLE(WINAPI* g_CreateFileA)(LPCSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE);
BOOL(WINAPI* g_DeleteFileA)(LPCSTR);
BOOL(WINAPI* g_MoveFileA)(LPCSTR, LPCSTR);
BOOL(WINAPI* g_CopyFileA)(LPCSTR, LPCSTR, BOOL);
DWORD(WINAPI* g_GetFileAttributesA)(LPCSTR);
BOOL(WINAPI* g_SetFileAttributesA)(LPCSTR, DWORD);
BOOL(WINAPI* g_CreateDirectoryA)(LPCSTR, LPSECURITY_ATTRIBUTES);
UINT(WINAPI* g_GetPrivateProfileIntA)(LPCSTR, LPCSTR, INT, LPCSTR);
HANDLE(WINAPI* g_FindFirstFileA)(LPCSTR, LPWIN32_FIND_DATAA);
BOOL(WINAPI* g_FindNextFileA)(HANDLE, LPWIN32_FIND_DATAA);
// msvcrt.dll (the game's C runtime): narrow functions and their wide counterparts.
void*(__cdecl* g_fopen)(const char*, const char*);
void*(__cdecl* g_wfopen)(const wchar_t*, const wchar_t*);
int(__cdecl* g_access)(const char*, int);
int(__cdecl* g_waccess)(const wchar_t*, int);
int(__cdecl* g_rename)(const char*, const char*);
int(__cdecl* g_wrename)(const wchar_t*, const wchar_t*);
int(__cdecl* g_chmod)(const char*, int);
int(__cdecl* g_wchmod)(const wchar_t*, int);
int(__cdecl* g_chdir)(const char*);
int(__cdecl* g_wchdir)(const wchar_t*);

bool HasHighBytes(const char* s)
{
    for (; s && *s; ++s) {
        if ((unsigned char)*s >= 0x80) return true;
    }
    return false;
}

bool IsUtf8(const char* s, int length)
{
    return length == 0 || MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s, length, nullptr, 0) > 0;
}

// Game path -> Windows path, by the component rule above. False if it does not fit.
bool Widen(const char* path, wchar_t* out, int capacity)
{
    int length = 0;
    const char* part = path;
    for (;;) {
        const char* end = part;
        while (*end && *end != '\\' && *end != '/') ++end;
        int bytes = (int)(end - part);
        if (bytes > 0) {
            int room = capacity - length - 1;
            if (room <= 0) return false;  // (0 would make MultiByteToWideChar only measure)
            UINT cp = IsUtf8(part, bytes) ? CP_UTF8 : g_codePage;
            int written = MultiByteToWideChar(cp, 0, part, bytes, out + length, room);
            if (written <= 0) return false;
            length += written;
        }
        if (!*end) break;
        if (length >= capacity - 1) return false;
        out[length++] = (wchar_t)*end;
        part = end + 1;
    }
    out[length] = 0;
    return true;
}

bool HasSeparator(const char* s)
{
    for (; *s; ++s) {
        if (*s == '\\' || *s == '/') return true;
    }
    return false;
}

// Name found on disk -> game name, by the rule above. A separator byte can appear only as
// the second byte of a character in a double-byte code page (932, 936, 950: "ソ" = 83 5C);
// Widen would split the name there, so such a name goes back as UTF-8, which never has one.
void Narrow(const wchar_t* name, char* out, int capacity)
{
    BOOL lossy = FALSE;
    int n = WideCharToMultiByte(g_codePage, WC_NO_BEST_FIT_CHARS, name, -1, out, capacity, nullptr, &lossy);
    if (n > 0 && !lossy && !HasSeparator(out) && (!HasHighBytes(out) || !IsUtf8(out, n - 1))) return;
    if (WideCharToMultiByte(CP_UTF8, 0, name, -1, out, capacity, nullptr, nullptr) <= 0) {
        lstrcpynA(out, "?", capacity);  // longer than the game's buffer: cannot happen with its names
    }
}

void CopyFindData(const WIN32_FIND_DATAW& from, WIN32_FIND_DATAA* to)
{
    to->dwFileAttributes = from.dwFileAttributes;
    to->ftCreationTime = from.ftCreationTime;
    to->ftLastAccessTime = from.ftLastAccessTime;
    to->ftLastWriteTime = from.ftLastWriteTime;
    to->nFileSizeHigh = from.nFileSizeHigh;
    to->nFileSizeLow = from.nFileSizeLow;
    to->dwReserved0 = from.dwReserved0;
    to->dwReserved1 = from.dwReserved1;
    Narrow(from.cFileName, to->cFileName, sizeof(to->cFileName));
    Narrow(from.cAlternateFileName, to->cAlternateFileName, sizeof(to->cAlternateFileName));
}

// A small helper for the wrappers below: the converted path, or null when the original
// function should get the path as it is (English letters only, or it does not fit).
struct WidePath {
    wchar_t text[kMaxPath];
    const wchar_t* ok;
    explicit WidePath(const char* path) : ok(nullptr)
    {
        if (HasHighBytes(path) && Widen(path, text, kMaxPath)) ok = text;
    }
};

// Same for short ASCII strings (an ini section, an fopen mode): plain widening.
void WidenAscii(const char* s, wchar_t* out, int capacity)
{
    int i = 0;
    for (; s && s[i] && i < capacity - 1; ++i) out[i] = (unsigned char)s[i];
    out[i] = 0;
}

HANDLE WINAPI HookCreateFileA(LPCSTR name, DWORD access, DWORD share, LPSECURITY_ATTRIBUTES sa,
                              DWORD disposition, DWORD flags, HANDLE templ)
{
    WidePath w(name);
    if (!w.ok) return g_CreateFileA(name, access, share, sa, disposition, flags, templ);
    return CreateFileW(w.ok, access, share, sa, disposition, flags, templ);
}

BOOL WINAPI HookDeleteFileA(LPCSTR name)
{
    WidePath w(name);
    return w.ok ? DeleteFileW(w.ok) : g_DeleteFileA(name);
}

BOOL WINAPI HookMoveFileA(LPCSTR from, LPCSTR to)
{
    if (!HasHighBytes(from) && !HasHighBytes(to)) return g_MoveFileA(from, to);
    wchar_t wa[kMaxPath], wb[kMaxPath];
    if (!Widen(from, wa, kMaxPath) || !Widen(to, wb, kMaxPath)) return g_MoveFileA(from, to);
    return MoveFileW(wa, wb);
}

BOOL WINAPI HookCopyFileA(LPCSTR from, LPCSTR to, BOOL failIfExists)
{
    if (!HasHighBytes(from) && !HasHighBytes(to)) return g_CopyFileA(from, to, failIfExists);
    wchar_t wa[kMaxPath], wb[kMaxPath];
    if (!Widen(from, wa, kMaxPath) || !Widen(to, wb, kMaxPath)) return g_CopyFileA(from, to, failIfExists);
    return CopyFileW(wa, wb, failIfExists);
}

DWORD WINAPI HookGetFileAttributesA(LPCSTR name)
{
    WidePath w(name);
    return w.ok ? GetFileAttributesW(w.ok) : g_GetFileAttributesA(name);
}

BOOL WINAPI HookSetFileAttributesA(LPCSTR name, DWORD attributes)
{
    WidePath w(name);
    return w.ok ? SetFileAttributesW(w.ok, attributes) : g_SetFileAttributesA(name, attributes);
}

BOOL WINAPI HookCreateDirectoryA(LPCSTR name, LPSECURITY_ATTRIBUTES sa)
{
    WidePath w(name);
    return w.ok ? CreateDirectoryW(w.ok, sa) : g_CreateDirectoryA(name, sa);
}

UINT WINAPI HookGetPrivateProfileIntA(LPCSTR section, LPCSTR key, INT def, LPCSTR file)
{
    WidePath w(file);
    if (!w.ok || HasHighBytes(section) || HasHighBytes(key)) return g_GetPrivateProfileIntA(section, key, def, file);
    wchar_t ws[256], wk[256];
    WidenAscii(section, ws, 256);
    WidenAscii(key, wk, 256);
    return GetPrivateProfileIntW(section ? ws : nullptr, key ? wk : nullptr, def, w.ok);
}

// The search itself always goes through FindFirstFileW: even for an English pattern the
// names found must come back by the rule above.
HANDLE WINAPI HookFindFirstFileA(LPCSTR pattern, LPWIN32_FIND_DATAA data)
{
    wchar_t w[kMaxPath];
    if (!pattern || !data || !Widen(pattern, w, kMaxPath)) return g_FindFirstFileA(pattern, data);
    WIN32_FIND_DATAW found;
    HANDLE search = FindFirstFileW(w, &found);
    if (search != INVALID_HANDLE_VALUE) CopyFindData(found, data);
    return search;
}

// A search handle is the same for the A and W functions, whichever started the search.
BOOL WINAPI HookFindNextFileA(HANDLE search, LPWIN32_FIND_DATAA data)
{
    if (!data) return g_FindNextFileA(search, data);
    WIN32_FIND_DATAW found;
    if (!FindNextFileW(search, &found)) return FALSE;
    CopyFindData(found, data);
    return TRUE;
}

void* __cdecl HookFopen(const char* name, const char* mode)
{
    WidePath w(name);
    if (!w.ok || !g_wfopen) return g_fopen(name, mode);
    wchar_t wm[16];
    WidenAscii(mode, wm, 16);
    return g_wfopen(w.ok, wm);
}

int __cdecl HookAccess(const char* name, int mode)
{
    WidePath w(name);
    return w.ok && g_waccess ? g_waccess(w.ok, mode) : g_access(name, mode);
}

int __cdecl HookRename(const char* from, const char* to)
{
    if ((!HasHighBytes(from) && !HasHighBytes(to)) || !g_wrename) return g_rename(from, to);
    wchar_t wa[kMaxPath], wb[kMaxPath];
    if (!Widen(from, wa, kMaxPath) || !Widen(to, wb, kMaxPath)) return g_rename(from, to);
    return g_wrename(wa, wb);
}

int __cdecl HookChmod(const char* name, int mode)
{
    WidePath w(name);
    return w.ok && g_wchmod ? g_wchmod(w.ok, mode) : g_chmod(name, mode);
}

int __cdecl HookChdir(const char* name)
{
    WidePath w(name);
    return w.ok && g_wchdir ? g_wchdir(w.ok) : g_chdir(name);
}

// Replaces the import 'dll!name' of a module with 'hook'. True if the module imports it.
bool PatchImport(HMODULE module, const char* dll, const char* name, void* hook, void* original)
{
    BYTE* base = (BYTE*)module;
    IMAGE_NT_HEADERS* nt = (IMAGE_NT_HEADERS*)(base + ((IMAGE_DOS_HEADER*)base)->e_lfanew);
    const IMAGE_DATA_DIRECTORY& dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (dir.VirtualAddress == 0) return false;
    for (IMAGE_IMPORT_DESCRIPTOR* imp = (IMAGE_IMPORT_DESCRIPTOR*)(base + dir.VirtualAddress); imp->Name; ++imp) {
        if (lstrcmpiA((const char*)(base + imp->Name), dll) != 0) continue;
        IMAGE_THUNK_DATA* slot = (IMAGE_THUNK_DATA*)(base + imp->FirstThunk);
        // Find the slot by the name table; a module without one: by the current address.
        IMAGE_THUNK_DATA* names = imp->OriginalFirstThunk ? (IMAGE_THUNK_DATA*)(base + imp->OriginalFirstThunk) : nullptr;
        for (; slot->u1.Function; ++slot) {
            bool match;
            if (names) {
                match = !IMAGE_SNAP_BY_ORDINAL(names->u1.Ordinal) &&
                        lstrcmpA((const char*)((IMAGE_IMPORT_BY_NAME*)(base + names->u1.AddressOfData))->Name, name) == 0;
                ++names;
            } else {
                match = (void*)slot->u1.Function == original;
            }
            if (!match) continue;
            DWORD old;
            if (!VirtualProtect(&slot->u1.Function, sizeof(slot->u1.Function), PAGE_READWRITE, &old)) return false;
            slot->u1.Function = (ULONG_PTR)hook;
            VirtualProtect(&slot->u1.Function, sizeof(slot->u1.Function), old, &old);
            return true;
        }
    }
    return false;
}

UINT SystemAnsiCodePage()
{
    char text[8] = {};
    UINT cp = 0;
    if (GetLocaleInfoA(LOCALE_SYSTEM_DEFAULT, LOCALE_IDEFAULTANSICODEPAGE, text, sizeof(text)) > 0) {
        for (const char* p = text; *p >= '0' && *p <= '9'; ++p) cp = cp * 10 + (*p - '0');
    }
    if (cp == 0 || cp == CP_UTF8 || !IsValidCodePage(cp)) cp = 1252;
    return cp;
}

}  // namespace

UINT FileNameCodePage()
{
    return g_codePage;
}

#ifdef WIZ8WS_TESTING
void SetFileNameCodePage(UINT cp)
{
    g_codePage = cp;
}
#endif

int InstallFileNameHooks(HMODULE hybrid)
{
    static int s_result = -2;
    if (s_result != -2) return s_result;
    if (GetACP() != CP_UTF8) return s_result = -1;
    g_codePage = SystemAnsiCodePage();

    HMODULE k32 = GetModuleHandleA("kernel32.dll");
    HMODULE crt = GetModuleHandleA("msvcrt.dll");
    struct Import {
        const char* dll;
        const char* name;
        void* hook;
        void** original;
    };
#define K32(fn) {"kernel32.dll", #fn, (void*)&Hook##fn, (void**)&g_##fn}
    const Import imports[] = {
        K32(CreateFileA), K32(DeleteFileA), K32(MoveFileA), K32(CopyFileA),
        K32(GetFileAttributesA), K32(SetFileAttributesA), K32(CreateDirectoryA),
        K32(GetPrivateProfileIntA), K32(FindFirstFileA), K32(FindNextFileA),
        {"msvcrt.dll", "fopen", (void*)&HookFopen, (void**)&g_fopen},
        {"msvcrt.dll", "_access", (void*)&HookAccess, (void**)&g_access},
        {"msvcrt.dll", "rename", (void*)&HookRename, (void**)&g_rename},
        {"msvcrt.dll", "_chmod", (void*)&HookChmod, (void**)&g_chmod},
        {"msvcrt.dll", "_chdir", (void*)&HookChdir, (void**)&g_chdir},
    };
#undef K32
    if (crt) {
        g_wfopen = (decltype(g_wfopen))GetProcAddress(crt, "_wfopen");
        g_waccess = (decltype(g_waccess))GetProcAddress(crt, "_waccess");
        g_wrename = (decltype(g_wrename))GetProcAddress(crt, "_wrename");
        g_wchmod = (decltype(g_wchmod))GetProcAddress(crt, "_wchmod");
        g_wchdir = (decltype(g_wchdir))GetProcAddress(crt, "_wchdir");
    }

    int patched = 0;
    for (const Import& imp : imports) {
        HMODULE from = imp.dll[0] == 'k' ? k32 : crt;
        *imp.original = from ? (void*)GetProcAddress(from, imp.name) : nullptr;
        if (!*imp.original) continue;  // never patch a slot we could not pass through
        if (PatchImport(GetModuleHandleA(nullptr), imp.dll, imp.name, imp.hook, *imp.original)) ++patched;
        if (hybrid && PatchImport(hybrid, imp.dll, imp.name, imp.hook, *imp.original)) ++patched;
    }
    return s_result = patched;
}
