// Test of filenames.cpp (game file names on UTF-8 Windows), without the game.
//
// The exe declares UTF-8 as its code page in its manifest, redirects its own file imports
// with InstallFileNameHooks and then calls the "A" functions the way Wiz8.exe does, with
// names in cp1251 bytes: for this system's ANSI code page, then as on cp1251 and cp1252
// systems, and a double-byte check as on cp932. Run: build\test_filenames.exe [work folder]
// (default: next to the exe). Prints PASS/FAIL per check; the exit code is the number of failures.

#include <windows.h>

#include <stdio.h>
#include <string.h>
#include <wchar.h>

#include <set>
#include <string>

#include "../filenames.h"

static int g_failures = 0;

static void Check(bool ok, const char* what)
{
    printf("%s  %s\n", ok ? "PASS" : "FAIL", what);
    if (!ok) ++g_failures;
}

// Bytes in the file-name code page -> what the file must be called on disk.
static std::wstring OnDisk(const std::string& bytes)
{
    wchar_t w[MAX_PATH];
    int n = MultiByteToWideChar(FileNameCodePage(), 0, bytes.c_str(), -1, w, MAX_PATH);
    return n > 0 ? std::wstring(w) : std::wstring();
}

static std::set<std::wstring> ListW(const wchar_t* pattern)
{
    std::set<std::wstring> names;
    WIN32_FIND_DATAW f;
    HANDLE h = FindFirstFileW(pattern, &f);
    if (h == INVALID_HANDLE_VALUE) return names;
    do {
        if (!(f.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) names.insert(f.cFileName);
    } while (FindNextFileW(h, &f));
    FindClose(h);
    return names;
}

static std::set<std::string> ListA(const char* pattern)
{
    std::set<std::string> names;
    WIN32_FIND_DATAA f;
    HANDLE h = FindFirstFileA(pattern, &f);
    if (h == INVALID_HANDLE_VALUE) return names;
    do {
        if (!(f.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) names.insert(f.cFileName);
    } while (FindNextFileA(h, &f));
    FindClose(h);
    return names;
}

static bool CreateA(const std::string& path)
{
    HANDLE h = CreateFileA(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;
    DWORD written;
    WriteFile(h, "chr", 3, &written, nullptr);
    CloseHandle(h);
    return true;
}

static bool CreateW(const std::wstring& path)
{
    HANDLE h = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;
    CloseHandle(h);
    return true;
}

static bool ExistsA(const std::string& path)
{
    return GetFileAttributesA(path.c_str()) != INVALID_FILE_ATTRIBUTES;
}

static std::string Utf8(const std::wstring& w)
{
    char s[MAX_PATH * 3];
    int n = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), -1, s, sizeof(s), nullptr, nullptr);
    return n > 0 ? std::string(s) : std::string();
}

static void DeleteTree(const std::wstring& dir)
{
    WIN32_FIND_DATAW f;
    HANDLE h = FindFirstFileW((dir + L"\\*").c_str(), &f);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            std::wstring name = f.cFileName;
            if (name == L"." || name == L"..") continue;
            std::wstring path = dir + L"\\" + name;
            if (f.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
                DeleteTree(path);
            } else {
                SetFileAttributesW(path.c_str(), FILE_ATTRIBUTE_NORMAL);
                DeleteFileW(path.c_str());
            }
        } while (FindNextFileW(h, &f));
        FindClose(h);
    }
    RemoveDirectoryW(dir.c_str());
}

// Work folder with a name that needs UTF-8 (a check mark fits no legacy code page), like a
// game folder under C:\Users\<Cyrillic name>; made fresh, entered, and its path returned.
static std::wstring EnterWorkFolder(const std::wstring& base)
{
    std::wstring root = base + L"\\test_filenames \u0418\u0433\u0440\u044b \u2713";
    DeleteTree(root);
    CreateDirectoryW(root.c_str(), nullptr);
    Check(SetCurrentDirectoryW(root.c_str()) != FALSE, "work folder created");
    return root;
}

// The game's flows with names in cp1251 bytes, for the current file-name code page.
static void RunSuite(const std::wstring& base)
{
    printf("-- names read as code page %u\n", FileNameCodePage());
    std::wstring root = EnterWorkFolder(base);

    // Nicknames in cp1251 bytes, as the game makes them with sprintf("%ls"): Иван, Петя
    // (same length: without the fix both become U+FFFD x4 and collide), and Васян.
    const std::string ivan = "\xC8\xE2\xE0\xED", petya = "\xCF\xE5\xF2\xFF", vasyan = "\xC2\xE0\xF1\xFF\xED";
    Check(CreateDirectoryA("Characters", nullptr) != FALSE, "CreateDirectoryA (English name)");
    Check(CreateA("Characters\\" + ivan + ".CHR"), "CreateFileA: first nickname");
    Check(CreateA("Characters\\" + petya + ".CHR"), "CreateFileA: second nickname of the same length (no collision)");
    std::set<std::wstring> disk = ListW(L"Characters\\*");
    Check(disk.size() == 2 && disk.count(OnDisk(ivan + ".CHR")) && disk.count(OnDisk(petya + ".CHR")),
          "on disk the names are in the file-name code page, as without the UTF-8 option");

    // A file made by the game while the option was off (same code page) and one made by the
    // unpatched game with the option on (U+FFFD): both must be listed and open again.
    Check(CreateW(L"Characters\\" + OnDisk(vasyan + ".CHR")), "older file (made without the option) placed");
    Check(CreateW(L"Characters\\\uFFFD\uFFFD\uFFFD.CHR"), "file with U+FFFD in its name placed");
    // A name that fits no single-byte code page together (Japanese + Cyrillic + check mark).
    Check(CreateW(L"Characters\\\u65e5\u0416\u2713.CHR"), "file with a name outside the code page placed");
    std::set<std::string> listed = ListA("Characters\\*.CHR");
    Check(listed.size() == 5, "FindFirstFileA/FindNextFileA list all five files");
    Check(listed.count(ivan + ".CHR") && listed.count(petya + ".CHR"), "the game gets its own names back byte for byte");
    Check(listed.count(vasyan + ".CHR") != 0, "the older file comes back with its original bytes");
    for (const std::string& name : listed) {
        std::string path = "Characters\\" + name;
        HANDLE h = CreateFileA(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, 0, nullptr);
        bool ok = h != INVALID_HANDLE_VALUE;
        if (ok) CloseHandle(h);
        char what[200];
        snprintf(what, sizeof(what), "every listed name opens again with CreateFileA (%u bytes)", (unsigned)name.size());
        Check(ok, what);
    }

    // Absolute path: the folder part comes from Windows in UTF-8 (GetModuleFileNameA in the
    // game), the name part is the game's.
    std::string absolute = Utf8(root) + "\\Characters\\" + ivan + ".CHR";
    Check(ExistsA(absolute), "absolute path: UTF-8 folder + cp1251 name");

    // The other functions the game uses.
    Check(MoveFileA(("Characters\\" + petya + ".CHR").c_str(), ("Characters\\" + petya + "2.CHR").c_str()) != FALSE &&
              ExistsA("Characters\\" + petya + "2.CHR") && !ExistsA("Characters\\" + petya + ".CHR"),
          "MoveFileA");
    Check(CopyFileA(("Characters\\" + petya + "2.CHR").c_str(), ("Characters\\" + vasyan + "2.CHR").c_str(), TRUE) != FALSE &&
              ListW(L"Characters\\*").count(OnDisk(vasyan + "2.CHR")),
          "CopyFileA");
    std::string copy = "Characters\\" + vasyan + "2.CHR";
    Check(SetFileAttributesA(copy.c_str(), FILE_ATTRIBUTE_READONLY) != FALSE &&
              (GetFileAttributesA(copy.c_str()) & FILE_ATTRIBUTE_READONLY),
          "SetFileAttributesA / GetFileAttributesA");
    SetFileAttributesA(copy.c_str(), FILE_ATTRIBUTE_NORMAL);
    Check(DeleteFileA(copy.c_str()) != FALSE && !ExistsA(copy), "DeleteFileA");

    // Two Cyrillic letters whose cp1251 bytes happen to be valid UTF-8 (Рё = D0 B8 = "и"): the
    // name is read as UTF-8 (the known ambiguity), and whatever comes back must open that file.
    const std::string rare = "\xD0\xB8.CHR";
    std::set<std::string> before = ListA("Characters\\*.CHR");
    Check(CreateA("Characters\\" + rare), "CreateFileA: name whose bytes are also valid UTF-8");
    Check(ListW(L"Characters\\*").count(L"и.CHR") != 0, "that name is stored under its UTF-8 meaning");
    std::string back;
    for (const std::string& name : ListA("Characters\\*.CHR")) {
        if (!before.count(name)) back = name;
    }
    Check(!back.empty() && ExistsA("Characters\\" + back), "the listed name opens that file again");

    // English names are passed through unchanged.
    Check(CreateA("Characters\\Plain.CHR") && ListW(L"Characters\\*").count(L"Plain.CHR"), "English name unchanged");

    // An ini file with a Cyrillic name.
    std::wstring ini = root + L"\\" + OnDisk(ivan + ".ini");
    WritePrivateProfileStringW(L"S", L"K", L"42", ini.c_str());
    Check(GetPrivateProfileIntA("S", "K", 0, (Utf8(root) + "\\" + ivan + ".ini").c_str()) == 42, "GetPrivateProfileIntA");

    SetCurrentDirectoryW(base.c_str());
    DeleteTree(root);
}

// Double-byte code page (Japanese, 932): its own names work, and a name whose encoding has a
// '\' as its second byte ("ソ" = 83 5C) comes back as UTF-8, so the path is not split there.
static void RunDoubleByteCheck(const std::wstring& base)
{
    printf("-- names read as code page %u\n", FileNameCodePage());
    std::wstring root = EnterWorkFolder(base);
    const std::string nihon = "\x93\xFA\x96\x7B.SAV";  // "日本" in cp932
    Check(CreateA(nihon), "CreateFileA: cp932 name");
    Check(ListW(L"*.SAV").count(L"日本.SAV") != 0, "stored as the Japanese name");
    Check(CreateW(L"ソ.SAV"), "file whose cp932 name has 0x5C inside placed");
    std::set<std::string> listed = ListA("*.SAV");
    Check(listed.size() == 2 && listed.count(nihon), "both listed, the cp932 name byte for byte");
    bool all = true;
    for (const std::string& name : listed) all = all && ExistsA(name);
    Check(all, "every listed name opens again (no split at 0x5C)");
    SetCurrentDirectoryW(base.c_str());
    DeleteTree(root);
}

int wmain(int argc, wchar_t** argv)
{
    printf("process code page %u\n", GetACP());
    int redirected = InstallFileNameHooks(nullptr);
    printf("redirected imports: %d, system ANSI code page %u\n", redirected, FileNameCodePage());
    Check(GetACP() == CP_UTF8, "the process runs with the UTF-8 code page (manifest)");
    Check(redirected >= 8, "the file imports of the exe are redirected");

    wchar_t base[MAX_PATH];
    if (argc > 1) {
        lstrcpynW(base, argv[1], MAX_PATH);
    } else {
        GetModuleFileNameW(nullptr, base, MAX_PATH);
        *wcsrchr(base, L'\\') = 0;
    }
    // This system's code page, then as on Russian and Western European systems.
    UINT system = FileNameCodePage();
    RunSuite(base);
    for (UINT cp : {1251u, 1252u}) {
        if (cp == system) continue;
        SetFileNameCodePage(cp);
        RunSuite(base);
    }
    SetFileNameCodePage(932);
    RunDoubleByteCheck(base);
    SetFileNameCodePage(system);

    printf("%s: %d failure(s)\n", g_failures ? "FAILED" : "OK", g_failures);
    return g_failures;
}
