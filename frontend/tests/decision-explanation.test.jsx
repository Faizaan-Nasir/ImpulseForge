import React from "react";
import {
  render,
  screen,
  fireEvent,
  within,
  waitFor,
} from "@testing-library/react";
import { it, expect, vi, afterEach } from "vitest";
import { DecisionSummary } from "../src/components/Results.jsx";

const output = {
  output_key: "front_s",
  label: "Front / peak time",
  display_scale: 1e6,
  display_unit: "µs",
  physics_value: 1.2e-6,
  ml_residual: -6e-9,
  corrected_value: 1.194e-6,
  target_value: 1.2e-6,
  explanation:
    "Physics gave 1.2 µs; the learned residual lowers the front time.",
  shap_status: "complete",
  shap_explanation:
    "The stage count and load capacitance lower the model residual relative to its training background.",
  reference_residual: 2e-9,
  sum_contributions: -8e-9,
  additivity_error: 1e-23,
  additivity_verified: true,
  method: "Kernel SHAP",
  nsamples: 32,
  background_count: 8,
  reference_meaning:
    "Expected model residual on training-background rows, not a physics baseline.",
  contributions: [
    {
      feature: "N",
      label: "Active stages",
      display_input_value: 9,
      input_unit: "stages",
      contribution: -5e-9,
      display_contribution: -0.005,
      direction: "decreases",
    },
  ],
};
output.top_contributions = output.contributions;
const summary = {
  status: "provider_error",
  explanation_status: "complete",
  provider_http_status: 429,
  reason: "Gemini quota or rate limit was exhausted (HTTP 429).",
  analysis: {
    selection_explanation:
      "Case #1 wins because S=0.1 is lower than S=0.2, before resistor count.",
    comparison: [
      {
        candidate_id: "case2",
        reason: "The smaller resistor count did not decide this comparison.",
      },
    ],
    search_explanation:
      "Seven proposals produced three passing ML predictions.",
    cases: [1, 2].map((n) => ({
      candidate_id: `case${n}`,
      case_number: n,
      physics_mode: "calculator",
      physics_explanation: `Actual circuit explanation for case ${n}.`,
      circuit_values: {},
      outputs: [output],
    })),
    constraints: [
      {
        constraint_group: "energy",
        explanation: "Stored energy exceeds the retained limit.",
      },
    ],
    interpretation: "SHAP describes model attribution, not physical causation.",
    scope: "Heat and environmental effects were not learned.",
    eligibility_note: "Waveform success is separate from hardware eligibility.",
  },
};
afterEach(() => vi.unstubAllGlobals());

it("keeps ranking and actual SHAP adjustments visible when Gemini is rate limited", () => {
  render(
    <DecisionSummary
      runId="run"
      summary={summary}
      onSummary={vi.fn()}
      gemini={{ configured: true }}
      busy={false}
    />,
  );
  expect(screen.getByText(/Case #1 wins because S=0.1/)).toBeInTheDocument();
  expect(screen.getByText(/HTTP 429/)).toBeInTheDocument();
  const table = within(
    screen.getByRole("table", {
      name: "Front / peak time physics and ML values",
    }),
  );
  expect(table.getAllByText("1.200000 µs")).toHaveLength(2);
  expect(table.getByText("-0.006000 µs")).toBeInTheDocument();
  expect(table.getByText("1.194000 µs")).toBeInTheDocument();
  expect(screen.getByText("-0.005000 µs")).toBeInTheDocument();
  expect(screen.getByText(/not physical causation/)).toBeInTheDocument();
  expect(
    screen.queryByText(/becomes available after Gemini/),
  ).not.toBeInTheDocument();
});

it("switches the case explanation without changing the ranking narrative", () => {
  render(
    <DecisionSummary
      runId="run"
      summary={summary}
      onSummary={vi.fn()}
      gemini={{}}
      busy={false}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Explain Case #2" }));
  expect(
    screen.getByText("Actual circuit explanation for case 2."),
  ).toBeInTheDocument();
  expect(screen.getByText(/Case #1 wins because S=0.1/)).toBeInTheDocument();
});

it("shows missing SHAP honestly while retaining the prediction values", () => {
  const partial = structuredClone(summary);
  partial.analysis.cases[0].outputs[0].shap_status = "unavailable";
  partial.analysis.cases[0].outputs[0].shap_reason = "model_artifact_changed";
  render(
    <DecisionSummary
      runId="run"
      summary={partial}
      onSummary={vi.fn()}
      gemini={{}}
      busy={false}
    />,
  );
  expect(
    screen.getByText(/SHAP attribution unavailable: model_artifact_changed/),
  ).toBeInTheDocument();
  expect(screen.getByText("1.194000 µs")).toBeInTheDocument();
  expect(
    screen.queryByLabelText("Front / peak time strongest SHAP contributions"),
  ).not.toBeInTheDocument();
});

it("generate-summary button accepts a computed explanation despite a provider error", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => summary }),
  );
  const onSummary = vi.fn();
  render(
    <DecisionSummary
      runId="run"
      summary={null}
      onSummary={onSummary}
      gemini={{}}
      busy={false}
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Generate decision summary" }),
  );
  await waitFor(() => expect(onSummary).toHaveBeenCalledWith(summary));
  expect(fetch.mock.calls[0][0]).toContain("/v1/runs/run/decision-summary");
});
