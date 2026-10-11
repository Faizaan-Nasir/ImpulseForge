import React from "react";
import { render, screen } from "@testing-library/react";
import { it, expect } from "vitest";
import FeasibilityWindows from "../src/components/FeasibilityWindows.jsx";
const windows = {
  fixed_charge_energy_infeasible: true,
  fixed_charge_energy_feasible_stage_counts: [],
  actual_stage_count: 9,
  current_stage_capacitance_upper_F: 0.134105e-6,
  current_stage_charge_upper_V: 40824.829,
  expected_efficiency_crest_upper_at_N_max_V: 449132.498,
  suggestions: [
    "Rating evidence is required; no numerical safe range is established.",
  ],
};
it("explains impossible stage-only repair and displays input windows in physical units", () => {
  render(<FeasibilityWindows windows={windows} />);
  expect(screen.getByText(/No stage count can satisfy/)).toBeInTheDocument();
  expect(screen.getByText("0.134105 µF")).toBeInTheDocument();
  expect(screen.getByText("40.824829 kV/stage")).toBeInTheDocument();
  expect(screen.getByText(/Charge and capacitance remain/)).toBeInTheDocument();
  expect(
    screen.getByText(/do not guarantee waveform timing/),
  ).toBeInTheDocument();
});
it("shows energy-compatible N without claiming waveform or hardware success", () => {
  render(
    <FeasibilityWindows
      windows={{
        ...windows,
        fixed_charge_energy_infeasible: false,
        fixed_charge_energy_feasible_stage_counts: [10, 11, 12],
      }}
    />,
  );
  expect(
    screen.getByText(/Energy-compatible stage counts.*10, 11, 12/),
  ).toBeInTheDocument();
});
