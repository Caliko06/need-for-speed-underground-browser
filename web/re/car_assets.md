# Car assets: how a car is assembled and drawn (NFSU Speed.exe)

> Source: `docs/re/car_assets.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 29

# Car assets: how a car is assembled and drawn (NFSU Speed.exe)

Tool tags: G = Ghidra export (census/ghidra/decomp_0x54c000_0x5f1800.c), H = Hopper export (census/hopper/decomp.c),
C = capstone (`.venv/bin/python tools/recomp/asm.py dis`), D = bytes of game/ files and pc/Speed.exe,
F = readers tools/re/{chunks,tpk,carinfo}.py. The REA MCP could not be loaded in this session; the REA CLI was not used.
Hash = bStringHash: h=-1; h=h*33+c (invertible, so LOD letters A/B/C give consecutive hashes).
All examples use RX7. Offsets are for Speed.exe base 0x400000.

## 1. Files per car

- game/Cars/<NAME>/GEOMETRY.BIN, TEXTURES.BIN, VINYLS.BIN (F, D). Cars/NEON is the Dodge Neon, not underglow.
- Shared dirs: Cars/WHEELS (all rim solids, 1476 solids, 84 wheel textures), BRAKES, EXHAUST, PLATES (D).
- Cars/TEXTURES.BIN = pack "Global\CarTextures.tpk", 353 textures: <CAR>_SKIN1..8 of traffic cars, logos, SHADOWIG (F tpk.py).
- GLOBALB.BUN holds the shared textures (INTERCOOLER 427b4565, GRILL_02 69c032ba, CARBONFIBRE 721aff7c, CARBOTTOM bd1f0e0a),
  the 139 materials (chunk 0x135200) and the part database (chunk 0x80034602) (F, D).
- RX7/TEXTURES.BIN: 112 textures: STYLE0n_HEADLIGHT/BRAKELIGHT, KIT00 lights, DOORLINE (+_KIT, _KIT_MASK, _WIDEBODY,
  _WIDEBODY_MASK), BADGING, ENGINE, STYLE0n_ENGINE, NEON, TIRE, KIT00_WHEEL_BLUR, SHADOWFE/IG (F).
- RX7/VINYLS.BIN: TPK "RX7_Vinyls.tpk", 874 paletted 512x512 P8 vinyl textures and masks (F tpk.py list).
- **RX7_SKIN1 (0xefd842c5) is in no pack** (F, D search of every TPK). It is a runtime composite: paint + doorline + vinyl + decals.
  How it is composited is NOT VERIFIED (see section 5).

### GEOMETRY.BIN chunk tree (F chunks.py, D; names agree with docs/re/assets.md)
- 0x80134000 top. 0x80134001 solid list: 0x134002 header ("SolidList,%s"), 0x134003 sorted (hash, ptr) pairs, 0x134004.
- One 0x80134010 per solid: 0x134011 header (176 B: name hash +0x10, texture count +0x19, material count +0x1a, marker count +0x1b),
  0x134012 texture table (hash, ptr), 0x134013 material table (hash, ptr).
- Mesh container 0x80134100: 0x134900 mesh header (64 B), 0x134b01 vertex buffer, 0x134b02 group array, 0x134b03 index buffer.
- Optional 0x134017/18/19 collision mesh; 0x13401a markers (0x50 B each, lights, wheel dummies).
- Solid names: `<CAR>_KIT<NN>_<PARTNAME>_<A|B|C|D>` (A = highest LOD). RX7 has 399 solids, all referenced by the part DB (D, hash inversion).

## 2. Which solid is chosen for an installed part

- Part DB chunk 0x80034602: 4537 records of 0x30 bytes (F carinfo.py parts(), D):
  +0 name off, +4 car hash, +8 part hash, +0xc brand hash, +0x10 type (= slot) byte, +0x11 level, +0x12 sub,
  +0x14 attributes ptr, +0x1c attribute count, **+0x20/+0x24/+0x28/+0x2c = solid-name hash for LOD A/B/C/D (0 = none)**.
- Attribute pairs (key, value). 0x6ba02c05 = material hash (paint parts: REGPAINT*, METPAINT*, PEARL*, CUSTOMPAINT_n;
  window tint: WINDSHIELD*). 0xe80a3b62 = "hide slot" (value = hash of a slot name). 0x10c98090 = wheel texture name (read at 0x580b00).
- Slot names, table 0x6f0970, stride 8 (index, name ptr), 120 entries (G, D): 0 BASE, 1 FRONT_BUMPER, 2 REAR_BUMPER, 3/4 side mirrors,
  5 BODY, 6 WIDE_BODY, 7 ROOF, 8 HOOD, 9 TRUNK, 10 SKIRT, 11 SPOILER, 12 ENGINE, 13 HEADLIGHT, 14 BRAKELIGHT, 15 EXHAUST,
  16 BRAKE, 17 WHEEL, 18 LICENSE_PLATE, 19..29 DECAL_*, 30 BASE_PAINT, 31..34 VINYL_LAYER0..3, 35 VINYL_HOOD, 36 VINYL_SPOILER,
  37..41 PAINT_ENGINE/SPOILER/BRAKE/EXHAUST/RIM, 42..57 VINYL_COLOUR*, 58..114 DECAL_TEX*, 115 WINDOW_TINT, 116 NEON, 118 WHEEL_MANUFACTURER.
- RideInfo (G, docs/re/garage.md): +0 car index, +0x44c CarPart*[0x78] (index = slot), **+0x6a4 + slot = "part enabled" byte**.
  RideInfo::UpdatePartsEnabled 0x57ea80 (G): set all to 1, then every installed part with attribute 0xe80a3b62 clears the enabled byte
  of the slot it names (e.g. a wide body hides stock quarter decals). Slot 6 builds "%s_WIDE%d_" and calls CarPartDatabase::GetCarPart 0x57ce10.
- Install path (docs/re/garage.md): InstallPart 0x5044b0 -> BuildRide 0x4ac5a0 -> 0x57ea80 -> FillFromRide 0x4ac750.
- CarRenderInfo ctor 0x56a130 (G): loops ride slots 0..0x1d; per slot and LOD it fills an entry (24 bytes, table at object +0x39b ints,
  0x18 ints per slot): [1] = solid hash from CarPart+0x20.., [3] = Solid* from Solid_FindInAllLists 0x540680. If LOD A is missing it
  falls back to the LOD B hash (CarPart+0x24).
- Stock vs kit: kit parts are just other part records of the same type with another solid hash (e.g. FRONT_BUMPER sub 1 -> RX7_KIT01_FRONT_BUMPER_A).
  KIT numbers run 00..15 per car and are not equal to the sub byte (D).

## 3. How a solid is drawn

- CarRenderInfo::Render 0x56dc30 (G, render.c lines ~940-1000), per frame, slots 0..0x1d with enabled byte (ride+0x6a4+slot) set:
  1. pick the entry for the current LOD (distance table UNK_006b5dec; forced LOD via DAT_006f1b30/34);
  2. patch the solid material table: every material hash 0xd6d6080a (CARSKIN) is replaced by the paint material
     ([obj+0x4d0], found by scanning list DAT_00743c18 for the hash in attribute 0x6ba02c05 of slot 30; spoiler slot 11 uses [obj+0x4e4]);
     every 0x471a1dca (WINDSHIELD) is replaced by [obj+0x4d4] (slot 115 tint). Exhaust tip (0x3b3a1f8d) is patched in the tail;
  3. call Solid_QueueGroups 0x40c910(view, entry, matrix, lod, 0). Mirrors (3,4) are drawn in a separate case; 0xf..0x12 are skipped here.
  So all painted kit surfaces share one paint material and the skin texture; only the other groups keep their own material.
- Solid_QueueGroups 0x40c910 (G/H): loops mesh groups. Group record 0x3c bytes: +0 bbox min, +0xc index count, +0x10 bbox max,
  +0x1c texture index (byte, into solid texture table), +0x20 material index (0xff = none), +0x34 first index, +0x38 flags
  (bit 0 = always draw, else frustum test 0x40db20). It picks the effect from the mesh flags with the tables 0x706898/0x706818/0x706798
  (see render_pc.md) and queues the item with 0x40f1e0; flush 0x40ed70 draws; texture bind 0x40f3d0; material -> constants 0x40fae0.
- Mesh header (chunk 0x134900 aligned: ptr = (chunk+0x17)&~0xf, D): +0xc flags (seen 0x4180, 0xc180), +0x10 group count, +0x14 groups.
  Mesh_FixupGroups 0x40c890 maps flag 0x01 -> effect slot 4 (worldbone), 0x40 -> slot 2 (worldreflect), 0x80 -> slot 5 (car.efx), table 0x701440.
- **Vertex = 36 bytes: float3 position, float3 normal, D3DCOLOR, float2 uv** (D: RX7_KIT00_BODY_A, 491 vertices, 50/50 unit normals,
  color 0xffffffff, uv in 0..1; matches census/car_draw_census.txt stride 36). No tangent, no second UV set.
  VB data starts at the next 0x80-aligned address: file offset = (chunk_off+0x87)&~0x7f.
- Shader car.efx (vs_1_1/ps_1_1, build/canon/w2/car.efx.txt, C census): VS uses position, normal, uv only. **Vertex colour is not used.**
  Lighting = per-vertex spherical harmonics from the normal (HarmonicCoeff[10]); diffuse scale = DiffuseMin + (N.V)*DiffuseRange;
  specular from reflection vector with SpecularPower; env cube EnvMapTex (initialised by 0x40eb30, cube at [0x73646c]).
  PS: out = 2*tex*diffuse; out.rgb += 2*tex.a*(specular + 2*env). **The diffuse texture alpha is the reflectivity mask.**
- Material record (GLOBALB 0x135200, 160 B: hash +0xc, name +0x14) -> constants in 0x40fae0 (G): DiffuseMin = rgb(+0x34..) * +0x30, a=+0x50;
  DiffuseRange = (rgb(+0x44..) * +0x40) - min; SpecularMin = rgb(+0x60..) * +0x5c; SpecularRange = (rgb(+0x70..) * +0x6c) - min;
  SpecularPower = global[0x7070d4] * +0x58; EnvmapMin = rgb(+0x84..) * +0x80 * 0.5; EnvmapRange = (rgb(+0x94..) * +0x90 * 0.5) - min;
  EnvmapPower = +0x7c. Env terms are zeroed when cube quality [0x700e74] is 0 or mesh flag 0x100 is clear; diffuse/spec are zeroed
  when flag 0x80 is clear (this flag source is inferred, NOT VERIFIED).
- Materials seen (D): CHROME has diffuse 0 and high env/spec; PLAINNOTHING and INTERIOR have zero diffuse range.

## 4. Table: part -> solid name -> material -> texture (RX7, D + F; hashes via bStringHash inversion)

| Slot (type) | Solid name pattern | Materials in groups | Texture hash / name |
|---|---|---|---|
| 0 BASE | RX7_KIT00_BASE_A | n/a | n/a |
| 5 BODY | RX7_KIT00_BODY_A..D | CARSKIN (1092 idx), MOLDINGS (156), PLAINNOTHING (291) | RX7_SKIN1 0xefd842c5 (runtime) |
| 1 FRONT_BUMPER stock | RX7_KIT00_FRONT_BUMPER_A.. | CARSKIN, PLAINNOTHING, BOTTOM | SKIN1, CARBOTTOM bd1f0e0a |
| 1 kit 01 SNYPER | RX7_KIT01_FRONT_BUMPER_A | DULLPLASTIC, CARSKIN, PLAINNOTHING, DECAL, BOTTOM (6 groups) | SKIN1, RX7_BADGING 0x12a4882b, CARBOTTOM |
| 1 kits 03..08 | RX7_KIT0n_FRONT_BUMPER_A | RAD, MESH, BOTTOM + CARSKIN | SKIN1, INTERCOOLER 427b4565, GRILL_02 69c032ba |
| 2 REAR_BUMPER | RX7_KITnn_REAR_BUMPER_A (KIT15 uses GRILL 69c032b9) | CARSKIN, PLAINNOTHING, BOTTOM | SKIN1, CARBOTTOM |
| 10 SKIRT | RX7_KITnn_SKIRT_A (KIT14 carbon) | CARSKIN, PLAINNOTHING, BOTTOM; KIT14 CARBONFIBER2 | SKIN1, CARBOTTOM; KIT14 CARBONFIBRE 721aff7c |
| 3/4 MIRRORS | RX7_KIT00_LEFT/RIGHT_SIDE_MIRROR_A,B | CARSKIN, MIRROR | SKIN1 |
| 7 ROOF, 8 HOOD, 9 TRUNK | RX7_KITnn_ROOF/HOOD/TRUNK_A..; kit names not all recovered | CARSKIN (+ carbon on some) | SKIN1 |
| 11 SPOILER | RX7_KIT00_SPOILER_A..D (mesh flags 0x4180, vertex colour 0xff000000) | CARSKIN (paint from [obj+0x4e4]) | SKIN1 |
| 6 WIDE_BODY | KITW01/02 (VAPOR, MANTIS), ColVol only for physics | CARSKIN | SKIN1 + DOORLINE_WIDEBODY(_MASK) |
| 12 ENGINE | RX7_KIT00_ENGINE_A,B | DULLENGINE, ENGINE | RX7_ENGINE 0xca6d8215 |
| 13 HEADLIGHT / 14 BRAKELIGHT | RX7_KITnn_HEADLIGHT/BRAKELIGHT_A.. (EYELIDS, VOLTAGE, PROJECTOR, LUNAR; CRIMSON, CHROME, MASKED, REAPER) | HEADLIGHTGLASS, BRAKELIGHT, CLEARPLASTIC, CARBONFIBER, RUBBER | RX7_STYLE0n_HEADLIGHT / BRAKELIGHT |
| 15 EXHAUST | RX7_KIT00_EXHAUST_A | DULLENGINE, CHROME, PLAINNOTHING; tip EXHAUST_TIP | n/a |
| 17 WHEEL | Cars/WHEELS solids, e.g. WHEEL_A | RUBBER, PLAINNOTHING, MAGSILVER (rim materials by type) | RX7_TIRE 0x35d0c513, rim textures from WHEELS pack |
| 16 BRAKE | Cars/BRAKES solids | BRAKEDISC, CALLIPER | CALIPER 0xd6640dff |
| 30 paint | no solid, material only | REGPAINT*, METPAINT*, PEARL*, CUSTOMPAINT_n (attribute 0x6ba02c05) | n/a |
| 31..36 vinyl | no solid; layers drawn into the skin | n/a | VINYLS.BIN textures |

Part counts for RX7 by slot (F): bumpers/skirts 16 kits each (STOCK, SNYPER, ACE, RENEGADE, SHADOW, STRIKE, FLASH, WOLFPACK, SPYDER,
TYPE V, VORTEX, CRANK, STORM, FRENZY, BLAST, RAGE); 4 headlight and 4 brakelight kits; many roof/hood/spoiler kits.

## 5. Unknown / NOT VERIFIED

- Compositing of RX7_SKIN1: 0x56c3d0 only builds decal hash lists (DUMMY_DECAL1..8, DEFAULTALPHA, _MEDIUM/_LARGE/_SQUARE) (G);
  the render-to-texture step was not found. 0x580b00 builds %s_SKIN1 ([0xf2]), %s_SKIN1B ([0xf3]), GLOBAL_SKIN1 ([0xf4]), %s_WHEEL ([0xf5]).
- Which matrix places each part: Render passes one car matrix to 0x40c910 (G); wheel/brake dummy markers (0x13401a) not read.
- No native RN_GEODUMP run was made; vertex format is from file bytes plus census, not from a live draw.
- Names of non-stock hood/roof/spoiler/headlight/wide-body solids (not needed: the runtime uses the DB hashes).

## 6. Remaster hooks (a switchable look change for kit parts, no new reflections)

1. **Material constants at 0x40fae0** (G), fed by the GLOBALB 0x135200 records. Raising DiffuseRange and lowering DiffuseMin gives more
   shading contrast (volume) while Env* and Specular* stay stock, so no new reflections. It can be scoped per part type because kit
   surfaces use distinct materials: BOTTOM, DULLPLASTIC, CARBONFIBER2, RAD, MESH, MOLDINGS, PLAINNOTHING, and CARSKIN (per car paint, patched at
   Render 0x56dc30). Evidence: the formula DiffuseMin + (N.V)*DiffuseRange and the per-material record layout above. Best first hook: one switch,
   one write site, and PLAINNOTHING/INTERIOR already have zero range, so they need a floor too.
2. **Per-vertex data of 0x134b01 / car.efx**. The VS ignores the vertex colour, yet kit, skirt and spoiler vertices carry baked values
   (0xff000000 and grays, D). A replacement car vertex shader (hash 0x4728b668 in host/d3d9.c, WVP in c10..c13) could read colour as an AO
   term and multiply the diffuse only, or recompute normals (smooth by position) for stronger curvature shading. Evidence: stride 36 and
   unit normals (D), VS input usage (C census). Risk: colour semantics are unproven; test on one kit before trusting it.
3. **Texture swap or filter at the group level**: the texture table (0x134012) is resolved by 0x53f9b0 and bound at 0x40f3d0. Kit parts share the
   SKIN1 atlas plus static kit textures (CARBOTTOM, INTERCOOLER, GRILL_02, CARBONFIBRE, BADGING, STYLE lights). A baked AO or normal-lit
   overlay can be added there. Constraint: ps_1_1 uses the texture alpha as the reflectivity mask, so any replaced texture must keep its
   alpha, or it adds reflections.

**Applied (2026-10-29): ?carvol=0|1|2 (RN_CARVOL, host/sm1.c car_ps_vol).** Hook 1 turned out to be the diffuse path itself: the kit materials
(DULLPLASTIC, MATTEPLASTIC, BOTTOM, MOLDINGS, SHINYPLASTIC, GRILL) have DiffuseRange 0 and DiffuseMin ~1 (build/carlook/carvol/materials.txt, GLOBALB
0x135200 read with the 0x40fae0 formulas), so c18/c19 in the shader mark them. The effect multiplies only the diffuse term (an N.V ramp plus
crease darkening from dN.dP/|dP|^2); the cube, Env and Specular terms are untouched. Default 1 (subtle, paint luminance within ~3 %), 2 = 1.7x,
split / split2 = right half only, for an A/B in one frame.
