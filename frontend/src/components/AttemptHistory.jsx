import { useState } from "react";
import { number } from "../lib/config.js";
import { Pill } from "./Controls.jsx";

export default function AttemptHistory({ history, error }) {
  const [page, setPage] = useState(0);
  const items = history?.items || [],
    size = 50;
  const pages = Math.max(1, Math.ceil(items.length / size));
  const rows = items.slice(page * size, (page + 1) * size);
  const verdict = (value) => (value == null ? "—" : value ? "Pass" : "Fail");
  return (
    <section className="card" aria-label="All calibration attempts">
      <div className="card-head">
        <h2>All calibration attempts · ML predictions</h2>
        <span className="sub">
          {history
            ? `${history.proposal_count} attempts · ${items.length} evaluation rows`
            : "Awaiting run history"}
        </span>
      </div>
      <p className="table-foot">
        From the first attempt to the last. Repeats remain visible as cached
        predictions; rejected or unsupported attempts have no invented ML
        values. Passing waveform thresholds and hardware eligibility are shown
        separately.
      </p>
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
      <div className="table-wrap">
        <table
          className="cmp attempts-table"
          aria-label="Chronological ML predictions for every attempt"
        >
          <thead>
            <tr>
              {[
                "Attempt",
                "ML call",
                "N",
                "Charge (kV/stage)",
                "Rf required (Ω)",
                "Rt required (Ω)",
                "Rf actual (Ω)",
                "Rt actual (Ω)",
                "ML front/peak (µs)",
                "ML tail (µs)",
                "ML crest (kV)",
                "Front",
                "Tail",
                "Crest",
                "Outcome",
                "Source / support",
                "Hardware",
                "Reason",
              ].map((label) => (
                <th key={label}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((item) => {
              const metrics = item.ml_metrics,
                errors = item.objective?.errors;
              const noML = !metrics;
              const outcome =
                item.attempt_status === "rejected"
                  ? "Rejected"
                  : item.attempt_status === "pending"
                    ? "Pending"
                    : noML
                      ? "ML unavailable"
                      : item.waveform_within_tolerance
                        ? "Thresholds met"
                        : "Outside thresholds";
              const source =
                item.prediction_source === "cached_ml"
                  ? "Cached prediction"
                  : item.prediction_source === "fresh_ml"
                    ? "Fresh ML"
                    : noML
                      ? "Not invoked"
                      : "Recorded ML";
              return (
                <tr
                  key={`${item.attempt_number}-${item.evaluation_in_attempt}-${item.event_sequence}`}
                >
                  <th scope="row">
                    {item.attempt_number}
                    {item.evaluation_in_attempt > 1
                      ? `.${item.evaluation_in_attempt}`
                      : ""}
                  </th>
                  <td>{item.ml_evaluation_number ?? "—"}</td>
                  <td>{item.N ?? item.proposal?.N ?? "—"}</td>
                  <td>
                    {number(
                      item.U_charge_V == null
                        ? undefined
                        : item.U_charge_V / 1000,
                    )}
                  </td>
                  <td>{number(item.proposal?.Rf_required_ohm)}</td>
                  <td>{number(item.proposal?.Rt_required_ohm)}</td>
                  <td>{number(item.Rf_actual_ohm)}</td>
                  <td>{number(item.Rt_actual_ohm)}</td>
                  <td>
                    {number(
                      metrics?.front_s == null
                        ? undefined
                        : metrics.front_s * 1e6,
                      6,
                    )}
                  </td>
                  <td>
                    {number(
                      metrics?.tail_s == null
                        ? undefined
                        : metrics.tail_s * 1e6,
                      6,
                    )}
                  </td>
                  <td>
                    {number(
                      metrics?.crest_V == null
                        ? undefined
                        : metrics.crest_V / 1000,
                      6,
                    )}
                  </td>
                  <td>{verdict(errors?.front?.within_tolerance)}</td>
                  <td>{verdict(errors?.tail?.within_tolerance)}</td>
                  <td>{verdict(errors?.crest?.within_tolerance)}</td>
                  <td>
                    <Pill
                      status={
                        item.waveform_within_tolerance
                          ? "good"
                          : noML
                            ? "neutral"
                            : "bad"
                      }
                    >
                      {outcome}
                    </Pill>
                  </td>
                  <td>
                    {source}
                    {item.correction_status === "predicted_extrapolation"
                      ? " · Extrapolated"
                      : ""}
                  </td>
                  <td>
                    {item.hardware_feasible == null
                      ? "Unknown"
                      : item.hardware_feasible
                        ? "Pass"
                        : "Failed / unknown checks"}
                  </td>
                  <td>
                    {[
                      ...(item.reason_codes || []),
                      ...(item.failed_hardware_constraints || []),
                      ...(errors?.crest?.reason_code
                        ? [errors.crest.reason_code]
                        : []),
                    ].join(", ") || "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {history && !items.length && (
        <p className="table-foot">No optimisation attempts were recorded.</p>
      )}
      {pages > 1 && (
        <div className="actions mt-3" aria-label="Attempt history pages">
          <button
            className="btn small"
            disabled={page === 0}
            onClick={() => setPage(0)}
          >
            First
          </button>
          <button
            className="btn small"
            disabled={page === 0}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </button>
          <span>
            Page {page + 1} of {pages} · rows {page * size + 1}–
            {Math.min((page + 1) * size, items.length)}
          </span>
          <button
            className="btn small"
            disabled={page === pages - 1}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
          <button
            className="btn small"
            disabled={page === pages - 1}
            onClick={() => setPage(pages - 1)}
          >
            Last
          </button>
        </div>
      )}
    </section>
  );
}
