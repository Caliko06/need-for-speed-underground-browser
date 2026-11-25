# Non-Destructive Binary Patching Without Source Code (15 Modules, 753 Hex Addresses)

> Architectural pattern for patching a statically recompiled x86 binary cleanly, auditable line-by-line.
> Source: `tools/recomp/patches*.py` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Hub: https://nfsu.cc/reverse-engineering/index.html

## ELI5: How Do You Fix or Upgrade a Program Without Its Source Code?

When you want to add widescreen support, fix a collision bug, or improve lighting in a 2003 executable, editing raw bytes with a hex editor quickly turns into an unmaintainable mess. Instead, we keep the original binary **read-only** and maintain small Python patch modules that say: *"at exact address `0x004f5891`, replace these bytes for this exact reason."* Every patch is documented in one line and can be switched off at runtime so **Original 2003 mode** stays untouched.

## Technical Pattern: Single-Source Patch Registry

All **753 unique binary addresses** modified in `Speed.exe` (base `0x400000`) are registered through `tools/recomp/patches.py` in a deterministic import order and shared by three consumers simultaneously:

1. **The static lifter (`tools/recomp/lift.py`)**: Lifts the patched instruction stream into C.
2. **The differential tester (`tools/recomp/difftest.py`)**: Knows exactly which addresses intentionally diverge from stock behavior.
3. **The runtime loader (`host/`)**: Keeps original vs remaster/enhanced behavior cleanly separated.

## All 15 Modular Patch Sets

| Module | Unique Hex Addrs | Purpose | Sample Addresses |
|---|---:|---|---|
| [`tools/recomp/patches.py`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/tools/recomp/patches.py) | 29 | PATCH table (AGENTS.md contract 3): every change to Speed.exe code or data, in one place. | `0x4086b0, 0x408760, 0x40877d, 0x40877e` |
| [`tools/recomp/patches_audio.py`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/tools/recomp/patches_audio.py) | 11 | Patches: engine audio. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order. | `0x51c720, 0x524f30, 0x5251e0, 0x52536a` |
| [`tools/recomp/patches_boot.py`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/tools/recomp/patches_boot.py) | 11 | Patches: frame limiter during loads. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order. | `0x447600, 0x448b11, 0x448d10, 0x4493a0` |
| [`tools/recomp/patches_collision.py`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/tools/recomp/patches_collision.py) | 49 | Patches: collision pools. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order. | `0x43fe84, 0x4400c1, 0x4407b0, 0x4412b0` |
| [`tools/recomp/patches_feel.py`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/tools/recomp/patches_feel.py) | 34 | Patches: feel candidates and feel defaults. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order. | `0x3e8000, 0x3e9999, 0x3f8000, 0x40cfb9` |
| [`tools/recomp/patches_input.py`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/tools/recomp/patches_input.py) | 10 | Patches: steering input. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order. | `0x40664a, 0x4070a0, 0x460970, 0x4609e3` |
| [`tools/recomp/patches_launcher.py`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/tools/recomp/patches_launcher.py) | 5 | Patches: no intro movies, no splash, always (OWNER 2026-11-11). Split from patches.py; imported last in patches.py. | `0x4de1e0, 0x4de395, 0x4de4a0, 0x735790` |
| [`tools/recomp/patches_lights.py`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/tools/recomp/patches_lights.py) | 23 | Patches: car lights, horn flash, neon. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order. | `0x425350, 0x425582, 0x42580a, 0x425853` |
| [`tools/recomp/patches_mode_menu.py`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/tools/recomp/patches_mode_menu.py) | 16 | Seventh MU_Main_PC button; OWNER 2026-11-14 permits this sole menu addition in Original too. | `0x4b309b, 0x4b33db, 0x4b33e0, 0x4b3769` |
| [`tools/recomp/patches_race.py`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/tools/recomp/patches_race.py) | 159 | Patches: rivals, Free Run, traffic. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order. | `0x41dd10, 0x41e200, 0x41e330, 0x421170` |
| [`tools/recomp/patches_render.py`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/tools/recomp/patches_render.py) | 100 | Patches: widescreen, blur, car look, flares, road reflection. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order. | `0x008296, 0x10a7f8, 0x1fbc9e, 0x1fffff` |
| [`tools/recomp/patches_reset.py`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/tools/recomp/patches_reset.py) | 7 | Patches: the player's reset placement (GOAL 2026-11-05 Block 2). Split out of the collision file; imported last by patches.py. | `0x4273d0, 0x427c50, 0x4314a0, 0x431724` |
| [`tools/recomp/patches_road.py`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/tools/recomp/patches_road.py) | 235 | Patches: the widened road graph. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order. | `0x41f8a2, 0x432ea7, 0x432eac, 0x435de7` |
| [`tools/recomp/patches_test.py`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/tools/recomp/patches_test.py) | 27 | Patches: test-only seed and autopilot. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order. | `0x123456, 0x40877e, 0x408814, 0x41f81d` |
| [`tools/recomp/patches_unlock.py`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/tools/recomp/patches_unlock.py) | 67 | Patches: everything open (RN_UNLOCK). Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order. | `0x41cf40, 0x4ab470, 0x4b9f40, 0x4bc170` |
