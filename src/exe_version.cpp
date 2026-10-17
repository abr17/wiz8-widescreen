#include "exe_version.h"

#include <windows.h>
#include <bcrypt.h>

#include <vector>

std::string Sha256File(const char* path)
{
    HANDLE f = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                           OPEN_EXISTING, 0, nullptr);
    if (f == INVALID_HANDLE_VALUE) {
        return {};
    }

    // BCrypt — the crypto library built into Windows; like hash('sha256', ...) in PHP,
    // except that we feed the data in chunks.
    BCRYPT_ALG_HANDLE alg = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    std::string result;
    if (BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA256_ALGORITHM, nullptr, 0) == 0 &&
        BCryptCreateHash(alg, &hash, nullptr, 0, nullptr, 0, 0) == 0) {
        std::vector<unsigned char> buf(1 << 16);
        DWORD got = 0;
        bool ok = true;
        while (ReadFile(f, buf.data(), (DWORD)buf.size(), &got, nullptr) && got > 0) {
            if (BCryptHashData(hash, buf.data(), got, 0) != 0) {
                ok = false;
                break;
            }
        }
        unsigned char digest[32];
        if (ok && BCryptFinishHash(hash, digest, sizeof(digest), 0) == 0) {
            static const char hex[] = "0123456789ABCDEF";
            for (unsigned char b : digest) {
                result += hex[b >> 4];
                result += hex[b & 15];
            }
        }
    }
    if (hash) BCryptDestroyHash(hash);
    if (alg) BCryptCloseAlgorithmProvider(alg, 0);
    CloseHandle(f);
    return result;
}

ExeVersion IdentifyExe(const std::string& sha256)
{
    if (sha256 == "18A74FF61C65B8A2D4CFA11FFCE82AD7FEF022A94EAF0C2F217E479E981420D2") {
        return ExeVersion::Gog124;
    }
    return ExeVersion::Unknown;
}

const char* ExeVersionName(ExeVersion v)
{
    switch (v) {
    case ExeVersion::Gog124:
        return "GOG 1.2.4";
    default:
        return "unknown";
    }
}
