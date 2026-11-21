"""x86-32 ISA Backend registration."""
from __future__ import annotations

from typing import Any

from recomp_kit.arch import ArchBackend, register_arch
from recomp_kit.arch.x86_32.frontend import discover_pe32
from recomp_kit.arch.x86_32.lifter import Lifter
from recomp_kit.arch.x86_32.oracle import run_difftest
from recomp_kit.config import ProjectConfig
from recomp_kit.patcher import PatchSet


@register_arch
class X86_32Backend(ArchBackend):
    name = "x86_32"

    def discover(
        self,
        cfg: ProjectConfig,
        on_progress: Any | None = None,
        cancel_event: Any | None = None,
    ) -> dict[str, Any]:
        return discover_pe32(cfg, on_progress=on_progress, cancel_event=cancel_event)

    def make_lifter(self, cfg: ProjectConfig, funcs: dict[int, str], patch_set: PatchSet) -> Lifter:
        return Lifter(
            str(cfg.resolve_binary()),
            funcs=funcs,
            patch_set=patch_set,
            native_overrides=cfg.native_overrides,
            code_sections=cfg.code_sections,
        )

    def verify(
        self,
        cfg: ProjectConfig,
        cases: int = 4,
        only: int | None = None,
        limit: int | None = None,
        jobs: int | None = None,
    ) -> dict[str, Any]:
        return run_difftest(cfg, cases=cases, only=only, limit=limit, jobs=jobs)
