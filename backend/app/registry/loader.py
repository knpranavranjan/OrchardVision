"""Model registry: orchard -> crop -> profile -> model versions.

Reads the models directory. Nothing in the application names a weights file
directly; it asks the registry for (crop, kind), optionally with a version an
orchard has pinned.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.registry.schemas import CropConfig, ModelKind, ModelManifest


class RegistryError(Exception):
    pass


@dataclass(frozen=True)
class ResolvedModel:
    crop: str
    kind: ModelKind
    manifest: ModelManifest
    weights_path: Path
    weights_present: bool
    checksum_ok: bool
    active: bool

    @property
    def usable(self) -> bool:
        return self.weights_present and self.checksum_ok

    @property
    def status(self) -> str:
        if not self.weights_present:
            return "missing"
        if not self.checksum_ok:
            return "checksum_mismatch"
        return "active" if self.active else "available"


class StubModel:
    """Stands in for a real model in tests and before weights exist. Detects nothing."""

    def __init__(self, resolved: ResolvedModel) -> None:
        self.resolved = resolved

    def predict(self, image: Any) -> list[dict]:
        return []


# framework name in the manifest -> loader. Real frameworks register here.
LOADERS: dict[str, Callable[[ResolvedModel], Any]] = {"stub": StubModel}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        raise RegistryError(f"cannot read {path}: {e}") from e


class ModelRegistry:
    def __init__(self, models_dir: Path) -> None:
        self.models_dir = Path(models_dir)

    def crops(self) -> list[CropConfig]:
        if not self.models_dir.is_dir():
            return []
        return [self._crop_from(c) for c in sorted(self.models_dir.glob("*/config.yaml"))]

    def crop(self, crop: str) -> CropConfig:
        config = self.models_dir / crop / "config.yaml"
        if not config.is_file():
            raise RegistryError(f"unknown crop '{crop}': {config} not found")
        return self._crop_from(config)

    def versions(self, crop: str, kind: ModelKind) -> list[ResolvedModel]:
        cfg = self.crop(crop)
        kind_dir = self.models_dir / crop / kind.value
        return [
            self._resolve_manifest(cfg, kind, m) for m in sorted(kind_dir.glob("*/manifest.yaml"))
        ]

    def all_versions(self) -> list[ResolvedModel]:
        return [
            m for cfg in self.crops() for kind in ModelKind for m in self.versions(cfg.crop, kind)
        ]

    def resolve(self, crop: str, kind: ModelKind, version: str | None = None) -> ResolvedModel:
        """The model for a crop and kind: a pinned version, or the crop's active one."""
        cfg = self.crop(crop)
        version = version or cfg.active.get(kind)
        if version is None:
            raise RegistryError(f"crop '{crop}' has no active {kind.value} model")
        manifest_path = self.models_dir / crop / kind.value / version / "manifest.yaml"
        if not manifest_path.is_file():
            raise RegistryError(f"{kind.value} model '{version}' of '{crop}' has no manifest")
        return self._resolve_manifest(cfg, kind, manifest_path)

    def load(self, crop: str, kind: ModelKind, version: str | None = None) -> Any:
        """Verify and load a model. Refuses weights that fail their checksum."""
        resolved = self.resolve(crop, kind, version)
        if not resolved.usable:
            name = f"{crop}/{kind.value}/{resolved.manifest.version}"
            raise RegistryError(f"{name} is not loadable: {resolved.status}")
        loader = LOADERS.get(resolved.manifest.framework)
        if loader is None:
            raise RegistryError(f"no loader for framework '{resolved.manifest.framework}'")
        return loader(resolved)

    def _crop_from(self, config: Path) -> CropConfig:
        try:
            cfg = CropConfig.model_validate(_read_yaml(config))
        except ValidationError as e:
            raise RegistryError(f"invalid crop profile {config}: {e}") from e
        if cfg.crop != config.parent.name:
            raise RegistryError(f"{config}: crop '{cfg.crop}' does not match its folder name")
        return cfg

    def _resolve_manifest(
        self, cfg: CropConfig, kind: ModelKind, manifest_path: Path
    ) -> ResolvedModel:
        try:
            manifest = ModelManifest.model_validate(_read_yaml(manifest_path))
        except ValidationError as e:
            raise RegistryError(f"invalid manifest {manifest_path}: {e}") from e
        weights = manifest_path.parent / manifest.weights
        present = weights.is_file()
        return ResolvedModel(
            crop=cfg.crop,
            kind=kind,
            manifest=manifest,
            weights_path=weights,
            weights_present=present,
            checksum_ok=present and sha256_of(weights) == manifest.sha256,
            active=cfg.active.get(kind) == manifest.version,
        )
