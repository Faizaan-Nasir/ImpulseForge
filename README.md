# PowerNext AI

The React/Tailwind dashboard lives in `frontend/`, the Python physics/ML/optimisation API in `backend/`, and reference material, contracts and verification evidence in `docs/`.

After installing dependencies (`npm --prefix frontend ci` and `uv sync --locked` from `backend/`), run `npm run dev` at the repository root to start both services. Open `http://127.0.0.1:5173`.

For the Gemini Decision Summary, copy `backend/.env.example` to `backend/.env` and set `GEMINI_MODEL` and `GEMINI_API_KEY`. Credentials remain on the backend.

See [dashboard setup](frontend/README.md), [dashboard implementation](docs/Dashboard_Implementation.md), [backend setup](backend/README.md) and the [technical specification](docs/Marx_Generator_Technical_Implementation_Specification.md).
