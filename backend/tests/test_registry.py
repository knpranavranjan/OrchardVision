from pathlib import Path

import pytest

from app.registry import ModelKind, ModelRegistry, RegistryError
from app.registry.loader import StubModel


def test_papaya_profile_loads(models_dir: Path):
    registry = ModelRegistry(models_dir)
    crops = registry.crops()
    assert [c.crop for c in crops] == ["papaya"]
    papaya = crops[0]
    assert papaya.plant_architecture == "trunk_column"
    assert papaya.viewpoint_template.provisional is True


@pytest.mark.parametrize("kind", list(ModelKind))
def test_resolves_and_loads_the_active_stub(models_dir: Path, kind: ModelKind):
    registry = ModelRegistry(models_dir)
    resolved = registry.resolve("papaya", kind)
    assert resolved.manifest.version == "stub-0"
    assert resolved.status == "active" and resolved.usable
    assert registry.resolve("papaya", kind, "stub-0") == resolved  # a pinned version
    model = registry.load("papaya", kind)
    assert isinstance(model, StubModel)
    assert model.predict(object()) == []


def test_tampered_weights_are_refused(models_dir: Path):
    weights = models_dir / "papaya" / "tree" / "stub-0" / "weights.bin"
    weights.write_bytes(b"not the registered weights")
    registry = ModelRegistry(models_dir)
    assert registry.resolve("papaya", ModelKind.TREE).status == "checksum_mismatch"
    with pytest.raises(RegistryError, match="checksum_mismatch"):
        registry.load("papaya", ModelKind.TREE)


def test_missing_weights_are_reported(models_dir: Path):
    (models_dir / "papaya" / "fruit" / "stub-0" / "weights.bin").unlink()
    registry = ModelRegistry(models_dir)
    assert registry.resolve("papaya", ModelKind.FRUIT).status == "missing"


def test_unknown_crop_and_version(models_dir: Path):
    registry = ModelRegistry(models_dir)
    with pytest.raises(RegistryError, match="unknown crop"):
        registry.crop("durian")
    with pytest.raises(RegistryError, match="has no manifest"):
        registry.resolve("papaya", ModelKind.TREE, "v99")


def test_profile_must_match_its_folder(models_dir: Path):
    (models_dir / "papaya").rename(models_dir / "mango")
    with pytest.raises(RegistryError, match="does not match its folder"):
        ModelRegistry(models_dir).crops()
