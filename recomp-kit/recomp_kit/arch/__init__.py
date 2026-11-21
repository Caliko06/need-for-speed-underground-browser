"""Pluggable ISA backend interface (Principle 6: Pluggable Boundaries)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from recomp_kit.config import ProjectConfig
from recomp_kit.patcher import PatchSet


class UnsupportedInstruction(Exception):
    """Raised when a function cannot be lifted at all (fatal decode/structure error)."""


class ArchBackend(ABC):
    name: str

    @abstractmethod
    def discover(self, cfg: ProjectConfig) -> dict[str, Any]:
        """Discover functions, basic blocks, jump tables, and imports. Writes discovery.json & functions.tsv."""

    @abstractmethod
    def make_lifter(self, cfg: ProjectConfig, funcs: dict[int, str], patch_set: PatchSet) -> Any:
        """Return a stateful lifter instance exposing .lift(entry, all_entries) and .body(entry)."""

    @abstractmethod
    def verify(
        self,
        cfg: ProjectConfig,
        cases: int = 4,
        only: int | None = None,
        limit: int | None = None,
        jobs: int | None = None,
    ) -> dict[str, Any]:
        """Run bit-exact differential testing against the ISA reference oracle (Unicorn)."""


_REGISTRY: dict[str, type[ArchBackend]] = {}


def register_arch(cls: type[ArchBackend]) -> type[ArchBackend]:
    _REGISTRY[cls.name] = cls
    return cls


def get_arch(name: str) -> ArchBackend:
    if name not in _REGISTRY:
        # Lazy-load built-in backends
        if name == "x86_32":
            from recomp_kit.arch.x86_32 import X86_32Backend  # noqa: F401
        if name not in _REGISTRY:
            raise KeyError(f"Unknown arch backend '{name}'. Available: {sorted(_REGISTRY)}")
    return _REGISTRY[name]()
