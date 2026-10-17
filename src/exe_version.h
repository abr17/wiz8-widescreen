#pragma once

#include <string>

// Which build of Wiz8.exe we are looking at. Hooks are installed only for known ones.
enum class ExeVersion {
    Unknown,
    Gog124,  // GOG 1.2.4, SHA-256 18A74FF6...20D2 — the main target
};

// Computes the SHA-256 of a file (upper-case hex). Empty string on error.
std::string Sha256File(const char* path);

ExeVersion IdentifyExe(const std::string& sha256);
const char* ExeVersionName(ExeVersion v);
