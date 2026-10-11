// Independent illustrative presets. No physics/ML/calibration inputs or API calls.
export const DEMO_CASES = Object.freeze([
  Object.freeze({
    id: "pass",
    classification: "Pass · reference waveform",
    title: "Reference: 1.2/50 µs wave (Pass)",
    explanation:
      "The pulse rises smoothly to its crest and decays without a sudden collapse or added ringing.",
    illustration: "Illustrates an intact response in this demonstration.",
    outcome: "Pass example",
    color: "#286b65",
    eventTimeUs: null,
    eventLabel: null,
  }),
  Object.freeze({
    id: "front-breakdown",
    classification: "Front breakdown",
    title: "Case 1: Front Breakdown",
    explanation:
      "The voltage collapses on the rising front, before the normal crest.",
    illustration: "Illustrates an early breakdown such as insulation puncture.",
    outcome: "Failure example",
    color: "#a13f38",
    eventTimeUs: 0.8,
    eventLabel: "Front collapse",
  }),
  Object.freeze({
    id: "tail-breakdown",
    classification: "Tail breakdown · chopped wave",
    title: "Case 2: Tail Breakdown (Chopped Wave)",
    explanation:
      "The pulse reaches its crest, then suddenly collapses during the tail.",
    illustration:
      "Illustrates chopping such as flashover across an insulator or air gap.",
    outcome: "Failure example",
    color: "#a16b20",
    eventTimeUs: 15,
    eventLabel: "Tail collapse",
  }),
  Object.freeze({
    id: "inter-turn",
    classification: "Inter-turn / partial breakdown",
    title: "Case 3: Inter-turn / Partial Breakdown",
    explanation:
      "Damped high-frequency ringing is added to the decaying pulse.",
    illustration:
      "Illustrates the ringing example associated with winding faults in the supplied reference.",
    outcome: "Failure example",
    color: "#795c89",
    eventTimeUs: 5,
    eventLabel: "Ringing begins",
  }),
]);

// Fresh illustrative reference fit in microseconds: conventional T1=1.2 and T2=50.
// This is a fixed display template, not the application physics engine.
const ALPHA = 0.014657593003681092;
const BETA = 2.4742258641400126;
const PEAK_TIME = Math.log(BETA / ALPHA) / (BETA - ALPHA);
const PEAK = Math.exp(-ALPHA * PEAK_TIME) - Math.exp(-BETA * PEAK_TIME);
export function referenceVoltage(timeUs) {
  return (Math.exp(-ALPHA * timeUs) - Math.exp(-BETA * timeUs)) / PEAK;
}
export function demoVoltage(caseId, timeUs) {
  if (!DEMO_CASES.some((item) => item.id === caseId))
    throw new Error("Unknown demo case");
  if (!Number.isFinite(timeUs) || timeUs < 0)
    throw new Error("Invalid demo time");
  const base = referenceVoltage(timeUs);
  if (caseId === "front-breakdown" && timeUs >= 0.8)
    return referenceVoltage(0.8) * Math.exp(-(timeUs - 0.8) / 0.12);
  if (caseId === "tail-breakdown" && timeUs >= 15)
    return referenceVoltage(15) * Math.exp(-(timeUs - 15) / 0.5);
  if (caseId === "inter-turn" && timeUs >= 5)
    return (
      base +
      0.17 * Math.exp(-(timeUs - 5) / 20) * Math.sin(Math.PI * (timeUs - 5))
    );
  return base;
}
export function sampleDemo(caseId) {
  // Exactly the same 4,001 samples for each occurrence of the same preset.
  return Array.from({ length: 4001 }, (_, i) => {
    const timeUs = i / 50;
    return { timeUs, voltagePu: demoVoltage(caseId, timeUs) };
  });
}
export function chooseDemoCase(random = Math.random) {
  const draw = random();
  if (!Number.isFinite(draw) || draw < 0 || draw >= 1)
    throw new Error("Invalid random draw");
  return DEMO_CASES[Math.floor(draw * DEMO_CASES.length)];
}
