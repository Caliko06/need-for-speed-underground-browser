# How Need for Speed Underground works inside

One note per system of `Speed.exe` (2003, PC), read from the binary. Each claim carries the address or data that proves it, marked **V** (read in code or bytes), **I** (inferred) or **U** (open). Function names live in [`census/`](../../census). A name like `re_zones` or `re_accel` is an earlier working note that was never published; what these notes reuse from it was read again in the binary. Links into `dd1146b` point to notes retired from the repo.

**Play: [nfsu.cc](https://nfsu.cc)** · How these notes are read: [English](https://nfsu.cc/blog/en/reverse-engineering-tools-ghidra-hopper-rea.html) · [Español](https://nfsu.cc/blog/es/herramientas-ingenieria-inversa-ghidra-hopper-rea.html)

| System | Driving | Camera | Rivals | Traffic | Tracks | Render | Sound | Menus and flow | Data |
|---|---|---|---|---|---|---|---|---|---|
| Start here | [physics](physics.md) | [camera](camera.md) | [rivals](rivals.md) | [traffic](traffic.md) | [track](track.md) | [render](render.md) | [sound](sound.md) | [gameflow](gameflow.md) | [assets](assets.md) |
| Then | [accel](accel.md), [tuning](tuning.md) | [chase](camera_chase.md), [speed](camera_speed.md), [jump](camera_jump.md), [crash](camera_crash.md) | [race_ai](race_ai.md), [stuck](ai_stuck.md), [draft](ai_draft.md) | [limits](traffic_limits.md), [react](traffic_react.md), [honks](traffic_honks.md), [placement](../traffic_placement.md) | [roadid](roadid.md), [props](props.md) | [render_pc](render_pc.md), [blur](blur.md), [night](../night_re.md), [flare](../flare_re.md), [minimap](../re_minimap.md) | [default volume](../re_audio_default.md) | [frontend_menu](frontend_menu.md), [garage](garage.md), [race_setup](race_setup.md), [hud_input](hud_input.md), [unlock](unlock.md), [mode_menu](mode_menu.md) | [car_assets](car_assets.md), [runtime](runtime.md), [misc](misc.md) |

| Serving the game | Where |
|---|---|
| What the browser downloads | [public_pack](public_pack.md) |
| Where it is hosted | [hosting](hosting.md) |

| Proof that a shipped patch cites | [feel_patch_plan](feel_patch_plan.md) | [feel_probe_fix](feel_probe_fix.md) | [ai_review2](ai_review2.md) | [traffic_cap_plan](traffic_cap_plan.md) | [reset_causes](reset_causes.md) | [hitches](hitches.md) |
|---|---|---|---|---|---|---|
| Cited by | `patches_feel.py` | `host/feellog.c` | `patches_race.py` | `patches_race.py` | `host/aitel.c` | `web/telemetry.js` |

| Method | [systems_method](systems_method.md): how functions get a system tag | [coverage_method](coverage_method.md): which functions ever ran |
|---|---|---|

Back to the [repo](../../README.md).
