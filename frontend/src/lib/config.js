export const initialForm = {
  impulse: "Lightning",
  vTest: 1425,
  systemMax: 400,
  cLoad: 850,
  cDiv: 500,
  cStray: 150,
  lStray: 18.5,
  eta: 0.82,
  nMax: 15,
  uMax: 200,
  cStage: 3,
  wStage: 2.5,
  wTotal: 30,
  cBo: 0,
  includeCbo: false,
  profile: "workbook",
  mode: "calculator",
  extrapolate: true,
  tFront: 1.2,
  tTail: 50,
  tolProfile: "project",
  tolCrest: 3,
  tolFront: 30,
  tolTail: 20,
  selection: "combo",
  maxUnits: 4,
  ranking: "balanced",
  loadModel: "capacitive_v1",
  loadR: 1000000,
  loadL: 1,
  maxProposals: "",
  wallSeconds: "",
};
export function withSearchDefaults(form, search) {
  return {
    ...form,
    maxProposals: search.max_proposals,
    wallSeconds: search.wall_time_seconds,
  };
}
export function toRequest(form, inventory) {
  const n = (key) => Number(form[key]);
  for (const key of [
    "vTest",
    "systemMax",
    "cLoad",
    "eta",
    "nMax",
    "uMax",
    "cStage",
    "wStage",
    "wTotal",
    "tFront",
    "tTail",
    "tolCrest",
    "tolFront",
    "tolTail",
    "maxUnits",
    "maxProposals",
    "wallSeconds",
  ]) {
    if (!Number.isFinite(n(key)) || n(key) <= 0)
      throw new Error(`${key} must be a positive number`);
  }
  if (
    !Number.isInteger(n("nMax")) ||
    !Number.isInteger(n("maxUnits")) ||
    !Number.isInteger(n("maxProposals"))
  )
    throw new Error(
      "Stage, resistor and iteration counts must be whole numbers",
    );
  const load = { model_id: form.loadModel, C_F: n("cLoad") * 1e-12 };
  if (form.loadModel !== "capacitive_v1") load.R_ohm = n("loadR");
  if (form.loadModel === "parallel_rlc_v1") load.L_H = n("loadL");
  return {
    purpose: "diagnostic",
    impulse_type: form.impulse,
    equipment_profile_id:
      form.profile === "haefely" ? "haefely_pdf_v1" : "workbook_benchmark_v1",
    equipment_inputs: {
      N_max: n("nMax"),
      U_stage_max_V: n("uMax") * 1000,
      C_stage_F: n("cStage") * 1e-6,
      stage_energy_max_J: n("wStage") * 1000,
      total_energy_max_J: n("wTotal") * 1000,
    },
    system_max_voltage_V: n("systemMax") * 1000,
    target: {
      crest_V: n("vTest") * 1000,
      front_s: n("tFront") * 1e-6,
      tail_s: n("tTail") * 1e-6,
      tolerances: {
        front: n("tolFront") / 100,
        tail: n("tolTail") / 100,
        crest: n("tolCrest") / 100,
      },
    },
    load,
    setup: {
      divider_C_F: n("cDiv") * 1e-12,
      stray_C_F: n("cStray") * 1e-12,
      stray_L_H: n("lStray") * 1e-6,
      basic_C_F: n("cBo") * 1e-12,
      basic_capacitance_inclusion: form.includeCbo
        ? "add_separately"
        : "already_included",
    },
    expected_voltage_efficiency: n("eta"),
    charging_policy: { kind: "seed_then_fixed" },
    inventory: {
      source: "inline",
      front: inventory.front.map((r) => ({ ...r })),
      tail: inventory.tail.map((r) => ({ ...r })),
    },
    physics_mode: form.mode,
    ml_domain_policy: form.extrapolate ? "diagnostic_extrapolation" : "strict",
    objective: { secondary_preference: form.ranking },
    dp_tolerances: { front_relative: 0.02, tail_relative: 0.05 },
    search: {
      max_proposals: n("maxProposals"),
      max_forward_evaluations: n("maxProposals"),
      max_ml_evaluations: n("maxProposals"),
      dp_max_parts: form.selection === "single" ? 1 : n("maxUnits"),
      dp_seconds: 8,
      cp_pair_retries: 1,
      archive_stagnation_window: n("maxProposals"),
      repeat_window: 10,
      wall_time_seconds: n("wallSeconds"),
    },
  };
}
export function shownMetrics(record) {
  return record?.correction?.corrected_metrics || record?.physics?.metrics;
}
export function shownObjective(record) {
  return (
    record?.performance?.corrected ||
    record?.performance?.physics ||
    record?.objective
  );
}
export const number = (value, digits = 3) =>
  typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("en-US", {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
      })
    : "—";
export const percentage = (value) =>
  typeof value === "number"
    ? `${value > 0 ? "+" : ""}${number(value, 2)} %`
    : "—";
