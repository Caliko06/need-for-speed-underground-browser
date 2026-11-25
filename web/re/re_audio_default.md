# Default music volume in Speed.exe

> Source: `docs/re_audio_default.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 57

# Default music volume in Speed.exe

Answer: the nine Options > Audio sliders are nine floats in the per-player options block. A constructor,
`0x4aa200`, sets all of them to 0.9. The music slider is the second one (`+0x3c`). One in-place patch at `0x4aa21e`
sets it to 0.3. A saved profile overrides the default, so the patch alone does not change the OWNER's profiles.

Tools: "objdump" = `objdump -D -M intel pc/Speed.exe` (REA CLI was not needed; the Hopper export names are all
`sub_<hex>` and its function bounds are wrong around 0x4cf000, so the disassembly is the authority here).
"Hopper" = census/hopper/decomp.c. "file" = the OWNER's save/*.opt read with Python. No game run was made.

## 1. Where the default is set

| Finding | Address | Tool |
|---|---|---|
| Constructor of the options/profile block. Stores `0x3f666666` (0.9f) into nine floats at `this+0x38 .. this+0x58` (`mov [esi+0x38..0x58], eax`, code `0x4aa223..0x4aa23b`) | `0x4aa200` (`mov eax,0x3f666666` at `0x4aa21e`) | objdump, Hopper (`sub_4aa200`, `ecx[0xe..0x16] = 0x3f666666`) |
| It runs once per player block: `0x4a9bc0` calls it with `ecx = esi+0x10` (block `0x7588c4`) and then builds a second one with the array constructor (count 2, stride `0xf944`, ctor `0x4aa200`, `0x4a9bef`) | `0x4a9be0`, `0x4a9bea` | objdump |
| Two other call sites make a block on the heap with the same defaults | `0x4cae16`, `0x4ccbba` | objdump |

So the "no profile" boot and a new profile start at 0.9 for all nine, because both read the block `0x4aa200`
filled. No other code writes these defaults (a search of `.text` for `0x3f666666` finds only this function plus
unrelated uses).

## 2. What the nine floats are, and which is music

Block base `P = 0x7588c4` (player 0; player 1 at `P + 0xf944 = 0x768208`). The floats are `P+0x38 .. P+0x58`,
that is `0x7588fc, 0x758900, 0x758904, 0x758908, 0x75890c, 0x758910, 0x758914, 0x758918, 0x75891c`.
I call them `b0..b8`. The sound manager (`[0x7356a8]`) keeps a pointer to them at `[mgr+8]`
(`0x51d059`: `mov [edi+8], 0x7588fc`, and `0x51ccf1`).

- Scale and units: a float from 0.0 to 1.0. The slider has min 0.0, max 1.0 and step 0.1 (`0x3dcccccd`), built in
  the Audio screen constructor at `0x4cedb7..0x4cef70` (nine `VolSlider_n_` / `VolSliderBase_n` pairs, each fed
  from `b[n-1]`). Tool: objdump.
- The sound engine turns a category into a 0..32767 volume at `0x51cb70`: category 0 returns `b0 * 32767`;
  categories 1 to 5 return `b[cat] * b0 * 32767` (`0x6cc8c8` = 32767.0). Callers (`0x5225d6`, `0x5230f4`,
  `0x5282ad`, `0x52a86b`, `0x52c5f9`) pass the category read from the sound profile (`profile+0x10`) and multiply
  by the profile's own volume. So `b0` is the master and `b1..b5` are per-category volumes. Tool: objdump.
- The category order matches the five labels in game/Languages/English.bin, in this order: Music Volume,
  Ambient Volume, Engine Volume, Tire Volume, Speech and Movie Volume (strings 228 to 232). So
  `b1` (`0x758900`) = Music. `b0` (`0x7588fc`) = the Master volume that multiplies every other one
  (the string "Master Volume" also exists). Tool: objdump plus English.bin.
- Supporting evidence for `b1` = music: the audio message handler `0x5a4cf0` computes
  `table[id] * b0 * b1` (`0x5a4d11`, `0x5a4d17`; table `0x6b5948` is 127 for ids 0 to 41) and for id 1 calls
  `0x520ae0`, which sets a fade target from `b1 * b0 * 32767` (`0x520b08..0x520b20`). Tool: objdump.
- Effective music level = `b0 * b1`. At the shipped default that is 0.9 * 0.9 = 0.81.
- NOT VERIFIED: the match of `b1` to the "Music Volume" label rests on the category order and on the code above. I
  did not run the game, and I did not decode the Options FNG (it is compressed in game/FrontEnd) to read
  the slider labels. A cheap runtime check: set `[0x758900]` to 0.0 and see whether the music goes silent while
  engine and tires remain.
- Out of the nine: `b6` (`0x758914`) is also multiplied by 32767 into `[0x6f871c]` (`0x51ccfd..0x51cd12`), likely
  the speech/movie bus. `b7` and `b8` I did not trace (the strings "Speed Volume", "Collision Volume" and
  "Sound Effects Volume" suggest them).

## 3. Where it is stored

- Global: `0x758900` (player 0) and `0x768244` (player 1), floats. Live copy that the sound engine reads.
- Profile save: `<profile>.opt` in the save folder (here save/a.opt, save/asas.opt). Layout: dword `0x13`
  (version), then 741 bytes (`0x2e5`) of the block, then an Adler-32 checksum. Writer `0x41e200`
  (serializer `0x4aaad0`, checksum `0x41dd10`); reader `0x41e330` (deserializer `0x4aac70`, call at `0x41e463`
  with `ebx = 0x7588c4`). In the file, the nine floats start at byte `0x3d`, so music is the float at byte `0x41`.
  Tool: objdump, Hopper, file.
- Read from the OWNER's current files (both a.opt and asas.opt, same content):

  | b0 master | b1 music | b2 | b3 | b4 | b5..b8 |
  |---|---|---|---|---|---|
  | 0.2 | 0.7 | 0.5 | 0.7 | 0.8 | 0.9 |

  (a.opt changed at 15:57 today while I worked; it is not mine, so recheck before relying on the numbers.)

## 4. Does a saved profile override the default?

Yes. `0x41e330` reads the `.opt` over the block when the version is `0x13` and the checksum matches, so a loaded
profile takes the values in its file. The default at `0x4aa200` only applies to a boot with no profile and to a new
profile without a `.opt`. The OWNER's two profiles already hold their own values (master 0.2, music 0.7), so the
default patch alone changes nothing for them. Effective music for them today is 0.2 * 0.7 = 0.14, already below 25%.

What would work for the OWNER's profiles (pick one, none applied):
1. They lower or raise the Music slider once in Options > Audio and leave the screen. The destructor of that
   screen (`0x4cf110`) and the autosave `0x4c96f0` write the `.opt` (see host/input.c line 524: leaving Options
   without a change may not write it, so change one tick and back).
2. A patch after the load at `0x41e463` that overwrites `[0x758900]` with the target every time. This forces the
   value and hides the OWNER's slider, so I do not recommend it.
3. Bumping the version check (`0x13` at `0x41e2ae` and the compare in `0x41e330`) makes every old `.opt` fail and
   fall back to defaults, but it resets every option (controls, display, camera), so no.

## 5. Proposed patch (for tools/recomp/patches.py, nothing applied)

Goal: music slider default 0.3 (effective 0.9 * 0.3 = 0.27, about 25%) with the other eight left at 0.9. 0.3 sits on
the 0.1 slider grid; 0.25 (`0x3e800000`, bytes `00 00 80 3e`) works too but sits between two ticks.

One line, in place, 32 bytes at `0x4aa21e` (no cave):

    dict(addr=0x4aa21e,
         old="b86666663f89463889463c89464089464489464889464c894650894654894658",
         new="b86666663f8d7e38b909000000f3abc7463c9a99993e90909090909090909090", when=lambda: True)

Decoded: `mov eax,0x3f666666 ; lea edi,[esi+0x38] ; mov ecx,9 ; rep stosd ; mov dword [esi+0x3c],0x3e99999a ; nop x10`.
The nine stores become one `rep stosd`, then the music float is overwritten. Checks: after the block `ecx` is 0 again
(the old code used `ecx = 0` from `0x4aa20d`, and `rep stosd` ends with `ecx = 0`); `edi` is not read until
`mov edi,4` at `0x4aa25e`; `eax` is reloaded at `0x4aa23e`. Same length, so no later address moves. The `old=` value
was read from pc/Speed.exe at that address; the `new=` bytes were encoded by hand and NOT run through difftest or the
build. The lifter must be run on it (`RN_ONLY=4aa200` difftest) before it lands.

Caveat on the effect: it changes only no-profile and new-profile boots. For the OWNER's existing profiles, use
option 1 above.
