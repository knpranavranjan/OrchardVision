"""Mirror the on-disk registry into the database so orchards can reference crops and versions."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.tables import Crop, ModelVersion
from app.registry.loader import ModelRegistry
from app.registry.schemas import ModelKind


def sync_registry(session: Session, registry: ModelRegistry) -> dict[str, int]:
    crops = 0
    versions = 0
    for cfg in registry.crops():
        crop = session.get(Crop, cfg.crop)
        if crop is None:
            crop = Crop(id=cfg.crop)
            session.add(crop)
        crop.name = cfg.name
        crop.plant_architecture = cfg.plant_architecture.value
        crop.profile = cfg.model_dump(mode="json")
        crops += 1

        for kind in ModelKind:
            for resolved in registry.versions(cfg.crop, kind):
                row = session.scalar(
                    select(ModelVersion).where(
                        ModelVersion.crop_id == cfg.crop,
                        ModelVersion.kind == kind.value,
                        ModelVersion.version == resolved.manifest.version,
                    )
                )
                if row is None:
                    row = ModelVersion(
                        crop_id=cfg.crop, kind=kind.value, version=resolved.manifest.version
                    )
                    session.add(row)
                row.framework = resolved.manifest.framework
                row.sha256 = resolved.manifest.sha256
                row.status = resolved.status
                row.manifest = resolved.manifest.model_dump(mode="json")
                versions += 1
    return {"crops": crops, "model_versions": versions}
