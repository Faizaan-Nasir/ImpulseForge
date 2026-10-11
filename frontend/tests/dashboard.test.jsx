import React from "react";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { it, expect, vi } from "vitest";
import Configuration from "../src/components/Configuration.jsx";
import {
  SettingsPanel,
  DecisionSummary,
  PhysicsBaseline,
  PerformanceMetrics,
} from "../src/components/Results.jsx";
import {
  initialForm as emptyForm,
  withSearchDefaults,
} from "../src/lib/config.js";
import { Schematic } from "../src/components/Networks.jsx";
const initialForm = withSearchDefaults(emptyForm, {
  max_proposals: 24,
  wall_time_seconds: 600,
});
const inventory = {
  front: [{ type_id: "f50", nominal_ohm: 50, available_quantity: 4 }],
  tail: [{ type_id: "t25", nominal_ohm: 25, available_quantity: 4 }],
};
it("shows an ML crest shortfall as requiring calibration with no negative allowance", () => {
  render(
    <PerformanceMetrics
      record={{
        correction: {
          corrected_metrics: {
            front_s: 1.2e-6,
            tail_s: 50e-6,
            crest_V: 1422000,
          },
        },
        objective: {
          waveform_within_tolerance: false,
          errors: {
            crest: {
              target: 1425000,
              allowed_delta: 42750,
              percentage_delta: -0.21,
              within_tolerance: false,
              reason_code: "crest_below_required",
            },
          },
        },
      }}
    />,
  );
  expect(screen.getByText("Calibrate")).toBeInTheDocument();
  expect(screen.getByText(/allowed 0 to \+3.0 %/)).toBeInTheDocument();
  expect(
    screen.getByText(/Below required voltage; calibration required/),
  ).toBeInTheDocument();
});
it("edits arbitrary inventory and sends calculation through the supplied handler", () => {
  const calculate = vi.fn(),
    change = vi.fn(),
    setInventory = vi.fn();
  render(
    <Configuration
      form={initialForm}
      change={change}
      inventory={inventory}
      setInventory={setInventory}
      busy={false}
      onCalculate={calculate}
      bootstrap={{}}
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Calculate recommendations" }),
  );
  expect(calculate).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Add resistor" }));
  expect(setInventory.mock.calls[0][0].front).toHaveLength(2);
  expect(screen.getByLabelText("Energy limit per stage")).toBeEnabled();
  fireEvent.change(screen.getByLabelText("Energy limit per stage"), {
    target: { value: "60" },
  });
  expect(change).toHaveBeenCalledWith("wStage", "60");
});
it("renders exact arbitrary nested networks from backend recipes", () => {
  const leaf = (ohm) => ({ op: "resistor", ohm, type_id: `r${ohm}` });
  render(
    <Schematic
      role="front"
      assembly={{
        recipe: {
          op: "series",
          children: [
            leaf(10),
            { op: "parallel", children: [leaf(30), leaf(75)] },
          ],
        },
      }}
    />,
  );
  expect(screen.getByRole("img")).toHaveAccessibleName(/10\.000 Ω/);
  expect(screen.getByText("PARALLEL")).toBeInTheDocument();
});
it("does not display illustrative numbers as real recommendations", () => {
  render(<SettingsPanel cases={[]} selected={0} onSelect={vi.fn()} />);
  expect(screen.getByText("Awaiting calculation")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Case #1" })).toBeDisabled();
});
it("keeps decision summary and credential setup visible without pretending Gemini ran", () => {
  render(
    <DecisionSummary
      runId={null}
      summary={null}
      onSummary={vi.fn()}
      gemini={{ configured: false }}
      busy={false}
    />,
  );
  expect(
    screen.getByText("Set GEMINI_MODEL and GEMINI_API_KEY in backend/.env."),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Generate decision summary" }),
  ).toBeDisabled();
});
it("accepts the workbook's full-precision efficiency without native step rejection", () => {
  render(
    <Configuration
      form={{ ...initialForm, eta: "0.837453939" }}
      change={vi.fn()}
      inventory={inventory}
      setInventory={vi.fn()}
      busy={false}
      onCalculate={vi.fn()}
      bootstrap={{}}
    />,
  );
  const efficiency = screen.getByLabelText("Expected efficiency η");
  expect(efficiency.validity.stepMismatch).toBe(false);
  expect(efficiency.checkValidity()).toBe(true);
});
it("shows source physics values separately from residual-corrected predictions", () => {
  render(
    <PhysicsBaseline
      record={{
        physics: {
          metrics: {
            front_s: 1.198028683e-6,
            tail_s: 52.18468319e-6,
            crest_V: 1404498.256,
          },
        },
        correction: {
          corrected_metrics: {
            front_s: 1.178149384e-6,
            tail_s: 51.85199155e-6,
            crest_V: 1413793.127,
          },
        },
      }}
    />,
  );
  const table = within(
    screen.getByRole("table", { name: "Physics baseline and ML correction" }),
  );
  expect(table.getByText("1.198028683")).toBeInTheDocument();
  expect(table.getByText("1.178149384")).toBeInTheDocument();
  expect(table.getByText("-0.019879299")).toBeInTheDocument();
  expect(table.getByText("52.184683190")).toBeInTheDocument();
});
it("exposes training-only scaling while displaying predictions in physical units", () => {
  render(
    <PhysicsBaseline
      record={{
        physics: {
          metrics: { front_s: 1.2e-6, tail_s: 50e-6, crest_V: 1425000 },
        },
        correction: {
          corrected_metrics: {
            front_s: 1.21e-6,
            tail_s: 51e-6,
            crest_V: 1426000,
          },
          normalisation: {
            status: "applied",
            fit_split: "Train",
            fit_count: 700,
          },
        },
      }}
    />,
  );
  expect(
    screen.getByText("ML scaling · fitted on training rows only"),
  ).toBeInTheDocument();
  const table = within(
    screen.getByRole("table", { name: "Physics baseline and ML correction" }),
  );
  expect(table.getByText("1.210000000")).toBeInTheDocument();
  expect(table.getByText("1,426.000000000")).toBeInTheDocument();
});
