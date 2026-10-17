#pragma once

// Addresses inside Wiz8.exe GOG 1.2.4 (SHA-256 18A74FF6...20D2), ImageBase 0x400000.
// Source: the public decompilation + byte checks (docs/functions.md,
// docs/history/phase2-static-raw.json). Before use they are converted to the real
// address via Va(), in case the exe is not loaded at 0x400000.
//
// Calling conventions (important for hooks):
//   cdecl    — the caller removes the arguments from the stack (ordinary game functions);
//   stdcall  — the function removes them itself (WinAPI, window procedures, Windows hooks);
//   thiscall — the object pointer is in the ECX register (C++ methods).

#include <stdint.h>

namespace gog124 {

constexpr uint32_t kImageBase = 0x00400000;
constexpr uint32_t kTimeDateStamp = 0x3C26EEE6;  // from the PE header, 2001-12-24
constexpr uint32_t kSizeOfImage = 0x00409261;

// --- window and video mode ---
constexpr uint32_t OpenRendererWindow_getDisplayModeResult = 0x00422895;  // 7 bytes: mov esi,eax; cmp esi,-1; jne
constexpr uint32_t VideoFullScreen = 0x00422970;           // cdecl void(uint8 fullscreen)
constexpr uint32_t WindowProcedure = 0x004011E0;           // stdcall LRESULT(HWND, UINT, WPARAM, LPARAM)

// --- Bink videos ---
constexpr uint32_t BeginVideoPresentation = 0x00423390;    // cdecl IDirectDrawSurface2*()
constexpr uint32_t FinishVideoPresentation = 0x004234A0;   // cdecl uint8()
constexpr uint32_t IntroScreenFrame = 0x005AE6F0;          // cdecl void(), frame of the video screen
constexpr uint32_t RenderFrame = 0x00426790;               // cdecl void(), draws and presents a frame
constexpr uint32_t InvalidateRegion = 0x00422D50;          // cdecl void(int l, int t, int r, int b, int)

// --- mouse ---
constexpr uint32_t MouseHandler = 0x00401C70;              // stdcall LRESULT(int, WPARAM, LPARAM) — WH_MOUSE
constexpr uint32_t Iat_GetCursorPos = 0x005EB250;          // import table slot USER32!GetCursorPos
constexpr uint32_t Iat_SetCursorPos = 0x005EB254;          // import table slot USER32!SetCursorPos

// --- frame drawing (Phase 4) ---
constexpr uint32_t RenderScene = 0x00427850;               // cdecl void(srScene*, srCamera*, const int* vp640, bool fog)
constexpr uint32_t RenderWorldToSurface = 0x00426F80;      // cdecl uint8(srColorSurface*, const int* rect, bool sky) — save thumbnails, automap
// Return addresses (where a call returns to) — they tell us WHO called the function.
constexpr uint32_t Ret_RenderFrame_FirstRenderScene = 0x00426A3F;  // first RenderScene of the frame (after beginFrame)
constexpr uint32_t Ret_RenderFrame_ClearScissor = 0x004269E8;      // setScissor before clearing the 3D area
constexpr uint32_t Ret_SetViewport_WorldPlane = 0x004263A9;        // setViewPlane(Rect) of the world camera
constexpr uint32_t Ret_SetViewport_SkyPlane = 0x004263C3;          // setViewPlane(Rect) of the sky camera
// The call instructions themselves (for byte checks): call [0x5EB604]... etc.
constexpr uint32_t Call_RenderFrame_ClearScissor = 0x004269E6;     // ff d3 (call ebx = setScissor)
constexpr uint32_t Load_RenderFrame_ScissorPtr = 0x004269C8;       // 8b 1d 40 b6 5e 00 (mov ebx,[setScissor])
constexpr uint32_t Load_SetViewport_PlanePtr = 0x00426340;         // 8b 35 ec b4 5e 00 (mov esi,[setViewPlane])
constexpr uint32_t Call_SetViewport_WorldPlane = 0x004263A7;       // ff d6 (call esi)
constexpr uint32_t Call_SetViewport_SkyPlane = 0x004263C1;         // ff d6 (call esi)
constexpr uint32_t Call_RenderFrame_FirstRenderScene = 0x00426A3A; // e8 rel32 -> RenderScene
constexpr uint32_t Call_RenderFrame_PushPick = 0x00426BAC;         // ff 15 30 b6 5e 00 (call [pushPick]), 6 bytes

// --- Wiz8.exe import table slots -> sr.dll (C++ methods, thiscall) ---
constexpr uint32_t Iat_srGERD_setScissor = 0x005EB640;     // void(ULONG x, y, w, h), retn 0x10
constexpr uint32_t Iat_srGERD_pushPick = 0x005EB630;       // void(const Pick&), retn 4
constexpr uint32_t Iat_srCamera_setViewPlaneRect = 0x005EB4EC;  // void(const Rect&, double), retn 0xC

// --- global variables ---
constexpr uint32_t g_gerd = 0x00659634;                    // srGERD* — the engine renderer
constexpr uint32_t g_viewport = 0x006595E8;                // int[4] {l, t, r+1, b+1} in 640x480 units — the 3D view
constexpr uint32_t g_overlayCamera = 0x00659670;           // srCamera* of the 2D camera (canvas, portraits, cursor)
constexpr uint32_t g_squareCamera = 0x00659674;            // srCamera* of the 2D camera for "square" sprites
constexpr uint32_t g_sceneOverlay0 = 0x00659654;           // srScene* of the scene with the 640x480 canvas
constexpr uint32_t g_surfaceNode = 0x00659664;             // stSurface2D* canvas; +0x140 shader bits
constexpr uint32_t SurfaceNode_ShaderBits = 0x140;
constexpr uint32_t ShaderBit_AlphaTest = 0x00800000;       // 1 — canvas "with holes" (world visible), 0 — solid
constexpr uint32_t g_world = 0x00659AB4;                   // W8World*; +0x44 — srCamera*
constexpr uint32_t g_secondaryWorld = 0x00659AB8;          // sky world; +0x44 — srCamera*
constexpr uint32_t World_Camera = 0x44;
constexpr uint32_t g_fullscreen = 0x00603C39;              // uint8
constexpr uint32_t ghWindow = 0x006596CC;                  // HWND of the main window
constexpr uint32_t gpVideo = 0x0069C258;                   // W8BinkVideo*; field +8 — target surface
// Keyboard modifier state (Shift/Ctrl/Alt) that gets "stuck" after Alt+Tab.
constexpr uint32_t KeyState_Words[] = {0x006F04EA, 0x006F0508, 0x006F051C};
constexpr uint32_t KeyState_Bytes = 0x006F0530;            // 3 bytes: 0x6F0530..0x6F0532

}  // namespace gog124
