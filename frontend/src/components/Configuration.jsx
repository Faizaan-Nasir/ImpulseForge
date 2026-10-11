import { useState } from "react";
import { Play, Plus, X, Square } from "lucide-react";
import { Field, Group, Segment, Select } from "./Controls.jsx";
export default function Configuration({
  form,
  change,
  inventory,
  setInventory,
  busy,
  onCalculate,
  onCancel,
  status,
  bootstrap,
}) {
  const [role, setRole] = useState("front");
  const f = (key, label, unit, props = {}) => (
    <Field
      key={key}
      id={key}
      label={label}
      unit={unit}
      value={form[key]}
      onChange={(value) => change(key, value)}
      {...props}
    />
  );
  const updateRes = (index, key, value) =>
    setInventory({
      ...inventory,
      [role]: inventory[role].map((r, i) =>
        i === index ? { ...r, [key]: value === "" ? "" : Number(value) } : r,
      ),
    });
  return (
    <form
      className="rail"
      onSubmit={(e) => {
        e.preventDefault();
        onCalculate();
      }}
    >
      <div className="rail-head">
        <h2>Test configuration</h2>
        <button
          type="submit"
          className="btn primary"
          disabled={busy || !bootstrap}
        >
          {busy ? (
            <span className="spin" />
          ) : (
            <Play size={14} fill="currentColor" />
          )}
          {busy ? "Calculating…" : "Calculate recommendations"}
        </button>
        <div className="calc-status" role="status">
          {status || "Enter a scenario to evaluate"}{" "}
        </div>
        {busy && (
          <button type="button" className="btn small" onClick={onCancel}>
            <Square size={12} />
            Stop calculation
          </button>
        )}
      </div>
      <Group label="Impulse type">
        <Segment
          label="Impulse type"
          value={form.impulse}
          onChange={(v) => change("impulse", v)}
          options={[
            ["Lightning", "Lightning", "1.2/50 µs"],
            ["Switching", "Switching", "250/2500 µs"],
          ]}
        />
      </Group>
      <Group label="Test inputs">
        {f("vTest", "Desired crest voltage", "kV")}
        {f("systemMax", "Maximum system voltage", "kV")}
        {f("cLoad", "Insulator / test-object capacitance", "pF")}
        {f("cDiv", "Measurement-system / divider capacitance", "pF")}
        <div className="grid2">
          {f("cStray", "Stray capacitance", "pF")}
          {f("lStray", "Loop inductance", "µH")}
        </div>
        {f("eta", "Expected efficiency η", "0–1", {
          min: 0,
          hint: "An initial charging estimate. Exact mode computes waveform efficiency from the circuit.",
        })}
        <details>
          <summary className="hint cursor-pointer">Other R/L/C loads</summary>
          <div className="mt-2 grid gap-2">
            <Select
              id="loadModel"
              label="Load equivalent"
              value={form.loadModel}
              onChange={(v) => change("loadModel", v)}
              options={[
                ["capacitive_v1", "Capacitive test object"],
                ["parallel_rc_v1", "Parallel R/C equivalent"],
                ["parallel_rlc_v1", "Parallel R/L/C equivalent"],
              ]}
            />
            {form.loadModel !== "capacitive_v1" &&
              f("loadR", "Load resistance", "Ω")}
            {form.loadModel === "parallel_rlc_v1" &&
              f("loadL", "Load inductance", "H")}
            <p className="hint">
              Equivalent loads must match the supported terminal topology.
            </p>
          </div>
        </details>
      </Group>
      <Group label="Generator settings">
        <Select
          id="profile"
          label="Generator profile"
          value={form.profile}
          onChange={(v) => change("profile", v)}
          options={[
            ["workbook", "Workbook generator · 3 µF stages"],
            ["haefely", "Document fallback · 0.125 µF stages"],
            ["custom", "Custom"],
          ]}
          hint="Presets fill editable inputs. Editing generator values switches to Custom."
        />
        <div className="grid2">
          {f("nMax", "Available stages", "stages", { step: 1, min: 1 })}
          {f("uMax", "Max charging voltage", "kV/stage")}
        </div>
        <div className="grid2">
          {f("cStage", "Stage capacitance", "µF")}
          {f("wStage", "Energy limit per stage", "kJ", { min: 0.000001 })}
        </div>
        {f("wTotal", "Total generator energy limit", "kJ", { min: 0.000001 })}
        <p className="hint">
          Calibration uses your per-stage and total generator energy limits.
        </p>
        {f("cBo", "Basic load Cbo", "pF")}
        <label className="check">
          <input
            type="checkbox"
            checked={form.includeCbo}
            onChange={(e) => change("includeCbo", e.target.checked)}
          />
          Add Cbo to the load
        </label>
        <div className="field">
          <span className="lbl">Calculation mode</span>
          <Segment
            label="Calculation mode"
            value={form.mode}
            onChange={(v) => change("mode", v)}
            options={[
              ["calculator", "Calculator"],
              ["exact", "Exact"],
            ]}
          />
          <p className="hint">
            Calculator uses workbook formulas. Exact solves the circuit.
            Standards compliance is not certified.
          </p>
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={form.extrapolate}
            onChange={(e) => change("extrapolate", e.target.checked)}
          />
          Estimate configurations outside the training range
        </label>
        <p className="hint">
          These ML estimates are marked extrapolated. The current dataset does
          not model environmental effects.
        </p>
      </Group>
      <Group label="Constraints">
        <div className="grid2">
          {f("tFront", "Target front time T1", "µs")}
          {f("tTail", "Target tail time T2", "µs")}
        </div>
        <Select
          id="tolProfile"
          label="Tolerance profile"
          value={form.tolProfile}
          onChange={(v) => change("tolProfile", v)}
          options={[
            ["project", "Project timing profile"],
            ["workbook", "Workbook sheet"],
            ["custom", "Custom"],
          ]}
        />
        <div className="grid grid-cols-3 gap-2">
          {f("tolCrest", "Crest upper tolerance +", "%")}
          {f("tolFront", "T1 ±", "%")}
          {f("tolTail", "T2 ±", "%")}
        </div>
        <div className="field">
          <span className="lbl">Resistor selection</span>
          <Segment
            label="Resistor selection"
            value={form.selection}
            onChange={(v) => change("selection", v)}
            options={[
              ["single", "Single resistor"],
              ["combo", "Series–parallel"],
            ]}
          />
        </div>
        {f("maxUnits", "Max resistors per combination", "per stage", {
          min: 1,
          step: 1,
          disabled: form.selection === "single",
          hint: "Search budget per assembly; each type has a separate four-copy cap in front and tail.",
        })}
        <Select
          id="ranking"
          label="Ranking priority"
          value={form.ranking}
          onChange={(v) => change("ranking", v)}
          options={[
            ["balanced", "Balanced"],
            ["accuracy", "Accuracy only"],
            ["resistors", "Fewest resistors"],
            ["stages", "Fewest stages"],
            ["voltage", "Voltage margin"],
          ]}
          hint="S and J stay first. Preferences affect exact ties only; no learned ranking."
        />
        <details>
          <summary className="hint cursor-pointer">Calculation budgets</summary>
          <div className="grid2 mt-2">
            {f("maxProposals", "Maximum iterations", "iterations", {
              min: 1,
              step: 1,
            })}
            {f("wallSeconds", "Time budget", "s", { min: 1 })}
          </div>
        </details>
      </Group>
      <Group label="Resistor inventory">
        <div className="tabs" role="tablist" aria-label="Resistor inventory">
          {["front", "tail"].map((r) => (
            <button
              key={r}
              type="button"
              role="tab"
              aria-selected={role === r}
              onClick={() => setRole(r)}
            >
              {r === "front" ? "Front" : "Tail"}{" "}
              <span className="num">({inventory[r].length})</span>
            </button>
          ))}
        </div>
        <div className="inv-head">
          <span>Value (Ω)</span>
          <span>Qty per stage</span>
          <span className="sr-only">Remove</span>
        </div>
        <div
          className="inv-list"
          role="tabpanel"
          aria-label={`${role} inventory`}
        >
          {inventory[role].map((r, i) => (
            <div className="inv-row" key={r.type_id}>
              <Field
                id={`inv-${role}-${r.type_id}`}
                label={
                  <span className="sr-only">{`${role} resistance ${i + 1}`}</span>
                }
                value={r.nominal_ohm}
                unit="Ω"
                min={0.000001}
                onChange={(v) => updateRes(i, "nominal_ohm", v)}
              />
              <Field
                id={`qty-${role}-${r.type_id}`}
                label={
                  <span className="sr-only">{`${role} quantity ${i + 1}`}</span>
                }
                value={r.available_quantity}
                step={1}
                min={0}
                onChange={(v) => updateRes(i, "available_quantity", v)}
              />
              <button
                className="iconbtn"
                type="button"
                aria-label={`Remove ${r.nominal_ohm} Ω ${role} resistor`}
                onClick={() =>
                  setInventory({
                    ...inventory,
                    [role]: inventory[role].filter((_, j) => j !== i),
                  })
                }
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
        <button
          className="btn small"
          type="button"
          onClick={() =>
            setInventory({
              ...inventory,
              [role]: [
                ...inventory[role],
                {
                  type_id: `${role}-${crypto.randomUUID()}`,
                  nominal_ohm: 10,
                  available_quantity: 4,
                  quantity_scope: "per_stage",
                },
              ],
            })
          }
        >
          <Plus size={14} />
          Add resistor
        </button>
        <p className="hint">
          Inventory is supplied with this run. Front and tail quantities are
          independent.
        </p>
      </Group>
    </form>
  );
}
