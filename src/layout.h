#pragma once

#include <windows.h>

// Where the game's 640x480 "virtual" screen lies on the real screen.
//   Stretch  — stretched over the whole window (as in the original, but the mouse now hits correctly);
//   Centered — 4:3 centered with bars at the sides (Phase 4).
enum class HudLayout { Stretch, Centered };

struct Block {
    int x, y;   // top-left corner of the block in screen coordinates
    int w, h;   // block size in pixels
};

// Screen (render buffer) W x H and the central 4:3 block in it, in pixels.
// bw = round(640*H/480), at most W; offX = (W - bw)/2. One formula for everything:
// 2D, clearing the bars, Hor+ and the mouse — so everything matches to the pixel.
struct ScreenBlock {
    int W, H;     // the whole screen
    int bw;       // width of the 4:3 block
    int offX;     // left edge of the block
};
ScreenBlock MakeScreenBlock(int W, int H);

// A rectangle in pixels (x, y, width, height) — the form taken by
// srGERD::setViewPort / setScissor.
struct PixelRect {
    int x, y, w, h;
};
// A game rectangle in 640x480 units {left, top, right, bottom} -> pixels
// inside the block. vp == nullptr — the whole block.
PixelRect BlockRect(const ScreenBlock& b, const int* vp640);

void SetHudLayout(HudLayout layout);
HudLayout GetHudLayout();

// Recompute the block from the game's current client window. false — no window yet.
bool CurrentBlock(Block* out);

// Screen pixels -> logical 640x480 (rounding down, no clamping).
POINT ScreenToLogical(const Block& b, POINT screen);
// Logical 640x480 -> screen pixels (the inverse function; the round trip is exact).
POINT LogicalToScreen(const Block& b, POINT logical);
