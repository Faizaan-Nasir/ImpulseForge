from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[float, Field(gt=0)]
Nonnegative = Annotated[float, Field(ge=0)]
MODEL_VERSION = "residual-tabpfn-v2-standardised-v1"


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)


class Ratings(Record):
    pulse_voltage_limit_V: Positive | None = None
    pulse_current_limit_A: Positive | None = None
    pulse_energy_limit_J: Positive | None = None
    average_power_limit_W: Positive | None = None
    temperature_limit_K: Positive | None = None
    R_theta_K_per_W: Positive | None = None
    C_theta_J_per_K: Positive | None = None
    evidence_id: str | None = None


class ResistorType(Record):
    type_id: str = Field(min_length=1)
    nominal_ohm: Positive
    available_quantity: int = Field(ge=0, strict=True)
    quantity_scope: Literal["per_stage", "global"] = "per_stage"
    tolerance_fraction: float = Field(default=0, ge=0, lt=1)
    approved: bool = False
    ratings: Ratings = Field(default_factory=Ratings)

    def capacity(self, N: int) -> int:
        return min(
            4,
            self.available_quantity
            if self.quantity_scope == "per_stage"
            else self.available_quantity // N,
        )


class InlineInventory(Record):
    source: Literal["inline"] = "inline"
    front: tuple[ResistorType, ...]
    tail: tuple[ResistorType, ...]

    @model_validator(mode="after")
    def unique_types(self):
        for role in (self.front, self.tail):
            names = [r.type_id for r in role]
            if len(names) != len(set(names)):
                raise ValueError("Duplicate role-specific inventory type IDs")
        return self


class InventoryReference(Record):
    source: Literal["registered"]
    profile_id: str
    version: str = "1"


InventoryInput = Annotated[InlineInventory | InventoryReference, Field(discriminator="source")]


class WaveformTolerances(Record):
    front: float = Field(gt=0, le=1)
    tail: float = Field(gt=0, le=1)
    crest: float = Field(gt=0, le=1)


class Target(Record):
    crest_V: Positive
    front_s: Positive | None = None
    tail_s: Positive | None = None
    tolerances: WaveformTolerances | None = None


class Load(Record):
    model_id: Literal["capacitive_v1", "parallel_rc_v1", "parallel_rlc_v1"] = "capacitive_v1"
    C_F: Positive
    R_ohm: Positive | None = None
    L_H: Positive | None = None
    topology: str = "shunt_at_test_terminals"
    terminal_connections: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def required_parameters(self):
        if self.model_id != "capacitive_v1" and self.R_ohm is None:
            raise ValueError("Parallel RC/RLC requires R_ohm")
        if self.model_id == "parallel_rlc_v1" and self.L_H is None:
            raise ValueError("Parallel RLC requires L_H")
        if self.model_id == "capacitive_v1" and (self.R_ohm is not None or self.L_H is not None):
            raise ValueError("Select the appropriate load model when supplying R/L")
        if self.topology != "shunt_at_test_terminals":
            raise ValueError("Unsupported load topology; register a solver first")
        return self


class Setup(Record):
    basic_C_F: Nonnegative = 0
    shot_rate_per_minute: Positive | None = None
    divider_C_F: Nonnegative = 0
    stray_C_F: Nonnegative = 0
    stray_L_H: Nonnegative = 0
    basic_capacitance_inclusion: Literal[
        "add_separately", "already_included", "benchmark_omitted"
    ] = "add_separately"
    external_front_series_ohm: Nonnegative | None = None
    auxiliary_states: dict[str, Literal["inactive", "unknown"]] = Field(default_factory=dict)
    circuit_evidence_id: str | None = None
    leads: dict[str, Any] = Field(default_factory=dict)
    return_path: dict[str, Any] = Field(default_factory=dict)
    geometry: dict[str, Any] = Field(default_factory=dict)


class Environment(Record):
    availability: Literal["not_recorded", "recorded"] = "not_recorded"
    values: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def availability_consistent(self):
        if self.availability == "not_recorded" and self.values:
            raise ValueError("Environment values require recorded availability")
        if self.values.get("ambient_temperature_K", 300) <= 0:
            raise ValueError("Ambient temperature in kelvin must be positive")
        return self


class ChargingPolicy(Record):
    kind: Literal["fixed", "seed_then_fixed"] = "fixed"
    U_charge_V: Positive | None = None

    @model_validator(mode="after")
    def fixed_value(self):
        if self.kind == "fixed" and self.U_charge_V is None:
            raise ValueError("Fixed charge requires U_charge_V")
        if self.kind == "seed_then_fixed" and self.U_charge_V is not None:
            raise ValueError(
                "Seed-derived charging policy must not supply a competing fixed charge"
            )
        return self


class DPTolerances(Record):
    front_relative: Nonnegative = 0.005
    tail_relative: Nonnegative = 0.005


class Search(Record):
    max_proposals: int = Field(
        default=24,
        ge=1,
        le=10000,
        description="Omitted API field uses POWERNEXT_CALIBRATION_MAX_ATTEMPTS; 24 is the fallback.",
    )
    max_forward_evaluations: int = Field(
        default=24,
        ge=1,
        le=10000,
        description="Omitted API field uses POWERNEXT_CALIBRATION_MAX_ATTEMPTS; 24 is the fallback.",
    )
    max_ml_evaluations: int = Field(
        default=24,
        ge=1,
        le=10000,
        description="Omitted API field uses POWERNEXT_CALIBRATION_MAX_ATTEMPTS; 24 is the fallback.",
    )
    dp_max_parts: int = Field(default=4, ge=1, le=12)
    dp_max_states: int = Field(default=100000, ge=1, le=1000000)
    dp_seconds: Positive = 10
    cp_sat_seconds: Positive = 2
    cp_pair_retries: int = Field(default=5, ge=1, le=100)
    repeat_window: int = Field(default=10, ge=1)
    archive_stagnation_window: int = Field(default=20, ge=1)
    wall_time_seconds: Positive = Field(
        default=600,
        description="Omitted API field uses POWERNEXT_CALIBRATION_WALL_TIME_SECONDS; 600 is the fallback.",
    )


class ObjectiveConfig(Record):
    policy: Literal["worst_normalised_then_weighted"] = "worst_normalised_then_weighted"
    weights: dict[str, float] = Field(default_factory=lambda: {"front": 1, "tail": 1, "crest": 1})
    secondary_preference: Literal["balanced", "accuracy", "resistors", "stages", "voltage"] = (
        "balanced"
    )

    @model_validator(mode="after")
    def weights_valid(self):
        if set(self.weights) != {"front", "tail", "crest"} or any(
            v <= 0 for v in self.weights.values()
        ):
            raise ValueError("Positive front/tail/crest weights required")
        return self


class EquipmentInputs(Record):
    """Editable workbook fields; omitted/null values request the profile fallback."""

    N_max: int | None = Field(
        default=None,
        ge=1,
        strict=True,
        description="Frontend maximum stages (Hybrid Calculator B13); example 15.",
    )
    U_stage_max_V: Positive | None = Field(
        default=None,
        description="Frontend maximum charging voltage per stage in V (B14); example 200000.",
    )
    C_stage_F: Positive | None = Field(
        default=None,
        description="Frontend stage capacitance in F (B15); example 3e-6.",
    )


class RunRequest(Record):
    schema_version: Literal["1.0"] = "1.0"
    purpose: Literal["diagnostic", "recommendation"] = "diagnostic"
    equipment_profile_id: str = "haefely_pdf_v1"
    equipment_inputs: EquipmentInputs = Field(default_factory=EquipmentInputs)
    inventory: InventoryInput
    impulse_type: Literal["Lightning", "Switching"] | None = None
    impulse_profile_id: str = "lightning_project_v1"
    system_max_voltage_V: Positive = 400000
    target: Target
    load: Load
    setup: Setup = Field(default_factory=Setup)
    environment: Environment = Field(default_factory=Environment)
    expected_voltage_efficiency: float = Field(default=0.82, gt=0, le=1)
    minimum_voltage_efficiency: float | None = Field(default=None, gt=0, le=1)
    charging_policy: ChargingPolicy
    dp_tolerances: DPTolerances = Field(default_factory=DPTolerances)
    search: Search = Field(default_factory=Search)
    objective: ObjectiveConfig = Field(default_factory=ObjectiveConfig)
    physics_mode: Literal["calculator", "exact"] = "exact"
    model_version: str = MODEL_VERSION
    ml_domain_policy: Literal["strict", "diagnostic_extrapolation"] = "strict"
    seed: int = Field(default=42, ge=0, le=2147483647)


class Proposal(Record):
    N: int = Field(ge=1, strict=True)
    Rf_required_ohm: Positive
    Rt_required_ohm: Positive
    proposal_index: int = Field(default=0, ge=0)
    source: str = "manual"


class Recipe(Record):
    op: Literal["resistor", "series", "parallel"]
    type_id: str | None = None
    ohm: Positive | None = None
    children: tuple[Recipe, ...] = ()

    @model_validator(mode="after")
    def valid_node(self):
        if self.op == "resistor":
            if not self.type_id or self.ohm is None or self.children:
                raise ValueError("Leaf requires type_id/ohm and no children")
        elif len(self.children) < 2 or self.type_id is not None or self.ohm is not None:
            raise ValueError("Network requires >=2 children and no leaf attributes")
        return self


class Assembly(Record):
    assembly_id: str
    role: Literal["front", "tail"]
    equivalent_ohm: Positive
    nominal_fraction: dict[str, int]
    recipe: Recipe
    netlist: tuple[dict[str, Any], ...]
    type_counts: dict[str, int]
    total_resistors: int
    ratings_status: str = "unknown"
    search_guarantee: str = "bounded"


class Candidate(Record):
    candidate_id: str
    context_hash: str
    proposal: Proposal
    N: int = Field(ge=1, strict=True)
    U_charge_V: Positive
    front: Assembly
    tail: Assembly


class Metrics(Record):
    front_s: Positive
    tail_s: Positive
    crest_V: Positive


class Constraint(Record):
    constraint_id: str
    origin: str
    kind: Literal["hard", "metadata", "waveform", "support"] = "hard"
    enforced_by: tuple[str, ...]
    rule: str
    observed_value: Any = None
    limit_value: Any = None
    unit: str | None = None
    margin: float | None = None
    status: Literal["pass", "fail", "unknown", "not_applicable"]
    reason_code: str | None = None


class DomainError(ValueError):
    def __init__(self, code: str, message: str, stage: str = "validation"):
        super().__init__(message)
        self.code, self.stage = code, stage


class PhysicsTrace(Record):
    time_s: list[Nonnegative]
    voltage_V: list[float]
    origin: Literal["physics"]


class RuntimePerformance(Record):
    clock: Literal["monotonic_wall_clock"] = "monotonic_wall_clock"
    scope: str
    stage_seconds: dict[str, Nonnegative]
    total_seconds: Nonnegative
    cache_hit: bool = False
    transport_time_included: bool = False


class PerformanceReport(Record):
    schema_version: Literal["1.0"] = "1.0"
    candidate_id: str
    context_hash: str
    target: Metrics
    physics: dict[str, Any]
    corrected: dict[str, Any] | None
    correction_status: str
    efficiency: dict[str, Any]
    stored_energy: dict[str, Any]
    hardware: dict[str, Any]
    model_quality: dict[str, Any]
    observed_accuracy: dict[str, Any]
    runtime: RuntimePerformance
    interpretation: str


class PhysicsEvaluation(Record):
    candidate_id: str
    context_hash: str
    physics_version: str
    baseline_mode: Literal["calculator", "exact"]
    derived: dict[str, Any]
    metrics: Metrics
    voltage_efficiency: Positive
    voltage_utilisation: Positive
    stage_energy_J: Positive
    total_energy_J: Positive
    landmarks: dict[str, float]
    rates: dict[str, float]
    trace: PhysicsTrace | None
    component_stresses: list[dict[str, Any]]
    constraints: list[Constraint]
    constraint_owner: str = "calibration_pending"
    feasibility_windows: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any]
    hardware_feasible: bool | None
    performance: PerformanceReport | None = None


class CorrectionPrediction(Record):
    model_version: str
    support: dict[str, Any]
    features: dict[str, float]
    input_effects_not_modelled: list[str]
    hardware_feasible: bool | None
    physics_constraints: list[Constraint]
    corrected_constraint_checks: list[Constraint] = Field(default_factory=list)
    residuals: dict[str, float] | None
    corrected_metrics: Metrics | None
    status: str
    lab_validated: bool
    explanation_status: str | None = None
    environment_effects: dict[str, Any] = Field(default_factory=dict)
    normalisation: dict[str, Any] = Field(default_factory=dict)
    performance: PerformanceReport | None = None


class CandidateEvaluation(Record):
    candidate_id: str
    candidate: Candidate
    physics: PhysicsEvaluation
    calibration: dict[str, Any] = Field(default_factory=dict)
    correction: dict[str, Any]
    objective: dict[str, Any] | None
    eligible: bool
    cost: Nonnegative
    objective_origin: Literal["residual_corrected", "physics_baseline"] | None = None
    cost_basis: (
        Literal[
            "calibration_constraints_then_ml_waveform",
            "eligible_waveform",
            "diagnostic_waveform_with_ineligibility_penalty",
            "hard_rejection",
            "ml_prediction_unavailable",
        ]
        | None
    ) = None
    performance: PerformanceReport | None = None


class WorkbookReferenceSettings(Record):
    N: int = Field(ge=1)
    U_charge_V: Positive
    Rf_actual_ohm: Positive
    Rt_actual_ohm: Positive


class WorkbookBaseline(Record):
    status: Literal["evaluated", "reference_only"]
    feasibility_windows: dict[str, Any] = Field(default_factory=dict)
    settings: WorkbookReferenceSettings
    ideal: dict[str, Any]
    record: dict[str, Any]
    context: dict[str, Any]
    inventory_check: dict[str, Any]
    policy: str
