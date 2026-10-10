# Project documentation

- [Technical implementation specification](Marx_Generator_Technical_Implementation_Specification.md): current backend contracts, physics/residual ML/optimisation workflow, API, waveform plot values, Python stack and deliverables.
- [Working architecture](Marx_Generator_Architecture_Working_Document.md): explanatory architecture document.
- [Physics formula book](Impulse%20Generator%20Physics%20Engine%20%E2%80%94%20Technical%20Specification.md): supplied physics reference; source conflicts are resolved in the technical specification.
- [Problem statement](HV%20IG%20Problem%20Statement.pdf) and [reference workbook](Hybrid_Physics_ML_Impulse_Generator_Optimiser.xlsx).
- [Nominal resistor DP prototype](resistor_inventory_search.py), [front example catalogue](resistor_inventory_front.json), [tail example catalogue](resistor_inventory_tail.json) and [saved example result](resistor_search_example.json).

All existing project material is stored here. Markdown is the editable source; existing PDF exports were moved unchanged and may predate the latest Markdown. Excel temporary lock files and Python caches are incidental files, not specifications.

The technical specification’s Section 15 identifies the exact selected library stack and future implementation deliverables. The listed production modules and lockfile are requirements, not claims of completed implementation.

## Backend implementation

- [Setup and execution](../backend/README.md)
- [Implemented sections and validation boundaries](backend_implementation_status.md)
- [OpenAPI](api/openapi.json)
- [Environment and installed versions](environment_report.json)
- [Actual model validation report](model_fit_report.json)
- [Model performance summary](model_performance_report.json): category validation MAE/RMSE/bias, baseline comparisons and dataset scope; per-setup metrics are specified in technical Section 17.
- [Constraint responsibility](constraint_responsibility.json)

- [React dashboard and Gemini Decision Summary](Dashboard_Implementation.md)
- [Frontend setup](../frontend/README.md)
