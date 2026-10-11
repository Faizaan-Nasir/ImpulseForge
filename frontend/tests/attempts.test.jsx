import React from "react";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { it, expect, vi, afterEach } from "vitest";
import AttemptHistory from "../src/components/AttemptHistory.jsx";
import { allAttempts } from "../src/lib/api.js";
import App from "../src/App.jsx";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it("renders a single network pair and history table before results are available", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise(() => {})),
  );
  const errors = vi.spyOn(console, "error").mockImplementation(() => {});
  render(<App />);
  expect(
    screen.getAllByRole("heading", { name: "Front resistor network" }),
  ).toHaveLength(1);
  expect(
    screen.getAllByRole("heading", { name: "Tail resistor network" }),
  ).toHaveLength(1);
  expect(
    screen.getByRole("table", {
      name: "Chronological ML predictions for every attempt",
    }),
  ).toBeInTheDocument();
  expect(errors).not.toHaveBeenCalled();
});

const prediction = (attempt) => ({
  attempt_number: attempt,
  evaluation_in_attempt: 1,
  event_sequence: attempt,
  attempt_status: "evaluated",
  prediction_source: "fresh_ml",
  ml_evaluation_number: attempt,
  N: 9,
  ml_metrics: { front_s: 1.27e-6, tail_s: 53.74e-6, crest_V: 1429558 },
  waveform_within_tolerance: true,
  hardware_feasible: false,
  objective: {
    errors: {
      front: { within_tolerance: true },
      tail: { within_tolerance: true },
      crest: { within_tolerance: true },
    },
  },
});

it("shows chronological ML values in physical units, cached repeats and rejected attempts", () => {
  render(
    <AttemptHistory
      history={{
        proposal_count: 3,
        items: [
          prediction(1),
          {
            ...prediction(2),
            prediction_source: "cached_ml",
            ml_evaluation_number: null,
          },
          {
            attempt_number: 3,
            evaluation_in_attempt: 1,
            event_sequence: 3,
            attempt_status: "rejected",
            prediction_source: "not_invoked",
            reason_codes: ["inventory_range_infeasible"],
          },
        ],
      }}
    />,
  );
  const table = within(screen.getByRole("table"));
  const rows = table.getAllByRole("row");
  expect(rows).toHaveLength(4);
  expect(within(rows[1]).getByText("1.270000")).toBeInTheDocument();
  expect(within(rows[1]).getByText("53.740000")).toBeInTheDocument();
  expect(within(rows[1]).getByText("1,429.558000")).toBeInTheDocument();
  expect(within(rows[1]).getByText("Thresholds met")).toBeInTheDocument();
  expect(
    within(rows[1]).getByText("Failed / unknown checks"),
  ).toBeInTheDocument();
  expect(within(rows[2]).getByText("Cached prediction")).toBeInTheDocument();
  expect(within(rows[3]).getByText("Rejected")).toBeInTheDocument();
  expect(within(rows[3]).queryByText("1.270000")).not.toBeInTheDocument();
  expect(
    within(rows[3]).getByText("inventory_range_infeasible"),
  ).toBeInTheDocument();
});

it("allows the first and last attempt to be viewed when more than fifty rows exist", () => {
  render(
    <AttemptHistory
      history={{
        proposal_count: 101,
        items: Array.from({ length: 101 }, (_, i) => prediction(i + 1)),
      }}
    />,
  );
  expect(screen.getByRole("rowheader", { name: "1" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Last" }));
  expect(screen.getByRole("rowheader", { name: "101" })).toBeInTheDocument();
  expect(
    screen.queryByRole("rowheader", { name: "1" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "First" }));
  expect(screen.getByRole("rowheader", { name: "1" })).toBeInTheDocument();
});

it("retrieves every API page without removing duplicate candidate attempts", async () => {
  const items = Array.from({ length: 1003 }, (_, i) => ({
    attempt_number: i + 1,
    candidate_id: "same",
  }));
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ total: 1003, items: items.slice(0, 1000) }),
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ total: 1003, items: items.slice(1000) }),
    });
  vi.stubGlobal("fetch", fetchMock);
  const history = await allAttempts("run");
  expect(history.items).toHaveLength(1003);
  expect(history.items.at(-1).attempt_number).toBe(1003);
  expect(fetchMock.mock.calls[1][0]).toContain("offset=1000&limit=1000");
});

it("reports incomplete history instead of silently truncating it", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ total: 1, items: [] }),
    }),
  );
  await expect(allAttempts("run")).rejects.toThrow(
    "before all rows were retrieved",
  );
});
