# DirectX 9 to WebGPU & WebGL 2: Native BC1/2/3 Textures and a Zero-Waste Draw Pipeline

- Date: 2026-11-23
- Commits: deb8f28, 00e474c
- Live game: https://nfsu.cc/
- Repository: https://github.com/Caliko06/need-for-speed-underground-browser

Translating a 2003 DirectX 9 renderer to WebGPU (with automatic WebGL 2 fallback) is easy to make correct and hard to make fast. Two rendering passes removed the biggest CPU and VRAM bottlenecks.

## Keeping DXT1/3/5 textures compressed as BC1/2/3 (`00e474c`)

Need for Speed Underground ships its car liveries, road surfaces, and Olympic City environment textures as DirectX DXT1, DXT3, and DXT5 blocks. Earlier browser builds decoded those blocks to uncompressed RGBA8 on the CPU before uploading them, multiplying VRAM usage by 4x to 8x and stalling frame times during streaming.

Commit `00e474c` introduced **`RN_S3TC`** end-to-end:

- **`host/d3d9.c`**: Detects hardware block-compression support and passes raw DXT1/3/5 mip bytes straight through the host GPU command stream without CPU decompression.
- **`web/gpu.js` (WebGPU)**: Requests `texture-compression-bc` when available and uploads directly to `bc1-rgba-unorm`, `bc2-rgba-unorm`, and `bc3-rgba-unorm` textures.
- **`web/webgpu_gl.js` (WebGL 2 fallback)**: Uses `WEBGL_compressed_texture_s3tc` (`compressedTexImage2D`) so browsers without WebGPU still get the same 4x-8x VRAM savings and zero-decode uploads.
- **Upload counters**: Boot logs track compressed vs uncompressed texture uploads so regressions are immediately visible.

## Zero-waste draw pipeline, compact dynamic UBO, and post `bindGroup` cache (`deb8f28`)

DirectX 9 games issue hundreds of small stateful draw calls per frame (changing a single transform matrix, light constant, or texture stage). In WebGPU, naively allocating a fresh uniform buffer or `GPUBindGroup` per draw call creates severe JS garbage-collection pressure.

Commit `deb8f28` overhauled `host/d3d9.c`, `host/gpu.c`, `host/sm1.c`, and `web/gpu.js`:

- **Compact dynamic UBO layout**: Packed shader uniforms tightly so each draw call slices a single pre-allocated dynamic uniform buffer via `setBindGroup(..., [dynamicOffset])`.
- **Zero-waste draw state**: Avoided redundant state writes and shader-constant re-uploads when consecutive draws share transforms or materials.
- **Post-process `bindGroup` cache**: Cached post-processing bind groups (bloom, motion blur, tone pass) instead of rebuilding them every frame.
