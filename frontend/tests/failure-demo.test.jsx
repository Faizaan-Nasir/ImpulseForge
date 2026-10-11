import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { it, expect, vi, afterEach } from "vitest";
import FailureWaveformDemo from "../src/components/FailureWaveformDemo.jsx";
import {
  DEMO_CASES,
  chooseDemoCase,
  sampleDemo,
  demoVoltage,
} from "../src/lib/failureDemo.js";
import App from "../src/App.jsx";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
it("uses every random interval, including boundaries, with repeated selections allowed", () => {
  expect(
    [0, 0.25, 0.5, 0.75, 0.999999].map((n) => chooseDemoCase(() => n).id),
  ).toEqual([
    "pass",
    "front-breakdown",
    "tail-breakdown",
    "inter-turn",
    "inter-turn",
  ]);
  expect(chooseDemoCase(() => 0.3)).toBe(chooseDemoCase(() => 0.3));
});
it("keeps template samples deterministic and reproduces the three qualitative failure shapes", () => {
  const front = sampleDemo("front-breakdown");
  expect(front).toEqual(sampleDemo("front-breakdown"));
  expect(front).toHaveLength(4001);
  expect(front[0]).toEqual({ timeUs: 0, voltagePu: 0 });
  expect(front.at(-1).timeUs).toBe(80);
  expect(demoVoltage("front-breakdown", 2)).toBeLessThan(0.001);
  expect(demoVoltage("tail-breakdown", 14)).toBe(demoVoltage("pass", 14));
  expect(demoVoltage("tail-breakdown", 20)).toBeLessThan(0.0001);
  expect(demoVoltage("inter-turn", 4)).toBe(demoVoltage("pass", 4));
  expect(demoVoltage("inter-turn", 5.5)).toBeGreaterThan(
    demoVoltage("pass", 5.5),
  );
  expect(demoVoltage("inter-turn", 6.5)).toBeLessThan(demoVoltage("pass", 6.5));
});
it("labels the chosen preset above its plot and makes no network requests", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const rng = vi.spyOn(Math, "random").mockReturnValue(0.3);
  render(<FailureWaveformDemo />);
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Generate random waveform" }),
  );
  expect(
    screen.getByRole("heading", { level: 2, name: "Front breakdown" }),
  ).toBeInTheDocument();
  const graph = screen.getByRole("img");
  expect(graph).toHaveAccessibleName(/Case 1: Front Breakdown/);
  const originalPath = graph.querySelector("path").getAttribute("d");
  fireEvent.click(screen.getByRole("button", { name: "Front detail · 10 µs" }));
  expect(graph.querySelector("path").getAttribute("d")).not.toBe(originalPath);
  fireEvent.click(
    screen.getByRole("button", { name: "Generate random waveform" }),
  );
  expect(graph.querySelector("path").getAttribute("d")).toBe(originalPath);
  expect(screen.getByText(/Demo draw #2/)).toBeInTheDocument();
  expect(rng).toHaveBeenCalledTimes(2);
  expect(fetch).not.toHaveBeenCalled();
});
it.each(DEMO_CASES.map((c, i) => [c, i]))(
  "shows each preset classification with its matching curve",
  (c, i) => {
    vi.spyOn(Math, "random").mockReturnValue((i + 0.5) / 4);
    render(<FailureWaveformDemo />);
    fireEvent.click(
      screen.getByRole("button", { name: "Generate random waveform" }),
    );
    expect(
      screen.getByRole("heading", { level: 2, name: c.classification }),
    ).toBeInTheDocument();
    expect(screen.getByRole("img").querySelector("title")).toHaveTextContent(
      c.title,
    );
  },
);
it("the independent tab works offline and preserves its draw across workspace switches", () => {
  const fetch = vi.fn(() => new Promise(() => {}));
  vi.stubGlobal("fetch", fetch);
  vi.spyOn(Math, "random").mockReturnValue(0.8);
  render(<App />);
  const initialCalls = fetch.mock.calls.length;
  const tab = screen.getByRole("tab", { name: "Transformer test demo" });
  fireEvent.click(tab);
  expect(tab).toHaveAttribute("aria-selected", "true");
  fireEvent.click(
    screen.getByRole("button", { name: "Generate random waveform" }),
  );
  const path = screen.getByRole("img").querySelector("path").getAttribute("d");
  fireEvent.click(
    screen.getByRole("tab", { name: "Configuration & calibration" }),
  );
  fireEvent.click(tab);
  expect(screen.getByRole("img").querySelector("path").getAttribute("d")).toBe(
    path,
  );
  expect(fetch).toHaveBeenCalledTimes(initialCalls);
  expect(
    screen.queryByRole("button", { name: "Export report" }),
  ).not.toBeInTheDocument();
  fireEvent.keyDown(tab, { key: "ArrowLeft" });
  expect(
    screen.getByRole("tab", { name: "Configuration & calibration" }),
  ).toHaveAttribute("aria-selected", "true");
});
