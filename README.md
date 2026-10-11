# PowerNext AI

The React/Tailwind dashboard lives in `frontend/`, the Python physics/ML/optimisation API in `backend/`, and reference material, contracts and verification evidence in `docs/`.

After installing dependencies (`npm --prefix frontend ci` and `uv sync --locked` from `backend/`), run `npm run dev` at the repository root to start both services. Open `http://127.0.0.1:5173`.

For the Gemini Decision Summary, copy `backend/.env.example` to `backend/.env` and set `GEMINI_MODEL` and `GEMINI_API_KEY`. Credentials remain on the backend. The summary explains physics baselines, verified SHAP residual contributions for all three cases, and the actual ranking comparison. Computed reasoning remains available when Gemini narration fails.

See [dashboard setup](frontend/README.md), [dashboard implementation](docs/Dashboard_Implementation.md), [backend setup](backend/README.md) and the [technical specification](docs/Marx_Generator_Technical_Implementation_Specification.md).


### Calibration owns physical constraints (11 October 2026)

Physics and residual ML now return numerical predictions with physical checks unassessed. Calibration applies all physical checks afterward, feeds known failures to SMAC and excludes those failures from the successful top-three archive. Unknown evidence still prevents verified recommendations. A fixed-charge/capacitance conflict that no N can repair returns `fixed_charge_energy_infeasible` after the first physics/ML attempt, with input/rating windows. Charge and capacitance are not silently optimised. `POST /v1/calibration/evaluate` exposes the complete independent sequence. The dashboard shows calibration windows, known-constraint status and an accurate successful count; failed diagnostic attempts stay inspectable. New context hashes apply the revised ownership policy; old runs stay historical. See technical Section 19 and working Section 16 for formulas, examples and independent deliverables.
