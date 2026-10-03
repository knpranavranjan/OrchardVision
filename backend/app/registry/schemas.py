"""Crop profile and model manifest file formats (docs/PLAN.md section 5.6)."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ModelKind(StrEnum):
    TREE = "tree"
    FRUIT = "fruit"


class PlantArchitecture(StrEnum):
    TRUNK_COLUMN = "trunk_column"
    ROUND_CANOPY = "round_canopy"
    WALL = "wall"


class ViewpointTemplate(BaseModel):
    """Where the camera must be to see fruit. Provisional until the field study measures it."""

    pass_type: str = "row_side_pass"
    heights_m: list[float] = Field(default_factory=list)
    standoff_m: float | None = None
    tilt_deg: float = 0.0
    sides: int = 2
    speed_mps: float | None = None
    provisional: bool = True


class CalibrationProtocol(BaseModel):
    trees: int = 18
    stratify_by: str = "crown_size"


class CropConfig(BaseModel):
    """models/<crop>/config.yaml"""

    crop: str
    name: str
    plant_architecture: PlantArchitecture
    classes: dict[ModelKind, list[str]]
    tree_spacing_m: float
    crown_diameter_m: float
    min_gsd_cm: dict[ModelKind, float]
    active: dict[ModelKind, str] = Field(description="Active model version per kind")
    viewpoint_template: ViewpointTemplate = Field(default_factory=ViewpointTemplate)
    assignment_rule: str = "nearest_trunk"
    estimator: dict = Field(default_factory=dict)
    calibration: CalibrationProtocol = Field(default_factory=CalibrationProtocol)


class ModelManifest(BaseModel):
    """models/<crop>/<kind>/<version>/manifest.yaml"""

    version: str
    framework: str = Field(description="Selects the loader, for example 'stub'")
    weights: str = Field(description="Weights file name, next to the manifest")
    sha256: str
    input_size: list[int] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    notes: str = ""
