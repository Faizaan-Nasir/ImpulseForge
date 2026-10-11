import DecisionExplanation from "./DecisionExplanation.jsx";
import { useState } from "react";
import { Check, AlertTriangle, Sparkles } from "lucide-react";
import {
  number,
  percentage,
  shownMetrics,
  shownObjective,
} from "../lib/config.js";
import { Pill } from "./Controls.jsx";
import { api, post } from "../lib/api.js";
export function SettingsPanel({ cases, selected, onSelect, context, mode }) {
  const record = cases[selected],
    candidate = record?.candidate,
    objective = shownObjective(record);
  const waveformOK = objective?.waveform_within_tolerance;
  const verified = mode === "eligible_recommendations";
  return (
    <section className="card" aria-label="Recommended settings">
      <div className="case-top">
        <h2>Recommended settings</h2>
        <div className="cases" role="group" aria-label="Select case">
          {[0, 1, 2].map((i) => (
            <button
              type="button"
              key={i}
              aria-pressed={selected === i}
              disabled={!cases[i]}
              onClick={() => onSelect(i)}
            >
              Case #{i + 1}
            </button>
          ))}
        </div>
      </div>
      <div className="case-title">
        <div className="flex flex-wrap items-center gap-3">
          <h3>
            {candidate
              ? `Selected case: #${selected + 1} · ${selected === 0 ? "Best evaluated match" : selected === 1 ? "Runner-up" : "Third option"}`
              : "Configure a test to compare settings"}
          </h3>
          <Pill
            status={
              candidate ? (verified && waveformOK ? "good" : "warn") : "neutral"
            }
          >
            {candidate
              ? verified
                ? "Eligible recommendation"
                : "Diagnostic only"
              : "Awaiting calculation"}
          </Pill>
          {record?.correction?.status === "predicted_extrapolation" && (
            <Pill status="warn">Extrapolated ML estimate</Pill>
          )}
        </div>
        <p className="small muted">
          {candidate
            ? `Largest waveform deviation: ${number((objective?.S ?? 0) * 100, 2)} % of its allowed band. ${record.correction?.corrected_metrics ? "Residual ML correction available." : "Showing physics baseline; ML correction unavailable."}`
            : "The backend will evaluate buildable resistor networks and expose every constraint verdict."}
        </p>
      </div>
      <div className="settings">
        <div>
          <span className="k">Generator stages</span>
          <div className="big">{candidate?.N ?? "—"}</div>
          <span className="support">
            of {context?.hardware?.N_max ?? "—"} available · C1 ={" "}
            {number(record?.physics?.derived?.C1_F * 1e6, 3)} µF
          </span>
        </div>
        <div>
          <span className="k">Charging voltage</span>
          <div className="big">
            {number(candidate?.U_charge_V / 1000, 2)}
            <small>kV/stage</small>
          </div>
          <span className="support">
            {number(record?.physics?.voltage_utilisation * 100, 0)} % of stage
            limit · {number(record?.physics?.stage_energy_J / 1000, 2)} kJ/stage
          </span>
        </div>
        {["front", "tail"].map((role) => (
          <div key={role}>
            <span className="k">
              {role === "front" ? "Front" : "Tail"} equivalent resistance
            </span>
            <div className="big">
              {number(candidate?.[role]?.equivalent_ohm, 3)}
              <small>Ω/stage</small>
            </div>
            <span className="support">
              {number(
                record?.physics?.derived?.[
                  role === "front" ? "R1_ohm" : "R2_ohm"
                ],
                2,
              )}{" "}
              Ω circuit equivalent · {candidate?.[role]?.total_resistors ?? "—"}{" "}
              resistors/stage
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
export function PhysicsBaseline({
  record,
  settings,
  title = "Physics baseline and ML correction",
  referenceStatus,
}) {
  if (!record?.physics?.metrics) return null;
  return (
    <section className="card" aria-label={title}>
      <div className="card-head">
        <h2>{title}</h2>
        {referenceStatus && (
          <Pill status="neutral">Workbook reference · diagnostic</Pill>
        )}
      </div>
      <p className="hint">
        Mode: {record.physics.baseline_mode ?? "—"} · N ={" "}
        {settings?.N ?? record.candidate?.N ?? "—"} · charge ={" "}
        {number(
          (settings?.U_charge_V ?? record.candidate?.U_charge_V) / 1000,
          9,
        )}{" "}
        kV/stage · Rf ={" "}
        {number(
          settings?.Rf_actual_ohm ?? record.candidate?.front?.equivalent_ohm,
          3,
        )}{" "}
        Ω/stage · Rt ={" "}
        {number(
          settings?.Rt_actual_ohm ?? record.candidate?.tail?.equivalent_ohm,
          3,
        )}{" "}
        Ω/stage.
      </p>
      {referenceStatus && (
        <p className="hint">
          This independently reproduces the worksheet's stage sizing and
          five-ohm resistor rounding before optimisation.
          {referenceStatus === "reference_only"
            ? " The rounded resistors are unavailable in the supplied inventory; these are mathematical reference values."
            : " The exact one-resistor recipes are available in your inventory."}{" "}
          Energy checks:{" "}
          {record.physics.constraints
            ?.filter((c) =>
              ["HW_STAGE_ENERGY", "HW_TOTAL_ENERGY"].includes(c.constraint_id),
            )
            .map((c) => `${c.constraint_id}: ${c.status}`)
            .join(" · ")}
          . Recommendation eligibility remains separate.
        </p>
      )}
      <p className="hint">
        Compare the Physics columns in the workbook with this baseline, using
        the same actual stage count, charge and resistor networks. ML values
        include the learned residual and may differ from observed labels.
      </p>
      {record.correction?.normalisation?.status === "applied" && (
        <details className="trace-detail">
          <summary>ML scaling · fitted on training rows only</summary>
          <p className="hint">
            Inputs and residual targets are standardised before inference.
            Displayed predictions are converted back to physical units before
            tolerance checks.
          </p>
          <pre>{JSON.stringify(record.correction.normalisation, null, 2)}</pre>
        </details>
      )}
      <div className="table-wrap">
        <table aria-label="Physics baseline and ML correction">
          <thead>
            <tr>
              <th className="l">Output</th>
              <th>Physics baseline</th>
              <th>ML corrected</th>
              <th>ML residual</th>
            </tr>
          </thead>
          <tbody>
            {[
              ["front_s", "Front time", 1e6, "µs"],
              ["tail_s", "Tail time", 1e6, "µs"],
              ["crest_V", "Crest voltage", 1e-3, "kV"],
            ].map(([key, label, scale, unit]) => {
              const baseline = record.physics.metrics[key];
              const prediction = record.correction?.corrected_metrics?.[key];
              return (
                <tr key={key}>
                  <th className="l">
                    {label} (<span className="normal-case">{unit}</span>)
                  </th>
                  <td>{number(baseline * scale, 9)}</td>
                  <td>
                    {prediction == null ? "—" : number(prediction * scale, 9)}
                  </td>
                  <td>
                    {prediction == null
                      ? "—"
                      : number((prediction - baseline) * scale, 9)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
export function PerformanceMetrics({ record, curve, context }) {
  const report = record?.performance,
    metrics = shownMetrics(record),
    objective = shownObjective(record);
  const [explanation, setExplanation] = useState(null),
    [error, setError] = useState("");
  const corrected = !!record?.correction?.corrected_metrics;
  const labels = {
    front: "Front time T1",
    tail: "Tail time T2",
    crest: "Predicted crest voltage",
  };
  const output = (role) => {
    const key = role === "crest" ? "crest_V" : `${role}_s`,
      value = metrics?.[key];
    return {
      value: role === "crest" ? value / 1000 : value * 1e6,
      unit: role === "crest" ? "kV" : "µs",
      error: objective?.errors?.[role],
    };
  };
  const metric = (
    name,
    val,
    unit,
    detail,
    status = "neutral",
    statusText = "Info",
  ) => (
    <div className="metric" key={name}>
      <div className="row">
        <span className="name">{name}</span>
        <Pill status={status}>{statusText}</Pill>
      </div>
      <div className="val">
        {val} {unit}
      </div>
      <div className="detail">{detail}</div>
    </div>
  );
  return (
    <section className="card" aria-label="Performance metrics">
      <div className="card-head">
        <h2>Performance metrics</h2>
        <Pill
          status={
            objective
              ? objective.waveform_within_tolerance
                ? "good"
                : "bad"
              : "neutral"
          }
        >
          {objective
            ? objective.waveform_within_tolerance
              ? "Waveform within"
              : "Waveform outside"
            : "Awaiting results"}
        </Pill>
      </div>
      <div className="metrics">
        {["crest", "front", "tail"].map((role) => {
          const { value, unit, error } = output(role);
          return metric(
            labels[role],
            number(value, role === "tail" ? 2 : 3),
            unit,
            error
              ? `Target ${number(role === "crest" ? error.target / 1000 : error.target * 1e6, 3)} ${unit} · deviation ${percentage(error.percentage_delta)} · allowed ${role === "crest" ? "0 to +" : "±"}${number((100 * error.allowed_delta) / error.target, 1)} %${error.reason_code === "crest_below_required" ? " · Below required voltage; calibration required" : ""}`
              : "Prediction unavailable",
            error ? (error.within_tolerance ? "good" : "bad") : "neutral",
            error
              ? error.within_tolerance
                ? "Within"
                : error.reason_code === "crest_below_required"
                  ? "Calibrate"
                  : "Outside"
              : "Unavailable",
          );
        })}
        {metric(
          "Peak time (time of maximum)",
          number(curve?.fit?.landmarks?.peak_s * 1e6, 3),
          "µs",
          "Peak of the parameter-reconstructed curve; informational.",
        )}
        {metric(
          "Predicted efficiency η",
          number(
            corrected
              ? report?.efficiency?.corrected_voltage_transfer
              : report?.efficiency?.physics_voltage_transfer,
            3,
          ),
          "",
          "Crest voltage ÷ initial erected voltage (N × charge).",
        )}
        {metric(
          "Waveform fit error",
          number(curve?.comparison_to_target?.normalised_rms_percent, 2),
          "%",
          "RMS difference between reconstructed curves; not model accuracy.",
        )}
        {metric(
          "Overshoot",
          "—",
          "",
          "Overshoot certification is not implemented; no invented compliance limit.",
          "neutral",
          "Unavailable",
        )}
      </div>
      <div className="defs">
        {!context
          ? "Timing definitions follow the selected impulse profile."
          : context.test.category === "Lightning"
            ? "T1 = 1.67 × (t90 − t30). T2 uses the virtual origin."
            : "Switching uses the recorded legacy time-to-peak / half-value convention."}
        <br />
        Mode: {context?.request?.physics_mode ?? "—"}.{" "}
        {corrected ? "Residual-corrected metrics." : "Physics baseline only."}{" "}
        Standards verification is pending.
        <br />
        {record?.correction?.status === "predicted_extrapolation" &&
          "This ML estimate is outside the training range. "}
        {record?.correction?.environment_effects?.status === "not_modelled" &&
          "Environmental effects are not modelled by the current synthetic dataset."}
      </div>
      {report && (
        <details className="trace-detail">
          <summary className="hint cursor-pointer">
            Model accuracy, speed and constraints
          </summary>
          <div className="small muted">
            {report.model_quality?.train_count ?? "—"} train ·{" "}
            {report.model_quality?.validation_count ?? "—"} validation ·{" "}
            {report.model_quality?.dataset_origin}
            <br />
            Candidate compute: {number(report.runtime?.total_seconds, 4)} s.
            Accuracy for this setup: {report.observed_accuracy?.status}.
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="l">Validation output</th>
                  <th>MAE</th>
                  <th>RMSE</th>
                  <th>Bias</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(report.model_quality?.metrics || {}).map(
                  ([key, m]) => (
                    <tr key={key}>
                      <th className="l">{key.replace("residual_", "")}</th>
                      <td>
                        {number(
                          m.validation_MAE * (m.unit === "s" ? 1e6 : 1e-3),
                          5,
                        )}{" "}
                        {m.unit === "s" ? "µs" : "kV"}
                      </td>
                      <td>
                        {number(
                          m.validation_RMSE * (m.unit === "s" ? 1e6 : 1e-3),
                          5,
                        )}
                      </td>
                      <td>
                        {number(
                          m.validation_bias * (m.unit === "s" ? 1e6 : 1e-3),
                          5,
                        )}
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
          <p className="hint">
            Synthetic validation scores are aggregate errors, not a confidence
            interval for this input.
          </p>
          <pre>
            {JSON.stringify(
              {
                runtime: report.runtime,
                hardware: report.hardware,
                energy: report.stored_energy,
                model_support: record.correction.support,
                input_effects_not_modelled:
                  record.correction.input_effects_not_modelled,
                constraints: record.physics.constraints,
              },
              null,
              2,
            )}
          </pre>
          <button
            type="button"
            className="btn small"
            disabled={!corrected}
            onClick={async () => {
              try {
                setExplanation(
                  await api(
                    `/v1/candidates/${record.candidate_id}/explanations`,
                  ),
                );
                setError("");
              } catch (e) {
                setError(e.message);
              }
            }}
          >
            Explain the ML correction
          </button>
          {error && <p className="error-text">{error}</p>}
          {explanation && <pre>{JSON.stringify(explanation, null, 2)}</pre>}
        </details>
      )}
    </section>
  );
}
export function Comparison({ cases, selected, onSelect, mode }) {
  const rows = [
    ["Generator stages", (r) => r.candidate.N],
    [
      "Charging voltage",
      (r) => `${number(r.candidate.U_charge_V / 1000, 2)} kV/stage`,
    ],
    ["Front Req", (r) => `${number(r.candidate.front.equivalent_ohm)} Ω/stage`],
    ["Tail Req", (r) => `${number(r.candidate.tail.equivalent_ohm)} Ω/stage`],
    [
      "Resistors per stage",
      (r) =>
        `${r.candidate.front.total_resistors} + ${r.candidate.tail.total_resistors}`,
    ],
    ["Front time T1", (r) => `${number(shownMetrics(r).front_s * 1e6)} µs`],
    ["Tail time T2", (r) => `${number(shownMetrics(r).tail_s * 1e6, 2)} µs`],
    ["Crest voltage", (r) => `${number(shownMetrics(r).crest_V / 1000, 1)} kV`],
    ["Status", (r) => (r.eligible ? "Eligible" : "Diagnostic")],
    [
      "Known physical constraints",
      (r) =>
        r.calibration?.known_constraints_satisfied === false
          ? "Fail"
          : r.calibration?.known_constraints_satisfied === true
            ? "No known failures"
            : "Unassessed",
    ],
    [
      "All waveform thresholds",
      (r) => (shownObjective(r)?.waveform_within_tolerance ? "Pass" : "Fail"),
    ],
    [
      "ML training range",
      (r) =>
        !r.correction?.corrected_metrics
          ? "Unavailable"
          : r.correction.status === "predicted_extrapolation"
            ? "Extrapolated"
            : "Within recorded range",
    ],
    ["Worst deviation S", (r) => number(shownObjective(r)?.S, 5)],
    ["Weighted deviation J", (r) => number(shownObjective(r)?.J, 5)],
  ];
  return (
    <section className="card" aria-label="Candidate comparison">
      <div className="card-head">
        <h2>Top three evaluated configurations</h2>
        <span className="sub">
          {cases.length}{" "}
          {mode === "eligible_recommendations"
            ? "eligible settings"
            : "diagnostic cases out of 3"}
        </span>
      </div>
      <div className="table-wrap">
        <table
          className="cmp"
          aria-label="Top 3 candidate settings, one column per case"
        >
          <thead>
            <tr>
              <th className="rowhead">Metric</th>
              {[0, 1, 2].map((i) => (
                <th key={i} className={i === selected ? "sel" : ""}>
                  <button
                    type="button"
                    className="colbtn"
                    disabled={!cases[i]}
                    aria-pressed={i === selected}
                    onClick={() => onSelect(i)}
                  >
                    <span className="cname">Case #{i + 1}</span>
                    <span className="ctag">
                      {cases[i]
                        ? i === 0
                          ? "Best evaluated"
                          : i === 1
                            ? "Runner-up"
                            : "Third option"
                        : "Unavailable"}
                    </span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, get]) => (
              <tr key={label}>
                <th className="rowhead" scope="row">
                  {label}
                </th>
                {[0, 1, 2].map((i) => (
                  <td key={i} className={i === selected ? "sel" : ""}>
                    {cases[i] ? get(cases[i]) : "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="table-foot">
        Only distinct ML waveform matches without known physical failures count
        toward convergence. Failed diagnostic cases remain inspectable here and
        in the attempt history. Required crest minimum first, then worst
        normalised deviation S and weighted deviation J. Secondary preferences
        affect ties only. Diagnostic cases have failed, unknown or unverified
        eligibility and are not recommended for physical use.
      </p>
    </section>
  );
}
export function DecisionSummary({
  runId,
  summary,
  onSummary,
  gemini,
  busy,
  pending = false,
  disabled = false,
}) {
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  const generate = async (refresh = false) => {
    if (!runId) return;
    setLoading(true);
    try {
      onSummary(await post(`/v1/runs/${runId}/decision-summary`, { refresh }));
      setError("");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };
  return (
    <section className="card" aria-label="Decision summary">
      <div className="card-head">
        <h2>Decision summary</h2>
        <span className="sub">
          {summary?.status === "generated"
            ? `Gemini · ${summary.model}`
            : summary?.explanation_status === "complete"
              ? "Computed SHAP + recorded physics/ML"
              : "Grounded in backend evidence"}
        </span>
      </div>
      <div className="summary">
        {(pending || loading) && (
          <p className="hint" role="status">
            Computing SHAP contributions and preparing the explanation.
            First-time attributions take longer; subsequent requests reuse
            verified evidence.
          </p>
        )}
        <DecisionExplanation summary={summary} />
        {summary?.reason && (
          <p className="inline-message" role="status">
            {summary.reason}{" "}
            {summary.analysis?.cases?.length
              ? "The computed physics, ML and ranking explanation above remains available."
              : ""}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <button
            className="btn small"
            type="button"
            disabled={!runId || busy || loading || pending || disabled}
            onClick={() => generate(summary?.status === "generated")}
          >
            <Sparkles size={14} />
            {loading || pending
              ? "Preparing explanation…"
              : summary?.status === "generated"
                ? "Regenerate summary"
                : "Generate decision summary"}
          </button>
          <span className="hint">
            {gemini?.configured
              ? `Model: ${gemini.model}`
              : "Set GEMINI_MODEL and GEMINI_API_KEY in backend/.env."}
          </span>
        </div>
        {error && <p className="error-text">{error}</p>}
      </div>
    </section>
  );
}
