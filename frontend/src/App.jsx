import FeasibilityWindows from "./components/FeasibilityWindows.jsx";
import { useEffect, useRef, useState } from "react";
import { Download, Info, RefreshCw, X } from "lucide-react";
import Configuration from "./components/Configuration.jsx";
import Networks from "./components/Networks.jsx";
import Waveform from "./components/Waveform.jsx";
import AttemptHistory from "./components/AttemptHistory.jsx";
import FailureWaveformDemo from "./components/FailureWaveformDemo.jsx";
import {
  SettingsPanel,
  PerformanceMetrics,
  PhysicsBaseline,
  Comparison,
  DecisionSummary,
} from "./components/Results.jsx";
import { api, post, sleep, allAttempts } from "./lib/api.js";
import {
  initialForm,
  toRequest,
  number,
  withSearchDefaults,
} from "./lib/config.js";

export default function App() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [form, setForm] = useState(initialForm),
    [inventory, setInventory] = useState({ front: [], tail: [] });
  const [bootstrap, setBootstrap] = useState(null),
    [dashboard, setDashboard] = useState(null),
    [workbookBaseline, setWorkbookBaseline] = useState(null),
    [baselineError, setBaselineError] = useState(""),
    [targetPlot, setTargetPlot] = useState(null);
  const [selected, setSelected] = useState(0),
    [busy, setBusy] = useState(false),
    [dirty, setDirty] = useState(false),
    [error, setError] = useState("");
  const [attempts, setAttempts] = useState(null),
    [historyError, setHistoryError] = useState("");
  const [summaryPending, setSummaryPending] = useState(false);
  const [status, setStatus] = useState("Connecting to backend…"),
    [runId, setRunId] = useState(null),
    [summary, setSummary] = useState(null),
    [exportOpen, setExportOpen] = useState(false);
  const active = useRef(null),
    latest = useRef("");
  latest.current = JSON.stringify({ form, inventory });
  useEffect(() => {
    const controller = new AbortController();
    api("/v1/dashboard/bootstrap", { signal: controller.signal })
      .then((data) => {
        setForm((previous) =>
          withSearchDefaults(previous, data.defaults.search),
        );
        setBootstrap(data);
        setInventory({
          front: data.inventory.front,
          tail: data.inventory.tail,
        });
        setStatus("Ready · backend connected");
        setError("");
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setError(e.message);
          setStatus("Backend unavailable");
        }
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!bootstrap || dashboard) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      try {
        post(
          "/v1/waveforms/reconstruct",
          { request: toRequest(form, inventory), candidate_metrics: [] },
          { signal: controller.signal },
        )
          .then(setTargetPlot)
          .catch(() => {});
      } catch {
        /* Keep the last valid target plot while a field is being edited. */
      }
    }, 300);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [form, inventory, bootstrap, dashboard]);
  useEffect(() => () => active.current?.abort(), []);
  const change = (key, value) => {
    setDirty(true);
    setForm((prev) => {
      let next = { ...prev, [key]: value };
      if (key === "profile" && value !== "custom")
        next = {
          ...next,
          nMax: 15,
          uMax: 200,
          cStage: value === "haefely" ? 0.125 : 3,
          cBo: 0,
          includeCbo: false,
          mode: value === "workbook" ? "calculator" : next.mode,
        };
      if (["nMax", "uMax", "cStage", "cBo", "includeCbo"].includes(key))
        next.profile = "custom";
      if (["tFront", "tTail", "tolCrest", "tolFront", "tolTail"].includes(key))
        next.tolProfile = "custom";
      if (key === "impulse") {
        const test = bootstrap.tests[value];
        next = {
          ...next,
          vTest: value === "Lightning" ? 1425 : 1050,
          tFront: test.front_s * 1e6,
          tTail: test.tail_s * 1e6,
          tolFront: test.tolerances.front * 100,
          tolTail: test.tolerances.tail * 100,
          tolCrest: test.tolerances.crest * 100,
          tolProfile: "project",
        };
      }
      if (key === "tolProfile" && value !== "custom") {
        const test = bootstrap.tests[prev.impulse];
        next = {
          ...next,
          tolFront: test.tolerances.front * 100,
          tolTail:
            value === "workbook" && prev.impulse === "Switching"
              ? 60
              : test.tolerances.tail * 100,
          tolCrest: test.tolerances.crest * 100,
        };
      }
      return next;
    });
  };
  const calculate = async () => {
    if (busy) return;
    let request;
    try {
      request = toRequest(form, inventory);
    } catch (e) {
      setError(e.message);
      return;
    }
    const submitted = latest.current;
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setError("");
    setSummary(null);
    setAttempts(null);
    setHistoryError("");
    setWorkbookBaseline(null);
    setBaselineError("");
    setStatus("Validating inputs…");
    try {
      if (request.load.model_id === "capacitive_v1") {
        setStatus("Calculating the workbook baseline…");
        try {
          setWorkbookBaseline(
            await post(
              "/v1/dashboard/workbook-baseline",
              { request },
              { signal: controller.signal },
            ),
          );
        } catch (e) {
          if (e.name === "AbortError") throw e;
          setBaselineError(`Workbook baseline unavailable: ${e.message}`);
        }
      }
      const created = await post("/v1/runs", request, {
        signal: controller.signal,
      });
      setRunId(created.run_id);
      let state;
      do {
        state = await api(`/v1/runs/${created.run_id}`, {
          signal: controller.signal,
        });
        setStatus(
          `${state.status} · ${state.returned_successful_predictions ?? 0}/3 successful setups · ${state.counters?.proposals ?? 0} proposals · ${number(state.elapsed_seconds ?? 0, 1)} s`,
        );
        if (["queued", "running"].includes(state.status))
          await sleep(600, controller.signal);
      } while (["queued", "running"].includes(state.status));
      if (state.status === "failed")
        throw new Error(
          state.error?.message ||
            "Calculation failed; inspect backend run history.",
        );
      let data = await api(`/v1/runs/${created.run_id}/dashboard`, {
        signal: controller.signal,
      });
      // Diagnostic inspection is separate from recommendation eligibility and never overrides it.
      if (
        data.display_mode === "diagnostic_evaluated_cases" &&
        request.physics_mode === "calculator"
      ) {
        setStatus("Inspecting residual correction support…");
        for (const record of data.cases) {
          if (record.correction?.status === "not_invoked")
            await post(
              `/v1/candidates/${record.candidate_id}/diagnostic-evaluation`,
              {},
              { signal: controller.signal },
            );
        }
        data = await api(`/v1/runs/${created.run_id}/dashboard`, {
          signal: controller.signal,
        });
      }
      setDashboard(data);
      try {
        setAttempts(
          await allAttempts(created.run_id, { signal: controller.signal }),
        );
      } catch (e) {
        if (e.name === "AbortError") throw e;
        setHistoryError(`Attempt history unavailable: ${e.message}`);
      }
      setSelected(0);
      setDirty(latest.current !== submitted);
      setStatus(
        `Calculated in ${number(data.run.performance?.elapsed_seconds ?? data.run.elapsed_seconds, 2)} s · ${data.run.returned_successful_predictions ?? 0}/3 ML setups without known constraint failures · ${data.run.ml_converged ? "All three meet waveform thresholds and known constraints" : `stopped: ${data.run.stop_reason}`}`,
      );
      try {
        setSummaryPending(true);
        setSummary(
          await post(
            `/v1/runs/${created.run_id}/decision-summary`,
            {},
            { signal: controller.signal },
          ),
        );
      } catch (e) {
        if (e.name !== "AbortError")
          setError(`Results ready. Decision summary: ${e.message}`);
      } finally {
        setSummaryPending(false);
      }
    } catch (e) {
      if (e.name !== "AbortError") {
        setError(e.message);
        setStatus("Calculation could not complete");
      }
    } finally {
      setBusy(false);
      active.current = null;
    }
  };
  const cancel = async () => {
    try {
      if (runId) {
        await post(`/v1/runs/${runId}/cancel`);
        setStatus("Stopping at the next iteration boundary…");
      }
    } catch (e) {
      setError(e.message);
    }
  };
  const cases = dashboard?.cases || [],
    record = cases[selected];
  const plot = dashboard?.waveforms || targetPlot;
  const curve = record
    ? plot?.curves?.find((c) => c.candidate_id === record.candidate_id)
    : null;
  const exported = {
    schema_version: "1.0",
    request: dashboard?.context?.request || null,
    result: dashboard,
    workbook_baseline: workbookBaseline,
    decision_summary: summary,
    attempt_history: attempts,
  };
  const reportPreview = {
    request: exported.request,
    run_id: runId,
    display_mode: dashboard?.display_mode,
    workbook_baseline: workbookBaseline && {
      status: workbookBaseline.status,
      settings: workbookBaseline.settings,
      physics_metrics: workbookBaseline.record.physics.metrics,
      corrected_metrics: workbookBaseline.record.correction?.corrected_metrics,
    },
    cases: cases.map((r) => ({
      candidate_id: r.candidate_id,
      N: r.candidate.N,
      U_charge_V: r.candidate.U_charge_V,
      Rf_actual_ohm: r.candidate.front.equivalent_ohm,
      Rt_actual_ohm: r.candidate.tail.equivalent_ohm,
      physics_metrics: r.physics.metrics,
      corrected_metrics: r.correction?.corrected_metrics,
      eligible: r.eligible,
    })),
    decision_summary: summary,
  };
  const download = () => {
    const blob = new Blob([JSON.stringify(exported, null, 2)], {
        type: "application/json",
      }),
      url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = `powernext-${runId || "configuration"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="page">
      <header className="appbar">
        <div>
          <h1>Impulse Physics Engine</h1>
          <p>
            Configure impulse tests, compare settings, and inspect predicted
            waveforms.
          </p>
        </div>
        <div className="actions">
          <span className="badge">
            <Info size={15} />
            {activeTab === "demo"
              ? "Synthetic demonstration"
              : "Model output · not lab-validated"}
          </span>
          <button
            className="btn"
            type="button"
            hidden={activeTab === "demo"}
            onClick={() => setExportOpen(true)}
          >
            <Download size={16} />
            Export report
          </button>
        </div>
      </header>
      <nav className="workspace-tabs" role="tablist" aria-label="Workspace">
        {[
          ["dashboard", "Configuration & calibration"],
          ["demo", "Transformer test demo"],
        ].map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`tab-${id}`}
            aria-selected={activeTab === id}
            aria-controls={`panel-${id}`}
            tabIndex={activeTab === id ? 0 : -1}
            onClick={() => setActiveTab(id)}
            onKeyDown={(event) => {
              if (
                ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)
              ) {
                event.preventDefault();
                const next =
                  event.key === "Home"
                    ? "dashboard"
                    : event.key === "End"
                      ? "demo"
                      : id === "dashboard"
                        ? "demo"
                        : "dashboard";
                setActiveTab(next);
                document.getElementById(`tab-${next}`).focus();
              }
            }}
          >
            {label}
          </button>
        ))}
      </nav>
      <div
        role="tabpanel"
        id="panel-dashboard"
        aria-labelledby="tab-dashboard"
        hidden={activeTab !== "dashboard"}
      >
        <div className="layout">
          <Configuration
            form={form}
            change={change}
            inventory={inventory}
            setInventory={(value) => {
              setInventory(value);
              setDirty(true);
            }}
            busy={busy}
            onCalculate={calculate}
            onCancel={cancel}
            status={status}
            bootstrap={bootstrap}
          />
          <main className={`results ${busy ? "busy" : ""}`}>
            {error && (
              <div className="banner error" role="alert">
                <span>{error}</span>
                {!bootstrap && (
                  <button
                    type="button"
                    className="btn small"
                    onClick={() => window.location.reload()}
                  >
                    <RefreshCw size={14} />
                    Reconnect
                  </button>
                )}
              </div>
            )}
            {dirty && dashboard && (
              <div className="banner stale">
                <span>
                  Inputs have changed. These results belong to the previous
                  scenario.
                </span>
                <button
                  type="button"
                  className="btn small"
                  disabled={busy}
                  onClick={calculate}
                >
                  Recalculate
                </button>
              </div>
            )}
            {dashboard?.display_mode === "diagnostic_evaluated_cases" && (
              <div className="banner info">
                <span>
                  <strong>No verified recommendation.</strong> Showing the best
                  evaluated diagnostic cases with their failed or unknown
                  checks. {dashboard.run.returned_recommendations ?? 0} of 3
                  eligible recommendations returned.{" "}
                  {dashboard.run.ml_converged
                    ? "Three ML-predicted setups meet waveform tolerances and have no known constraint failures."
                    : "ML calibration has not reached three matching setups."}
                </span>
              </div>
            )}
            {baselineError && (
              <div className="banner error" role="alert">
                {baselineError}
              </div>
            )}
            {workbookBaseline && (
              <PhysicsBaseline
                record={workbookBaseline.record}
                settings={workbookBaseline.settings}
                title="Workbook baseline · before optimisation"
                referenceStatus={workbookBaseline.status}
              />
            )}
            <SettingsPanel
              cases={cases}
              selected={selected}
              onSelect={setSelected}
              context={dashboard?.context}
              mode={dashboard?.display_mode}
            />
            <Comparison
              cases={cases}
              selected={selected}
              onSelect={setSelected}
              mode={dashboard?.display_mode}
            />
            <Networks
              key={record?.candidate_id || "empty"}
              record={record}
              rank={selected + 1}
              inventory={dashboard?.context?.inventory || inventory}
            />
            <div className="wave-row">
              <Waveform
                key={`${runId || "initial"}-${selected}`}
                bundle={plot}
                selectedId={record?.candidate_id}
                rank={selected + 1}
              />
              <PerformanceMetrics
                key={record?.candidate_id || "empty"}
                record={record}
                curve={curve}
                context={dashboard?.context}
              />
            </div>
            <PhysicsBaseline record={record} />
            <AttemptHistory
              key={`attempts-${runId || "empty"}`}
              history={attempts}
              error={historyError}
            />
            <FeasibilityWindows windows={dashboard?.run?.feasibility_windows} />
            <DecisionSummary
              runId={runId}
              summary={summary}
              onSummary={setSummary}
              gemini={bootstrap?.gemini}
              busy={busy}
              pending={summaryPending}
              disabled={dirty}
            />
            {dashboard && (
              <details className="card">
                <summary className="cursor-pointer font-semibold">
                  Run performance and input provenance
                </summary>
                <div className="trace-detail">
                  <pre>
                    {JSON.stringify(
                      {
                        run: dashboard.run.performance,
                        source_precedence: dashboard.context.source_precedence,
                        value_sources: dashboard.context.value_sources,
                        input_sources: dashboard.context.input_sources,
                        target_sources: dashboard.context.target_sources,
                        rejections: dashboard.run.rejections,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </div>
              </details>
            )}
          </main>
        </div>
      </div>
      <div
        role="tabpanel"
        id="panel-demo"
        aria-labelledby="tab-demo"
        hidden={activeTab !== "demo"}
      >
        <FailureWaveformDemo />
      </div>
      {exportOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setExportOpen(false)}
        >
          <section
            className="panel w-full max-w-3xl"
            role="dialog"
            aria-modal="true"
            aria-label="Export report"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="dlg-head">
              <h2>Export report</h2>
              <button
                type="button"
                className="iconbtn"
                aria-label="Close report"
                onClick={() => setExportOpen(false)}
              >
                <X size={16} />
              </button>
            </div>
            <textarea
              className="block w-full h-[50vh] p-4 font-mono text-xs bg-stone-50"
              readOnly
              aria-label="Report preview"
              value={JSON.stringify(reportPreview, null, 2)}
            />
            <div className="dlg-foot">
              <span className="hint">
                Preview shown here. Download includes full wiring, constraints,
                waveform samples and provenance.
              </span>
              <button type="button" className="btn primary" onClick={download}>
                <Download size={14} />
                Download JSON
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
