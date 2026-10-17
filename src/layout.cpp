#include "layout.h"

#include "game_gog124.h"
#include "patch.h"

static HudLayout g_layout = HudLayout::Stretch;

void SetHudLayout(HudLayout layout) { g_layout = layout; }
HudLayout GetHudLayout() { return g_layout; }

// Division rounding down (in C++ `/` rounds negatives toward zero,
// but we need -0.5 pixel to become -1, not 0 — otherwise the left edge is "sticky").
static int FloorDiv(long long a, long long b)
{
    long long q = a / b;
    if ((a % b != 0) && ((a < 0) != (b < 0))) --q;
    return (int)q;
}
static int CeilDiv(long long a, long long b) { return -FloorDiv(-a, b); }

ScreenBlock MakeScreenBlock(int W, int H)
{
    int bw = (int)((640LL * H + 240) / 480);  // round(640*H/480)
    if (bw > W) bw = W;
    return {W, H, bw, (W - bw) / 2};
}

static int Clamp(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }

PixelRect BlockRect(const ScreenBlock& b, const int* vp)
{
    if (!vp) return {b.offX, 0, b.bw, b.H};
    // The game sometimes passes a right/bottom edge of 641/481 (its own off-by-one error) —
    // we clamp it so the picture doesn't spill into the side bar.
    int l = Clamp(vp[0], 0, 640), r = Clamp(vp[2], 0, 640);
    int t = Clamp(vp[1], 0, 480), btm = Clamp(vp[3], 0, 480);
    // Compute edges, not widths: neighboring rectangles meet without gaps.
    int x0 = b.offX + (int)((long long)l * b.bw / 640);
    int x1 = b.offX + (int)((long long)r * b.bw / 640);
    int y0 = (int)((long long)t * b.H / 480);
    int y1 = (int)((long long)btm * b.H / 480);
    return {x0, y0, x1 - x0, y1 - y0};
}

bool CurrentBlock(Block* out)
{
    HWND hwnd = *(HWND*)Va(gog124::ghWindow);
    RECT rc;
    if (!hwnd || !GetClientRect(hwnd, &rc) || rc.right <= 0 || rc.bottom <= 0) {
        return false;
    }
    POINT origin = {0, 0};
    ClientToScreen(hwnd, &origin);
    int W = rc.right, H = rc.bottom;
    if (g_layout == HudLayout::Centered) {
        ScreenBlock sb = MakeScreenBlock(W, H);
        out->w = sb.bw;
        out->h = H;
        out->x = origin.x + sb.offX;
    } else {
        out->w = W;
        out->h = H;
        out->x = origin.x;
    }
    out->y = origin.y;
    return true;
}

POINT ScreenToLogical(const Block& b, POINT s)
{
    return {FloorDiv((long long)(s.x - b.x) * 640, b.w), FloorDiv((long long)(s.y - b.y) * 480, b.h)};
}

POINT LogicalToScreen(const Block& b, POINT l)
{
    // ceil guarantees that ScreenToLogical(LogicalToScreen(L)) == L.
    return {b.x + CeilDiv((long long)l.x * b.w, 640), b.y + CeilDiv((long long)l.y * b.h, 480)};
}
