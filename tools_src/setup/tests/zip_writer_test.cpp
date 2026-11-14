// zip_writer_test.cpp - packs files with ..\zip_writer.h so that zip_writer_test.py can check
// the archive with Python's zipfile. Plain C++, builds anywhere:
//   g++ -std=c++17 -O2 zip_writer_test.cpp -o zip_writer_test
//   zip_writer_test out.zip list.txt [limit]
// list.txt: one line per file, "name in the archive<TAB>path of the file" (UTF-8; a list and
// not arguments, because a Windows program gets its arguments in the ANSI code page).
// Every file gets the time 2026-11-12 13:14:16.
// Without a limit a file the writer refuses is an error (exit code 1). With one (bytes, the
// `limit` of Writer::Add) a refused file is named on a line "refused: <name>" and the rest
// still goes in.

#include <cstdio>
#include <cstdlib>
#include <string>

#include "../zip_writer.h"

static bool ReadFile(const char* path, std::string* bytes)
{
    FILE* f = fopen(path, "rb");
    if (!f) {
        return false;
    }
    char buffer[65536];
    size_t n;
    while ((n = fread(buffer, 1, sizeof(buffer), f)) > 0) {
        bytes->append(buffer, n);
    }
    fclose(f);
    return true;
}

int main(int argc, char** argv)
{
    std::string list;
    if (argc < 3 || argc > 4 || !ReadFile(argv[2], &list)) {
        fprintf(stderr, "usage: zip_writer_test out.zip list.txt [limit]\n");
        return 2;
    }
    const size_t limit = argc == 4 ? (size_t)strtoul(argv[3], nullptr, 10) : 0;
    zipw::Writer zip;
    const uint16_t time = (uint16_t)((13 << 11) | (14 << 5) | (16 / 2));
    const uint16_t date = (uint16_t)(((2026 - 1980) << 9) | (11 << 5) | 12);
    size_t at = 0;
    while (at < list.size()) {
        size_t end = list.find('\n', at);
        if (end == std::string::npos) {
            end = list.size();
        }
        std::string line = list.substr(at, end - at);
        at = end + 1;
        size_t tab = line.find('\t');
        if (tab == std::string::npos) {
            continue;
        }
        std::string name = line.substr(0, tab);
        std::string path = line.substr(tab + 1);
        std::string bytes;
        if (!ReadFile(path.c_str(), &bytes)) {
            fprintf(stderr, "cannot read %s\n", path.c_str());
            return 1;
        }
        if (zip.Add(name, bytes, time, date, limit)) {
            continue;
        }
        if (limit == 0) {
            fprintf(stderr, "cannot add %s\n", name.c_str());
            return 1;
        }
        printf("refused: %s\n", name.c_str());
    }
    std::string archive = zip.Finish();
    if (archive.empty()) {
        fprintf(stderr, "the archive is over the limits\n");
        return 1;
    }
    FILE* f = fopen(argv[1], "wb");
    if (!f || fwrite(archive.data(), 1, archive.size(), f) != archive.size()) {
        fprintf(stderr, "cannot write %s\n", argv[1]);
        return 1;
    }
    fclose(f);
    return 0;
}
