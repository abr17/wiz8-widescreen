// The patch as a client of srDD_D3D11's extension API (drivers/srdd_d3d11/include/w8x.h,
// docs/extensions.md there). With another render driver this does nothing. With srDD_D3D11 the
// patch hands the driver what only sr.dll's code knows ([D3D11] Extensions=1, the default):
//   - "camera.view" on the driver's board: the view matrix of the world's camera,
//     view_from_world as sr.dll builds it in srCamera::processPush (the inverse of the camera's
//     world matrix with its z row negated, row-major, v' = m * v). The driver gives it to its
//     clients as W8xGpu.view / prev_view. Only the world's camera (W8World +0x44): the game
//     draws its other scenes (the sky's world, the full-screen and overlay scenes) with cameras
//     of their own, each flushed on its own.
//   - the point OPAQUE_DONE (mark_point) at srGERD::flushSort: endFrame flushes the immediate
//     renderers first (the opaque world) and then the sorting ones (the transparent batch), so
//     flushSort's start is the moment the opaque world is drawn and nothing transparent is.
//     The game's RenderScene flushes after each of its scenes (about seven a frame), so it is
//     marked once after each push of the world's camera, at the flush of the renderer of that
//     push, never in a frame without one.
//   - the tag "water" (with W8X_TAG_TRANS_Z) on the textures of the game's water, by the
//     texture's name: srGERD::changeTexture tells which texture sr.dll binds at stage 0, and the
//     driver's DRAW event, which follows the bind, gives that texture's handle. The patch takes
//     DRAW only from the bind of a water texture to the first draw that samples it.
//
// All three hooks are MinHook hooks on sr.dll exports (sr.dll calls flushSort and changeTexture
// itself, so import slots would not see them), made only on the build of sr.dll they were
// written for, all three or none. Everything runs on the game's render thread.
// The driver may be unloaded with its device (srGERD frees the library): it says so
// (DRIVER_CLOSING), and before each use outside its callbacks the driver's module is checked;
// a stale client is registered again.
//
// The driver package's bridge add-on (drivers/srdd_d3d11/addons/w8x_bridge) gives the same three
// things without the patch. What the two must have alike (the build of sr.dll, the names of its
// functions, the view matrix, the water's names, the draws that get the tag) is in
// drivers/srdd_d3d11/sdk/w8x_sr.h.

#include "hooks_game.h"

#include <windows.h>
#include <psapi.h>  // K32EnumProcessModules for w8x_find_api

#include <MinHook.h>

#define W8X_FIND_API
#include "../drivers/srdd_d3d11/include/w8x.h"
#include "../drivers/srdd_d3d11/sdk/w8x_sr.h"

#include "game_gog124.h"
#include "log.h"
#include "patch.h"

#define SR_THISCALL __attribute__((thiscall))

namespace {

typedef void(SR_THISCALL* ProcessPush_t)(void* camera, void* gerd);
typedef void(SR_THISCALL* FlushSort_t)(void* gerd);
typedef void(SR_THISCALL* ChangeTexture_t)(void* gerd, void* texture, unsigned long stage, int apply);
typedef void(SR_THISCALL* WorldMatrix_t)(const void* node, double* m);
typedef const char*(SR_THISCALL* GetName_t)(const void* object);

ProcessPush_t g_processPush;
FlushSort_t g_flushSort;
ChangeTexture_t g_changeTexture;
WorldMatrix_t g_worldMatrix;
GetName_t g_getName;

// The driver: its module, the table, our client and our tag. g_api is null while no srDD_D3D11
// is loaded (or it refused us: another ABI, Extensions=0).
HMODULE g_driver;
const void* g_getApi;   // the driver's W8xGetApi: checked without reading the driver's memory
const W8xApi* g_api;
W8xClient* g_client;
uint16_t g_waterTag;
unsigned g_retry;       // camera pushes until the next look for the driver
HMODULE g_refused;      // a driver that refused us: not asked again
void* g_pushGerd;       // the renderer the world's camera was pushed to; null: no OPAQUE_DONE due
bool g_stage0Water;     // the texture sr.dll bound last at stage 0 is water
bool g_drawOn;          // subscribed to DRAW

void Forget()
{
    g_driver = nullptr;
    g_getApi = nullptr;
    g_api = nullptr;
    g_client = nullptr;
    g_waterTag = 0;
    g_pushGerd = nullptr;
    g_stage0Water = false;
    g_drawOn = false;
}

// A call that found our client stale (the driver started over): register again at the next push.
void Check(W8xResult r)
{
    if (r == W8X_E_STALE) {
        Forget();
        g_retry = 0;
    }
}

W8xResult W8X_CALL OnDraw(void*, const W8xEvent* ev);

// DRAW on or off. It is wanted only from the bind of a water texture at stage 0 to the first draw
// that samples it: only that draw (W8xDrawInfo) names the driver's texture and says whether it
// has its tag, and sr.dll gives the driver another texture only in changeTexture. Every other
// draw of the frame then costs no call into the patch. First among the DRAW subscribers, so
// that the others see the water tag.
void DrawEvents(bool on)
{
    if (on == g_drawOn) return;
    const W8xResult r = on ? g_api->subscribe(g_client, W8X_EV_DRAW, -1000, 0, OnDraw, nullptr)
                           : g_api->unsubscribe(g_client, W8X_EV_DRAW, OnDraw, nullptr);
    g_drawOn = on && r == W8X_OK;
    Check(r);
}

W8xResult W8X_CALL OnDraw(void*, const W8xEvent* ev)
{
    const W8xDrawInfo* d = (const W8xDrawInfo*)ev->payload;
    if (!g_api || !g_stage0Water || !w8x_sr_stage0_draw(d)) return W8X_OK;
    // The first draw with this water texture: the texture keeps the tag from now on.
    if (!d->tag && g_api->tag_texture(g_client, d->texture[0], g_waterTag) == W8X_OK)
        g_api->set_draw_tag(g_client, g_waterTag);
    DrawEvents(false);  // the texture has its tag: no DRAW until the next bind of a water texture
    return W8X_OK;
}

// DRIVER_CLOSING: the driver unregisters its clients after this event and is freed; nothing it
// handed out is used any more. The hooks pass everything on until Ready finds the next driver.
W8xResult W8X_CALL OnClosing(void*, const W8xEvent*)
{
    Log("w8x: the render driver went away");
    Forget();
    return W8X_OK;
}

// The driver's module still loaded at the same place (srGERD frees it with its device). Asks
// Windows about the export's address only: the driver's memory may be gone.
bool DriverStillThere()
{
    HMODULE m = nullptr;
    return GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                              (LPCWSTR)g_getApi, &m) &&
           m == g_driver && GetProcAddress(m, "W8xGetApi") == (FARPROC)g_getApi;
}

// The driver of g_api is still there; a driver that was freed without DRIVER_CLOSING is
// forgotten here. The hooks ask before each use of g_api.
bool Alive()
{
    if (g_api && !DriverStillThere()) {
        Log("w8x: the render driver went away");
        Forget();
    }
    return g_api != nullptr;
}

bool Attach()
{
    W8xGetApiFn get = w8x_find_api();
    if (!get) return false;
    HMODULE m = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            (LPCWSTR)(const void*)get, &m) ||
        m == g_refused)
        return false;
    const W8xApi* api = nullptr;
    const W8xResult r = get(W8X_ABI_MAJOR, &api);
    if (r != W8X_OK || !api) {
        Log("w8x: the render driver's extension API is off or not ABI %d (%d): not used", W8X_ABI_MAJOR, (int)r);
        g_refused = m;
        return false;
    }
    W8xClientDesc desc = {};
    desc.size = sizeof(desc);
    desc.version = 1;
    desc.name = "wiz8-widescreen";
    desc.abi_minor = W8X_ABI_MINOR;
    W8xClient* c = nullptr;
    if (api->register_client(&desc, &c) != W8X_OK) {
        g_refused = m;
        return false;
    }
    uint16_t tag = 0;
    api->alloc_tag(c, "water", W8X_TAG_TRANS_Z, &tag);
    api->subscribe(c, W8X_EV_DRIVER_CLOSING, 0, 0, OnClosing, nullptr);
    g_driver = m;
    g_getApi = (const void*)get;
    g_api = api;
    g_client = c;
    g_waterTag = tag;
    g_pushGerd = nullptr;
    g_stage0Water = false;
    g_drawOn = false;  // DRAW comes with the first water texture (DrawEvents)
    Log("w8x: render driver with extension API %u.%u: camera.view, OPAQUE_DONE and the water tag (%u) on",
        api->abi_major, api->abi_minor, tag);
    return true;
}

// The client, ready for this camera push or flush; false without srDD_D3D11.
bool Ready()
{
    if (Alive()) return true;
    if (g_retry) {
        --g_retry;
        return false;
    }
    g_retry = 255;  // looking costs a module walk: once every 256 camera pushes
    return Attach();
}

// The camera of the game's world (W8World +0x44), null without a world.
void* WorldCamera()
{
    uint8_t* world = *(uint8_t**)Va(gog124::g_world);
    return world ? *(void**)(world + gog124::World_Camera) : nullptr;
}

// srCamera::processPush(srGERD*): the camera's view and projection go onto sr.dll's matrix
// stacks; the scene of that camera (the world, the sky, a full-screen scene) is drawn with them
// next. Only the world's camera counts.
void SR_THISCALL HookProcessPush(void* camera, void* gerd)
{
    if (camera && camera == WorldCamera() && Ready()) {
        // processPush (decomp src/surrender/camera.cpp): view = Inverse(world), its row 2 negated.
        double world[16];
        float view[16];
        g_worldMatrix(camera, world);
        if (w8x_sr_view(world, view)) Check(g_api->publish(g_client, "camera.view", view, sizeof(view)));
        g_pushGerd = g_api ? gerd : nullptr;
    }
    g_processPush(camera, gerd);
}

// srGERD::flushSort: from srGERD::flushRenderers (endFrame), after flushImmediateRenderers.
// Marked once for each push of the world's camera, at the flush of the renderer that push went
// to. The bridge add-on marks under one more condition, that draws reached the driver since the
// push; it counts them with a DRAW subscription for the whole session, which the patch does not
// keep (DrawEvents).
void SR_THISCALL HookFlushSort(void* gerd)
{
    if (g_pushGerd && gerd == g_pushGerd) {
        g_pushGerd = nullptr;
        if (Ready()) Check(g_api->mark_point(g_client, W8X_PT_OPAQUE_DONE));
    }
    g_flushSort(gerd);
}

// srGERD::changeTexture(srTextureIFace*, stage, apply): binds the texture at the stage.
void SR_THISCALL HookChangeTexture(void* gerd, void* texture, unsigned long stage, int apply)
{
    g_changeTexture(gerd, texture, stage, apply);
    if (stage != 0 || !g_api) return;
    g_stage0Water = texture && w8x_sr_is_water(g_getName(texture));
    // DRAW from here to the first draw that samples the texture, or to the bind of another one.
    // The driver may have gone since the last camera push: asked before it is called.
    if (g_stage0Water != g_drawOn && g_waterTag && Alive()) DrawEvents(g_stage0Water);
}

}  // namespace

bool InstallW8xHooks(HookReport* r)
{
    // sr.dll is mapped (it imports us); its DllMain has not run, so only its header and export
    // addresses are read.
    HMODULE sr = GetModuleHandleA("sr.dll");
    if (!sr) return false;
    // The hooks rest on the code and the class layout of the one build every game version has.
    // Another build gets none; the report keeps its time stamp for the log, which opens later.
    const uint32_t build = w8x_sr_build(sr);
    if (build != W8X_SR_BUILD) {
        r->w8xOtherSr = true;
        r->w8xSrStamp = build;
        return false;
    }
    g_worldMatrix = (WorldMatrix_t)GetProcAddress(sr, W8X_SR_WORLD_MATRIX);
    g_getName = (GetName_t)GetProcAddress(sr, W8X_SR_GET_NAME);
    void* const target[3] = {
        (void*)GetProcAddress(sr, W8X_SR_PROCESS_PUSH),
        (void*)GetProcAddress(sr, W8X_SR_FLUSH_SORT),
        (void*)GetProcAddress(sr, W8X_SR_CHANGE_TEXTURE),
    };
    void* const detour[3] = {(void*)&HookProcessPush, (void*)&HookFlushSort, (void*)&HookChangeTexture};
    void** const original[3] = {(void**)&g_processPush, (void**)&g_flushSort, (void**)&g_changeTexture};
    if (!g_worldMatrix || !g_getName || !target[0] || !target[1] || !target[2]) return false;
    // All three or none: a hook is enabled only when all three are made, and a failure takes out
    // the ones made so far (MH_RemoveHook disables an enabled hook first).
    int made = 0;
    while (made < 3 && MH_CreateHook(target[made], detour[made], original[made]) == MH_OK) ++made;
    bool ok = made == 3;
    for (int i = 0; ok && i < 3; ++i) ok = MH_EnableHook(target[i]) == MH_OK;
    if (!ok)
        for (int i = 0; i < made; ++i) MH_RemoveHook(target[i]);
    r->w8x = ok;
    return ok;
}
