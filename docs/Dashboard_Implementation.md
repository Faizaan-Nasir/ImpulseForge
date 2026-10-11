# React dashboard and Gemini Decision Summary

11 October 2026. Implemented in `frontend/` against the existing Python backend. Design reference: [Impulse Physics Engine artifact](https://claude.ai/artifact/UbRz4HMvFDn8LUzFdiKqJo). Static source snapshots in `reference/` preserve the supplied visual reference; original runtime/physics scripts are not executed in the React application.

## Stack and delivered sections

| Section | Implementation | Libraries / deliverables |
| --- | --- | --- |
| Dashboard shell and forms | `frontend/src/App.jsx`, `components/Configuration.jsx`, `Controls.jsx` | React 19, Vite 7, Tailwind CSS 4, Lucide; responsive artifact-derived styling, SI conversion, input validation and stale-result status |
| Exact resistor schematic | `components/Networks.jsx` | Recursive SVG layout for arbitrary nested series/parallel recipes, quantities, netlists and stage/component identities |
| Target/candidate waveform plot | `components/Waveform.jsx` | Backend numeric curves, case selection/overlay, full/front detail, zoom, drag range, hover values and landmarks |
| Metrics/comparison/export | `components/Results.jsx`, `App.jsx` | Candidate metrics, synthetic validation metrics, processing times, constraints, optional SHAP request and complete JSON export |
| API binding | `src/lib/api.js`, `config.js`, `vite.config.js` | Fetch with error/abort handling, job polling/cancellation, Vite same-origin API proxy, browser-safe optional API base |
| Dashboard backend | `backend/src/powernext/dashboard/view.py`, API routes | Persisted candidate aggregation, diagnostic/eligible separation, per-curve reconstructed RMS comparison, bootstrap/catalogues |
| Decision summary | `backend/src/powernext/dashboard/summary.py` | `google-genai` 2.29.0, Pydantic structured outputs, backend evidence, cached generated narratives, unavailable/error fallback |
| Environment/runtime | `.env.example` files, root `scripts/dev.mjs` | Configurable Gemini model/key, local CORS, root `npm run dev` starts both services, process cleanup |
| Verification | `frontend/tests/`, `backend/tests/test_dashboard.py` | Vitest 4, Testing Library, pytest/httpx, production build, package audit, actual browser/backend flow |

Resolved versions are pinned by `frontend/package-lock.json` and `backend/uv.lock`. Use `npm ci` and `uv sync --locked`. No hosted deployment is configured for this local Python/React application.

## Reference reconciliation

The presentation retains the warm-stone instrument-panel style, fonts, teal selection controls, section structure, schematics and waveform graticule. It replaces illustrative numbers with actual backend outcomes and keeps prior user decisions authoritative:

- All eleven workbook input fields are available, including maximum system voltage. Inventory is editable; front/tail limits remain independent. Add/remove/edit arbitrary inventory types.
- Available stages default to 15 and remain frontend input. The fallback preset does not restore the excluded 12-stage value or 545 pF loading. Stage capacitance input wins over fallback.
- Stage energy is an editable positive input (`equipment_inputs.stage_energy_max_J`, displayed in kJ); omission/null uses 2500 J. Total energy is supplied through `equipment_inputs.total_energy_max_J` with 30000 J fallback. Basic capacitance is optional explicit `setup.basic_C_F`; included only under the selected inclusion policy. No excluded PDF value is silently imported.
- Timing targets and front/tail/crest tolerances are optional new `target` fields and otherwise retain profile defaults. Exact mode uses the established project/legacy conventions without claiming standards certification.
- Ranking priority is a **secondary tie preference**, exposed as `objective.secondary_preference`: balanced/accuracy/resistors/stages/voltage. S and J remain primary. No KNN or learnt ranking is introduced; no additive part/stage penalties replace the objective.
- Current equipment/model evidence can yield zero eligible recommendations. The dashboard then displays up to three evaluated **diagnostic cases**, not three manufactured recommendations. A baseline and residual-corrected prediction are clearly distinguished; only actual ML-corrected candidates enter the calibration comparison. Missing ML support and overshoot certification are explicit.
- Curve comparison RMS measures difference between reconstructed curves on the backend common grid, relative to target crest. It is not measured model accuracy or a new waveform constraint. All source samples remain available through the API/export.

## Reproducing a recorded physics setup

The scenario form starts a design search. Supplying only a dataset row's test inputs does not fix its actual resistor networks or stage count. The new **Physics baseline and ML correction** panel shows the evaluated stage count, charging voltage, actual front/tail equivalents and three baseline outputs separately from residual-corrected outputs, with nine decimal places in display units. Expected efficiency accepts arbitrary decimal precision; its previous 0.01 step caused Firefox to reject dataset values.

Verified in Firefox with the user-supplied first Lightning training row: target 1404.498256 kV, load 796.907347 pF, divider 383.9852149 pF, stray capacitance 163.876987 pF, loop inductance 21.27743093 µH, efficiency 0.837453939, stage capacitance 3 µF and basic capacitance 0 pF. Select **Calculator** and **Single resistor**. Make only a 55 Ω front type and 25 Ω tail type available (four copies each per stage; set other quantities to zero), and set **Maximum iterations = 1**. Keep maximum stage count 15 and maximum charging voltage 200 kV. This evaluates the initial supported-inventory setup at N = 9, rather than continuing an optimisation search.

The resulting physics baseline is front 1.198028683 µs, tail 52.184683192 µs and crest 1404.498256000 kV. The charging policy derives 186.345008973 kV/stage from the rounded target/efficiency inputs, compared with 186.3450091 in the pasted row. The tiny differences reflect source rounding. Exact replay at full source precision uses the module API with fixed charging voltage and an explicit proposal.

The displayed diagnostic ML values for this run were front 1.189383868 µs, tail 51.856917396 µs and crest 1410.312045888 kV. They are model estimates, not copies of the row's synthetic Observed labels. Diagnostic correction does not waive stored-energy checks or create an eligible physical recommendation. Firefox evidence is saved in `verification/firefox-physics-row-1.jpg` and `verification/firefox-physics-row-1.json`.

## Backend routes and frontend use

| Route | Dashboard use |
| --- | --- |
| `POST /v1/dashboard/workbook-baseline` | Independent input-driven worksheet baseline, exact single-resistor inventory verdict, diagnostic residual correction and unchanged energy constraints |
| `GET /v1/dashboard/bootstrap` | Inventory, equipment/test presets, defaults, capability scope and Gemini configured flag/model name; never the API key |
| `POST /v1/runs` | Start actual optimisation with current inputs/inventory |
| `GET /v1/runs/{id}` | Poll status, counters and run time |
| `POST /v1/runs/{id}/cancel` | Stop at backend iteration boundary |
| `GET /v1/runs` | Lightweight durable history list (available for later navigation) |
| `GET /v1/runs/{id}/dashboard` | Resolved context, up to three eligible or diagnostic cases, waveform samples and compact summary evidence |
| `GET /v1/runs/{id}/attempts?offset=0&limit=1000` | Every proposal and ML prediction in chronological order, including cached repeats, pair retries and rejected/unsupported attempts |
| `POST /v1/candidates/{id}/diagnostic-evaluation` | Optional direct residual inspection using stored physics; stores separate diagnostic record, never modifies production eligibility/archive |
| `POST /v1/runs/{id}/decision-summary` | `{refresh:false}` caches a valid generated explanation; `{refresh:true}` requests regeneration |
| `POST /v1/waveforms/reconstruct` | Target-only reference before a calculation |
| `GET /v1/candidates/{id}/generator-stages` | Complete physical stage manifest, exact wiring and resistor stress data |
| `GET /v1/candidates/{id}/explanations` | Optional residual attribution details; no invented heat/environmental explanations |
| Existing performance endpoints | Saved performance fields are embedded in dashboard case/run responses; independently callable endpoints remain available |

Dashboard defaults and the Workbook generator preset now use Calculator mode to reproduce the primary workbook. Exact remains an explicit option. The existing residual models support the recorded workbook Calculator baseline and limited feature envelope. Selecting Calculator enables diagnostic support checks; many arbitrary assemblies can still be unsupported, especially Lightning tail values outside the constant training value. The dashboard reports this rather than replacing it with a fabricated ML result. Calibrated cases are ordered only by their ML-corrected waveform objectives. Physics-only evaluations stay in raw history and do not become calibrated cases. Numeric out-of-range diagnostic estimates can be enabled explicitly and are marked extrapolated; incompatible model/baseline combinations remain unavailable. The current synthetic dataset contains no environmental measurements.

## Gemini environment and evidence

Set only on the backend:

```dotenv
GEMINI_MODEL=gemini-flash-latest
GEMINI_API_KEY=
POWERNEXT_GEMINI_TIMEOUT_SECONDS=30
```

Copy `backend/.env.example` to ignored `backend/.env`, supply the key/model, and restart the backend. `GEMINI_MODEL` is editable; the example default is the documented model alias, not a promise of an immutable checkpoint. Keep a stable model ID when reproducible provider behaviour is required. Frontend environment values only identify the API server/proxy. Credentials never appear in bootstrap, summaries, exports, prompts or client bundles.

The server reads persisted run/candidate evidence directly, using the same data services as existing metrics/stage APIs. It sends Gemini targets/tolerances, actual N/charge/resistances/counts, S/J and deviations, constraint verdicts, model-support provenance and recommendation shortfall. It omits large traces, raw files, credentials and unneeded request metadata. JSON identifiers are treated as evidence, never instructions. Gemini is explicitly instructed not to change scores, approve hardware, invent environmental causality or assert measured/standards accuracy.

`DecisionSummary` contains `status`, provider/model, backend-chosen `recommended_candidate_id` (null for diagnostic mode), narrative, authoritative score rows, evidence/model hash, cached flag, generation duration and reason. Narrative fields are `lead`, candidate explanations with validated IDs/references, `needs_attention` and evidence references. Pydantic validates the response schema and the backend rejects invented case/evidence IDs. Recommendation selection stays outside the generated narrative. Narrative text remains generated explanation, not a numerical proof; recorded data is authoritative.

Only successful generated summaries are cached, keyed by evidence, model and prompt version. Missing key produces `unavailable`; expected provider/transport failure produces `provider_error`; malformed response/reference produces `invalid_response`. These outcomes retain the full computed physics/ML/SHAP explanation and ranking comparison; no Gemini narration is invented. Raw provider exception text is suppressed because it can contain request details or credentials. Live Gemini generation was verified for all three cases on 2026-10-11. Small live probes also returned HTTP 429; this is an intermittent provider quota/rate-limit failure. Mocked provider tests cover safe error messages and retention of the computed explanation.

Google SDK/structured output choices follow the [official Python GenAI SDK](https://github.com/googleapis/python-genai) and [Gemini structured-output documentation](https://ai.google.dev/gemini-api/docs/generate-content/structured-output?hl=en).

## Independent execution and acceptance

Run from the repository root with `npm run dev` after installing the locked Python/frontend environments. The launcher waits for backend health before starting Vite. Frontend: `http://127.0.0.1:5173`; backend: `http://127.0.0.1:8000`. See `../frontend/README.md` for separate processes and environment setup.

The React components accept record fixtures and callbacks, so they can be developed without a running physics/ML/optimisation engine. The summary service accepts compact evidence and a mocked provider, independently of real computation or credentials. Backend view tests use persisted fixtures. Tests cover unit conversion, input validation, arbitrary nested wiring, missing recommendations, independent inventory, editable targets/basic loading, CORS, credential omission, diagnostic separation, ties after S/J, provider output validation, caching and failure redaction.

Acceptance also requires production frontend build, full backend suite with real local model tests, lint/type checks, package audit and browser verification of the real calculation flow, case selection, plot modes, inventory interaction, metrics/summary states and report export. Generated contracts/evidence are refreshed under `docs/api` and `docs/verification`. Physical equipment and model validation limitations remain unchanged.


Default reconciliation: the dashboard displays a separate workbook baseline before search results, without requiring the user to edit inventory or reduce iterations. The current default inventory contains the 50 ohm and 25 ohm single resistors needed by this reference. Arbitrary edited inventories are still primary; missing reference resistors result in a mathematical-reference-only verdict. Worker runs invoke correction after every completed forward prediction and report only ML-derived waveform objectives, while recommendation eligibility and the resolved stage-energy input and resolved total-energy input (30000 J fallback) remain enforced.


ML-loop correction: defaults enable explicitly marked diagnostic extrapolation so the optimiser can vary realised resistances beyond the narrow workbook envelope. Strict policy is selectable. The three displayed calibration cases must all have corrected metrics; no physics-only fallback is scored or displayed as a calibrated alternative. Run status reports ML target convergence independently of hardware recommendation eligibility. New counters distinguish successful physics predictions, correction calls and actual ML predictions. A compatible ML artifact is required, and environmental effects remain explicitly not modelled until training data supports them.

Crest acceptance now uses `crest_no_shortfall_v1`: zero shortfall is allowed. The crest tolerance input controls the upper allowance only; the result card shows `Calibrate` below the requested voltage. Calibration cannot converge until all three selected ML predictions meet the minimum crest and all waveform bands. Start a fresh calculation to apply the policy to previously saved results.

Search time budget default is 600 seconds (10 minutes). The dashboard retains a separate default Maximum iterations of 24, setting proposal/physics/ML count caps together. A longer time budget does not raise this count. Stop earlier for three accepted ML predictions, repeated/stagnant search, cancellation or other applicable limits. Saved historical runs retain their submitted budgets.

Budget values now come from backend `.env`: `POWERNEXT_CALIBRATION_WALL_TIME_SECONDS` (fallback 600) and `POWERNEXT_CALIBRATION_MAX_ATTEMPTS` (fallback 24). Bootstrap returns `defaults.search`; App initialises budget fields from it instead of frontend numeric constants. Edits remain explicit per-run overrides. Restart the backend and refresh the dashboard after changing environment defaults.

## Three successful configurations and all attempts

The comparison table now appears directly below Recommended settings and before the wiring diagrams. Only distinct ML predictions passing every waveform threshold fill its three columns. One successful setup keeps calibration running; cached repeats do not count as alternatives. Failed predictions stay in search history. The existing budgets still apply; fewer than three matches produce an explicit shortfall rather than filled slots with failed cases. Hardware eligibility remains separate from successful diagnostic waveform matching.

The separate **All calibration attempts · ML predictions** table follows the physics/ML metrics panel. It shows each proposal from first to last and each inner ML retry, including rejected proposals, unavailable correction and cached predictions. Front/peak and tail use µs; crest uses kV; requested/actual Rf/Rt and per-output acceptance checks remain visible. The API supplies exact recipes and full-precision SI outputs. All pages are retrieved; First/Previous/Next/Last controls display 50 rows per page. Exported JSON includes the entire attempt history. A history-loading failure is reported without hiding completed configurations.

Real trained-model verification found three distinct waveform matches after 7 proposals and 5 ML calls. The two other proposals had no ML inference and remain visible as rejected attempts. See `verification/three-successful-configurations.json` for exact predictions, wiring, counters and constraint failures. The tested workbook setup still fails stage/total stored-energy limits; successful waveform matching does not approve the hardware.


## Physics, SHAP and selection explanation

The summary now presents a readable explanation rather than only a score table: first-place selection and comparisons, search outcome, per-case physics baseline, and three output explanations showing baseline + residual = predicted value. Each output includes signed SHAP feature impacts in µs/kV, the training-background reference, strongest drivers and expandable full attributions. Select “Explain Case #1/#2/#3” to inspect the corresponding prediction. Unknown resistor checks are grouped with expandable original evidence, and energy failures show quantities and limits.

`dashboard/explanations.py` computes and caches real saved-prediction SHAP; `dashboard/reasoning.py` produces deterministic analysis; `DecisionExplanation.jsx` renders it independently of Gemini. Gemini adds validated physics, ranking and per-candidate prose. The structured `analysis` is present even on quota/transport/validation failure. A safe `reason_code` and `provider_http_status` distinguish failure causes. Output-level evidence IDs are schema-constrained and accepted by reference validation.

Verified attributions must reconstruct saved residuals. Eight Train-only background rows and 32 sampled coalitions are used; initial three-case computation took approximately 68 seconds in the live check, then cached requests were fast. No predictions or ranking scores are changed while explaining. SHAP explains synthetic-model allocations, not causal physical reality or unlearned temperature/heat/wiring effects. See technical Section 18.1 for full contracts and standalone deliverables/tests.


### Calibration owns physical constraints (11 October 2026)

Physics and residual ML now return numerical predictions with physical checks unassessed. Calibration applies all physical checks afterward, feeds known failures to SMAC and excludes those failures from the successful top-three archive. Unknown evidence still prevents verified recommendations. A fixed-charge/capacitance conflict remains visible in feasibility windows but never stops calibration early. Failed constraints, repeated candidates and stagnation do not terminate the loop; it continues until three qualifying setups, explicit proposal/evaluation/time budgets, cancellation or search-space exhaustion. The frontend energy-per-stage limit is editable and supplied as `equipment_inputs.stage_energy_max_J`; omitted/null uses 2500 J. Total generator energy is also editable as `equipment_inputs.total_energy_max_J`; omitted/null uses 30000 J. SMAC receives an unclipped relative-violation penalty so reducing even a large failure improves its cost. Charge and capacitance are not silently optimised. `POST /v1/calibration/evaluate` exposes the complete independent sequence. The dashboard shows calibration windows, known-constraint status and an accurate successful count; failed diagnostic attempts stay inspectable. New context hashes apply the revised ownership policy; old runs stay historical. See technical Section 19 and working Section 16 for formulas, examples and independent deliverables.

## Independent transformer test demo

A separate **Transformer test demo** workspace tab now randomly selects one of four fixed illustrative waveforms: pass reference, front breakdown, tail breakdown/chopped wave, or inter-turn/partial breakdown ringing. Classification appears above the curve. Only preset selection is random; samples, event times and classification are fixed. It uses no generator, ML, calibration, inventory or Gemini results and makes no feature-specific API requests. Dashboard and demo state survive tab switches. Implementation/formulas/checks are recorded separately in [Transformer_Test_Demo.md](Transformer_Test_Demo.md).
