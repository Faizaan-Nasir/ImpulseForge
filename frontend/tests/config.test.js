import { describe, it, expect } from "vitest";
import {
  initialForm,
  toRequest,
  withSearchDefaults,
} from "../src/lib/config.js";
const form = withSearchDefaults(initialForm, {
  max_proposals: 24,
  wall_time_seconds: 600,
});
const inventory = {
  front: [{ type_id: "f", nominal_ohm: 50, available_quantity: 4 }],
  tail: [{ type_id: "t", nominal_ohm: 25, available_quantity: 4 }],
};
describe("frontend request contract", () => {
  it("converts editable values to SI and preserves independent inventories", () => {
    const r = toRequest(form, inventory);
    expect(r.physics_mode).toBe("calculator");
    expect(r.ml_domain_policy).toBe("diagnostic_extrapolation");
    expect(r.equipment_inputs.N_max).toBe(15);
    expect(r.equipment_inputs.C_stage_F).toBe(3e-6);
    expect(r.target.front_s).toBeCloseTo(1.2e-6, 12);
    expect(r.target.tolerances.front).toBe(0.3);
    expect(r.load.C_F).toBeCloseTo(850e-12, 15);
    expect(r.system_max_voltage_V).toBe(400000);
    expect(r.inventory.front[0].available_quantity).toBe(4);
    expect(r.inventory.tail[0].available_quantity).toBe(4);
    expect(
      toRequest({ ...form, extrapolate: false }, inventory).ml_domain_policy,
    ).toBe("strict");
    expect(r.equipment_inputs).not.toHaveProperty("stage_energy_max_J");
  });
  it("sends switching and RLC inputs without hardcoding insulator-only loads", () => {
    const r = toRequest(
      {
        ...form,
        impulse: "Switching",
        loadModel: "parallel_rlc_v1",
        loadR: 1e6,
        loadL: 1,
        tFront: 250,
        tTail: 2500,
        cBo: 100,
        includeCbo: true,
      },
      inventory,
    );
    expect(r.load.R_ohm).toBe(1e6);
    expect(r.load.L_H).toBe(1);
    expect(r.setup.basic_C_F).toBeCloseTo(100e-12, 15);
    expect(r.setup.basic_capacitance_inclusion).toBe("add_separately");
    expect(r.impulse_type).toBe("Switching");
  });
  it("distinguishes single-resistor policy and quantity caps", () => {
    const r = toRequest(
      { ...form, selection: "single", maxUnits: 8 },
      inventory,
    );
    expect(r.search.dp_max_parts).toBe(1);
    expect(r.inventory.front[0].available_quantity).toBe(4);
  });
  it("rejects invalid numeric input before starting a job", () => {
    expect(() => toRequest({ ...form, vTest: "" }, inventory)).toThrow();
    expect(() => toRequest({ ...form, nMax: 1.5 }, inventory)).toThrow();
  });
  it("loads runtime environment defaults and preserves later explicit budget edits", () => {
    expect(initialForm.maxProposals).toBe("");
    expect(initialForm.wallSeconds).toBe("");
    const configured = withSearchDefaults(initialForm, {
      max_proposals: 41,
      wall_time_seconds: 900,
    });
    const r = toRequest(configured, inventory);
    expect(r.search.max_proposals).toBe(41);
    expect(r.search.max_forward_evaluations).toBe(41);
    expect(r.search.max_ml_evaluations).toBe(41);
    expect(r.search.wall_time_seconds).toBe(900);
    expect(
      toRequest(
        { ...configured, wallSeconds: 800, maxProposals: 12 },
        inventory,
      ).search,
    ).toMatchObject({ max_proposals: 12, wall_time_seconds: 800 });
  });
});
