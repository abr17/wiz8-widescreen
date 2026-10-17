// Check "is this that exact game build?" directly in memory: PE header fields and
// the first bytes of every function we touch. Cheap and safe even in
// DllMain (unlike the file's SHA-256, which we compute later, only for the log).

#include "hooks_game.h"

#include <windows.h>

#include "game_gog124.h"
#include "patch.h"

using namespace gog124;

struct Sig {
    uint32_t addr;
    uint8_t bytes[8];
};

// First bytes of the functions (taken from GOG 1.2.4, see docs/functions.md).
static const Sig kSigs[] = {
    {VideoFullScreen, {0x8A, 0x44, 0x24, 0x04, 0xA2, 0x39, 0x3C, 0x60}},
    {BeginVideoPresentation, {0x8B, 0x0D, 0x34, 0x96, 0x65, 0x00, 0x83, 0xEC}},
    {FinishVideoPresentation, {0xA1, 0xAC, 0x96, 0x65, 0x00, 0x85, 0xC0, 0x74}},
    {IntroScreenFrame, {0x8D, 0x44, 0x24, 0xF0, 0x83, 0xEC, 0x10, 0x50}},
    {RenderFrame, {0x83, 0xEC, 0x3C, 0x8D, 0x4C, 0x24, 0x10, 0xC7}},
    {InvalidateRegion, {0x83, 0xEC, 0x08, 0x53, 0x55, 0x8B, 0x2D, 0xE4}},
    {MouseHandler, {0x83, 0xEC, 0x10, 0x53, 0x55, 0x8B, 0x6C, 0x24}},
    {WindowProcedure, {0xA0, 0xAC, 0x0D, 0x65, 0x00, 0x53, 0x55, 0x56}},
};

bool CheckGameSignature()
{
    auto* base = (uint8_t*)GetModuleHandleA(nullptr);
    auto* dos = (IMAGE_DOS_HEADER*)base;
    auto* nt = (IMAGE_NT_HEADERS32*)(base + dos->e_lfanew);
    if (nt->FileHeader.TimeDateStamp != kTimeDateStamp || nt->OptionalHeader.SizeOfImage != kSizeOfImage) {
        return false;
    }
    for (const Sig& s : kSigs) {
        if (!BytesMatch(s.addr, s.bytes, sizeof(s.bytes))) {
            return false;
        }
    }
    return true;
}
