"""Glue between stored missions, the compiler, validation and the model registry."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.tables import Mission, Orchard
from app.mission.compiler import CompiledMission, compile_plan
from app.mission.schema import MissionPlan
from app.mission.validate import CropContext, Validation, validate_plan
from app.registry import ModelKind, ModelRegistry, RegistryError


def crop_context(registry: ModelRegistry, orchard: Orchard | None) -> CropContext | None:
    """What validation and pre-flight need to know about an orchard's crop and its models."""
    if orchard is None:
        return None
    try:
        cfg = registry.crop(orchard.crop_id)
    except RegistryError as e:
        return CropContext(crop=orchard.crop_id, models_ready=False, models_detail=str(e))
    problems = []
    names = []
    for kind, pinned in (
        (ModelKind.TREE, orchard.tree_model_version),
        (ModelKind.FRUIT, orchard.fruit_model_version),
    ):
        try:
            model = registry.resolve(cfg.crop, kind, pinned)
        except RegistryError as e:
            problems.append(str(e))
            continue
        names.append(f"{kind.value} {model.manifest.version}")
        if not model.usable:
            problems.append(f"{kind.value} model {model.manifest.version}: {model.status}")
    return CropContext(
        crop=cfg.name,
        min_gsd_cm=cfg.min_gsd_cm.get(ModelKind.TREE),
        models_ready=not problems,
        models_detail="; ".join(problems) if problems else f"{cfg.name}: " + ", ".join(names),
    )


@dataclass
class Evaluated:
    plan: MissionPlan
    compiled: CompiledMission
    validation: Validation
    crop: CropContext | None


def evaluate_plan(
    plan: MissionPlan, registry: ModelRegistry, orchard: Orchard | None, data_dir: Path
) -> Evaluated:
    compiled = compile_plan(plan)
    crop = crop_context(registry, orchard)
    return Evaluated(plan, compiled, validate_plan(plan, compiled, crop, data_dir), crop)


def evaluate_mission(
    session: Session, mission: Mission, registry: ModelRegistry, data_dir: Path
) -> Evaluated:
    orchard = session.get(Orchard, mission.orchard_id) if mission.orchard_id else None
    return evaluate_plan(MissionPlan.model_validate(mission.plan), registry, orchard, data_dir)
