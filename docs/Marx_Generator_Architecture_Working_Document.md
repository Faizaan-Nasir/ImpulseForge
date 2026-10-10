# Marx Generator Configuration Through Physics, Inventory Search, ML and Optimisation

Working architecture document | 10 October 2026

## 1. Purpose and agreed design

This system recommends a constructible Marx generator configuration for a specified impulse voltage test. It begins with electrical calculations, converts the required front and tail resistance into assemblies available from inventory, predicts the achievable waveform under the current conditions, and improves the configuration through a bounded feedback loop.

The intended scope includes insulators and other supported test objects, including transformers. The load is described by an appropriate electrical model using resistance, inductance, capacitance, and their connection arrangement. The initial insulator dataset is development material; it does not define the complete load scope.

The agreed design has three engines and one supporting solver:

| Component | Responsibility |
| --- | --- |
| Physics Engine | Propose an initial active stage count and required front/tail resistance per stage; predict a waveform for actual constructible settings |
| Inventory DP Solver | Convert required per-stage resistance into allowed series–parallel resistor assemblies, within inventory and an explicit search budget |
| ML Prediction Engine | Hold the candidate's realised settings fixed and predict front/peak time, tail time and crest under the specified load, setup and environmental conditions |
| Optimisation and Calibration Engine | Propose revised stage count and required per-stage resistances to reduce waveform deviations; retain the three best distinct evaluated configurations and manage stopping |

The DP solver is a component-selection service used by the Physics Engine and the optimisation loop. It is not a fourth learning engine. A dashboard presents up to three distinct recommended configurations and the evidence supporting each.

Decisions deliberately left open:

- The ML algorithm and whether it predicts outputs directly or learns corrections to physics.
- The optimisation algorithm.
- The final environmental variables, to be supplied after feature extraction and assessment.
- Numerical resistance and waveform tolerances, convergence thresholds and iteration budgets.
- The dashboard layout.

No nearest-neighbour model or neighbour count is prescribed. The three recommended configurations are selected from the evaluated optimisation history using the declared objective; this does not prescribe the workbook’s ML architecture. The supplied Excel workbook is reference material, not the implementation specification.

## 2. Electrical foundations and terminology

### 2.1 What the generator does

A Marx generator stores electrical energy in stage capacitors. The capacitors are charged through charging paths, approximately in parallel in a conventional arrangement. When the switching gaps fire, charged stages are erected into a series discharge arrangement. Their voltages add to produce a high-voltage pulse.

For `N` identical active stages, each charged to `U_ch`:

```text
Ideal erected voltage = N × U_ch
Effective series generator capacitance = C_stage / N
Stored energy = N × ½ × C_stage × U_ch²
```

Here `C_stage` is the capacitance of one stage. These relations assume identical stages and the conventional series discharge arrangement. Other generator connection arrangements require their own electrical mapping.

For example, nine stages charged to 100 kV each provide an ideal erected voltage of 900 kV. The voltage actually appearing across the test object depends on the complete circuit, its load and losses.

An approximate crest estimate can use an independently justified transfer efficiency:

```text
Estimated crest ≈ efficiency × N × U_ch
```

If a detailed circuit model already represents load transfer and losses, avoid applying an efficiency factor that counts those effects again.

Here “efficiency” means voltage-transfer efficiency, approximately `V_crest / (N × U_ch)`, not the fraction of stored energy delivered to the load. Reaching the required crest and increasing this efficiency are different objectives. The main objective in this architecture remains matching the required voltage and timing within equipment limits.

### 2.2 Front resistance and tail resistance

`Rf` and `Rt` are waveform-shaping resistances in the generator circuit:

- **Front resistance, Rf:** helps control the rising edge and damping.
- **Tail resistance, Rt:** helps control the discharge and falling portion of the impulse.

They are separate from the test object's own resistance. Their effect depends on their placement and on the rest of the circuit. Altering one resistance can influence more than one output, so the optimiser must evaluate the complete waveform response.

Use explicit notation:

| Symbol | Meaning |
| --- | --- |
| `N` | Integer number of active generator stages |
| `Rf_req` | Required equivalent front resistance for one stage, proposed by physics or optimisation |
| `Rt_req` | Required equivalent tail resistance for one stage |
| `Rf_actual` | Equivalent resistance of the selected front assembly for one stage |
| `Rt_actual` | Equivalent resistance of the selected tail assembly for one stage |
| `A_f`, `A_t` | Actual wiring recipes and component usage for those assemblies |
| `U_ch` | Charging voltage per active stage |
| `R_load`, `L_load`, `C_load` | Parameters of the test-object model |
| `L_lead`, `C_stray` | Connection/setup parasitics, distinct from load parameters |

“Required” and “actual” must remain separate fields. The required value can be any positive number within the physical model. The actual value must correspond to a circuit that can be built from inventory.

### 2.3 Per-stage inventory and uniform configuration

The current project assumption is:

1. Each stage has a front catalogue of **10 types** and a tail catalogue of **12 types**.
2. Up to four copies of each type are available in its respective catalogue in that stage.
3. Allowed assemblies may use arbitrary two-terminal series–parallel connections.
4. The selected front assembly and selected tail assembly are repeated identically across all active stages.

This represents **40 available front parts and 48 available tail parts per stage**, or 88 listed parts across both catalogues. It does not require using every available part. “Four copies of each type” also does not mean that every assembly must contain exactly four resistors.

| Catalogue | Nominal values (Ω) | Types | Copies per type per stage |
| --- | --- | --- | --- |
| Front | 10, 20, 30, 50, 75, 100, 150, 200, 300, 500 | 10 | 4 |
| Tail | 5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 150, 200 | 12 | 4 |

These are the workbook's proposed catalogues, not the different resistor set printed in the PDF's equipment figure. Select a verified equipment/inventory profile before making a physical recommendation.

The system selects the configuration for one representative stage and applies it to all `N` active stages. It does not independently optimise a different resistor network for every stage.

```mermaid
flowchart LR
    A[One per-stage inventory profile] --> B[Select front assembly and tail assembly]
    B --> C[Stage 1: same selected assemblies]
    B --> D[Stage 2: same selected assemblies]
    B --> E[Stage N: same selected assemblies]
    C --> F[Approved generator discharge arrangement]
    D --> F
    E --> F
    F --> G[Impulse applied to the load]
```

Front and tail inventories have independent limits: **front usage ≤ 4 per front type, and tail usage ≤ 4 per tail type, per stage**. A resistance value appearing in both catalogues can therefore use up to four front parts and independently up to four tail parts. There is no combined front-plus-tail limit of four.

If stock is specified globally rather than per stage, repeated assemblies consume `N` times their per-stage component quantities. The inventory profile must state which interpretation applies.

Combining resistors in series and parallel determines `Rf_actual` and `Rt_actual`. It does not, by itself, determine `N`. The Physics Engine and optimiser select `N` subject to voltage, energy and generator limits. Generator-stage connection topology is a separate choice from resistor assembly topology. The base design uses identical stages in the approved Marx discharge arrangement.

### 2.4 Units and a general load model

Use ohms, farads, henries, volts and seconds inside the calculations. Display Ω, pF/µF, µH/H, kV and µs where convenient.

```text
1 kV = 1,000 V
1 µs = 10⁻⁶ s
1 µF = 10⁻⁶ F
1 pF = 10⁻¹² F
1 µH = 10⁻⁶ H
```

The familiar electrical relationships are:

```text
V = I × R
Q = C × V
Capacitor energy = ½ × C × V²
Capacitor current = C × dV/dt
Inductor voltage = L × dI/dt
```

`dV/dt` means the rate of change of voltage. A larger capacitance needs more current to raise its voltage at the same speed. Inductance resists rapid changes in current. Resistance dissipates energy and damps oscillations. These effects explain why different loads need different generator settings.

R, L and C values must be accompanied by a circuit arrangement. The same three values connected in series and in parallel have different responses. A supported load model may be a simple capacitive/RC model, a lumped RLC circuit or a more detailed winding network. Transformer inputs must also identify the tested terminals and other terminal connections. A simple three-value representation is used only where adequate for the required prediction.

The objective is the applied voltage at the specified test terminals. Predicting internal transformer winding stress or declaring that an object has passed a withstand test is beyond this configuration-recommendation task.

### 2.5 The three waveform outputs

For the lightning case:

```text
Target front time tf* = 1.2 µs
Target tail time tt* = 50 µs
Target crest V* = the requested test voltage
```

Lightning front time is a conventional rise parameter rather than simply the time at the crest. For a smooth full lightning impulse, the rising 30% and 90% points define the usual front and virtual origin:

```text
tf = 1.67 × (t90 − t30)
t0 = t30 − 0.5 × (t90 − t30)
tt = t50,fall − t0
```

The waveform evaluator must use the applicable test convention, especially for overshoot or ringing. A raw maximum and arbitrary threshold crossing do not establish standards compliance.

The same architecture can support switching impulses using an explicit profile. The supplied challenge describes 250/2500 µs using switching peak time. IEC 60060-1:2025 introduces a different switching front-time definition and a 170/2500 µs designation. Preserve the selected timing definition with every request and output; do not silently interchange peak time and front time. Source: [IEC edition summary](https://webstore.iec.ch/en/publication/65088).

## 3. Inputs, controls and fixed conditions

| Input group | Contents | Behaviour during one optimisation run |
| --- | --- | --- |
| Target | Impulse category, target front/peak, target tail, required crest and tolerances | Fixed |
| Load | Supported load model, R/L/C or network parameters, terminal arrangement | Fixed unless a new test scenario is explicitly started |
| Setup | Divider loading, parasitics, lead/return arrangement and other known conditions | Fixed |
| Environment | Features to be defined after extraction/assessment | Fixed for the run's declared scenario |
| Hardware | Stage ratings, maximum stages, energy limits, per-stage inventory and allowed wiring | Fixed |
| Proposed controls | `N`, `Rf_req`, `Rt_req` | May change between cycles |
| Realised controls | `N`, `Rf_actual`, `Rt_actual`, `A_f`, `A_t` | Fixed during a particular forward prediction |
| ML model and feature transformations | One accepted version of each | Fixed throughout the optimisation run |

Charging voltage must also be defined. Stage count alone cannot determine crest. The initial Physics Engine must receive or calculate `U_ch`, and the run must declare one policy:

- **Fixed-charge policy:** keep a specified charging voltage while changing `N`, `Rf_req` and `Rt_req`.
- **Recomputed-charge policy:** compute charging voltage for each proposal using a declared physics rule and verify its limits.

Under either policy, capacitor/stage voltage ratings are hard constraints. If a low predicted crest would require charging above an allowed voltage, reject that proposed charge and consider other feasible settings, including a larger active stage count. Increasing `N` is therefore an available way to address voltage feasibility, not merely a timing adjustment. Section 5.4 gives the physical reasoning and its limits.

The charging policy is not yet selected. `U_ch` must be included in the candidate record and physics/ML context under either policy. It does not become a new independent optimiser control unless that is explicitly chosen later.

The environment is held fixed so that successive deviations refer to the same problem. A change in measured conditions starts a new scenario or requires an explicit update and reevaluation of stored candidates.

### 3.1 Complete workbook input contract

All calculator inputs remain part of the architecture. Highlighting `N`, `Rf` and `Rt` as adjustable controls does not remove the other inputs. The following are the current values in the **Hybrid Calculator** sheet; they are example settings, not universally approved ratings.

| Workbook input | Example | Meaning and use |
| --- | --- | --- |
| Maximum system voltage | 400 kV | Equipment/system voltage classification; retain as request context for selecting the applicable test profile. It is not the desired impulse crest or the generator's charging limit. |
| Impulse category | Lightning | Selects the waveform definition, timing targets and applicable tolerances. |
| Required test voltage | 1,425 kV | Target crest used by physics and the optimisation objective. |
| Test-object capacitance | 850 pF | Load model input; general loads additionally require appropriate R/L and topology information. |
| Divider capacitance | 500 pF | Measurement circuit loading in the forward model. |
| Stray capacitance | 150 pF | Setup parasitic capacitance, with a declared circuit location. |
| Stray inductance | 18.5 µH | Loop/setup inductance; does not replace a transformer's load inductance. |
| Expected efficiency | 0.82 | Initial generator voltage-transfer estimate for stage/charge sizing; retain its source and use consistently with the chosen physics fidelity. |
| Maximum stages | 15 | Editable frontend stage-count upper bound; 15 is the current example. |
| Maximum stage voltage | 200 kV | Editable frontend per-stage charging-voltage ceiling; use the supplied value for this run. |
| Stage capacitance | 3 µF | Determines effective generator capacitance, energy and the forward waveform. |
| Front and tail inventories | See Section 2.3 | Catalogue values and quantities constrain DP's physical assemblies. |

Selected practical front/tail resistances and units per stage are **results** in the calculator, not extra independent targets. In this architecture, DP produces these results, including the full wiring recipe.

The workbook supplies one expected efficiency for the generator, not separately measured efficiencies for individual stages. Define predicted generator voltage-transfer efficiency as `η = V_crest / (N × U_ch)` for equal charged series stages. Stage-voltage utilisation is `U_ch / U_stage,max`; it is a different quantity. If the project also requires a minimum efficiency or a distinct per-stage efficiency target, preserve that requirement in the input contract, define its numerator/denominator and acceptance rule, and enforce it explicitly. Do not invent per-stage efficiencies from the single workbook field or multiply stage efficiencies without a supporting circuit model. An expected estimate used to initialise physics is also distinct from a minimum efficiency constraint.

### 3.2 Three permitted document values

Only the following values from the last page of the problem statement enter the runtime:

| Parameter | Value | Use |
| --- | --- | --- |
| Maximum stored energy at rated voltage | 30 kJ | Hard total stored-energy limit |
| Stored energy per stage | 2.5 kJ | Hard energy limit for each stage |
| Impulse capacitance per stage | 0.125 µF | Fallback only when frontend stage capacitance is missing; a supplied value wins |

Compute `E_stage = 0.5 × supplied_or_fallback_C_stage × U_charge²` and `E_total = N × E_stage`. Do not overwrite a supplied capacitance to make these limits pass. A 3 µF stage at 200 kV stores 60 kJ, so those frontend values fail the retained per-stage limit.

No other last-page values are imported. In particular, there is no document-based stack/crest-voltage ceiling, two-stage minimum, 545 pF basic-capacitance addition, shot-rate limit or auxiliary resistor/installation default. The workbook defines the remaining frontend inputs and example defaults, including maximum stages 15 and maximum stage voltage 200 kV. Those example numbers remain editable run inputs.

### 3.3 Resolve all frontend inputs and propagate them

All eleven fields in the workbook’s USER INPUT section (`Hybrid Calculator!B5:B15`) have API fields. Use `impulse_type` for Lightning/Switching, `equipment_inputs.N_max` for maximum stages, `equipment_inputs.U_stage_max_V` for maximum stage voltage and `equipment_inputs.C_stage_F` for stage capacitance. Other fields carry system-voltage classification, required crest, load/divider/stray capacitance, stray inductance and expected efficiency. Inventory is also a supplied input, independent of the example catalogue.

A missing stage-count or stage-voltage maximum uses the workbook example default. Missing capacitance uses 0.125 µF in the default document-fallback profile. Only the two retained energy limits are unconditional document constraints. Require positive integer `1 ≤ N ≤ resolved.N_max`; a PDF minimum of two is not imported. Component ratings supplied with inventory, supported circuit topology, ML coverage and the previously agreed independent four-per-type/role cap remain separate project/input/model policies.

API output exposes `value_sources`, `input_sources`, resolved values and constraint outcomes. Physics uses `C_effective_load = C_object + C_divider + C_stray`, with no automatic document basic-capacitance term. Optional shot rate must be supplied explicitly for average-power/periodic-heat estimates. The optimiser varies actual `N`, required `Rf` and required `Rt` while the scenario inputs remain fixed within that run.

Pass the same complete scenario through the loop:

1. **Initial physics:** consume targets, expected efficiency where appropriate, load/setup parameters, stage capacitance and all equipment bounds to propose stage count, charge and required resistances.
2. **DP:** use the selected front/tail catalogues, quantities, permitted assembly wiring and component constraints to realise resistances.
3. **Forward physics:** recompute from actual settings and active auxiliary circuitry; recheck the supplied stage-voltage limit and the two retained energy limits. Never set predicted crest equal to the requested crest merely to satisfy the request.
4. **ML:** predict at the same realised operating point using its validated feature contract. Expected efficiency may be supplied if appropriate, but a post-shot measured efficiency would be unavailable during prediction and must not leak into the input.
5. **Optimisation:** hold the scenario and bounds fixed while proposing new `N`, `Rf_req` and `Rt_req`; evaluate waveform errors and any explicitly declared efficiency requirement after each realisation. The optimiser cannot change equipment ratings to obtain feasibility.
6. **Dashboard/testing:** retain all inputs and constraint outcomes with each of the three retained configurations; record any explicitly supplied operating rate and setup evidence when measurements are taken; no PDF shot-rate restriction is imported.

## 4. End-to-end architecture

```mermaid
flowchart TB
    A[Target, load, setup, environment and equipment profile] --> B[Validate inputs and declared policies]
    B --> C[Physics Engine: propose N and required per-stage Rf and Rt]
    C --> D[Inventory DP Solver: realise front and tail assemblies]
    D --> E{Constructible and within resistance tolerance?}
    E -->|Yes| F[Physics Engine: recompute waveform for actual assemblies]
    E -->|No| G[Expand allowed search or reject proposal with reasons]
    G --> O[Optimisation and Calibration Engine]
    F --> H[ML Prediction Engine: fixed actual settings and current conditions]
    H --> I[Calculate absolute waveform deviations]
    I --> J[Update three best distinct evaluated configurations]
    J --> K{Stopping condition met?}
    K -->|No| O
    O --> L[New N and required per-stage Rf and Rt]
    L --> D
    K -->|Yes| M[Return up to three best supported configurations with stop reason]
    M --> N[Dashboard presents three configurations and their predictions]
```

Every proposal, including later proposals, passes through DP and forward physics before ML evaluation. The optimiser cannot skip the inventory-realisation step, and ML must not receive unrealised required resistances as if they were actual settings.

Invalid proposals consume a declared proposal budget as well as valid ML evaluations consuming a prediction-cycle budget. A deterministic overall maximum prevents repeated invalid proposals from bypassing the stopping rule.

## 5. Physics Engine

### 5.1 Initial proposal

The Physics Engine receives the target, load, setup and verified equipment profile. It proposes:

```text
N_initial
Rf_req_initial per stage
Rt_req_initial per stage
U_ch according to the declared charging policy
```

It also returns the assumed generator topology, load model, constraint status and calculation version.

For a conventional generator and an approximate independently known efficiency, an initial stage-count estimate is:

```text
N_initial = max(N_min, ceil(V_target / (efficiency × U_stage,max)))
```

`ceil` means round upward to an integer. This is only a starting estimate. The full circuit, permissible charge, stored energy and waveform shape determine whether the proposal is feasible.

Required front and tail resistance can be estimated by inverting an appropriate circuit approximation or solving a physical inverse problem. Use equations suited to the declared load model. A capacitive-load formula must not automatically serve as a transformer/RLC-load formula.

Where an initial calculation produces total shaping resistance, convert it to per-stage required values using the approved topology. In a simple arrangement where stage resistances add, total resistance is `N × R_stage`. Do not assume this mapping for every tail-resistor placement or alternative generator connection.

### 5.2 Prediction after inventory realisation

Once DP returns actual assemblies, the Physics Engine uses:

```text
N, Rf_actual, Rt_actual, A_f, A_t, U_ch,
load model, setup and hardware profile
```

It predicts `tf_physics`, `tt_physics` and `V_physics`, and a voltage-versus-time trace if the model supports one. It computes stage and total energy and verifies the candidate's required ratings.

The predicted crest must respond to the candidate settings. Setting it equal to the requested voltage regardless of the candidate is not a valid forward model for optimisation.

There are two complementary computational methods:

- **Analytical approximations:** transparent, fast expressions for supported simple circuits, suitable for seed estimates and independent checks.
- **Numerical circuit simulation:** solve capacitor voltages and inductor currents over time for a declared generator/load network. This is the more general route for supported RLC and winding models.

The numerical method applies the electrical relations in Section 2 repeatedly over small time intervals. The same waveform evaluator extracts parameters from simulated and measured traces. Check solver convergence and known circuit cases before relying on the results.

### 5.3 Physics checks remain active in every cycle

Reject or mark unverified any proposal with an invalid stage count, charging voltage, stored energy, required component rating, generator connection or load representation. A model prediction close to the target does not override a physical constraint.

All stages share the selected per-stage assemblies. Changing `N` still changes the overall circuit: erected voltage, effective capacitance, total shaping network and load interaction must be recomputed.

### 5.4 Capacitor voltage limits and why stage count remains adjustable

**Design decision:** enforce the applicable voltage limits of each stage capacitor, and retain integer `N` as an optimisation variable within the installed generator's permitted range. This combination prevents matching the target by asking an individual stage to operate beyond its rating and allows additional active stages to contribute to the required erected voltage.

The precise physics is:

1. The charging supply and its control determine the capacitor's initial voltage `U_ch`.
2. Front/tail resistances shape the subsequent discharge. Their values affect front time, tail time, crest and voltage-transfer efficiency in a coupled, topology-dependent way.
3. Changing Rf or Rt does **not**, by itself, automatically increase the initial charging voltage. Neither resistor should be forced downward on the assumption that this always increases crest or fixes an inadequate charging condition.
4. If a control rule compensates for a low predicted crest by increasing `U_ch`, the required value may exceed the allowed capacitor/stage voltage.
5. A larger permitted stage count may supply the required total voltage with a lower charge per stage. Reevaluate the complete circuit to determine whether it actually does so while preserving the required timing.

“Capacitor voltage rating/withstand limit” is the relevant constraint. Capacitance tolerance, such as a percentage variation in µF, is a separate component property.

The distinction between selected charging voltage, series-stage multiplication and load-dependent output voltage is described in the manufacturer-authored [HAEFELY SGDA brochure, page 3](https://hvtechnologies.com/wp-content/uploads/2020/12/HVT_DS_HAEFELY_SGDA.pdf). Its values describe that product family and are not adopted as ratings for the project's equipment.

#### Approximate charging requirement

For an independently supported voltage-transfer efficiency estimate:

```text
V_target ≈ eta × N × U_ch
U_ch,required ≈ V_target / (eta × N)

Voltage-feasible condition:
    U_ch,required ≤ U_ch,allowed

Approximate stage-count lower bound:
    N ≥ ceil(V_target / (eta × U_ch,allowed))
```

`U_ch,allowed` must respect the applicable capacitor charging-voltage limit, stage rating, charging-supply operating limit and other verified operating limits. Use any required operating margin explicitly. Do not equate a stack voltage rating with the voltage permitted across one capacitor.

The estimate is a feasibility screen, not a final solution. Efficiency depends on actual assemblies, stage count, load, setup and conditions. If charge is computed from an inferred efficiency, use validated evidence and a bounded charge-selection procedure; never extrapolate an efficiency or increase charge without enforcing the limits.

#### Illustrative example

Assume a target crest of 1,425 kV, voltage-transfer efficiency 0.75, and a verified permitted charge of 200 kV per stage:

| Active stages | Approximate charge needed per stage | Voltage-limit outcome |
| --- | --- | --- |
| 9 | `1425 / (0.75 × 9) ≈ 211.11 kV` | Exceeds the assumed 200 kV limit |
| 10 | `1425 / (0.75 × 10) = 190 kV` | Within the assumed charge limit |

This illustrates why the optimiser may increase the active stage count rather than accept an excessive capacitor charge. It assumes efficiency stays at 0.75 for the comparison. The real ten-stage candidate must pass DP, forward physics, ML, energy and waveform checks; the table alone does not establish its feasibility.

#### More stages do not guarantee better transfer efficiency

For conventional identical stages in series, `C_generator = C_stage / N`. Adding stages increases ideal erected voltage at fixed charge but reduces effective generator capacitance and changes the overall shaping circuit. Load interaction and efficiency can therefore change too.

Consequently, varying `N` expands the search for a feasible target-voltage solution, but increasing it is not automatically an improvement. If a fixed `N` already admits a satisfactory configuration, a stage increase is unnecessary. If all available stage counts fail the full constraints, report that the target cannot be achieved within the tested equipment/model region rather than relax the capacitor rating.

#### Charge, energy and transient constraints

At a minimum, check charging voltage and stored energy for every realised candidate:

```text
U_ch ≤ U_ch,allowed
E_stage = ½ × C_stage × U_ch² ≤ E_stage,allowed
E_total = N × E_stage ≤ E_total,allowed
N_min ≤ N ≤ N_max, with integer N
```

The stored-energy limits can impose additional charge bounds even when the nominal voltage limit passes. Increasing `N` can increase total energy at a fixed charge, so an allowed stage voltage alone is insufficient.

Where the capacitor specification requires transient or reverse-voltage checks, simulate the voltage **across each capacitor's two terminals** over the discharge and apply the specified withstand/reversal envelope. Its absolute voltage to ground is a separate insulation constraint. Changing the shaping resistors can affect these transient stresses even when the initial charge remains fixed.

An equivalent single generator capacitor and three predicted waveform outputs do not necessarily reveal every individual stage capacitor's transient stress. Use a sufficiently detailed circuit model or a verified conservative constraint for those checks. A model that predicts only `tf`, `tt` and load crest cannot independently certify internal capacitor voltage limits.

### 5.5 Where this constraint is enforced in the loop

After DP realises the candidate, apply the charging policy and check capacitor/stage charging limits before accepting or evaluating it as a feasible setting. Forward physics then checks energy and any represented internal transient stresses. ML evaluates the resulting load waveform for that same actual operating point.

If ML predicts an inadequate crest, the optimiser may propose revised required resistances or a different `N`. It may request a different charge only through the declared charging policy. Every revised charge and stage count must pass the hard limits again. Feasibility is enforced by the hardware/physics checks, not learned as an optional preference by ML.

The actual realised Rf/Rt values are fixed for a prediction; their effect on efficiency is a predicted response, not an independent voltage-setting mechanism.

## 6. Inventory DP Solver

### 6.1 What it solves

The solver receives required per-stage resistances and the stage inventory. It returns actual front/tail assemblies and their equivalent values:

```text
Input:  Rf_req, Rt_req, stage inventory, allowed topology, search limits
Output: Rf_actual, Rt_actual, A_f, A_t, component usage and errors
```

For positive subnetworks `a` and `b`:

```text
Series(a, b) = a + b
Parallel(a, b) = a*b/(a+b)
```

Larger assemblies are built recursively from smaller assemblies. This covers arbitrary nested two-terminal series–parallel wiring under the project assumption. Non-series–parallel bridge networks are outside this solver.

### 6.2 Count vectors and reuse of subproblems

For a catalogue with `m` types, a count vector `c = (c1, ..., cm)` records how many of each type are used. Each count is between zero and four. The front solver uses `m = 10`; the tail solver uses `m = 12`. Each uses its own catalogue and stock counts.

Store the achievable equivalent resistances for each count vector, with wiring recipes. Build results in order of total parts used:

1. One part gives one inventory value.
2. Split a larger count vector into every unordered pair of nonempty smaller vectors.
3. Combine their achievable values in series and parallel.
4. Remove duplicate nominal values within the same stock-consumption state.
5. Retain enough assembly information for subsequent feasibility checks.

This is dynamic programming: each smaller subproblem is solved once and its results are reused. Inventory counts prevent the same physical stock being used twice in a larger assembly.

Use exact fractions for nominal decimal resistance values when practical. Do not rely on arbitrary floating-point rounding to decide that two results are equal.

One recipe per value and count vector is sufficient for nominal resistance matching. For topology-dependent ratings or parasitics, keep alternatives or appropriate constraint metadata. Identical nominal resistance does not establish identical pulse behaviour.

### 6.3 Search budget versus available stock

Full enumeration of the available 40 front parts or 48 tail parts is not a practical default. Even the stock-consumption vectors are numerous, before circuit arrangements and resistance values are considered:

| Search catalogue | Available parts | All quantity vectors, including empty | Nonempty vectors using at most four parts |
| --- | --- | --- | --- |
| Front: 10 types | 40 | `5^10 = 9,765,625` | 1,000 |
| Tail: 12 types | 48 | `5^12 = 244,140,625` | 1,819 |

The last column counts quantity vectors, not unique circuits or equivalent resistances.

Start with a smaller search part limit `K`. Search all permitted assemblies with at most one, two, three, four, or more parts as required, increasing the limit within an explicit computation budget.

For `K = 4`, inspect the bounded front or tail region shown above. This does not impose a permanent four-part hardware limit; it is an initial tractable search region.

At a completed exact search limit, the solver can claim the closest nominal match within that region. It must not claim the closest across the complete 40-part front or 48-part tail inventory unless that larger region is actually certified. A tolerance-based early stop returns a satisfactory match, and an approximate search must be labelled approximate.

The prior expression `sum(i! × 2^(i−1))` is not a count of unique achievable resistances. It omits subset and general grouping choices and counts many duplicate descriptions. DP avoids relying on that counting estimate.

### 6.4 Resistance tolerances and inventory allocation

For each returned assembly, calculate:

```text
front resistance error = abs(Rf_actual − Rf_req)
tail resistance error  = abs(Rt_actual − Rt_req)
```

A tolerance can be expressed in ohms or as a fraction of the required value. Declare the rule and its numeric threshold separately for front and tail. These tolerances measure whether DP adequately realises the request; they are not the waveform-compliance tolerances.

For the workbook's separate catalogues:

```text
front_count[j] ≤ 4, for each of the 10 front types
tail_count[k]  ≤ 4, for each of the 12 tail types
```

Select each assembly independently from its respective permitted catalogue, enforcing its own quantities and resistance tolerance. For example, four 30 Ω front parts and four 30 Ω tail parts in the same stage satisfy the inventory rule. The presence of the same nominal value in both catalogues does not join their stock budgets. The two resulting assemblies are then evaluated together as one complete generator candidate.

If DP cannot realise a request within tolerance, it can expand its permitted search budget or reject that proposal so the optimiser proposes a different request. It must not silently use an outside-tolerance value and describe the request as satisfied.

### 6.5 Example of a constructible front assembly

Using the proposed inventory, a per-stage required front resistance of `49.52213922066368 Ω` can be approximated by:

```text
Front branch A: 100 Ω + 30 Ω = 130 Ω
Front branch B:  50 Ω + 30 Ω =  80 Ω
Connect the two branches in parallel:

Rf_actual = 130*80/(130+80) = 1040/21 ≈ 49.523809524 Ω
```

This uses two 30 Ω parts, one 50 Ω part and one 100 Ω part, giving about 0.003373% nominal resistance error. The bounded nominal search verified that this is a closest match using at most four parts from that proposed front inventory.

Under uniform-stage configuration, every active stage receives this same front assembly. Within the front catalogue, each stage has two 30 Ω parts and three each of its 50 Ω and 100 Ω parts left. This does not consume the separate tail catalogue.

The actual front value is fed into physics and ML. The required value is retained for traceability, not substituted back into prediction.

The existing [nominal DP prototype](resistor_inventory_search.py), [proposed front inventory](resistor_inventory_front.json), [12-type tail inventory](resistor_inventory_tail.json) and [saved example](resistor_search_example.json) demonstrate the single-assembly search. The prototype does not yet implement repeated-stage resource checks, ratings or every equal-resistance topology. These are implementation requirements for the architecture, not features claimed to exist already.

## 7. Feature preparation and ML Prediction Engine

### 7.1 Fixed settings in one prediction

For an evaluated candidate, the ML engine receives the realised `N`, `Rf_actual` and `Rt_actual`. It treats these as given settings and predicts the resulting waveform. It does not choose a stage count or resistor value during that prediction.

“Fixed” applies to a single evaluation. In the next cycle, the optimiser may change `N` or required resistance; DP then supplies a new realised configuration for a new ML evaluation.

The ML inputs must contain enough information to identify the electrical operating point. Alongside the realised settings, include charging voltage/policy, the declared load model and setup representation. Assembly features and physics outputs may be included if the selected model design uses them.

The environmental variables will be supplied later. The model should learn how the recorded conditions and realised settings relate to measured `tf`, `tt` and `V`. It cannot learn an explicit environmental effect from a variable that was never recorded or from variation that the training data never contained.

### 7.2 Two possible prediction interfaces

The ML architecture is not selected yet. Either of these interfaces can support the agreed loop:

```text
Direct prediction:
    ML(realised settings, load, setup, environment) → tf, tt, V

Physics correction:
    ML(realised settings, load, setup, environment, physics outputs)
        → corrections
    predicted outputs = physics outputs + corrections
```

Choose using validation, data coverage and engineering interpretability. The rest of the loop consumes the same three predicted outputs regardless of the selected interface. The source workbook's particular ML implementation does not bind this choice.

### 7.3 Feature extraction and selection

Feature extraction prepares useful inputs from recorded data. Feature selection determines which legitimate inputs improve prediction. The final environmental feature list remains open.

The workflow is:

1. Define field meanings, units, provenance and pre-shot availability.
2. Separate identifiers, realised controls, load/setup/environment features and measured outcomes.
3. Assign grouped training/validation/test partitions before fitting data-driven transformations.
4. Extract derived quantities and fit selection/preparation on training folds only.
5. Assess performance separately by impulse category, load family and operating region.
6. Save the accepted feature pipeline with the model.

The model may need a setting as an input even when that setting is fixed in an individual prediction. Variation in training data is how it learns the response when the optimiser changes the setting between evaluations.

Never use the measured outputs of the predicted shot as input features. Required resistances must not be mistaken for the actual applied settings. Avoid dropping meaningful controls simply because the initial synthetic dataset contains little variation in them.

```mermaid
flowchart LR
    A[Recorded actual settings, conditions and measured outputs] --> B[Assign grouped train, validation and test sets]
    B --> C[Fit feature preparation and selection on training data]
    C --> D[Fit candidate ML model]
    D --> E[Validate and accept a model version]
    E --> F[Save model and feature pipeline]
    F --> G[Apply unchanged pipeline to each optimisation candidate]
```

Preparation and selection must not learn from the final test set. Source: [scikit-learn leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html).

### 7.4 Use the same model throughout the loop

Keep one accepted ML model and feature pipeline fixed for a run. Each new realised candidate is evaluated by that same version under the same declared conditions. This makes changes in predicted deviation attributable to changes in the candidate rather than a moving model.

Recompute forward physics for every realised candidate, even if the chosen direct ML model does not consume the physics outputs. Physics still validates the assembly and provides an independent baseline.

Return prediction-support information alongside `tf`, `tt` and `V`. A model trained only on insulator-oriented examples cannot establish transformer prediction accuracy. A proposal outside supported load, stage, resistance, voltage or environmental coverage needs explicit handling rather than an unsupported claim of realistic behaviour.

## 8. Optimisation and Calibration Engine

### 8.1 Objective and outputs

The optimiser receives the evaluated realised configuration, ML predictions, deviations, constraints and history. It proposes:

```text
N_new
Rf_req_new per stage
Rt_req_new per stage
```

The charging policy then supplies or retains `U_ch`. The proposal goes back to the DP solver, not directly to the ML engine.

Retaining `N_new` enables the optimiser to distribute the required erected voltage across more active stages when a smaller count would require excessive charge per capacitor. It must not use reduced Rf/Rt as a substitute for checking charging voltage, and it must not assume that increasing `N` necessarily increases transfer efficiency. Evaluate the complete voltage/timing objective after inventory realisation and all hard constraints.

For lightning, minimise the absolute deviations:

```text
delta_front = abs(tf_predicted − 1.2 µs)
delta_tail  = abs(tt_predicted − 50 µs)
delta_crest = abs(V_predicted − V_required)
```

For another impulse category, use the selected profile's timing targets and definitions. Stage count must remain an integer within allowed limits; required resistances must be positive and appropriate for the equipment.

### 8.2 Combining errors without mixing units

Front/tail errors are times and crest error is a voltage. Adding their raw numbers is not a meaningful objective. Retain the three absolute errors and, if the selected optimiser needs one scalar, use tolerance-normalised absolute errors:

```text
e_front = delta_front / allowed_front_deviation
e_tail  = delta_tail  / allowed_tail_deviation
e_crest = delta_crest / allowed_crest_deviation

J = w_front*e_front + w_tail*e_tail + w_crest*e_crest
```

The scales must be positive and the weights declared. Acceptance still requires each output to satisfy its own tolerance. A good average must not conceal one unacceptable output or an invalid hardware configuration.

The optimisation model is to be selected later. Whatever method is chosen, it must use the realised candidate's error, account for integer/discrete changes and enforce feasibility. The final three configurations are ordered using this declared objective and acceptance priorities. This ordering compares complete generator setups; it does not require any particular ML or optimisation algorithm.

### 8.3 The objective is evaluated after DP

The realised output is a function of the inventory mapping:

```text
Proposed N, Rf_req, Rt_req
    → DP-realised N, Rf_actual, Rt_actual and assemblies
    → physics and ML prediction
    → measured objective in predicted-output space
```

The optimiser must evaluate this complete mapping. Optimising an ideal continuous resistance while ignoring the nearest constructible assembly can produce an improvement that disappears after DP.

The mapping can be stepped or flat: several required resistance values may produce the same actual assembly. The optimisation strategy must account for that behaviour rather than assume that every small required-resistance change produces a new waveform.

### 8.4 Retain the three best distinct evaluated configurations

Keep a history entry for every proposal and an ordered archive containing the **three best eligible distinct realised setups** found across all completed cycles. A later worse candidate must not overwrite a better earlier candidate. This is the best three within the evaluated search scope, not proof of the global three optimal configurations.

Define eligibility using constructibility, independent front/tail inventory limits, hard equipment constraints and model support. Keep waveform-tolerance status separately. Prefer candidates satisfying all waveform tolerances, then order within each acceptance class using the declared objective `J` and a deterministic tie-break rule. If fewer than three satisfy the waveform tolerances, remaining eligible entries may be shown with an explicit outside-tolerance status. Hardware-infeasible or unsupported candidates cannot fill recommendation slots.

Preserve stage count, both assembly recipes, actual resistances, charge voltage, conditions and model versions as one complete candidate record. Do not mix the front assembly of one evaluated setup with the tail assembly of another without evaluating that combination as a new candidate.

Deduplicate by the realised identity described in Section 9.2. Different requested resistances mapping to the same realised setup count as one configuration. Equivalent redrawings or reordered descriptions of the same assembly also count as one. Different wiring recipes with equal nominal resistance are separate alternatives only when they represent genuinely different physical assemblies; do not imply different ML-predicted behaviour unless the model represents their relevant differences.

After each eligible evaluation, insert or update its complete record, sort by the declared acceptance/objective policy and retain the best three distinct entries. Use the full history to guide subsequent proposals. All three recommendations are alternatives for the same scenario; inventory limits apply to each setup individually.

ML predictions can differ from measured results even when predicted errors are zero. Offering three evaluated setups gives the operator alternatives for subsequent verification or calibration. It does not itself quantify uncertainty or guarantee that any setup will produce the exact target. Present predicted values as predictions and keep actual measured results separately.

If fewer than three eligible distinct configurations have been found when the run stops, return the available one or two and the reason. If none are available, report the limiting constraints or unsupported coverage. Never fabricate or duplicate configurations to fill three slots.

## 9. Feedback, convergence and deterministic stopping

### 9.1 Full cycle

1. Physics proposes the initial stage count and required per-stage resistances.
2. DP constructs a feasible front/tail assembly pair within the resistance tolerances and search budget.
3. Physics recomputes the achievable waveform and verifies the actual configuration.
4. The fixed ML model predicts `tf`, `tt` and `V` for that configuration under the declared conditions.
5. Calculate deviations and update the archive of the three best distinct eligible candidates.
6. Evaluate stopping conditions.
7. If continuing, the optimiser proposes revised `N`, `Rf_req` and `Rt_req`.
8. Repeat from DP, including forward physics, with the new proposal.

The loop improves generator settings in software. It does not require performing a physical shot at every prediction cycle.

### 9.2 What “the result is the same” means

Use a realised-configuration identity containing:

```text
N + actual front assembly + actual tail assembly + U_ch
+ generator/load topology and fixed scenario/model versions
```

If the same realised configuration returns under the same context and deterministic predictor, reevaluating it gives the same outputs. Cache the result and treat the repetition as evidence of stagnation. Different requested values mapping to that same realised configuration do not represent an improvement.

Equal nominal Rf/Rt alone is not always identical configuration: different wiring can have different ratings or parasitics. Candidate identity should include assembly recipes where those effects are represented.

Predicted deviations may also be effectively unchanged without an identical configuration. Define numerical thresholds, rather than relying on exact floating-point equality. The run can stop after a declared number of cycles without a meaningful improvement in the best objective. If the chosen strategy deliberately explores plateaus, allow a declared stagnation window rather than stopping on its first repeated value.

### 9.3 Stopping rules

| Rule | Condition | Reported meaning |
| --- | --- | --- |
| Three satisfactory setups found | Three distinct setups each meet all three waveform bounds and required support/feasibility checks | Three satisfactory predicted configurations found |
| Repeated realised configuration | The strategy returns an already evaluated configuration without an allowed new exploration step | Stagnation under the current search strategy |
| Negligible improvement | Best objective improves by less than a declared threshold over a declared window | Converged/stalled within that criterion, not proof of global optimum |
| Maximum iterations | The deterministic overall proposal/cycle cap is reached | Search budget exhausted |
| DP budget exhausted | Constructibility cannot be resolved within its allowed effort | Proposal unresolved or rejected; bounded handling required |
| No feasible/supported candidate | Constraints or data coverage prevent meaningful evaluation | Explain the blocking conditions |

Finding a single predicted exact match does not trigger the three-setup success condition. Continue exploring distinct setups within the declared budgets. Stagnation and deterministic maximum counts may still end the run with fewer than three; report this explicitly. Track improvement in archive membership and quality as well as the leading objective, so the second and third recommendations can improve even when the first remains unchanged.

Store the stop reason and the limits used. A repeated candidate or negligible improvement does not establish that no better configuration exists elsewhere.

For reproducible stopping, fix maximum counts, model versions, search policies and random seeds where applicable. If an ML predictor is stochastic, use a declared reproducible inference/aggregation policy before comparing deviations.

### 9.4 Conceptual control loop

```text
proposal = physics.propose_initial_configuration(request)
top_three = empty ordered archive
history = empty

for cycle in range(maximum_proposals):
    actual = dp.realise_front_and_tail(proposal, separate_inventories, dp_limits)
    if actual is not constructible within the declared resistance tolerances:
        record rejection
        proposal = optimiser.propose_next(request, history)
        continue

    actual.U_ch = apply_declared_charging_policy(actual, request)
    if actual.U_ch exceeds an applicable capacitor or stage charging limit:
        record voltage-limit rejection and stage-count feasibility information
        proposal = optimiser.propose_next(request, history)
        continue
    baseline = physics.predict_and_check(actual, request)
    if baseline violates a required hardware constraint:
        record rejection
        proposal = optimiser.propose_next(request, history)
        continue

    if actual identity already evaluated:
        reuse cached evaluation
        apply declared repeated-candidate/stagnation policy
    else:
        prediction = fixed_ml.predict(actual, baseline, request.conditions)
        errors = compare_to_target(prediction, request.target)
        record full evaluation
        insert eligible candidate, deduplicate by realised identity, keep best three

    if three distinct supported candidates meet predicted tolerances
       or declared stagnation criterion reached:
        break
    proposal = optimiser.propose_next(request, history)

return top_three, per-candidate tolerance status, search scope and stop reason
```

Every failed branch remains bounded by the overall proposal cap. If `top_three` is empty, return explained failure rather than inventing a configuration. If it contains only one or two eligible distinct candidates when the budget or stopping criterion is reached, return those with an explicit shortfall reason.

## 10. Walkthrough of the architecture

Consider a lightning request for 1.2/50 µs and a specified crest voltage, with one fixed load model and one fixed environmental scenario.

The Physics Engine proposes an allowed `N` and required front/tail resistances per stage. For illustration, suppose the front requirement is `49.522139 Ω`. DP selects the `49.523810 Ω` front assembly described in Section 6. It also selects a tail assembly that meets its own resistance tolerance within the independent tail catalogue limits.

The Physics Engine now evaluates the actual assemblies repeated across `N` stages, using the declared charging policy. Its waveform estimate is the baseline for that realised candidate.

The ML engine receives those same realised settings and the scenario features. Suppose its predictions have a front that is too slow, a tail that is too long and a crest that is above the requested value. These deviations describe the current candidate; the ML engine does not modify the resistors to repair them.

The optimiser proposes a revised `N` and required per-stage resistances. Its exact update rule remains undecided. DP again maps these required values to constructible assemblies. Physics and the same ML model evaluate the new actual candidate, and the loop compares its deviations with the target.

Three outcomes are possible:

- The new actual configuration qualifies for the top three, so it enters the archive and displaces the worst retained entry if necessary.
- It performs worse than the retained top three, so the earlier three remain stored; the new evaluation remains in the history.
- The required-value change maps back to the same actual assemblies and stage count/charge, so the realised candidate is unchanged and the stagnation policy applies.

If three distinct candidates reach the thresholds, return those best satisfactory configurations. If the maximum iterations or stagnation condition is reached first, return up to three best supported hardware-feasible evaluated configurations with individual deviations and tolerance statuses. The dashboard never substitutes ideal requested resistance for the selected wiring.

This walkthrough illustrates the control flow. It does not assert a measured improvement or prescribe an optimiser.

## 11. Calibration and model development

### 11.1 Optimisation cycles and calibration have different evidence

The component retains the agreed name “Optimisation and Calibration Engine”. Inside it, distinguish:

- **Configuration optimisation:** change generator settings using the fixed forward predictor to reduce deviations.
- **Model calibration:** use actual measured waveforms to update circuit parameters, learned corrections or other model quantities.

The software loop can find settings that its model predicts will work. Feeding predictions back into the same predictor does not create new evidence about the laboratory. Prediction-only cycles must not be treated as new measured training records.

### 11.2 Measured feedback

After reviewing a recommendation, the engineer performs an authorised laboratory shot. Record actual stage count, actual resistor assemblies, charging voltage, load, setup, environmental readings and the measured waveform.

Evaluate `tf`, `tt` and `V` from that trace using the selected timing convention. Compare the measurement with the stored prediction and physics baseline. Eligible measurements can support calibration and training of a new model version.

```mermaid
flowchart TB
    A[Accepted fixed models] --> B[Bounded software optimisation loop]
    B --> C[Recommended actual stage configuration]
    C --> D[Engineer performs laboratory shot]
    D --> E[Store actual settings, conditions and measured waveform]
    E --> F[Evaluate measurement and model discrepancy]
    F --> G[Calibrate physics and train or update ML offline]
    G --> H[Validate new versions on reserved measured cases]
    H -->|Accepted| A
```

Do not change the deployed ML model midway through a candidate-comparison run. A newly accepted version starts a new run or requires reevaluation of stored candidates. If the ML model learns residuals and the physics baseline changes, regenerate residual labels against the new baseline.

### 11.3 Validation requirements

Compare physics-only and ML predictions on untouched cases. Evaluate front/peak, tail and crest separately, including load family and operating region. Evaluate whether recommended actual configurations achieve the predicted results in measurements.

Useful evidence includes absolute errors in µs/kV, tolerance-normalised errors, performance on held-out objects/configurations and the frequency of predicted acceptance followed by measured failure. Prediction uncertainty, if used, must be validated on relevant data. Three separate per-output intervals do not automatically imply a stated joint coverage for all outputs.

The environmental feature set, training model and uncertainty method remain decisions for later model development.

## 12. Records and interfaces

| Record | Required contents |
| --- | --- |
| Test request | Target profile/voltage, load and terminal model, setup, environmental scenario, hardware/inventory versions, charging policy |
| Required proposal | Integer `N`, `Rf_req`, `Rt_req`, proposal source and iteration |
| DP realisation | `Rf_actual`, `Rt_actual`, front/tail recipes, per-type usage, matching errors, part/search limits and guarantee scope |
| Actual generator candidate | Realisation plus `N`, `U_ch`, approved stage topology and repeated-stage resource interpretation |
| Physics evaluation | Predicted parameters/trace, stage/total stored energy, capacitor charging-voltage margin, represented transient/reverse stresses, feasibility checks, assumptions and physics version |
| ML evaluation | Predicted `tf`, `tt`, `V`, support/uncertainty metadata and fixed model/feature versions |
| Recommendation archive | Up to three distinct complete candidate records, selection order, per-candidate feasibility/support/tolerance status and any shortfall reason |
| Optimisation history | Candidate identity, target deviations, objective, rejection reasons, top-three archive, selection order and stop criterion |
| Measured shot | Actual applied settings/conditions, raw waveform, extracted outputs, instrument metadata and quality flags |

The optimiser uses required resistances as proposal variables. The predictor uses actual realised resistances as operating inputs. This boundary must be explicit in field names and interfaces.

Store requested and actually applied laboratory settings separately. An operator adjustment must not be recorded as if the original recommendation was used.

## 13. Dashboard output

The exact layout is deferred. The result must nevertheless communicate:

- Selected number of active stages.
- Per-stage actual front and tail resistance.
- Front/tail wiring recipes and component quantities, repeated identically across stages.
- Charging voltage and the policy used to determine it.
- Applicable capacitor/stage voltage limit and remaining charging-voltage margin.
- Target, physics estimate and ML prediction for front/peak, tail and crest.
- Absolute and normalised deviations and tolerance status.
- Hardware feasibility and model-support status.
- Iterations completed, search limits and stopping reason.
- Relevant hardware, inventory, feature, ML and physics versions.

Present the **three best distinct evaluated setups**, ordered using the declared objective and acceptance priorities. Show the listed information separately for each setup. If only one or two eligible distinct setups were found, show those and explain the shortfall; do not duplicate an entry to fill three positions. Each is an alternative complete setup for the same equipment, load and environmental scenario, rather than three setups to build simultaneously.

A plotted waveform needs a declared origin: numerical physics trace, measured trace or illustrative reconstruction. Three summary parameters do not uniquely identify ringing, overshoot or the complete waveform shape.

```mermaid
flowchart LR
    A[Three best distinct full candidate records] --> B[Stages, charging voltage and repeated per-stage assemblies]
    A --> C[Predicted waveform outputs and target deviations]
    A --> D[Feasibility, support and tolerance status]
    A --> E[Search scope, iterations and stop reason]
    B --> F[Dashboard layout to be decided]
    C --> F
    D --> F
    E --> F
```

## 14. Implementation sequence and checks

1. **Define equipment and scenario profiles.** Verify stage ratings, resistor stock scope, permitted assemblies, load models, waveform definitions and charging policy.
2. **Implement initial and forward physics.** Keep required per-stage resistance separate from actual settings and evaluate candidate-driven voltage/timing.
3. **Implement DP realisation.** Use bounded exact nominal search, independent front and tail stock checks, wiring reconstruction and explicit resistance tolerance outcomes.
4. **Prepare data and features.** Preserve actual settings, load/setup distinctions and measured outcomes; the environmental variables will be added after extraction/assessment.
5. **Select and validate the ML model.** Keep its interface fixed and ensure relevant settings and scenario coverage.
6. **Implement the chosen optimiser.** Consume realised-candidate predictions, propose `N/Rf_req/Rt_req`, retain the three best distinct complete results and enforce all stopping rules.
7. **Build the agreed dashboard.** Present actual assemblies and their predicted performance with clear status and provenance.
8. **Validate with measurements and calibrate.** Introduce model updates only after separate measured-data evaluation.

Checks that protect the agreed architecture:

- Four-per-type quantities are enforced correctly, and no requirement to use all 40 front or 48 tail parts is introduced.
- Every active stage repeats the selected front/tail assembly pair.
- Front and tail each allow four parts per type independently; global-versus-per-stage stock is handled correctly.
- Nominal DP results cover the declared bounded series–parallel search and preserve a buildable witness.
- Outside-tolerance or unresolved DP proposals cannot bypass the loop's limits.
- Actual resistance and charging voltage drive forward predictions.
- Changing `N` triggers complete physics reevaluation.
- A target requiring excessive per-stage charging voltage is rejected at that stage count; any larger-N proposal is reevaluated rather than assumed feasible.
- Decreasing Rf/Rt is never assumed to raise initial capacitor charging voltage automatically.
- Capacitor charging limits, applicable transient/reverse-voltage limits and stage/total energy limits remain separate checks.
- Load R/L/C, generator shaping resistance and setup inductance remain distinct.
- Each candidate is evaluated using the same ML/feature versions and scenario.
- Repeated realised candidates are cached and handled by the declared stagnation policy.
- The three best distinct complete evaluated candidates survive later worse candidates; repeated proposals never occupy multiple recommendation slots.
- The maximum proposal/cycle count remains effective even when proposals fail before ML.
- Predicted outcomes never become measured training labels.
- Final output distinguishes threshold success, stagnation, exhausted budget and lack of feasible candidates.

## 15. Source status and decisions still required

The architecture above follows the latest project decisions. The source workbook and written statement provide context and provisional data, not a required ML or optimisation implementation.

Local sources:

- [HV IG Problem Statement.pdf](HV%20IG%20Problem%20Statement.pdf): impulse-testing objective, inputs/outputs, variable setup parameters and equipment constraints.
- [Hybrid_Physics_ML_Impulse_Generator_Optimiser.xlsx](Hybrid_Physics_ML_Impulse_Generator_Optimiser.xlsx): proposed inventory, initial data and the numerical resistance example.

Section 3.3 defines source precedence: workbook input fields are primary, frontend values are used as supplied, and only the two stored-energy limits and capacitance fallback are taken from the document. All other input defaults come from the workbook or explicit project/model decisions. Supplied capacitance remains authoritative; energy and supplied voltage constraints can still make a run infeasible. Its synthetic records do not establish laboratory prediction accuracy or general RLC/transformer coverage, and its calculator's inductance input describes stray inductance rather than load inductance.

The broader load scope, uniform-stage/per-stage inventory assumptions and independent front/tail limits come from the assigners’ guidance and the project team’s decisions. The latest project decision requires the three best distinct setups from the evaluated optimisation history. This output requirement does not adopt the workbook’s proposed ML architecture.

Remaining decisions:

| Decision | Current status |
| --- | --- |
| Verified hardware and generator topology | To be confirmed against the intended equipment |
| Front/tail stock scope | Independent 40-part front and 48-part tail catalogues per stage; four copies per type in each catalogue |
| Charging voltage policy | Fixed or recomputed policy to be selected |
| Capacitor/stage voltage and energy constraints | Hard constraints required; equipment-specific charging and transient/reversal limits to be verified |
| Front/tail DP tolerances and effort limits | To be set |
| Environmental feature set and preparation | To be provided after feature extraction/assessment |
| ML algorithm and direct/correction interface | To be selected and validated |
| Optimisation algorithm and objective preferences | To be selected |
| Waveform tolerances, stagnation window and maximum iterations | To be set |
| Supported load models and terminal conditions | To be declared and validated |
| Dashboard layout | To be decided |

The document specifies the intended workflow and interfaces. It does not claim that the complete application, complete inventory/rating validator, validated ML model or optimiser has already been implemented.
