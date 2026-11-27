"""Patches: frame limiter during loads. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order."""
from patches import PATCHES

# PATCH: 0x585b94 (+ mask 0x707fc8), OWNER 2026-10-24 (faster loads): the frame limiter 0x585b40 (main loop 0x447600) spins on
# QPC until a frame lasts 1/60 s ([0x6f0890], never written). The loads are synchronous job loops paced one job per frame
# (UnloadingFrontEnd 0x448d10, the track load, 0x4493a0), so menu->race was ~400 limited frames (7.4 s). The limiter now
# skips its wait while the game-flow state [0x77a920] (writes 0x448b11 .. 0x449a15) is a load: 1, 2, 4, 5, 7, 8 (bit mask
# 0x1b6 at [0x707fc8], free .data), or 6 while the race state [[0x7361f0]] is still 1 (loading screen up to the race HUD).
# Front end (3), boot (0) and the race keep the 1:1 limit. Room: the second test (wait < 1/30 s) is dead since the target
# is 1/60 and the frame time is >= 0; the > 0 test is now an integer compare of the stored float (same result, no NaN here).
PATCHES.append(dict(addr=0x707fc8, old="00000000", new="b6010000", when=lambda: True))
PATCHES.append(dict(addr=0x585b94,
                    old="d9542404d81da4c76c00dfe0568bfa8b542428c1e70481c7d80a7300f6c44189170f8595000000d9442408d81deccd6c00dfe0f6c4050f8a80000000",
                    new="d95c2404" "56" "c1e204" "8dbad80a7300" "8b542428" "8917" "837c240800" "7e1c" "a120a97700"
                        "0fa305c87f7000" "720e" "3c06" "750f" "a1f0617300" "833801" "7505" "e980000000",
                    when=lambda: True))
