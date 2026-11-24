# Assets: containers, chunk loaders, resource files, compression

> Source: `docs/re/assets.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 55

# Assets: containers, chunk loaders, resource files, compression

Marks: V = verified (two tools agree or bytes round-trip), I = inferred, U = open. Tools: H = Hopper export,
G = Ghidra export/headless, C = capstone (tools/recomp/asm.py), F = the game files through tools/re readers.

## Answer
- Every BUN/BIN/LZC game file is a flat list of chunks `{u32 id, u32 size, payload}`; bit 31 of the id = container
  of more chunks, id 0 = padding. 235 files tile exactly, 116 ids, 58 at top level (`tools/re/chunks.py check`, V F).
- Top-level chunks go to 47 loaders in the table `0x7007e0` (unloaders `0x7008a0`), tried round-robin by
  `0x447ac0`; every top-level id in game/ has a loader (V F+H+G). Chunk meanings: table below (137 ids = 115 seen in game files + 22 known only from code or nested children, 18 of them U; the 116th id seen in files is 0, padding; reconciled 2026-10-29).
- Files are read async by ResourceFile objects (`0x447f90`..`0x448440`), decompressed by `0x58d3f0`
  (JDLZ or COMP), placed by `0x447c00` and handed to the dispatcher by `0x447d90` (V H+G).
- Textures live in TPK packs (`0xb3300000`, loader `0x5455c0`); `tools/re/tpk.py` lists them and writes .dds (V F).
- Readers: `tools/re/chunks.py` (tree/census/check), `tools/re/tpk.py` (list/dds/check), `tools/census/jdlz.py`
  (GlobalB.lzc and InGameB.lzc unpack byte-exact to GLOBALB.BUN / INGAMEB.BUN).

## Pipeline (V H+G unless marked)
1. `CreateResourceFile 0x4482f0` takes a slot (0xb4 bytes) from `ResourceFileSlotPool` (`0x447f40`): +0x18 name,
   +0x30 flags (2/4, 8 = compressed), +0x88 pool, +0x8c pending reads, +0x90 loaded, +0x94/+0x98 callback,
   +0x9c buffer, +0xa0 size. Files are kept in the list `0x77a924/0x77a928`; pending count `0x7360e8`.
2. `ResourceFile::BeginLoading 0x448110` allocates and queues the async read `0x58aba0`; `OnReadDone 0x4482e0`
   counts down; `ServiceResourceLoading 0x4483c0` (per frame) calls `FinishLoading 0x448220` when reads are done.
3. `FinishLoading`: `IsCompressedBuffer 0x58d3c0` ("COMP" ver 1 or "JDLZ" ver 2) -> `DecompressBuffer 0x58d3f0`
   (COMP path `0x58d2c0`). JDLZ header: "JDLZ", 02, 10, 00 00, u32 unpacked, u32 packed.
4. `LoadResourceChunks 0x447d90` -> `PlaceChunks 0x447c00`: two pools; `0xb3320000` pixel data goes to the second
   pool (flag 0x2000); id-0 padding filled with 0x11 keeps 128-byte alignment of pixel/vertex data.
5. `bChunkLoader::LoadChunks 0x447ac0`: for each top-level chunk, loaders from the table, starting from the one
   that took the last chunk; no taker after n+1 tries -> int3. `UnloadChunks 0x447b10` walks chunks last-first.
6. `UnloadResourceFile 0x448370`, `FindResourceFile 0x448440` (by name).

GameFlow file order (V H+G): `0x448600` GLOBALA.BUN + LANGUAGETEXTURES.BIN; `0x448650` GLOBALB.LZC (flags 9, slot
renamed .BUN) + car part files; `0x448b10` FRONTB; `0x449765` TRACKB%d.LZC/.BUN; `0x44952b` TEX%dTRACK.BIN.
`0x447160` sets up the optional ZDIR.BIN/ZZDATA archive (not shipped). PRERACEANIM.LZC is only looked up, never
created (I). NFSU20MEG.bin is not referenced by Speed.exe (V: no string).

## Textures (TPK, loader 4 `0x5455c0`, V F+C+G headless)
- `0xb3300000` pack = `0xb3310000` header container + `0xb3320000` data container (the data may also stand alone
  at top level, paired to its pack by key: header `+0x60` = data node `0x33320001 +0xc`, matched at `0x545660`).
- `0x33310001` header 0x7c: version 4, name[0x1c], path[0x40] (`...\240SX_Textures.tpk`), key.
- `0x33310002` sorted {hash, slot} index, binary search `0x53e400`. `0x33310004` records 0x7c: name +0xc,
  hash +0x24, link hash +0x2c, pixel/palette offsets +0x30/+0x34, sizes +0x38/+0x3c, mip0 size +0x40, w/h +0x44/+0x46,
  pixel code +0x4a, mips +0x4e. `0x33310005` GPU entries 0x20: D3DFORMAT at +0x14 (P8 0x29, DXT1, DXT3, A8R8G8B8).
- 84 packs (car TEXTURES/VINYLS, HUDTEX) carry `0x33310003`: 20-byte entries pointing at one JDLZ stream per
  texture; each stream unpacks to the record's range pixel offset .. palette end, same layout as the blob (V F,
  all streams). No reader of it found in the load path (consumer U).
- Several packs in one file may share a key (STREAML1RE: 13 packs, 2 keys): a data block binds to the latest pack
  with its key in file order (I from 0x545660 list walk; V F: all ranges fit).
- `tools/re/tpk.py check`: 347 packs, 27,458 textures, 0 bad; pixel size = sum of mip sizes for every texture
  (P8 17,572, DXT1 7,356, DXT3 2,062, A8R8G8B8 468). `tpk.py dds` output opens in macOS Preview (HUD gauge).
- `0x545900` binds records to GPU entries; `0x5459f0` maps pixels; `0x407db0` creates the D3D texture (w/h must be
  powers of two). Fallback texture DEFAULTALPHA (hash `0x66994f4a`) kept at `0x73551c`.
- 2247 car-pack records have a +0x24 hash that is not bStringHash(name) (U: other input).

## Second-tool agreement (10 sampled names)
H and G show the same entry, compares and callees for: `0x447ac0`, `0x447b10`, `0x447d90`, `0x448220`,
`0x4483c0`, `0x448370`, `0x448440`, `0x58d3c0`, `0x441380` (ids 0x34130..0x34134, 0xffff stamp), `0x47dcd0`
(0x80034405..25, 0x34440..0x34492). 10/10 agree. Table-only entry points (`0x5455c0`, `0x545770`) are not in
either export: G headless + C only.

## Open (U)
- `0x33310003` consumer; `0x34a07`, `0x37010`, `0x34300/1`, `0x39100..2`, `0x3a000` meanings; `0x134004`,
  `0x13401b`; TPK record +0x28 tag and +0x50..0x5f flags; camera-table containers 0x80034405..25 (accepted, not shipped).
- Dead ids (accepted, absent from game/): `0x34021`, `0x34030`, `0x13401b`, `0x80035000/10`, `0x80034405..25`,
  `0x34440..0x34490`, `0x34300/1`, `0x39100..2`, `0x37010`.

## Chunk ids
Raw rows with layout, globals and evidence: `census/names_raw/assets_loaders{A,B}.tsv`; counts per id:
`census/chunks.json`.

| id | name | mark | chunks | meaning |
|---|---|---|---|---|
| `0x00030201` | FEngFontDef | V | 67 | Front-end font definition: font file and bitmap names plus glyph tables; a 0x30-byte host node is malloc'd per chunk and registered. |
| `0x00030203` | FEngPackage | V | 22 | FrontEnd (FEng) UI package: whole .fng file wrapped as a chunk; 22 chunks in 5 files (GLOBAL, INGAMEB, FrontB...) |
| `0x00030210` | FEngPackage (variant) | V | 201 | FEng package chunk, second form (201 chunks in 5 files); package id hash at payload+0 |
| `0x00030220` | PresetRide[] | V | 1 | preset car configurations of the garage/front end, 0x408 (1032) B each, 184 rows (189,888 B, FrontB only) |
| `0x00030230` | MagazineTables | V | 2 | front-end tables, 23,024 B (GLOBALB, 2 files): 8 counts then 8 object lists |
| `0x00030240` | CarDecalSlots[] | V | 1 | per-car decal slot records: u32 count then 28-byte (7 dword) records; 564 B = 4 + 20 x 28 (FrontB, 1 file) |
| `0x00034021` | CarShapeSkipped | V | 0 | Skipped by the shape loader (explicit compare, no action). Absent from game files. |
| `0x00034026` | SmackableDef[] | V | 33 | destructible street-furniture records, 0x100 (256) B each, 16-aligned start; 33 chunks in 33 files (INGAMEB, TRACKB*) |
| `0x00034027` | SmackableProp[] | V | 24 | smackable prop placements, 0x70 (112) B each, 16-aligned start; 24 TRACKB files (120 B..49.8 KB) |
| `0x00034030` | UnusedChunk34030 | V | 0 | Accepted by loader 22 (links the chunk in list 0x737b48 and sets two fields) but absent from all game files. |
| `0x00034035` | NisSceneHeader | I | 175 | Cutscene/NIS descriptor: first dword is rewritten to point at a name string at payload+0x7c (e.g. 'Day start'); used by the intro NIS coordinator (0x47ef00) ... |
| `0x00034036` | PostRaceSceneTable | I | 2 | Twelve pick-lists of streamer section ids (2301..2335) for the post-race scene, by racer count and finishing rank; shuffled by 0x47b730 and picked at random. |
| `0x00034101` | SceneryHeader | V | 593 | 60..68-byte section header: +0xc section id, +8 loaded flag, +0x18/+0x1c info ptr/count (0x34102), +0x20/+0x24 instances (0x34103), +0x28/+0x2c tree (0x34104). |
| `0x00034102` | SceneryModelSlots | V | 593 | 0x48-byte records: 6 solid-name hashes at +0..+0x14 (skipping 0 and two sentinel hashes), resolved at load to solid objects at +0x24..+0x38. |
| `0x00034103` | SceneryInstances | V | 593 | 0x30-byte placed-object records (flags short at +0xe: 0x10 = hidden flag toggled by DAT_00734470 table). |
| `0x00034104` | SceneryTreeNodes | I | 593 | 0x18-byte nodes (bounding tree over instances). |
| `0x00034107` | StreamSection[] | V | 31 | streaming section table: 0x38 (56) B per section; 401 rows in each TRACKB (31 files, 2.4..22 KB) |
| `0x00034108` | StreamSectionInfo | V | 31 | 12 B: {u32 0x135e0, u32 total size of the base STREAM*.BUN (0x581d4c0 = size of STREAML1RA.BUN), u32 0} |
| `0x00034121` | RoadSections | V | 31 | Road-network sections: a 0x27c header followed by n 0x88-byte nodes (n = s16 at +0x10); section id s16 at +0xa selects slot; value at +0xc picks list 0 or 1. |
| `0x00034122` | RoadPathEntries | V | 30 | 32-byte path entries between nodes (distance f32, section id byte +0xa, type byte +0xb, node index u16 +0xc). |
| `0x00034123` | RoadTrafficData | V | 14 | 0x170-byte per-section traffic rows. |
| `0x00034124` | RoadRoutes | V | 20 | 0x108-byte traffic route/junction records. |
| `0x00034130` | TrackCollisionQuadtree (wmap) | V | 31 | Quadtree of the collision grid: 8-byte nodes (4 x u16 child); row 0 is the root, leaf value is a wcell row. |
| `0x00034131` | TrackCollisionCells (wcell) | V | 31 | Cell table of the collision grid: f32 x, f32 y, u32 first widx index, u32 count (16 B); row 0 sentinel. |
| `0x00034132` | TrackPolygons (wsrc) | V | 31 | Collision polygons, ground and walls, 32 B each; loader marks every row's runtime body slot (+6) as 0xffff. |
| `0x00034133` | TrackCollisionIndex (widx) | V | 31 | u16 polygon-row lists addressed by wcell (off,count). |
| `0x00034134` | TrackWorldBounds | V | 31 | World bounding box: min xyz at record +0..+8, max xyz at +0x10..+0x18 (7 dwords copied, +0xc and +0x1c skipped). |
| `0x00034146` | TrackPositionMarker | V | 31 | Named positions on the track (start grid forward/backward, others) as a linked list of 0x30-byte records; looked up by (type hash, index). |
| `0x00034148` | TrackPath[] | V | 31 | route table, 40 B (0x28) per path; every track has exactly one (size 40) |
| `0x00034149` | TrackPathNode[] | V | 31 | path nodes, 20 B (0x14) each (200..2000 B per file = 10..100 nodes) |
| `0x0003414a` | TrackZone[] | V | 31 | zone table, 0xb4 (180) B per row, sorted by +0 type 0..10; 11-entry first-index table built at obj+0x20 (rows with type < n) |
| `0x00034151` | StreamBoundaryPolygon | V | 31 | 0x8c-byte boundary polygon rows (id s16 at +8, vertex count s16 at +0xa, up to 16 f32 xy); two lists chosen by id shape (letter 'A'..'T' + digit). |
| `0x00034152` | StreamVisibleSet | V | 31 | 0x94-byte rows: s16 id (=a 0x34151 id), polygon ptr at +0xc (set at load), count at +0x10, section ids from +0x14. |
| `0x00034153` | StreamCorridor | V | 31 | 0x110-byte rows: track id, count, list of boundary ids (per track, lookahead filter). |
| `0x00034154` | StreamAlwaysOn | V | 31 | 32-byte rows: track id, count (<=8), section ids always wanted for this track. |
| `0x00034201` | TrackInfoTable | V | 2 | Per-track description rows (31 tracks): the career/track list read by menus and loading (strings SkipFE, LoadingTrackCommon seen in 0x4b6390). |
| `0x00034202` | TrackSkyInfo | I | 2 | Sun/sky/fog style rows per region name: version dword 2, name hash at +4, name string at +8 (e.g. PARKLAND), a vec3 at +0x20 copied to 0x740400..0x740408. |
| `0x00034250` | TriggerVolumeSet | V | 31 | named volumes (FOG_..., sound/ambient triggers) in 5 class lists; 31 TRACKB files (24 B empty .. 21 KB) |
| `0x00034300` | Table34300 | U | 0 | table of 0x44 (68) B rows; absent from every game/ file |
| `0x00034301` | Table34301 | U | 0 | rows of 0xb4 (180) B; absent from every game/ file |
| `0x00034440` | CameraTableChild_40 | U | 0 | Child of the camera-table containers (header); absent from the shipped files. |
| `0x00034450` | CameraTableChild_50 | U | 0 | Child of the camera-table containers (entry); absent from the shipped files. |
| `0x00034460` | CameraTableChild_60 | U | 0 | Child of the camera-table containers (entry B); absent from the shipped files. |
| `0x00034470` | CameraTableChild_70 | U | 0 | Child of the camera-table containers (entry C); absent from the shipped files. |
| `0x00034480` | CameraTableChild_80 | U | 0 | Child of the camera-table containers (entry D); absent from the shipped files. |
| `0x00034490` | CameraTableChild_90 | U | 0 | Child of the camera-table containers (entry E); absent from the shipped files. |
| `0x00034492` | CameraShakePresets | I | 2 | Camera shake pattern table: records named 'ShakeA1','ShakeA2',... each with a sample count and up to 32 samples of two floats. |
| `0x00034600` | CarTypeInfoTable | V | 2 | CarTypeInfo array for 35 cars: each 0xc90 bytes starting with the car name ('GOLF'...), then asset paths (CARS\GOLF\GEOMETRY.BIN ...). |
| `0x00034601` | CarColorTable | I | 2 | Car paint/colour records: 0x40 bytes (u32 0, u32 1, name string such as 'Graphite Black w/ Silver Stripe' from +8, then numbers). |
| `0x00034603` | CarPartHeader | I | 2 | 32-byte header: payload[4]=part record count (0x11b9=4537), payload[6]=attribute pair count (0x1fb1=8113), payload[2]=5 (version?). |
| `0x00034604` | CarPartRecords | I | 2 | Part records, 0x30 bytes each (4537): +0 name offset, +0xc hash, +0x10 u8 category (0x1e/0x1f = bucketed wheel/body-kit style parts), +0x14/+0x18 attribute o... |
| `0x00034605` | CarPartAttributes | I | 2 | Attribute table: 8-byte entries (hash/id, value) indexed by records with offsets *8. |
| `0x00034606` | CarPartNames | V | 2 | String pool of part names (LIVIA 20, SPLIT 20, ...), NUL separated; record name offsets are relative to it. |
| `0x00034a01` | EventClassRow[] | V | 1 | 32-byte rows keyed by a u32 index < 32 (25 rows, 800 B); thresholds 300/600/900 ... 30/60/90 |
| `0x00034a02` | EventDesc[] | V | 1 | career event descriptions, 0x14c (332) B each, 116 rows (38512 B) |
| `0x00034a03` | CharacterRoster | V | 1 | FrontB roster: 64 x 12 B {u32 id, char name[8]} (eddie, carl, nesto, bopper, lazio, ricco, b-dog...) followed at payload+0x300 by 128 x 44 B {u32 id, u8 map[... |
| `0x00034a07` | ModeFlagTable | U | 2 | 31 rows of 0x20 bytes (hash at +0, flags +6/+7, floats) indexed by object number; byte +7 is masked with a per-game-mode bit when 31 objects of 0x44 bytes ar... |
| `0x00034a08` | Table34A08[] | V | 2 | 32-byte rows, 114 rows (3656 B incl. 8 B alignment pad), GLOBALB |
| `0x00034a09` | Table34A09 | V | 1 | 144 B = 9 x 16 B rows {u32 id 0..8, u32 3/4/5, ...}; the aligned payload ptr is stored; unloader clears the FIRST dword only |
| `0x00034a0a` | Table34A0A[] | V | 1 | 16-byte rows, 86 rows (1384 B incl. 8 B pad); row = {u16 a, u16 c?, u16 b, u16 v, 8 zero B}, e.g. (0,1,1,0x2d01) |
| `0x00034b00` | RacerAITuning | V | 2 | one block of 523 f32 (2092 B) copied to a fixed array; GLOBALB only (2 files) |
| `0x00035020` | ParticleEmitter | I | 33 | Particle emitter instances: 0xc0 bytes each (version dword 5, count at +0xc); each links to its definition by key (0x402b40) and is queued by type (0x402bd0). |
| `0x00035021` | ParticleEmitterDef | I | 33 | Particle/effect definitions: 0x220 bytes each (version dword 4, count at +0xc), each linked into a list and its texture hash (+0xc of record) resolved via th... |
| `0x00036001` | WorldZoneHeader | V | 31 | 24-byte header; version dword 1 at +8, record count (0x161 in TRACKB1001) at +0xc, pointers +0x10/+0x14 written at load. |
| `0x00036002` | WorldZoneNodes | V | 31 | Tree nodes of 0x30 bytes: center xyz, half extents +0x10..+0x18, s16 child/leaf count at +0xe (>0 internal, <=0 leaf of -count entries), s16 indices from +0x1c. |
| `0x00036003` | WorldZoneEntries | V | 31 | 0x20-byte zone entries: +4 id, +0xc u32 direction mask tested with 1<<arg, +0x10..+0x18 center xyz, +0x1c radius. |
| `0x00037010` | Chunk37010 | U | 0 | accepted and ignored: loader #25 only compares the id and stores nothing; no game/ file contains it |
| `0x00039000` | LanguageStrings | V | 22 | language string table, one top-level chunk per Languages/*.bin (22 files) |
| `0x00039010` | MovieSubtitles | V | 1 | subtitle scripts for the story movies; FrontB only (864 B): u32 n=20 then n variable entries |
| `0x00039100` | Chunk39100 | U | 0 | payload pointer kept; absent from every game/ file |
| `0x00039101` | Chunk39101 | U | 0 | linked list node (next at payload+0, prev at payload+4), payload+0x38 set to 1; absent from game/ |
| `0x00039102` | Chunk39102 | U | 0 | payload pointer kept; absent from game/ |
| `0x00039200` | CarShapeHeader | V | 2506 | 88..100-byte shape header: key at +0x18, name at +0x1c; then the next two sibling chunks hold vertices and indices. |
| `0x00039201` | CarShapeVertices | V | 2506 | Collision-hull vertices: 0x30-byte entries (xyz at +0x10), 16-aligned start; count=(end-start)/0x30. |
| `0x00039202` | CarShapeIndices | I | 2506 | u16 index list of the hull; count=(end-start)>>1. |
| `0x0003a000` | Table3A000 | U | 2 | two s16 then 128 x 64 u16 table (16388 B = 4+16384); present in 2 files (INGAMEB) |
| `0x0003b200` | DragCameraSet | V | 31 | drag-race camera records; chunk is EMPTY (size 0) in all 31 TRACKB files, the same parser reads ..\..\World\Location1\Track_%04d\DragCameras.bin |
| `0x0003b300` | WorldObjectCohort[] | V | 31 | scene-object launch records, 0xa0 (160) B each, 16-aligned; 31 TRACKB files (about 114 KB, 700+ rows) |
| `0x00134002` | SolidListHeader | V | 1276 | 128-byte header: list links (+0/+4), name string at +0x10 ('SolidList,%s'), flag short +0x72 =1, pointers +0x78 -> 0x134003, +0x7c -> 0x134004. |
| `0x00134003` | SolidHashIndex | V | 1276 | Sorted array of (u32 solid name hash, u32 solid pointer) pairs for the list; the solid loader fills the pointers. |
| `0x00134004` | SolidListExtra | U | 40 | Extra table that only car GEOMETRY.BIN files carry (40 chunks); pointer kept in the list header, content not read by the loader. |
| `0x00134011` | SolidHeader | V | 19989 | 176..188-byte solid record: +4/+8 list links, +0xd loaded flag, +0xe flags (0x10 no-reorder, 0x80, 0x100), +0x10 name hash, +0x19 u8 texture count, +0x1a u8 ... |
| `0x00134012` | SolidTextureTable | V | 19989 | Per-solid texture hashes: (u32 texture hash, u32 texture object ptr) pairs resolved through the texture packs at load (0x53f9b0 -> 0x5461c0). |
| `0x00134013` | SolidMaterialTable | V | 11828 | Per-solid material hashes: (u32 hash, u32 ptr) pairs; ptr resolved by scanning the 0x135200 material list (0x743c18) and falling back to the default material... |
| `0x00134017` | SolidCollisionHeader | I | 4968 | 12-byte runtime header for a small low-poly mesh (cars only): +0 vertex ptr, +4 triangle ptr, +8 u16 vertex count, +0xa u16 triangle count. |
| `0x00134018` | SolidCollisionVertices | I | 4968 | Array of 8-byte vertices (count = size>>3). |
| `0x00134019` | SolidCollisionTriangles | I | 4968 | Array of 12-byte triangle records (count = size/0xc). |
| `0x0013401a` | SolidMarkers | I | 3197 | 0x50-byte marker/attachment records (positions with a type at +0xd; light flares on cars per docs/flare_re.md); count stored as a byte at solid+0x1b. |
| `0x0013401b` | SolidExtra13401b | U | 0 | Accepted by the solid loader (pointer to +0x90, size added to DAT_0072fa10) but absent from every game file. |
| `0x00134900` | MeshHeader | V | 19989 | 64-byte mesh header (vertex format mask +0xc, group count +0x10, groups ptr +0x14, index ptr +0x18/size +0x1c, vertex ptr +0x28/size +0x30, triangle count +0... |
| `0x00134b01` | MeshVertices | V | 19989 | Vertex bytes, 128-byte aligned ((addr+0x87)&~0x7f), copied into a D3D vertex buffer. |
| `0x00134b02` | MeshGroups | V | 19989 | 0x3c-byte draw groups (bbox, index count, texture slot, start index, flags). |
| `0x00134b03` | MeshIndices | V | 19989 | u16 index data copied into a D3D index buffer. |
| `0x00135001` | LightTreeHeader | V | 31 | 28-byte header: version 3 at +8, pointers to the tree (+0xc) and entries (+0x14) written at load, count near +0x18. |
| `0x00135002` | LightTreeNodes | I | 31 | Tree nodes (center, extents, child/leaf short lists), first dword pre-set to point +0x10 into itself. |
| `0x00135003` | LightTreeEntries | I | 31 | Light entries (colour, position, radius ...) addressed by the tree. |
| `0x00135101` | LampFlareHeader | V | 31 | 64-byte header: version 3 at +8, record count at +0x30, list sentinel at +0x38. |
| `0x00135102` | LampFlareRecords | V | 31 | Flare records, 0x50 bytes each, inserted in the header's list (links in the first 8 bytes). |
| `0x00135200` | Material | V | 278 | Material (shader parameter) record, 160 bytes: hash at +0xc, version 3 at +0x10, name string at +0x14 (e.g. ALUMINUM) then float colour parameters. |
| `0x00e34009` | AnimationSkeleton | V | 16 | EAGL skeleton: also an ELF object, loaded by EAGL::DynamicLoader CAnimSkeleton, symbol 'Skeleton'. |
| `0x00e34010` | AnimationBank | V | 712 | EAGL animation bank: the payload is a 32-bit little-endian ELF relocatable object (e_machine 8 = MIPS) loaded by EAGL::DynamicLoader, symbol 'AnimationBank'. |
| `0x30300101` | TexAnimHeader | V | 35 | 16-byte header of the animation pack; first dword is a version that must equal 1. |
| `0x30300102` | TexAnimSets | V | 35 | Animation sets: 0x34-byte records (up to 10), each with a frame count at +0x1c and a runtime frame-data pointer written at +0x28. |
| `0x30300103` | TexAnimFrames | I | 35 | Frame records for all sets, 16 bytes each (2..38 per chunk). |
| `0x33310001` | TexturePackHeader | V | 347 | pack header, 124 B (0x7c), payload IS the in-memory pack object |
| `0x33310002` | TexturePackHashIndex | V | 347 | sorted name-hash -> texture-record index; 8 B per texture |
| `0x33310003` | TexturePackStreamDirectory | V | 84 | directory of per-texture JDLZ-compressed pixel streams; present only in the 84 car TEXTURES.BIN packs |
| `0x33310004` | TextureRecord[] | V | 347 | per-texture record array, 0x7c (124) B each; sorted ascending by +0x24 hash |
| `0x33310005` | TextureGpuEntry[] | V | 347 | per-texture GPU format entry, 32 B each; same count as 0x33310004 (record i uses entry i) |
| `0x33320001` | TexturePackDataNode | V | 347 | 24 B list node tying a data blob to its pack |
| `0x33320002` | TexturePackPixelBlob | V | 347 | raw pixel data: all textures of the pack, addressed by record +0x30/+0x34 offsets from the 128-byte aligned start |
| `0x80034020` | CarShapeContainer | V | 68 | Container of collision-shape triples (0x39200,0x39201,0x39202); identical in all 16 street TRACKB files and cars' GEOMETRY.BIN. |
| `0x80034100` | ScenerySection | V | 593 | One streamed track section (STREAMxxx.BUN): header, model-slot table, instances and tree nodes. |
| `0x80034147` | TrackPathContainer | V | 31 | per-track route polylines + zones container (31 TRACKB files); loader 24 |
| `0x80034150` | StreamBoundaries | V | 31 | Container of streaming boundary data: boundary polygons, visible-set lists, corridor and always-on lists. |
| `0x80034405` | CameraTableContainer_05 | U | 0 | Container accepted by the same loader (0x47dcd0) with child 0x34440 (header 4 dwords) and 0x34450 (entries); none of these exist in the shipped game files. |
| `0x80034410` | CameraTableContainer_10 | U | 0 | Container accepted by the same loader (0x47dcd0) with child 0x34460; none of these exist in the shipped game files. |
| `0x80034415` | CameraTableContainer_15 | U | 0 | Container accepted by the same loader (0x47dcd0) with child 0x34470; none of these exist in the shipped game files. |
| `0x80034420` | CameraTableContainer_20 | U | 0 | Container accepted by the same loader (0x47dcd0) with child 0x34480; none of these exist in the shipped game files. |
| `0x80034425` | CameraTableContainer_25 | U | 0 | Container accepted by the same loader (0x47dcd0) with child 0x34490; none of these exist in the shipped game files. |
| `0x80034602` | CarPartDatabase | V | 2 | Part database: header, string pool, attribute table, part records; stored as one node with prev/next links in list 0x73ad40. |
| `0x80034a00` | CareerEventTables (container) | V | 1 | FrontB career container: 0x34a01 + 0x34a02; 1 file |
| `0x80035000` | ParticleContainerA | V | 0 | Accepted as a no-op by loader 9 (returns 1 immediately). Absent from all game files. |
| `0x80035010` | ParticleContainerB | V | 0 | Accepted as a no-op by loader 9. Absent from all game files. |
| `0x80036000` | WorldZoneTree | I | 31 | Per-track spatial tree of sphere zones (mask by driving direction) used for player-position queries. |
| `0x8003b000` | SplineSet (container) | I | 31 | container of spline records; present but EMPTY (size 0) in all 31 TRACKB files |
| `0x80134000` | SolidPack | V | 1276 | Top-level container of model data: one 0x80134001 (list) followed by many 0x80134010 (solids). |
| `0x80134001` | SolidListContainer | V | 1276 | Per-model-file list of solids: header (name of the .bin), sorted hash->solid table, optional extra table. |
| `0x80134008` | SolidListSeparator | V | 1276 | Empty container inside a solid list; loop walks it and does nothing (0 bytes in all 1276 files). |
| `0x80134010` | Solid | V | 19989 | One drawable model: header 0x134011, texture hash table, material hash table, optional collision mesh, light markers and a 0x80134100 mesh container. |
| `0x80134100` | SolidMesh | V | 19989 | Mesh container of a solid (D3D mesh header + vertex/index/group data); loaded by 0x40c690, which builds the D3D vertex buffer. |
| `0x80135000` | LightTreePack | I | 31 | Per-track spatial tree of dynamic lights near the car: header, tree nodes, light entries. |
| `0x80135100` | LampFlarePack | V | 31 | Per-track-section list of street-lamp flare records, drawn as flares by the 'Track lamps' pass (0x544f30 from 0x409580). |
| `0xb0300100` | TextureAnimationPack | V | 35 | Animated-texture (frame sequence) tables, loaded by the texture-pack loader (not listed under any loader in chunks.py). |
| `0xb3300000` | TexturePack (container) | V | 347 | one texture pack (TPK): header container + data container; 347 chunks in 142 files (CARS/*/TEXTURES.BIN, VINYLS.BIN, GLOBAL, FRONTEND, STREAM*.BUN) |
| `0xb3310000` | TexturePack header (container) | V | 347 | pack index: header, hash table, optional compressed-stream directory, texture records, GPU-format entries |
| `0xb3320000` | TexturePackData (container) | V | 347 | pixel data container; either child of 0xb3300000 or a top-level chunk streamed separately (loader 0x5455c0 branch 0x5456b0 -> 0x545580) |
