# Backend implementation and verification

The implementation is in `../backend/`. This document maps the specification's work packages to executable modules; related small responsibilities share files rather than creating empty placeholder modules. The React/Tailwind frontend is implemented in `../frontend/`; see [dashboard implementation](Dashboard_Implementation.md).

| Section | Implemented deliverables | Checks and scope |
| --- | --- | --- |
| Contracts / inputs | `contracts/models.py`, `protocols.py`, `constraint_ids.py`; generated `api/schemas/`; example requests and standalone fixtures | Pydantic and JSON-schema round trips; SI units; unknown-field/invalid-value rejection; independent role quantities |
| Context / profiles | `profiles/registry.py`, `resolve.py` | Frontend maximum stages, stage voltage and stage capacitance take precedence; missing stage/voltage limits use workbook defaults; only capacitance and energy values use retained document/benchmark parameters; resolved values and provenance exposed; immutable snapshot/hash; supplied inventories and global stock |
| Physics | `physics/forward.py`, `waveform.py` | Calculator inverse/forward; ideal analytic response; scaled Radau ODE for capacitive, parallel RC and parallel RLC circuits; waveform extraction, energies and constraint reports |
| Assemblies | `assembly/dp.py`, `cp_sat.py`, `validate.py` | Exact rational series/parallel reduction; canonical trees/netlists; bounded enumeration; separate stock caps; integer mismatch/quantity objectives; buildable SMAC seed and rejected options |
| Stress / heat | `physics/stress.py`, `thermal.py` | Per-resistor/per-stage voltage, current, power, integrated pulse energy and average power; periodic linear thermal RC estimate when constants/ambient exist; missing quantities remain unknown |
| Features / residuals | `correction/features.py`, `data.py`, `model.py`, `validation.py` | Workbook units, residual identities and splits; train-only feature/range preparation; six actual fitted TabPFN **v2** regressors; artifact/checkpoint/source hashes; synthetic support checks |
| Explanations | `ResidualModel.explain` | Three real Kernel-SHAP explanations checked for additivity; separate physical stress evidence; absent environment/heat features explicitly identified; no causal claims |
| Optimisation / archive | `optimisation/objective.py`, `smac_adapter.py` | Real SMAC3 ask/tell; finite normalised objective and failure penalty; best three distinct eligible evaluated setups; earlier best retained; explicit iteration/evaluation/search budgets |
| Jobs / history | `pipeline/runner.py`, `jobs.py`, `storage.py` | SQLite durable runs/events/cache; idempotency; spawn workers; cancellation; restart recovery and bounded warm-start replay; model/context version guards |
| Recommendation records | `recommendations/serialise.py` | Exact per-stage component/node identities; physical stages distinct from pipeline events; full constraints and nested outputs |
| Plot values | `physics/plot_reconstruction.py` | Target plus three candidate reconstructions; shared adaptive grid; fitted metric checks; JSON/CSV; four-curve HTTP smoke test |
| API / configuration | `api/app.py`, `config.py`, `cli.py` | FastAPI independent section routes and asynchronous runs; generated OpenAPI; arbitrary inventory registration; measurement/calibration endpoints; live HTTP worker check |
| Measurement calibration | `calibration/labels.py` | External observed-minus-physics labels; exact setup linkage; interpolation/uncertainty review flags; no predicted outputs used as measurements |

## Model evidence

Actual CPU fitting completed with 700 train and 150 validation records for each category. Hidden-test predictions were not evaluated. Standard pretrained TabPFN v2 uses in-context fitting: downstream gradient updates are zero and epochs are not applicable.

Validation MAE is the error in corrected output against the supplied synthetic observation:

| Category | Front/peak MAE | Tail MAE | Crest MAE |
| --- | --- | --- | --- |
| Lightning | 0.006514 µs | 0.583151 µs | 4.485187 kV |
| Switching | 1.606315 µs | 22.427952 µs | 3.147473 kV |

All six improve on the mean-residual baseline on this validation split. The linear residual baseline is slightly better on several timing outputs; TabPFN is not established as universally best. Compare the complete metrics in `model_fit_report.json`. These comparisons do not establish real-equipment performance or general-load support.

## Explicit verification boundaries

Software checks, exact-network arithmetic and numerical reference checks are evidence about implementation. They are separate from equipment validation and standards compliance.

- The document capacitance fallback and workbook example capacitance differ; stage-count defaults come from the workbook. The fitted residuals support the workbook **calculator** baseline only; changing to exact physics or the PDF profile is rejected by model support rules.
- Existing synthetic records have no environmental, temperature or exact wiring observations. They cannot train those effects. An electrical/thermal calculation is exposed separately and remains assumption-dependent.
- Lightning Rt is constant; switching Rt and stage count cover very small ranges. Out-of-envelope predictions are rejected; range checks do not prove joint-distribution or causal support.
- The lumped solver cannot certify internal capacitor transient/reverse stresses. User-supplied component ratings and circuit-approval evidence are still incomplete; excluded PDF auxiliary values are not prerequisites. These remain hard `unknown` constraints. Current physical recommendation runs return a shortfall rather than verified alternatives.
- All supported stage assemblies are identical and tail reduction uses the explicitly named generator-side series model. Other tail/load connections need a registered circuit adapter. A parallel RLC equivalent does not fully model an arbitrary transformer.
- Thermal estimates use supplied linear RC constants, constant ambient and periodic identical pulses, with zero heating outside the retained trace horizon. Pulse integration is truncated at the reported horizon; unmeasured temperatures and validated pulse-rating curves are not invented.
- Independent numerical evaluations have a 60-second ceiling (also bounded by the request wall budget) and reject more than 250,000 maximum-step intervals. DP option caches retain at most four entries. Cancellation is checked at iteration boundaries; a running integrator also checks its deadline.
- Current waveform extraction implements project lightning definitions and legacy switching peak/half-value metrics. It does not certify standards, ringing/overshoot or chopped impulses.
- DP is exhaustive only within a **completed declared part/state/time scope**. Larger searches can return budget exhaustion. CP-SAT reports its finite pool and integer resolution. SMAC does not prove a global optimum.
- Restart recovery replays completed trial costs into a new SMAC instance. Budgets/archive/cache survive; bit-identical uninterrupted search is not promised. Local SQLite worker ownership assumes one API process.

## Reproduce and inspect

Follow `../backend/README.md`. Numerical arrays, fitted models and job histories are under `../backend/artifacts/`; exported contracts, environment and verification evidence are in this `docs/` folder. `source_manifest.json` records input hashes and conflicts; `constraint_responsibility.json` maps enforcement ownership.

The technical specification remains the architectural authority. Its Section 15 paths described future deliverables at repository root; the actual source/test/environment directories now reside beneath `backend/`. Existing PDF exports have not been regenerated.

## Recorded checks

The full suite passed **107 tests**, including actual local TabPFN v2 inference tests, with no skips. It verifies all eleven frontend fields together, the three retained document values, removed voltage/shot-rate checks, single-stage input support and inspectable cached failures for stored-energy violations. Lint and static type checks passed. The locked environment resolved successfully; the real HTTP service and background worker smoke check passed. Three SHAP residual outputs passed additivity checks. SMAC emits deprecation warnings from its installed dependency; these are retained in the test report.

The completed four-part reference search retained 27,620 canonical front recipes and 55,028 tail recipes. That proves enumeration only within the declared four-part scope, not all assemblies allowed by four units of every type.

See [verification summary](verification_report.json), [tests](verification/tests.txt), [HTTP evidence](verification/live-api-report.json) and [plot QA](verification/waveform_fixture_qa.png).

Frontend input precedence is implemented through `RunRequest.equipment_inputs` (`N_max`, `U_stage_max_V`, `C_stage_F`). All eleven workbook inputs are mapped in `input_sources`; hardware resolution details are exposed in `value_sources`. The optimiser, inventory stock bounds and physics consume the resolved values. Only total/per-stage energy limits and capacitance fallback are imported from the last page. Removed stack/crest/basic-capacitance/shot-rate/auxiliary values are not active constraints. `impulse_type` accepts Lightning/Switching directly; positive stage counts include one. Optional supplied shot rate enables thermal estimates. Changed capacitance is also checked against residual-model baseline coverage; existing synthetic models are not retrained by changing a request.

## Performance metrics

Implemented technical Section 17 and combined `POST /v1/performance/evaluate`. Each production candidate exposes target errors, tolerance limits/verdicts, efficiency, energy/constraint summaries, category validation scores and measured stage durations. `GET /v1/models/{version}/performance` and `GET /v1/candidates/{id}/performance` provide separate reports. Run summaries expose processing time, proposal throughput, cache fraction and model quality, including when no recommendation is eligible. An optional observed metric triplet plus provenance enables separate prediction/observation error; caller-supplied identity is explicitly unverified. Per-input measured accuracy stays unavailable until observations exist. All HTTP responses include processing-time headers. The React/Tailwind frontend is implemented in `../frontend/`; see [dashboard implementation](Dashboard_Implementation.md).

## Dashboard integration

Dashboard aggregation, editable timing/tolerances/basic loading, secondary tie preferences, CORS and Gemini structured summaries are implemented. React tests/build/audit and browser verification accompany the backend checks. The live dashboard displayed three real evaluated diagnostic cases; none were falsely marked eligible. Missing Gemini credentials retain an unavailable status and deterministic evidence. Provider generation/cache/reference/failure paths were verified with mocks; live Gemini generation requires the configured key.


Workbook/dashboard reconciliation: independent `dashboard/baseline.py` and `POST /v1/dashboard/workbook-baseline` reproduce the input-driven worksheet sizing/five-ohm rounding. The Workbook preset uses Calculator. Diagnostic runs evaluate residual support/prediction despite hardware failures, retain hard constraints and recommendation rejection, and send varying objective feedback with a separate diagnostic improvement key. Exact inverse refinement is still outstanding; this change does not claim to implement it.


Required ML-loop revision: every successful forward prediction invokes the correction engine for both diagnostic and recommendation purposes. No physics-only objective fallback or calibrated-case selection remains. Numeric diagnostic extrapolation is explicit; baseline/model incompatibilities remain blocked. Actual corrected triplets populate a separate three-prediction archive and determine tolerance stopping; hard constraints still govern a separate eligible archive. Environment input values are exposed as not modelled by the current synthetic dataset. Live loop verification is in `verification/ml-required-loop.json`.
