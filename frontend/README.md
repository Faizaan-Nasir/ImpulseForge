# PowerNext React dashboard

React 19, Tailwind CSS 4, Vite 7 and Lucide icons recreate the supplied [Claude artifact](https://claude.ai/artifact/UbRz4HMvFDn8LUzFdiKqJo). The original warm-stone background, teal controls, panel typography, left configuration rail, resistor diagrams, chart and comparison/summary sections are retained. Application state and interactions are React components; Tailwind utilities and component styles build the presentation. Original artifact source snapshots are under `docs/reference/` and are not executed by this app.

From the repository root:

```sh
npm --prefix frontend ci
cd backend
uv sync --locked
cd ..
npm run dev
```

Open `http://127.0.0.1:5173`. This starts both services. Individual commands are `npm --prefix frontend run dev` and, from `backend/`, `uv run python -m powernext serve`.

Copy `backend/.env.example` to `backend/.env` and set `GEMINI_MODEL` and `GEMINI_API_KEY` for the Decision Summary. Restart the backend after editing the environment. The key stays server-side; do not place it in frontend environment variables. `frontend/.env.example` provides an optional browser API base URL and a development proxy target. Production requires a same-origin reverse proxy or an explicit API base URL and approved backend CORS origin.

The dashboard sends all workbook inputs, arbitrary role-specific inventory, optional R/L/C equivalents, timing targets and tolerances in SI units. It runs the actual backend job, polls progress, shows exact nested recipes/netlists, switches among up to three cases, supports waveform overlay/zoom, exposes model validation/runtime/constraint reports and exports JSON. Input edits mark previous results as stale. Stop requests use backend cancellation boundaries.

A diagnostic display is explicitly separate from physical recommendations. Current evidence gaps can result in zero eligible recommendations; the dashboard then shows evaluated diagnostic cases. Optional residual inspection cannot override eligibility. ML corrections outside fitted-model support remain unavailable, with physics baseline labelled accordingly. Waveforms are metric-based reconstructions, not measured traces. Overshoot is unavailable rather than assigned an invented pass result.

Gemini receives only the backend's compact decision evidence. The backend validates structured responses and references, caches successful explanations by evidence/model hash, and holds recommendation IDs and scores outside Gemini's control. Missing credentials or provider failures show deterministic evidence and an explicit status. No live Gemini request was verified without a configured key.

Differences from the illustrative artifact preserve agreed project authority: stage energy is editable (2.5 kJ initial value, passed in J to the API); total energy remains 30 kJ; the fallback preset uses 15 default available stages and zero default basic capacitance; target timing/tolerances are editable; all workbook fields include maximum system voltage; priority preferences only break equal S/J scores. No KNN ranking or additive part/stage penalty is introduced. No unverified IEC certification is claimed.

```sh
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend audit --audit-level=moderate
```

See `docs/Dashboard_Implementation.md` for route mappings and tests.

The **Transformer test demo** tab is an independent illustration. Click **Generate random waveform** to select a fixed pass/failure preset and show its label above the plot. It requires no backend inference; the existing dashboard remains in its own workspace. See `docs/Transformer_Test_Demo.md` for the templates and isolation checks.
