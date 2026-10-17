// Borderless: the game stays in its "fullscreen" mode (a WS_POPUP window
// the size of the monitor), but we forbid it to change the monitor resolution.
//
// 1) OpenRendererWindow asks the engine for the video mode number matching 3DVideo.CFG
//    and opens output in that mode (changing the monitor resolution). We change
//    7 bytes so that the number is always -1. To the engine -1 means "windowed output
//    the size of the window's client area" — i.e. the size of the monitor, no mode change.
// 2) VideoFullScreen (the /WINDOW switch, the toggle in the settings, maximizing the window)
//    is turned into a stub that keeps the "fullscreen" flag = 1.
// 3) Bink videos: the original switches the monitor to 640x480 and writes frames straight to the screen.
//    Instead we don't give it a "screen" — then the player writes the frame into the game's ordinary
//    640x480 2D canvas itself, and after each frame we ask the game to draw the whole frame.

#include "hooks_game.h"

#include <windows.h>

#include "game_gog124.h"
#include "log.h"
#include "patch.h"

using namespace gog124;

// --- 1. video mode number = -1 ---
static const uint8_t kModeOrig[] = {0x8B, 0xF0, 0x83, 0xFE, 0xFF, 0x75, 0x12};
// or esi,-1 ; jmp +0x14 (to the continuation, skipping the "mode not supported" branch) ; nop ; nop
static const uint8_t kModePatch[] = {0x83, 0xCE, 0xFF, 0xEB, 0x14, 0x90, 0x90};

// --- 2. VideoFullScreen ---
static void __cdecl HookVideoFullScreen(unsigned char)
{
    *(uint8_t*)Va(g_fullscreen) = 1;
}

// --- 3. Bink ---
typedef void(__cdecl* VoidFn)();
typedef void(__cdecl* InvalidateRegion_t)(int, int, int, int, int);
static VoidFn g_origIntroScreenFrame;

static void* __cdecl HookBeginVideoPresentation()
{
    // The player's constructor does not zero the "target surface" field (+8); the original
    // always wrote the screen there. Since we don't provide a screen, we zero it ourselves, otherwise
    // the player would pick up garbage from memory.
    uint8_t* video = *(uint8_t**)Va(gpVideo);
    if (video) {
        *(void**)(video + 8) = nullptr;
    }
    Log("Bink: BeginVideoPresentation bypassed (no exclusive mode, no 640x480 switch)");
    return nullptr;
}

static unsigned char __cdecl HookFinishVideoPresentation()
{
    // Mark the whole canvas "dirty" so that the next screen is redrawn over the video frame.
    ((InvalidateRegion_t)Va(InvalidateRegion))(0, 0, 640, 480, 0);
    Log("Bink: FinishVideoPresentation bypassed");
    return 1;
}

static void __cdecl HookIntroScreenFrame()
{
    g_origIntroScreenFrame();
    // The video screen doesn't draw frames itself (they used to go straight to video memory).
    // While a video plays, we draw the frame like any other game screen.
    if (*(void**)Va(gpVideo)) {
        ((VoidFn)Va(RenderFrame))();
    }
}

bool InstallVideoHooks(HookReport* r)
{
    r->modePatch = BytesMatch(OpenRendererWindow_getDisplayModeResult, kModeOrig, sizeof(kModeOrig)) &&
                   WriteBytes(OpenRendererWindow_getDisplayModeResult, kModePatch, sizeof(kModePatch));
    r->videoFullScreen = HookGameFunction(VideoFullScreen, (void*)&HookVideoFullScreen, nullptr);
    *(uint8_t*)Va(g_fullscreen) = 1;
    r->bink = HookGameFunction(BeginVideoPresentation, (void*)&HookBeginVideoPresentation, nullptr) &&
              HookGameFunction(FinishVideoPresentation, (void*)&HookFinishVideoPresentation, nullptr) &&
              HookGameFunction(IntroScreenFrame, (void*)&HookIntroScreenFrame, (void**)&g_origIntroScreenFrame);
    return r->modePatch && r->videoFullScreen && r->bink;
}
