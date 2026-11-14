// Finding Wizardry 8 under Wine: the launchers' own files (see wine_find.h).
//
// The files read here are written by Linux programs, in UTF-8:
//   - Steam: steamapps\libraryfolders.vdf (the libraries) and steamapps\appmanifest_245450.acf
//     (the Steam game), in Steam's text format: "key"  "value" lines and { } blocks;
//     userdata\<user>\config\shortcuts.vdf (the non-Steam games), in Steam's binary format;
//   - Heroic: JSON (gog_store\installed.json, sideload_apps\library.json, GamesConfig\<id>.json);
//   - Lutris: games\*.yml, YAML as Python's yaml.safe_dump writes it.
// Only the few values needed are read, and a file that cannot be read is skipped: a broken or
// unusual launcher file must never stop the installer (the player can still pick the folder).

#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>

#include <algorithm>
#include <cctype>
#include <string>
#include <vector>

#include "wine_find.h"
#include "../../src/wine_overrides.h" /* FolderId, SameFolder, TrimSlashes */

namespace wine {

namespace {

/* ---------------- text and files ---------------- */

/* UTF-8 (the launchers' files, Linux paths) to Windows' UTF-16, and back */
std::wstring Widen(const std::string& text)
{
    int size = MultiByteToWideChar(CP_UTF8, 0, text.data(), (int)text.size(), 0, 0);
    std::wstring wide(size > 0 ? size : 0, L'\0');
    if (size > 0) {
        MultiByteToWideChar(CP_UTF8, 0, text.data(), (int)text.size(), &wide[0], size);
    }
    return wide;
}

std::string Narrow(const std::wstring& text)
{
    int size = WideCharToMultiByte(CP_UTF8, 0, text.data(), (int)text.size(), 0, 0, 0, 0);
    std::string bytes(size > 0 ? size : 0, '\0');
    if (size > 0) {
        WideCharToMultiByte(CP_UTF8, 0, text.data(), (int)text.size(), &bytes[0], size, 0, 0);
    }
    return bytes;
}

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

bool DirExists(const std::wstring& path)
{
    DWORD attr = GetFileAttributesW(path.c_str());
    return attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY);
}

/* "Z:\a\b\Wiz8.exe" -> "Z:\a\b" (a drive root keeps its backslash: "C:\") */
std::wstring Parent(const std::wstring& path)
{
    size_t slash = path.find_last_of(L"\\/");
    if (slash == std::wstring::npos) {
        return std::wstring();
    }
    return path.substr(0, slash == 2 && path[1] == L':' ? 3 : slash);
}

std::wstring BaseName(const std::wstring& path)
{
    size_t slash = path.find_last_of(L"\\/");
    return slash == std::wstring::npos ? path : path.substr(slash + 1);
}

/* The whole file; false if it cannot be read or is bigger than the limit (no launcher file is
   anywhere near it). Others may have it open (Steam keeps its files open): read sharing. */
bool ReadBytes(const std::wstring& path, std::string* out, DWORD limit = 16u << 20)
{
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, 0,
                              OPEN_EXISTING, 0, 0);
    if (file == INVALID_HANDLE_VALUE) {
        return false;
    }
    DWORD size = GetFileSize(file, 0);
    DWORD read = 0;
    bool ok = size != INVALID_FILE_SIZE && size <= limit;
    if (ok) {
        out->assign(size, '\0');
        ok = size == 0 || (ReadFile(file, &(*out)[0], size, &read, 0) && read == size);
    }
    CloseHandle(file);
    if (ok && out->compare(0, 3, "\xEF\xBB\xBF") == 0) {
        out->erase(0, 3); /* a UTF-8 mark at the start */
    }
    return ok;
}

/* The names of the folders (folders = true) or files in a folder */
std::vector<std::wstring> ListFolder(const std::wstring& dir, bool folders)
{
    std::vector<std::wstring> names;
    WIN32_FIND_DATAW data;
    HANDLE find = FindFirstFileW(Join(dir, L"*").c_str(), &data);
    if (find == INVALID_HANDLE_VALUE) {
        return names;
    }
    do {
        std::wstring name = data.cFileName;
        bool folder = (data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
        if (name != L"." && name != L".." && folder == folders) {
            names.push_back(name);
        }
    } while (FindNextFileW(find, &data));
    FindClose(find);
    return names;
}

/* The lines of a text, without their line ends */
std::vector<std::string> Lines(const std::string& text)
{
    std::vector<std::string> lines;
    for (size_t start = 0; start < text.size();) {
        size_t end = text.find('\n', start);
        if (end == std::string::npos) {
            end = text.size();
        }
        std::string line = text.substr(start, end - start);
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        lines.push_back(line);
        start = end + 1;
    }
    return lines;
}

/* A Unicode code point appended as UTF-8 (for the \u escapes of JSON and YAML) */
void AppendUtf8(std::string* text, unsigned int code)
{
    if (code < 0x80) {
        *text += (char)code;
    } else if (code < 0x800) {
        *text += (char)(0xC0 | code >> 6);
        *text += (char)(0x80 | (code & 0x3F));
    } else if (code < 0x10000) {
        *text += (char)(0xE0 | code >> 12);
        *text += (char)(0x80 | (code >> 6 & 0x3F));
        *text += (char)(0x80 | (code & 0x3F));
    } else if (code < 0x110000) {
        *text += (char)(0xF0 | code >> 18);
        *text += (char)(0x80 | (code >> 12 & 0x3F));
        *text += (char)(0x80 | (code >> 6 & 0x3F));
        *text += (char)(0x80 | (code & 0x3F));
    }
}

/* The value of a hex digit, or -1 */
int HexDigit(char c)
{
    if (c >= '0' && c <= '9') {
        return c - '0';
    }
    c = (char)(c | 0x20);
    return c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
}

/* An environment variable of this program, as UTF-8 (the Steam variables hold Linux paths) */
std::string EnvText(const wchar_t* name)
{
    DWORD size = GetEnvironmentVariableW(name, 0, 0);
    if (size == 0) {
        return std::string();
    }
    std::wstring value(size, L'\0');
    DWORD length = GetEnvironmentVariableW(name, &value[0], size);
    value.resize(length < size ? length : 0);
    return Narrow(value);
}

/* WINEHOMEDIR and WINECONFIGDIR hold NT paths: "\??\Z:\home\deck", or "\??\unix\home\deck" when
   no drive maps the folder. As a path a program can open: "Z:\home\deck", "\\?\unix\home\deck". */
std::wstring EnvFolder(const wchar_t* name)
{
    std::wstring value = Widen(EnvText(name));
    if (value.compare(0, 4, L"\\??\\") == 0) {
        value = value.size() > 5 && value[5] == L':' ? value.substr(4) : L"\\\\?\\" + value.substr(4);
    }
    return value;
}

/* A path from a launcher's settings: a Linux path, where Heroic and Lutris also allow "~" for
   the home folder. "~/x" is joined to the home folder as this program sees it (FromUnix of the
   home folder's Linux name would need that name, which Wine does not give). */
std::wstring FromLauncher(const std::string& path)
{
    if (path == "~" || path.compare(0, 2, "~/") == 0) {
        std::wstring home = HomeFolder();
        if (home.empty()) {
            return std::wstring();
        }
        std::wstring rest = Widen(path.substr(path.size() > 1 ? 2 : 1));
        for (wchar_t& c : rest) {
            if (c == L'/') {
                c = L'\\';
            }
        }
        return rest.empty() ? home : Join(home, rest);
    }
    return FromUnix(path);
}

void Add(std::vector<Candidate>* places, const std::wstring& folder, Source source,
         const std::vector<std::wstring>& prefixes, const std::wstring& label = std::wstring())
{
    if (folder.empty()) {
        return;
    }
    Candidate place;
    place.folder = folder;
    place.source = source;
    place.label = label;
    place.prefixes = prefixes;
    places->push_back(place);
}

/* ---------------- Steam's text files ---------------- */

/* The value of "key" on a line of a Steam text file, such as
       "path"		"/run/media/deck/SD card"
   with the \\ and \" escapes undone; false when the line does not start with that key. A line
   reader, as setup.cpp's FindSteam on Windows, is enough for the two keys read here (path in
   libraryfolders.vdf, installdir in an appmanifest). */
bool VdfValue(const std::string& line, const char* key, std::string* value)
{
    size_t start = line.find_first_not_of(" \t");
    std::string quoted = std::string("\"") + key + "\"";
    if (start == std::string::npos ||
        CompareStringA(LOCALE_INVARIANT, NORM_IGNORECASE, line.c_str() + start,
                       (int)std::min(quoted.size(), line.size() - start), quoted.c_str(),
                       (int)quoted.size()) != CSTR_EQUAL) {
        return false;
    }
    size_t open = line.find('"', start + quoted.size());
    if (open == std::string::npos) {
        return false;
    }
    value->clear();
    for (size_t i = open + 1; i < line.size(); ++i) {
        if (line[i] == '"') {
            return true;
        }
        if (line[i] == '\\' && i + 1 < line.size()) {
            ++i; /* \\ is one backslash, \" a quote */
        }
        *value += line[i];
    }
    return false; /* no closing quote */
}

/* ---------------- Steam's shortcuts.vdf (binary) ---------------- */

/* One non-Steam game of shortcuts.vdf, as stored (Exe and StartDir usually in quotes) */
struct Shortcut {
    bool has_appid = false;
    unsigned int appid = 0;
    std::string name, exe, start;
};

/* shortcuts.vdf: a tree of entries, each a type byte, a name (ending in a 0 byte), then the
   value: 0x00 a block of entries (until 0x08), 0x01 UTF-8 text ending in 0, 0x02 a 32-bit
   number, 0x03 a float, 0x04 a pointer, 0x06 a colour (4 bytes each), 0x05 UTF-16 text ending in
   two 0 bytes, 0x07 and 0x0A 64-bit numbers. The file is a block "shortcuts" holding one block
   per game ("0", "1", ...), whose entries are AppName, Exe, StartDir, appid, ... (older files
   write them in lower case). false if the file does not parse to its end. */
bool ParseShortcuts(const std::string& bytes, std::vector<Shortcut>* out)
{
    size_t i = 0;
    int depth = 0;
    Shortcut current;
    auto text = [&](std::string* value) {
        size_t end = bytes.find('\0', i);
        if (end == std::string::npos) {
            return false;
        }
        *value = bytes.substr(i, end - i);
        i = end + 1;
        return true;
    };
    while (i < bytes.size()) {
        unsigned char type = (unsigned char)bytes[i++];
        if (type == 0x08 || type == 0x0B) { /* end of a block (0x0B in some writers) */
            if (depth == 2) {
                out->push_back(current);
            }
            if (--depth <= 0) {
                return true;
            }
            continue;
        }
        std::string key;
        if (!text(&key)) {
            return false;
        }
        CharLowerBuffA(&key[0], (DWORD)key.size());
        if (type == 0x00) {
            if (++depth > 16) {
                return false;
            }
            if (depth == 2) {
                current = Shortcut();
            }
        } else if (type == 0x01) {
            std::string value;
            if (!text(&value)) {
                return false;
            }
            if (depth == 2 && key == "appname") {
                current.name = value;
            } else if (depth == 2 && key == "exe") {
                current.exe = value;
            } else if (depth == 2 && key == "startdir") {
                current.start = value;
            }
        } else if (type == 0x05) {
            size_t end = i;
            while (end + 1 < bytes.size() && (bytes[end] || bytes[end + 1])) {
                end += 2;
            }
            if (end + 1 >= bytes.size()) {
                return false;
            }
            i = end + 2;
        } else if (type == 0x02 || type == 0x03 || type == 0x04 || type == 0x06) {
            if (i + 4 > bytes.size()) {
                return false;
            }
            if (depth == 2 && key == "appid" && type == 0x02) {
                /* stored as a signed number; the prefix folder uses it unsigned */
                current.appid = (unsigned char)bytes[i] | (unsigned char)bytes[i + 1] << 8 |
                                (unsigned char)bytes[i + 2] << 16 |
                                (unsigned int)(unsigned char)bytes[i + 3] << 24;
                current.has_appid = true;
            }
            i += 4;
        } else if (type == 0x07 || type == 0x0A) {
            if (i + 8 > bytes.size()) {
                return false;
            }
            i += 8;
        } else {
            return false;
        }
    }
    return false;
}

/* A Steam field without the spaces around it and one pair of quotes ("\"/home/x/Wiz8.exe\"") */
std::string Unquote(const std::string& field)
{
    size_t first = field.find_first_not_of(" \t");
    size_t last = field.find_last_not_of(" \t");
    std::string value = first == std::string::npos ? std::string() : field.substr(first, last - first + 1);
    if (value.size() >= 2 && value.front() == '"' && value.back() == '"') {
        value = value.substr(1, value.size() - 2);
    }
    return value;
}

/* CRC-32 (the zip one), from which Steam made the id of an old shortcut without an appid */
unsigned int Crc32(const std::string& text)
{
    unsigned int crc = 0xFFFFFFFF;
    for (unsigned char c : text) {
        crc ^= c;
        for (int bit = 0; bit < 8; ++bit) {
            crc = (crc >> 1) ^ (0xEDB88320 & (0 - (crc & 1)));
        }
    }
    return ~crc;
}

/* ---------------- JSON (Heroic) ---------------- */

/* A JSON value: text and numbers are kept as text, objects as name/value pairs in file order */
struct Json {
    enum Type { NONE, TEXT, OTHER, LIST, OBJECT } type = NONE;
    std::string text;
    std::vector<Json> items;
    std::vector<std::pair<std::string, Json>> members;

    const Json* Member(const std::string& name) const
    {
        for (const auto& member : members) {
            if (member.first == name) {
                return &member.second;
            }
        }
        return nullptr;
    }
    std::string Text(const char* name) const
    {
        const Json* value = Member(name);
        return value && value->type == TEXT ? value->text : std::string();
    }
};

class JsonReader {
public:
    explicit JsonReader(const std::string& text) : text_(text) {}

    /* false when the text is not JSON (or nests deeper than any launcher file does) */
    bool Value(Json* out, int depth = 0)
    {
        Space();
        if (depth > 64 || at_ >= text_.size()) {
            return false;
        }
        char c = text_[at_];
        if (c == '{') {
            out->type = Json::OBJECT;
            ++at_;
            if (Next('}')) {
                return true;
            }
            for (;;) {
                Space();
                std::string name;
                if (!String(&name) || !Next(':')) {
                    return false;
                }
                out->members.push_back({name, Json()});
                if (!Value(&out->members.back().second, depth + 1)) {
                    return false;
                }
                if (Next(',')) {
                    continue;
                }
                return Next('}');
            }
        }
        if (c == '[') {
            out->type = Json::LIST;
            ++at_;
            if (Next(']')) {
                return true;
            }
            for (;;) {
                out->items.push_back(Json());
                if (!Value(&out->items.back(), depth + 1)) {
                    return false;
                }
                if (Next(',')) {
                    continue;
                }
                return Next(']');
            }
        }
        if (c == '"') {
            out->type = Json::TEXT;
            return String(&out->text);
        }
        /* a number, true, false or null */
        size_t start = at_;
        while (at_ < text_.size() && (isalnum((unsigned char)text_[at_]) || text_[at_] == '-' ||
                                      text_[at_] == '+' || text_[at_] == '.')) {
            ++at_;
        }
        out->type = Json::OTHER;
        out->text = text_.substr(start, at_ - start);
        return at_ > start;
    }

private:
    void Space()
    {
        while (at_ < text_.size() && (text_[at_] == ' ' || text_[at_] == '\t' || text_[at_] == '\r' ||
                                      text_[at_] == '\n')) {
            ++at_;
        }
    }
    /* the next character (after spaces) is c: then it is taken */
    bool Next(char c)
    {
        Space();
        if (at_ < text_.size() && text_[at_] == c) {
            ++at_;
            return true;
        }
        return false;
    }
    bool Hex4(unsigned int* code)
    {
        if (at_ + 4 > text_.size()) {
            return false;
        }
        *code = 0;
        for (int k = 0; k < 4; ++k) {
            int digit = HexDigit(text_[at_++]);
            if (digit < 0) {
                return false;
            }
            *code = *code * 16 + digit;
        }
        return true;
    }
    /* "text" with JSON's escapes: \" \\ \/ \n \t ..., \uXXXX (UTF-16, so two of them for a
       character beyond the first 65536) */
    bool String(std::string* out)
    {
        if (at_ >= text_.size() || text_[at_] != '"') {
            return false;
        }
        for (++at_; at_ < text_.size();) {
            char c = text_[at_++];
            if (c == '"') {
                return true;
            }
            if (c != '\\') {
                *out += c;
                continue;
            }
            if (at_ >= text_.size()) {
                return false;
            }
            char e = text_[at_++];
            if (e == 'u') {
                unsigned int code, low;
                if (!Hex4(&code)) {
                    return false;
                }
                if (code >= 0xD800 && code < 0xDC00 && text_.compare(at_, 2, "\\u") == 0) {
                    at_ += 2;
                    if (!Hex4(&low)) {
                        return false;
                    }
                    code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00);
                }
                AppendUtf8(out, code);
            } else {
                *out += e == 'n' ? '\n' : e == 't' ? '\t' : e == 'r' ? '\r' : e == 'b' ? '\b'
                      : e == 'f' ? '\f' : e;
            }
        }
        return false;
    }

    const std::string& text_;
    size_t at_ = 0;
};

bool LoadJson(const std::wstring& path, Json* out)
{
    std::string text;
    return ReadBytes(path, &text) && JsonReader(text).Value(out);
}

/* ---------------- YAML (Lutris) ---------------- */

/* The "key: value" pairs of one top-level section of a Lutris game file, such as
       game:
         exe: /home/deck/Games/wizardry-8/drive_c/GOG Games/Wizardry 8/Wiz8.exe
         prefix: /home/deck/Games/wizardry-8
   The values as yaml.safe_dump writes them: plain (a long one goes on over more deeply
   indented lines, joined with one space; "null" or "~" is no value), in 'single quotes' ('' is
   one quote) or in "double quotes" (\uXXXX and other escapes for non-ASCII and special
   characters; a line ending in \ goes on without a space, "\ " is a space). */
std::vector<std::pair<std::string, std::string>> YamlSection(const std::string& text,
                                                             const std::string& section)
{
    std::vector<std::pair<std::string, std::string>> values;
    std::vector<std::string> lines = Lines(text);
    auto indent = [&](size_t k) {
        size_t first = lines[k].find_first_not_of(' ');
        return first == std::string::npos ? std::string::npos : first;
    };
    bool inside = false;
    for (size_t k = 0; k < lines.size(); ++k) {
        size_t depth = indent(k);
        if (depth == std::string::npos || lines[k][depth] == '#') {
            continue; /* empty line or comment */
        }
        if (depth == 0) {
            inside = lines[k] == section + ":";
            continue;
        }
        size_t colon = lines[k].find(": ", depth);
        if (!inside || depth != 2 || colon == std::string::npos) {
            continue;
        }
        std::string key = lines[k].substr(depth, colon - depth);
        std::string raw = lines[k].substr(colon + 2);
        /* the lines the value goes on over: indented more than the key */
        std::vector<std::string> more;
        while (k + 1 < lines.size() && indent(k + 1) != std::string::npos && indent(k + 1) > depth) {
            ++k;
            more.push_back(lines[k].substr(indent(k)));
        }
        std::string value;
        if (!raw.empty() && raw[0] == '\'') {
            std::string all = raw.substr(1);
            for (const std::string& line : more) {
                all += " " + line;
            }
            for (size_t i = 0; i < all.size(); ++i) {
                if (all[i] != '\'') {
                    value += all[i];
                } else if (i + 1 < all.size() && all[i + 1] == '\'') {
                    value += '\'';
                    ++i;
                } else {
                    break; /* the closing quote */
                }
            }
        } else if (!raw.empty() && raw[0] == '"') {
            std::vector<std::string> parts = {raw.substr(1)};
            parts.insert(parts.end(), more.begin(), more.end());
            bool closed = false;
            for (size_t p = 0; p < parts.size() && !closed; ++p) {
                const std::string& part = parts[p];
                bool joined = false; /* the line ended in \: no space before the next one */
                for (size_t i = 0; i < part.size(); ++i) {
                    char c = part[i];
                    if (c == '"') {
                        closed = true;
                        break;
                    }
                    if (c != '\\') {
                        value += c;
                        continue;
                    }
                    if (i + 1 >= part.size()) {
                        joined = true;
                        break;
                    }
                    char e = part[++i];
                    int digits = e == 'x' ? 2 : e == 'u' ? 4 : e == 'U' ? 8 : 0;
                    if (digits) {
                        unsigned int code = 0;
                        for (int d = 0; d < digits && i + 1 < part.size(); ++d) {
                            int digit = HexDigit(part[++i]);
                            code = code * 16 + (digit < 0 ? 0 : digit);
                        }
                        AppendUtf8(&value, code);
                    } else {
                        value += e == 'n' ? '\n' : e == 't' ? '\t' : e; /* \\ \" "\ " ... */
                    }
                }
                if (!closed && !joined && p + 1 < parts.size()) {
                    value += ' ';
                }
            }
        } else {
            value = raw;
            for (const std::string& line : more) {
                value += " " + line;
            }
            size_t comment = value.find(" #");
            if (comment != std::string::npos) {
                value.resize(comment);
            }
            while (!value.empty() && value.back() == ' ') {
                value.pop_back();
            }
            if (value == "~" || value == "null") {
                value.clear();
            }
        }
        values.push_back({key, value});
    }
    return values;
}

std::string YamlValue(const std::vector<std::pair<std::string, std::string>>& values, const char* key)
{
    for (const auto& value : values) {
        if (value.first == key) {
            return value.second;
        }
    }
    return std::string();
}

/* ---------------- the launchers ---------------- */

/* Adds a library (a folder with steamapps\) unless it is listed already, under any name */
void AddLibrary(std::vector<std::wstring>* libraries, const std::wstring& path)
{
    std::wstring folder = TrimSlashes(path);
    if (folder.empty() || !DirExists(Join(folder, L"steamapps"))) {
        return;
    }
    for (const std::wstring& known : *libraries) {
        if (SameFolder(known, folder, L"steamapps")) {
            return;
        }
    }
    libraries->push_back(folder);
}

/* Steam's own folders ("roots": Steam installed natively, as a flatpak or a snap; ~/.steam/steam
   and ~/.steam/root are links to one of them) and its libraries: each root, the libraries its
   libraryfolders.vdf lists (an SD card, another disk), and those Proton was told about. */
void FindSteamFolders(const std::wstring& home, std::vector<std::wstring>* roots,
                      std::vector<std::wstring>* libraries)
{
    std::vector<std::wstring> places;
    std::string client = EnvText(L"STEAM_COMPAT_CLIENT_INSTALL_PATH"); /* set by Steam for Proton */
    if (!client.empty()) {
        places.push_back(FromUnix(client));
    }
    if (!home.empty()) {
        for (const wchar_t* root : {L".local\\share\\Steam", L".steam\\steam", L".steam\\root",
                                    L".var\\app\\com.valvesoftware.Steam\\.local\\share\\Steam",
                                    L".var\\app\\com.valvesoftware.Steam\\data\\Steam",
                                    L"snap\\steam\\common\\.local\\share\\Steam"}) {
            places.push_back(Join(home, root));
        }
    }
    for (const std::wstring& place : places) {
        size_t before = libraries->size();
        AddLibrary(libraries, place);
        if (libraries->size() == before) {
            continue; /* not a Steam folder, or one already seen */
        }
        roots->push_back(libraries->back());
        std::string text;
        ReadBytes(Join(libraries->back(), L"steamapps\\libraryfolders.vdf"), &text);
        for (const std::string& line : Lines(text)) {
            std::string path;
            if (VdfValue(line, "path", &path)) {
                AddLibrary(libraries, FromUnix(path));
            }
        }
    }
    /* STEAM_COMPAT_LIBRARY_PATHS: "<library>/steamapps:<library 2>/steamapps" */
    std::string list = EnvText(L"STEAM_COMPAT_LIBRARY_PATHS");
    for (size_t start = 0; start < list.size();) {
        size_t end = list.find(':', start);
        if (end == std::string::npos) {
            end = list.size();
        }
        std::string one = list.substr(start, end - start);
        if (one.size() > 10 && one.compare(one.size() - 10, 10, "/steamapps") == 0) {
            AddLibrary(libraries, FromUnix(one.substr(0, one.size() - 10)));
        }
        start = end + 1;
    }
}

/* The prefix folder Proton uses for a game: compatdata\<id>\pfx, in any library */
std::vector<std::wstring> SteamPrefixes(const std::vector<std::wstring>& libraries, unsigned int id)
{
    std::vector<std::wstring> prefixes;
    for (const std::wstring& library : libraries) {
        prefixes.push_back(Join(library, L"steamapps\\compatdata\\" + std::to_wstring(id) + L"\\pfx"));
    }
    return prefixes;
}

/* Non-Steam games (a GOG copy added to Steam): every Steam user's shortcuts.vdf. The game folder
   is the folder of Exe when that is Wiz8.exe, or StartDir; a shortcut that starts a launcher
   (Heroic's "heroic://launch/...") is not a game folder and is left to that launcher's search.
   A shortcut that starts this installer (added to Steam to run it with Proton, as the README
   says) is not the game's either, though its StartDir is the game folder when the package was
   unpacked there: its prefix is the installer's, where the game need not run. */
void FindShortcuts(const std::vector<std::wstring>& roots, const std::vector<std::wstring>& libraries,
                   std::vector<Candidate>* places)
{
    wchar_t self[MAX_PATH * 2];
    DWORD length = GetModuleFileNameW(0, self, MAX_PATH * 2);
    std::wstring installer = length > 0 && length < MAX_PATH * 2 ? BaseName(self) : std::wstring();
    for (const std::wstring& root : roots) {
        std::wstring userdata = Join(root, L"userdata");
        for (const std::wstring& user : ListFolder(userdata, true)) {
            std::string bytes;
            std::vector<Shortcut> shortcuts;
            if (!ReadBytes(Join(Join(userdata, user), L"config\\shortcuts.vdf"), &bytes) ||
                !ParseShortcuts(bytes, &shortcuts)) {
                continue;
            }
            for (const Shortcut& shortcut : shortcuts) {
                /* the prefix folder is named by the shortcut's id; a shortcut without an appid
                   (an old one) has the id Steam made from its Exe (as stored) and name */
                unsigned int id = shortcut.has_appid ? shortcut.appid
                                                     : Crc32(shortcut.exe + shortcut.name) | 0x80000000u;
                std::vector<std::wstring> prefixes = SteamPrefixes(libraries, id);
                std::wstring name = Widen(shortcut.name);
                std::wstring exe = FromUnix(Unquote(shortcut.exe));
                if (lstrcmpiW(BaseName(exe).c_str(), L"Wiz8.exe") == 0) {
                    Add(places, Parent(exe), SOURCE_SHORTCUT, prefixes, name);
                }
                if (lstrcmpiW(BaseName(exe).c_str(), L"Wiz8WideSetup.exe") == 0 ||
                    (!installer.empty() && lstrcmpiW(BaseName(exe).c_str(), installer.c_str()) == 0)) {
                    continue; /* this installer (under its usual name or the one it runs under) */
                }
                std::string start = Unquote(shortcut.start);
                if (!start.empty()) {
                    Add(places, FromUnix(start), SOURCE_SHORTCUT, prefixes, name);
                }
            }
        }
    }
}

/* Heroic (natively or as a flatpak): its GOG games (gog_store\installed.json) and the games
   added by hand ("sideloaded", sideload_apps\library.json); the prefix of each is in
   GamesConfig\<id>.json. With Proton the prefix is <winePrefix>\pfx (umu makes pfx a link to
   the folder itself), so both are listed. */
void FindHeroic(const std::wstring& home, std::vector<Candidate>* places)
{
    for (const wchar_t* config : {L".config\\heroic", L".var\\app\\com.heroicgameslauncher.hgl\\config\\heroic"}) {
        std::wstring dir = Join(home, config);
        auto prefixes = [&](const std::string& id) {
            std::vector<std::wstring> list;
            Json settings;
            if (id.empty() || !LoadJson(Join(dir, L"GamesConfig\\" + Widen(id) + L".json"), &settings)) {
                return list;
            }
            const Json* game = settings.Member(id);
            std::string prefix = game ? game->Text("winePrefix") : std::string();
            if (!prefix.empty()) {
                list.push_back(FromLauncher(prefix));
                list.push_back(Join(FromLauncher(prefix), L"pfx"));
            }
            return list;
        };
        Json installed;
        const Json* games = LoadJson(Join(dir, L"gog_store\\installed.json"), &installed)
                                ? installed.Member("installed") : nullptr;
        for (const Json& game : games && games->type == Json::LIST ? games->items : std::vector<Json>()) {
            std::string path = game.Text("install_path");
            if (!path.empty()) {
                Add(places, FromLauncher(path), SOURCE_HEROIC, prefixes(game.Text("appName")));
            }
        }
        Json library;
        games = LoadJson(Join(dir, L"sideload_apps\\library.json"), &library) ? library.Member("games") : nullptr;
        for (const Json& game : games && games->type == Json::LIST ? games->items : std::vector<Json>()) {
            const Json* install = game.Member("install");
            std::string exe = install ? install->Text("executable") : std::string();
            if (!exe.empty()) {
                Add(places, Parent(FromLauncher(exe)), SOURCE_HEROIC, prefixes(game.Text("app_name")));
            }
        }
    }
}

/* Lutris (natively, in its old or new folder, or as a flatpak): games\*.yml. exe is the path of
   the program, absolute or relative to the game's folder (working_dir) or its prefix; with no
   prefix given, a game inside "<prefix>\drive_c\..." runs in that prefix. */
void FindLutris(const std::wstring& home, std::vector<Candidate>* places)
{
    for (const wchar_t* folder : {L".config\\lutris\\games", L".local\\share\\lutris\\games",
                                  L".var\\app\\net.lutris.Lutris\\config\\lutris\\games",
                                  L".var\\app\\net.lutris.Lutris\\data\\lutris\\games"}) {
        std::wstring dir = Join(home, folder);
        for (const std::wstring& file : ListFolder(dir, false)) {
            std::string text;
            if (file.size() < 5 || lstrcmpiW(file.c_str() + file.size() - 4, L".yml") != 0 ||
                !ReadBytes(Join(dir, file), &text, 1 << 20)) {
                continue;
            }
            auto game = YamlSection(text, "game");
            std::string exe = YamlValue(game, "exe");
            std::string prefix = YamlValue(game, "prefix");
            std::string working = YamlValue(game, "working_dir");
            std::vector<std::wstring> paths;
            if (!exe.empty() && (exe[0] == '/' || exe[0] == '~')) {
                paths.push_back(FromLauncher(exe));
            } else if (!exe.empty()) {
                std::wstring relative = Widen(exe);
                for (wchar_t& c : relative) {
                    if (c == L'/') {
                        c = L'\\';
                    }
                }
                if (!working.empty()) {
                    paths.push_back(Join(FromLauncher(working), relative));
                }
                if (!prefix.empty()) {
                    paths.push_back(Join(FromLauncher(prefix), relative));
                }
            }
            for (const std::wstring& path : paths) {
                if (lstrcmpiW(BaseName(path).c_str(), L"Wiz8.exe") != 0) {
                    continue;
                }
                std::vector<std::wstring> prefixes;
                if (!prefix.empty()) {
                    prefixes.push_back(FromLauncher(prefix));
                } else {
                    std::wstring lower = path;
                    CharLowerBuffW(&lower[0], (DWORD)lower.size());
                    size_t drive_c = lower.rfind(L"\\drive_c\\");
                    if (drive_c != std::wstring::npos) {
                        prefixes.push_back(path.substr(0, drive_c));
                    }
                }
                Add(places, Parent(path), SOURCE_LUTRIS, prefixes);
            }
        }
    }
}

/* GOG installers run by hand in a prefix: <prefix>\drive_c\GOG Games\Wizardry 8 (the GOG
   installer's default) or GOG Galaxy's folder, in the prefixes at the usual places: Steam's
   (compatdata\*\pfx), ~/.wine, Heroic's (Games\Heroic\Prefixes\<runner>\<game>, with Proton its
   pfx), Lutris' (Games\<game>) and Bottles' (natively or as a flatpak). */
void FindInPrefixes(const std::wstring& home, const std::vector<std::wstring>& libraries,
                    std::vector<Candidate>* places)
{
    std::vector<std::wstring> prefixes;
    for (const std::wstring& library : libraries) {
        std::wstring compat = Join(library, L"steamapps\\compatdata");
        for (const std::wstring& id : ListFolder(compat, true)) {
            prefixes.push_back(Join(Join(compat, id), L"pfx"));
        }
    }
    prefixes.push_back(Join(home, L".wine"));
    std::wstring heroic = Join(home, L"Games\\Heroic\\Prefixes");
    for (const std::wstring& runner : ListFolder(heroic, true)) {
        for (const std::wstring& game : ListFolder(Join(heroic, runner), true)) {
            prefixes.push_back(Join(Join(heroic, runner), game));
            prefixes.push_back(Join(Join(Join(heroic, runner), game), L"pfx"));
        }
    }
    std::wstring games = Join(home, L"Games");
    for (const std::wstring& game : ListFolder(games, true)) {
        prefixes.push_back(Join(games, game));
    }
    for (const wchar_t* folder : {L".local\\share\\bottles\\bottles",
                                  L".var\\app\\com.usebottles.bottles\\data\\bottles\\bottles"}) {
        std::wstring bottles = Join(home, folder);
        for (const std::wstring& bottle : ListFolder(bottles, true)) {
            prefixes.push_back(Join(bottles, bottle));
        }
    }
    for (const std::wstring& prefix : prefixes) {
        if (!DirExists(Join(prefix, L"drive_c"))) {
            continue;
        }
        for (const wchar_t* game : {L"drive_c\\GOG Games\\Wizardry 8",
                                    L"drive_c\\Program Files (x86)\\GOG Galaxy\\Games\\Wizardry 8"}) {
            Add(places, Join(prefix, game), SOURCE_PREFIX, {prefix});
        }
    }
}

/* The Steam game (app 245450) in every library: the folder its appmanifest names, then the two
   names the folder is known by; its prefix is compatdata\245450\pfx. */
void FindSteamGame(const std::vector<std::wstring>& libraries, std::vector<Candidate>* places)
{
    std::vector<std::wstring> prefixes = SteamPrefixes(libraries, 245450);
    for (const std::wstring& library : libraries) {
        std::wstring common = Join(library, L"steamapps\\common");
        std::string text, folder;
        ReadBytes(Join(library, L"steamapps\\appmanifest_245450.acf"), &text);
        for (const std::string& line : Lines(text)) {
            if (VdfValue(line, "installdir", &folder)) {
                break;
            }
        }
        if (!folder.empty()) {
            Add(places, Join(common, Widen(folder)), SOURCE_STEAM, prefixes);
        }
        Add(places, Join(common, L"Wizardry 8"), SOURCE_STEAM, prefixes);
        Add(places, Join(common, L"Wizardry8"), SOURCE_STEAM, prefixes);
    }
}

/* "file:///home/deck/My%20Games" -> "/home/deck/My Games" (what some file managers copy) */
std::string FileUrlPath(const std::string& url)
{
    std::string path = url.substr(7);
    if (path.compare(0, 9, "localhost") == 0) {
        path.erase(0, 9);
    }
    std::string decoded;
    for (size_t i = 0; i < path.size(); ++i) {
        if (path[i] == '%' && i + 2 < path.size() && HexDigit(path[i + 1]) >= 0 && HexDigit(path[i + 2]) >= 0) {
            decoded += (char)(HexDigit(path[i + 1]) * 16 + HexDigit(path[i + 2]));
            i += 2;
        } else {
            decoded += path[i];
        }
    }
    return decoded;
}

}  // namespace

/* kernel32!wine_get_dos_file_name exists only under Wine, so it is looked up by name. It takes
   the Linux path in UTF-8 and returns memory of the process heap, which the caller frees. */
typedef WCHAR*(CDECL* DosFileName)(const char*);

std::wstring FromUnix(const std::string& path)
{
    if (path.empty() || path[0] != '/') {
        return Widen(path);
    }
    static DosFileName convert =
        (DosFileName)(void*)GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "wine_get_dos_file_name");
    if (convert) {
        WCHAR* dos = convert(path.c_str());
        if (dos) {
            std::wstring result = dos;
            HeapFree(GetProcessHeap(), 0, dos);
            return result;
        }
    }
    std::wstring result = L"\\\\?\\unix" + Widen(path); /* Wine's own name when no drive maps it */
    for (wchar_t& c : result) {
        if (c == L'/') {
            c = L'\\';
        }
    }
    return result;
}

std::wstring HomeFolder()
{
    return EnvFolder(L"WINEHOMEDIR");
}

std::wstring ThisPrefix()
{
    return EnvFolder(L"WINECONFIGDIR");
}

void FindWineGames(std::vector<Candidate>* places)
{
    std::wstring home = HomeFolder();
    std::vector<std::wstring> roots, libraries;
    FindSteamFolders(home, &roots, &libraries);
    FindShortcuts(roots, libraries, places);
    if (!home.empty()) {
        FindHeroic(home, places);
        FindLutris(home, places);
        FindInPrefixes(home, libraries, places);
    }
    FindSteamGame(libraries, places);
}

Verdict PrefixVerdict(const std::vector<std::wstring>& prefixes)
{
    FolderIdentity self;
    std::wstring here = ThisPrefix();
    if (prefixes.empty() || here.empty() || !FolderId(here, &self, L"drive_c")) {
        return VERDICT_UNKNOWN;
    }
    bool this_prefix = false, other_prefix = false;
    for (const std::wstring& prefix : prefixes) {
        FolderIdentity id;
        if (FolderId(prefix, &id, L"drive_c")) {
            if (id.folder == self.folder && id.file == self.file) {
                this_prefix = true;
            } else {
                other_prefix = true;
            }
        }
    }
    /* this prefix and another existing one (a game installed in this prefix and started by a
       Steam shortcut in the shortcut's own): it may run in either */
    if (this_prefix) {
        return other_prefix ? VERDICT_UNKNOWN : VERDICT_THIS;
    }
    return other_prefix ? VERDICT_OTHER : VERDICT_NOT_CREATED;
}

std::wstring NormalizeTypedFolder(const std::wstring& text)
{
    size_t first = text.find_first_not_of(L" \t\r\n");
    size_t last = text.find_last_not_of(L" \t\r\n");
    std::wstring folder = first == std::wstring::npos ? std::wstring() : text.substr(first, last - first + 1);
    /* one pair of quotes: "..." (Steam's fields) or '...' (a path dropped into a terminal) */
    if (folder.size() >= 2 && (folder[0] == L'"' || folder[0] == L'\'') && folder.back() == folder[0]) {
        folder = folder.substr(1, folder.size() - 2);
    }
    if (CompareStringW(LOCALE_INVARIANT, NORM_IGNORECASE, folder.c_str(), (int)std::min<size_t>(folder.size(), 7),
                       L"file://", 7) == CSTR_EQUAL) {
        folder = Widen(FileUrlPath(Narrow(folder)));
    }
    if (lstrcmpiW(BaseName(folder).c_str(), L"Wiz8.exe") == 0) {
        folder = Parent(folder);
    }
    if (!folder.empty() && (folder[0] == L'/' || folder == L"~" || folder.compare(0, 2, L"~/") == 0)) {
        folder = FromLauncher(Narrow(folder));
    }
    return TrimSlashes(folder);
}

}  // namespace wine
