import { useState } from "react";
import { number } from "../lib/config.js";

const value = (v, scale = 1) => (v == null ? "—" : number(v * scale, 6));
const signed = (v) =>
  v == null
    ? "—"
    : `${v > 0 ? "+" : ""}${Math.abs(v) > 0 && Math.abs(v) < 1e-6 ? v.toExponential(3) : number(v, 6)}`;

function OutputExplanation({ output }) {
  const s = output.display_scale,
    unit = output.display_unit;
  const top = output.top_contributions || [];
  const maximum = Math.max(
    ...top.map((f) => Math.abs(f.display_contribution)),
    1e-30,
  );
  return (
    <article
      className="ml-explanation"
      aria-label={`${output.label} ML explanation`}
    >
      <h4>{output.label}</h4>
      <div className="table-wrap">
        <table
          className="score-tbl"
          aria-label={`${output.label} physics and ML values`}
        >
          <thead>
            <tr>
              <th>Physics baseline</th>
              <th>ML correction</th>
              <th>ML prediction</th>
              <th>Target</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                {value(output.physics_value, s)} {unit}
              </td>
              <td>
                {signed(
                  output.ml_residual == null ? null : output.ml_residual * s,
                )}{" "}
                {unit}
              </td>
              <td>
                {value(output.corrected_value, s)} {unit}
              </td>
              <td>
                {value(output.target_value, s)} {unit}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>{output.explanation}</p>
      {output.shap_status === "complete" ? (
        <>
          <p>{output.shap_explanation}</p>
          <div className="shap-equation">
            Background residual {signed(output.reference_residual * s)} {unit}
            <span>
              {" "}
              + feature contributions {signed(
                output.sum_contributions * s,
              )}{" "}
              {unit}
            </span>
            <strong>
              {" "}
              = ML correction {signed(output.ml_residual * s)} {unit}
            </strong>
          </div>
          <ul
            className="shap-drivers"
            aria-label={`${output.label} strongest SHAP contributions`}
          >
            {top.slice(0, 3).map((f) => (
              <li key={f.feature}>
                <span>
                  {f.label}{" "}
                  <small>
                    ({number(f.display_input_value, 6)} {f.input_unit})
                  </small>
                </span>
                <span className="shap-impact">
                  <i
                    className={f.contribution >= 0 ? "raises" : "lowers"}
                    style={{
                      width: `${(Math.abs(f.display_contribution) / maximum) * 100}%`,
                    }}
                  />
                </span>
                <b>
                  {signed(f.display_contribution)} {unit}
                </b>
              </li>
            ))}
          </ul>
          <details className="explanation-detail">
            <summary>All SHAP contributions and calculation evidence</summary>
            <p>{output.reference_meaning}</p>
            <p>
              {output.method} · {output.nsamples} sampled coalitions ·{" "}
              {output.background_count ?? "unrecorded"} training-background rows
              · additivity{" "}
              {output.additivity_verified
                ? "verified against this saved ML prediction"
                : "not verified"}
              .
            </p>
            <p>
              Reconstruction error: {signed(output.additivity_error * s)} {unit}
              . Contributions are approximate model attributions.
            </p>
            <div className="table-wrap">
              <table
                className="score-tbl"
                aria-label={`${output.label} all SHAP contributions`}
              >
                <thead>
                  <tr>
                    <th>Feature</th>
                    <th>Input</th>
                    <th>Effect on residual ({unit})</th>
                  </tr>
                </thead>
                <tbody>
                  {output.contributions.map((f) => (
                    <tr key={f.feature}>
                      <th>{f.label}</th>
                      <td>
                        {number(f.display_input_value, 6)} {f.input_unit}
                      </td>
                      <td>
                        {signed(f.display_contribution)} · {f.direction}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : (
        <p className="inline-message">
          SHAP attribution unavailable:{" "}
          {output.shap_reason || "no verified attribution was recorded"}. The
          saved baseline and ML values above remain available.
        </p>
      )}
    </article>
  );
}

export default function DecisionExplanation({ summary }) {
  const [selected, setSelected] = useState(0);
  const analysis = summary?.analysis;
  const cases = analysis?.cases || [];
  const current = cases[selected] || cases[0];
  const generated = summary?.status === "generated";
  const mlNarrative = summary?.narrative?.ml_explanations?.find(
    (item) => item.candidate_id === current?.candidate_id,
  );
  if (!analysis)
    return (
      <p className="lead">
        {summary?.narrative?.lead ||
          "Calculate a scenario to explain its physics baseline, ML corrections and best-case selection."}
      </p>
    );
  return (
    <div className="decision-explanation">
      <section className="rep-sec" aria-label="Why Case 1 ranks first">
        <h3>Why Case #1 ranks first</h3>
        <p className="lead">{analysis.selection_explanation}</p>
        {generated && summary.narrative.why_first_ranked && (
          <p>{summary.narrative.why_first_ranked}</p>
        )}
        <ul className="why">
          {analysis.comparison.map((r) => (
            <li key={r.candidate_id}>{r.reason}</li>
          ))}
        </ul>
        {cases.length > 0 && (
          <p className="hint">
            This is the best of the evaluated passing setups, not a proven
            global optimum. Resistor and stage counts decide exact objective
            ties only.
          </p>
        )}
      </section>
      <section className="rep-sec">
        <h3>How the search reached these setups</h3>
        <p>{analysis.search_explanation}</p>
      </section>
      {current && (
        <>
          <div
            className="actions explanation-cases"
            aria-label="Choose a case to explain"
          >
            {cases.map((c, i) => (
              <button
                className={`btn small ${i === selected ? "explanation-selected" : ""}`}
                key={c.candidate_id}
                aria-pressed={i === selected}
                onClick={() => setSelected(i)}
              >
                Explain Case #{c.case_number}
              </button>
            ))}
          </div>
          <section
            className="rep-sec"
            aria-label={`Case ${current.case_number} physics explanation`}
          >
            <h3>1. Why the physics baseline has these values</h3>
            <p>{current.physics_explanation}</p>
            {generated && summary.narrative.physics_explanation && (
              <p>{summary.narrative.physics_explanation}</p>
            )}
            <details className="explanation-detail">
              <summary>Effective circuit values and formulas</summary>
              {current.physics_mode === "calculator" && (
                <p className="formula-line">
                  Front = k_front × √[(R_front × C_load)² + k_LC × L × C_load].
                  Tail = k_tail × R_tail × (C_generator + C_load). Crest =
                  expected efficiency × N × charging voltage.
                </p>
              )}
              <div className="table-wrap">
                <table
                  className="score-tbl"
                  aria-label="Effective circuit values"
                >
                  <tbody>
                    {[
                      [
                        "Erected generator capacitance",
                        current.circuit_values.C1_F,
                        1e6,
                        "µF",
                      ],
                      [
                        "Effective load capacitance",
                        current.circuit_values.C2_F,
                        1e12,
                        "pF",
                      ],
                      [
                        "Effective front resistance",
                        current.circuit_values.R1_ohm,
                        1,
                        "Ω",
                      ],
                      [
                        "Effective tail resistance",
                        current.circuit_values.R2_ohm,
                        1,
                        "Ω",
                      ],
                      [
                        "Loop inductance",
                        current.circuit_values.L_effective_H,
                        1e6,
                        "µH",
                      ],
                      [
                        "Initial erected voltage",
                        current.circuit_values.V0_V,
                        1e-3,
                        "kV",
                      ],
                    ].map(([label, v, scale, unit]) => (
                      <tr key={label}>
                        <th>{label}</th>
                        <td>
                          {value(v, scale)} {unit}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </section>
          <section
            className="rep-sec"
            aria-label={`Case ${current.case_number} SHAP explanation`}
          >
            <h3>2. Why ML adjusted the physics baseline</h3>
            {generated && mlNarrative && (
              <p className="lead">{mlNarrative.explanation}</p>
            )}
            <p>
              The model predicts corrections to the physics estimates. Positive
              SHAP contributions raise the predicted residual; negative
              contributions lower it. They are relative to a training-background
              prediction.
            </p>
            {current.model_status === "predicted_extrapolation" && (
              <p className="inline-message">
                This case is outside part of the training envelope. Its
                prediction and SHAP explanation are extrapolated estimates.
              </p>
            )}
            {current.outputs.map((o) => (
              <OutputExplanation key={o.output_key} output={o} />
            ))}
            <p className="hint">{analysis.interpretation}</p>
            <p className="hint">{analysis.scope}</p>
          </section>
        </>
      )}
      <section
        className="rep-sec"
        aria-label="Hardware evidence and limitations"
      >
        <h3>3. What still prevents hardware approval</h3>
        <p>{analysis.eligibility_note}</p>
        <ul className="attn">
          {analysis.constraints.map((c) => (
            <li key={c.constraint_group}>{c.explanation}</li>
          ))}
        </ul>
        <details className="explanation-detail">
          <summary>Detailed constraint evidence</summary>
          <pre>{JSON.stringify(analysis.constraints, null, 2)}</pre>
        </details>
      </section>
      {summary.status === "generated" && (
        <details className="explanation-detail">
          <summary>Additional Gemini overview</summary>
          <p>{summary.narrative.lead}</p>
          <ul className="why">
            {summary.narrative.why_others_rank_lower.map((r) => (
              <li key={r.candidate_id}>{r.reason}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
