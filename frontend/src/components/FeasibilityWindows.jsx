import { number } from "../lib/config.js";
export default function FeasibilityWindows({ windows }) {
  if (!windows) return null;
  return (
    <section className="card" aria-label="Calibration feasibility windows">
      <div className="card-head">
        <h2>Calibration · constraint windows</h2>
        <span className="sub">
          Physical constraints checked after physics + ML
        </span>
      </div>
      <div className="summary">
        <p className="lead">
          {windows.fixed_charge_energy_infeasible
            ? "No stage count can satisfy the energy limits at the supplied fixed charging voltage and stage capacitance."
            : `Energy-compatible stage counts at the supplied fixed charge: ${windows.fixed_charge_energy_feasible_stage_counts.join(", ")}.`}
        </p>
        <p>
          The optimiser can change N, Rf and Rt. Charge and capacitance remain
          your inputs; changing them requires a new calculation. Constraint
          failures do not stop the search: calibration continues until three
          successful setups or the configured search limits.
        </p>
        <table className="score-tbl" aria-label="Necessary energy windows">
          <tbody>
            <tr>
              <th>
                At N = {windows.actual_stage_count}: maximum stage capacitance
              </th>
              <td>
                {number(windows.current_stage_capacitance_upper_F * 1e6, 6)} µF
              </td>
            </tr>
            <tr>
              <th>
                At the supplied capacitance and N: maximum charging voltage
              </th>
              <td>
                {number(windows.current_stage_charge_upper_V / 1000, 6)}{" "}
                kV/stage
              </td>
            </tr>
            <tr>
              <th>
                Maximum expected crest at the available stage maximum, if charge
                is retuned
              </th>
              <td>
                {number(
                  windows.expected_efficiency_crest_upper_at_N_max_V / 1000,
                  3,
                )}{" "}
                kV
              </td>
            </tr>
          </tbody>
        </table>
        <ul className="why">
          {windows.suggestions.map((text, i) => (
            <li key={i}>{text}</li>
          ))}
        </ul>
        <p className="hint">
          These are necessary energy/charging conditions using your expected
          efficiency. They do not guarantee waveform timing, ML agreement,
          inventory availability or hardware approval. Missing rating evidence
          has no invented safe range.
        </p>
      </div>
    </section>
  );
}
