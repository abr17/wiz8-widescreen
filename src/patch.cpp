#include "patch.h"

#include <windows.h>

#include <MinHook.h>

#include "game_gog124.h"

void* Va(uint32_t addr)
{
    // GetModuleHandle(nullptr) — the address where Windows loaded Wiz8.exe itself.
    uintptr_t base = (uintptr_t)GetModuleHandleA(nullptr);
    return (void*)(addr - gog124::kImageBase + base);
}

bool BytesMatch(uint32_t addr, const uint8_t* expected, size_t n)
{
    return memcmp(Va(addr), expected, n) == 0;
}

bool WriteBytes(uint32_t addr, const uint8_t* bytes, size_t n)
{
    void* p = Va(addr);
    DWORD old;
    // Code pages are usually "read + execute only"; temporarily allow writing.
    if (!VirtualProtect(p, n, PAGE_EXECUTE_READWRITE, &old)) {
        return false;
    }
    memcpy(p, bytes, n);
    VirtualProtect(p, n, old, &old);
    // The CPU caches instructions — tell it the code has changed.
    FlushInstructionCache(GetCurrentProcess(), p, n);
    return true;
}

bool PatchIatSlot(uint32_t slotAddr, void* replacement, void** original)
{
    void** slot = (void**)Va(slotAddr);
    DWORD old;
    if (!VirtualProtect(slot, sizeof(void*), PAGE_READWRITE, &old)) {
        return false;
    }
    if (original) {
        *original = *slot;
    }
    *slot = replacement;
    VirtualProtect(slot, sizeof(void*), old, &old);
    return true;
}

bool HookGameFunction(uint32_t addr, void* detour, void** original)
{
    void* target = Va(addr);
    return MH_CreateHook(target, detour, original) == MH_OK && MH_EnableHook(target) == MH_OK;
}
