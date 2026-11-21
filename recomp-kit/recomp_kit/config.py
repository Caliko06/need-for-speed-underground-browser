"""Declarative project.toml schema and loader (Principle 3: Engine vs. Target separation)."""
from __future__ import annotations

import hashlib
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectConfig:
    root: Path
    name: str
    binary: Path
    arch: str = "x86_32"
    fmt: str = "pe32"
    sha256: str = ""
    code_sections: list[str] = field(default_factory=lambda: [".text"])
    chunks: int = 160
    guest_mb: int = 384
    wasm_mb: int = 1024
    stack_mb: int = 4
    code_area: tuple[int, int] = (0, 0)
    native_overrides: set[int] = field(default_factory=set)
    patches_file: Path | None = None
    runtime_os: str = "win32"
    runtime_modules: list[str] = field(default_factory=lambda: ["kernel32", "user32", "files_vfs"])
    subsystems: list[str] = field(default_factory=lambda: ["core", "render", "audio", "input", "assets", "runtime"])

    @property
    def census_dir(self) -> Path:
        return self.root / "census"

    @property
    def build_dir(self) -> Path:
        return self.root / "build"

    @property
    def gen_dir(self) -> Path:
        return self.build_dir / "gen"

    @property
    def functions_tsv(self) -> Path:
        return self.census_dir / "functions.tsv"

    @property
    def discovery_json(self) -> Path:
        return self.census_dir / "discovery.json"

    @property
    def lift_report_json(self) -> Path:
        return self.census_dir / "lift_report.json"

    def resolve_binary(self) -> Path:
        if self.binary.is_absolute():
            return self.binary
        return (self.root / self.binary).resolve()


def load_project(project_dir: str | Path) -> ProjectConfig:
    root = Path(project_dir).resolve()
    toml_path = root / "project.toml"
    if not toml_path.exists():
        raise FileNotFoundError(f"Missing project.toml in {root}")
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    t = data.get("target", {})
    m = data.get("memory", {})
    b = data.get("build", {})
    r = data.get("runtime", {})
    re_cfg = data.get("re", {})

    ca = m.get("code_area", [0, 0])
    code_area = (int(ca[0]), int(ca[1])) if len(ca) == 2 else (0, 0)
    natives = {int(x, 0) if isinstance(x, str) else int(x) for x in b.get("native_overrides", [])}
    pf = b.get("patches_file")
    patches_file = (root / pf).resolve() if pf else None

    return ProjectConfig(
        root=root,
        name=t.get("name", root.name),
        binary=Path(t["binary"]),
        arch=t.get("arch", "x86_32"),
        fmt=t.get("format", "pe32"),
        sha256=t.get("sha256", ""),
        code_sections=list(m.get("code_sections", [".text"])),
        chunks=int(b.get("chunks", 160)),
        guest_mb=int(m.get("guest_mb", 384)),
        wasm_mb=int(m.get("wasm_mb", 1024)),
        stack_mb=int(m.get("stack_mb", 4)),
        code_area=code_area,
        native_overrides=natives,
        patches_file=patches_file,
        runtime_os=r.get("os", "win32"),
        runtime_modules=list(r.get("modules", ["kernel32", "user32", "files_vfs"])),
        subsystems=list(re_cfg.get("subsystems", ["core", "render", "audio", "input", "assets", "runtime"])),
    )


def write_project_toml(
    out_dir: Path,
    name: str,
    binary_path: Path,
    arch: str = "x86_32",
    fmt: str = "pe32",
    code_sections: list[str] | None = None,
    runtime_modules: list[str] | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "census").mkdir(exist_ok=True)
    (out_dir / "patches").mkdir(exist_ok=True)
    sha = hashlib.sha256(binary_path.read_bytes()).hexdigest()
    try:
        rel_bin = os.path.relpath(binary_path.resolve(), out_dir.resolve())
    except ValueError:
        rel_bin = str(binary_path.resolve())
    secs = code_sections or [".text"]
    mods = runtime_modules or ["kernel32", "user32", "files_vfs"]
    text = f'''[target]
name = "{name}"
binary = "{rel_bin}"
sha256 = "{sha}"
arch = "{arch}"
format = "{fmt}"

[memory]
guest_mb = 384
wasm_mb = 1024
stack_mb = 4
code_sections = [{", ".join(f'"{s}"' for s in secs)}]
code_area = [0, 0]

[build]
chunks = 160
native_overrides = []
# patches_file = "patches/patches.toml"

[runtime]
os = "win32"
modules = [{", ".join(f'"{m}"' for m in mods)}]

[re]
subsystems = ["core", "render", "audio", "input", "assets", "runtime"]
'''
    toml_path = out_dir / "project.toml"
    toml_path.write_text(text, encoding="utf-8")
    return toml_path
