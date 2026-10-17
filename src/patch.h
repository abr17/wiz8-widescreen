#pragma once

#include <stddef.h>
#include <stdint.h>

// Convert an address from the table (at ImageBase 0x400000) to the real address in memory.
void* Va(uint32_t addr);

// Do the bytes in the game's memory match the expected ones (a check that this is that exact build).
bool BytesMatch(uint32_t addr, const uint8_t* expected, size_t n);

// Write bytes into the game's code (removes the page protection for the duration of the write).
bool WriteBytes(uint32_t addr, const uint8_t* bytes, size_t n);

// Replace the pointer in an exe import table slot. *original receives the old value.
bool PatchIatSlot(uint32_t slotAddr, void* replacement, void** original);

// MinHook hook of a game function at an address from the table.
bool HookGameFunction(uint32_t addr, void* detour, void** original);
