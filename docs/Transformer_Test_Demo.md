# Independent transformer impulse-test demonstration

Implemented 11 October 2026. This is a separate **Transformer test demo** workspace tab. It illustrates the pass reference and three waveform shapes from the user's image. It is independent of generator configuration, physics predictions, residual ML, calibration, inventory, constraints, measurements and Gemini.

## Behaviour

Click **Generate random waveform**. One of four fixed presets is selected with equal probability and its classification is shown above the graph. Repeated selections are allowed; randomness does not imply a change in a preset's shape. Equal selection probabilities are demonstration choices, not measured transformer failure probabilities. The classification is the preset's label, not the result of a learned classifier or fault-diagnosis rule.

The graph plots time in microseconds against voltage in per unit, normalised to the reference crest. **Full impulse** shows 0–80 µs; **Front detail** shows 0–10 µs. Both views use the same samples. No graph is generated until the button is pressed. Switching workspace tabs preserves the chosen waveform and existing dashboard state. A browser reload starts the demonstration over.

## Fixed templates

Let t be time in µs, a=0.014657593003681092 and b=2.4742258641400126. The independent reference shape is:

```text
t_peak = ln(b/a)/(b-a)
peak = exp(-a*t_peak) - exp(-b*t_peak)
f(t) = [exp(-a*t) - exp(-b*t)] / peak
```

The constants were fitted once for this display template to conventional front T1≈1.2 µs and half-value tail T2≈50 µs. Runtime generation does not call a physics solver, load generator inputs or use a previous model prediction. This template is an illustration, not standards certification or an actual test record.

| Preset label | Fixed shape |
| --- | --- |
| Pass · reference waveform | f(t) |
| Front breakdown | f(t) before 0.8 µs; f(0.8)×exp(-(t−0.8)/0.12) afterward |
| Tail breakdown · chopped wave | f(t) before 15 µs; f(15)×exp(-(t−15)/0.5) afterward |
| Inter-turn / partial breakdown | f(t) before 5 µs; f(t)+0.17×exp(-(t−5)/20)×sin(π(t−5)) afterward |

Every selected preset returns the same 4,001 samples at t=i/50 µs for i=0…4000. No random noise, severity, event time or model output is added. The failure descriptions explain the supplied illustrations; a measured ringing waveform alone does not establish the fault cause.

## Independent deliverables and checks

| Deliverable | Purpose |
| --- | --- |
| `frontend/src/lib/failureDemo.js` | Fixed metadata, deterministic waveform functions/sampling and random preset selector; no project-model/API imports |
| `frontend/src/components/FailureWaveformDemo.jsx` | Label above SVG, sample generation button, range controls, plain-language explanations and case catalogue |
| `frontend/src/App.jsx` | Accessible workspace tabs, keyboard navigation and preserved dashboard/demo states |
| `frontend/tests/failure-demo.test.jsx` | Selection boundaries/repeats, waveform repeatability, failure shapes, classification/curve consistency, no-network generation, offline tab use and state preservation |

Stack: React 19, JavaScript `Math`, native SVG, existing Tailwind 4/CSS, lucide-react icons, Vitest and Testing Library. No backend endpoints, Python dependencies or ML artifacts are needed for this feature. The existing dashboard still performs its normal bootstrap when the application loads; entering/generating in this demo does not call any backend service.

Validation: 32 frontend tests passed and production build passed. Browser verification exercised repeated pass selections followed by front breakdown and its 10 µs close-up; no browser errors were reported. Preview: `verification/transformer-failure-demo.jpg`. Test report: `verification/failure-demo-frontend-tests.txt`.
