# PowerNext backend

Python 3.12 backend for physics evaluation, exact resistor synthesis, residual corrections and SMAC3 optimisation. The React/Tailwind frontend is implemented in `../frontend/`; see its README for local startup and Gemini environment setup.

## Start

Run these commands from this folder:

```sh
uv sync --locked
uv run python -m powernext serve
```

The service listens on `http://127.0.0.1:8000`. Interactive API documentation is at `/docs`; machine-readable contracts are at `/openapi.json`. Run one API process: SQLite recovery and local worker ownership currently assume a single service process. Two optimisation workers may run concurrently.

Set `POWERNEXT_ARTIFACTS_DIR` to an absolute directory to change storage. Generated models, SQLite history and waveform arrays default to `backend/artifacts/` and are excluded from source control. The installed environment and local fitted models are already present in this workspace. New checkouts must install the locked environment and fit models.

## Frontend inputs and fallback values

The workbook’s input fields define the request contract. Send `equipment_inputs` with `N_max`, `U_stage_max_V` (V) and `C_stage_F` (F), for example `{"N_max":15,"U_stage_max_V":200000,"C_stage_F":3e-6}`. These are editable run inputs. Missing/null stage-count and stage-voltage maxima use workbook defaults; missing/null capacitance uses the selected template’s fallback; an explicit supplied value replaces that template value. The profile route returns a template, while `/v1/requests/validate` returns resolved hardware, `value_sources` and all workbook-field mappings in `input_sources`.

The optimiser holds these inputs fixed within one run and searches actual N/Rf/Rt within them. Exactly three last-page document values are retained: total energy 30 kJ, energy per stage 2.5 kJ, and capacitance fallback 0.125 µF. There are no imported stack/crest voltage, basic capacitance, shot-rate or auxiliary-component constraints. Use `impulse_type` to send Lightning/Switching directly. Positive integer stage counts begin at one. Energy uses the supplied stage capacitance. A valid input may lead to an infeasible result; the service reports failed constraints instead of overwriting the input. Changed settings can also be unsupported by the synthetic correction model. Optional `setup.shot_rate_per_minute` enables average-power/periodic-temperature estimates; without it these outputs remain unavailable.

## Execute sections independently

All numerical values are in SI units. Inventory is an input; the example inventory is optional. Four resistors per type **per role per stage** is a quantity cap. `dp_max_parts` is a separate bounded search policy and may exceed four.

```sh
uv run python -m powernext validate examples/lightning_request.json
uv run python -m powernext model-report
uv run python -m powernext fit
```

Use `examples/lightning_module_input.json` or `switching_module_input.json` to call `POST /v1/physics/inverse` and `POST /v1/assemblies/realise`. These files include a complete request and a valid candidate proposal. Put the returned `candidate` into the same module-input body for `/v1/physics/evaluate` or `/v1/corrections/predict`.

Additional CLI commands are `inverse`, `realise`, `physics`, `correct`, `objective` and `waveforms`; each has `--help`. Use the proposal's N/Rf/Rt values from the example when calling `realise`. A candidate must have the same immutable context and model hash as the subsequent request.

```sh
uv run python -m powernext --output artifacts/plot_bundle.json waveforms examples/lightning_request.json examples/plot_metrics.json
```

`POST /v1/runs` starts a durable background optimisation job. Poll its status, events, candidates, result and waveform endpoints. Idempotency keys prevent duplicate request creation. Cancellation is checked at iteration boundaries. Restarted jobs become `interrupted`; `/resume` preserves consumed budgets, cached evaluations and the archive, and starts a new SMAC instance with completed costs replayed. This is a documented warm start, not a promise of an identical uninterrupted random sequence.

Recommendation-mode runs give failed/unknown hardware or unsupported predictions cost 2 and exclude them from verified recommendations. Every completed physics prediction calls residual correction regardless of hardware verdict. Calibration costs use ML-corrected metrics only; missing predictions get cost 2 and no physics fallback. Diagnostic extrapolation of numeric inputs is explicit, marked untrusted and never permits physical recommendation eligibility. Ineligible diagnostic ML predictions have cost `1 + S/(1+S)`. `predicted_setups` and `ml_converged` are separate from eligible `recommendations`. Environmental effects are not modelled by current synthetic data. The provided equipment evidence cannot certify capacitor transient ratings or all resistor ratings, and synthetic models are not laboratory validated. Current real-data runs therefore return an explicit recommendation shortfall. Independent diagnostic correction endpoints still permit examining supported workbook predictions and report their hardware constraints. Mock integration tests demonstrate the complete three-candidate cycle without lab-accuracy claims.

`POST /v1/waveforms/reconstruct` returns target plus up to three reconstructed curves on one grid. The ML corrects front/tail/crest; reconstructed curves are not pointwise ML predictions or measured traces. `POST /v1/measurements` ingests external traces; `/v1/calibration/labels` requires exact actual-setting identities and produces reviewed residual labels without automatic retraining or triggering hardware shots.

## Performance for an entered setup

Send a complete module-input example to `POST /v1/performance/evaluate`, with either its `proposal` (automatically realised from inventory) or an actual `candidate`. It returns physics and corrected front/tail/crest, signed/absolute/percentage target deviations, tolerance limits/verdicts, objective scores, voltage-transfer efficiency, energy utilisation, constraint counts, model validation metrics and section processing times. Unsupported correction is explicit; baseline metrics remain available. This is diagnostic and does not make an infeasible candidate eligible.

Every saved production candidate has the same `performance` report, accessible at `GET /v1/candidates/{id}/performance`; optimisation results include it for each returned recommendation and include run processing time, proposal throughput and cache-hit fraction. Reused candidates retain the original computation times; iteration events indicate cache reuse. Every HTTP response includes `X-Processing-Time-Seconds` for service processing through response preparation, excluding network delivery.

`GET /v1/models/residual-tabpfn-v2-standardised-v1/performance` exposes actual validation MAE/RMSE/bias and physics/mean/linear baseline MAE, separately for Lightning and Switching. These are synthetic dataset aggregates, not exact error scores for an entered setup. Optional `observed_metrics` (`front_s`, `tail_s`, `crest_V`) and `observation_provenance` must be supplied together to compare predictions with an observation. Identity matching remains unverified in this diagnostic route; the calibration-label workflow performs setting/measurement identity validation. Values are returned in SI without display rounding. See technical specification Section 17.

## Check

The current `residual-tabpfn-v2-standardised-v1` artifact fits feature and residual-target `StandardScaler` transforms separately for each impulse category on its 700 Train rows only. Each of the three regressors is a `TransformedTargetRegressor` containing a feature-scaling `Pipeline` and the pretrained TabPFN v2 estimator. Inference reuses the frozen transforms and returns inverse-transformed residuals in seconds/volts before adding them to physics. Validation, support checks and SHAP retain physical units. `normalisation` exposes standardised inputs/residuals and training target means/scales; the model manifest stores all scaler parameters. TabPFN's own preprocessing remains enabled. This makes scaling explicit; it does not change waveform tolerances or supply missing training coverage. Older artifacts must be refitted with `uv run python -m powernext fit`.

```sh
uv run pytest -q
uv run ruff check src tests scripts
uv run pyright --pythonpath .venv/bin/python
uv run python scripts/export_contracts.py
```

Model tests use local fitted TabPFN v2 artifacts and clearly skip when those artifacts are absent. They ran against actual fitted models during this implementation. Fitting uses 700 train rows/category; validation uses 150/category. Hidden-test predictions remain untouched. Standard pretrained TabPFN fitting has no downstream gradient-training epochs.

For HTTP smoke tests, start the server on port 8765 and run `uv run python scripts/live_smoke.py`. Generated reports are exported to `docs/verification/`.

See [implementation status](../docs/backend_implementation_status.md), [model results](../docs/model_fit_report.json), [environment](../docs/environment_report.json) and [OpenAPI](../docs/api/openapi.json) for concrete outcomes and limitations.

## Dashboard and Decision Summary

Dashboard APIs provide bootstrap presets, a per-run view with up to three evaluated cases, explicit diagnostic inspection and a Gemini decision explanation. Optional `target.front_s`, `target.tail_s`, `target.tolerances` and `setup.basic_C_F` fields support the dashboard controls. Primary waveform objectives stay first; `objective.secondary_preference` only changes ties. Copy `.env.example` to `.env` and set `GEMINI_MODEL`/`GEMINI_API_KEY`; keys never reach frontend responses. See `../docs/Dashboard_Implementation.md` for contracts, provenance and missing-key behaviour.

## Calibration budget environment settings

Set these in `backend/.env` (also present in `.env.example`):

```dotenv
POWERNEXT_CALIBRATION_WALL_TIME_SECONDS=600
POWERNEXT_CALIBRATION_MAX_ATTEMPTS=24
```

Restart the backend and refresh the dashboard after changes. Bootstrap exposes active values under `defaults.search`. Omitted API proposal/physics/ML caps use the configured attempt count; omitted worker wall time uses the configured seconds. Explicit per-run values override these defaults, and saved/resumed runs keep their frozen request. Attempts include the initial proposal. Repeated or rejected proposals can mean fewer fresh ML predictions, and waveform success or another stopping rule can finish earlier.

### Successful alternatives and complete attempt history

`predicted_setups` contains only distinct ML waveform matches passing all three thresholds; `returned_successful_predictions` reports the count. One match does not satisfy the three-configuration goal. Outside-threshold predictions remain in `evaluated_setups` and history, and budget exhaustion with fewer than three matches is an explicit shortfall. Hardware/laboratory eligibility remains separate. During a run, `top_three_successful_ids` identifies accumulated matches.

`GET /v1/runs/{id}/attempts?offset=0&limit=1000` returns every proposal and inner correction attempt in chronological order, with requested/realised settings, exact recipes, SI ML predictions, acceptance checks, hardware checks and reasons. Cached repeats remain rows and are labelled cached; they do not count as additional successful configurations. Rejected/unsupported attempts have null prediction fields where ML did not produce values. `/candidates` remains the distinct-candidate endpoint. See `tests/test_attempts.py` and `docs/verification/three-successful-configurations.json` for fixture and real-model verification.
