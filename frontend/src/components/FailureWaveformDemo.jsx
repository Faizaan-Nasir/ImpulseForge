import { useState } from "react";
import { Shuffle, Activity } from "lucide-react";
import { chooseDemoCase, DEMO_CASES, sampleDemo } from "../lib/failureDemo.js";

function DemoPlot({ example, points, frontDetail }) {
  const end = frontDetail ? 10 : 80;
  const W = 1080,
    H = 410,
    left = 72,
    right = 1058,
    top = 32,
    bottom = 346;
  const x = (t) => left + (t / end) * (right - left);
  const y = (v) => bottom - (v / 1.2) * (bottom - top);
  const path = points
    .filter((p) => p.timeUs <= end)
    .map(
      (p, i) =>
        `${i ? "L" : "M"}${x(p.timeUs).toFixed(3)},${y(p.voltagePu).toFixed(3)}`,
    )
    .join(" ");
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`${example.title}. Voltage in per unit against time in microseconds. Synthetic demonstration.`}
    >
      <title>{example.title}</title>
      <desc>
        {example.explanation} A fixed illustrative waveform, not a measured
        transformer test.
      </desc>
      <rect
        x={left}
        y={top}
        width={right - left}
        height={bottom - top}
        fill="white"
        stroke="#cbc7bd"
      />
      {Array.from({ length: 9 }, (_, i) => (i * end) / 8).map((t) => (
        <g key={t}>
          <line
            x1={x(t)}
            y1={top}
            x2={x(t)}
            y2={bottom}
            stroke="#e2dfd8"
            strokeDasharray="5 4"
          />
          <text x={x(t)} y={bottom + 24} textAnchor="middle" className="mono">
            {Number(t.toFixed(2))}
          </text>
        </g>
      ))}
      {[0, 0.2, 0.4, 0.6, 0.8, 1, 1.2].map((v) => (
        <g key={v}>
          <line
            x1={left}
            y1={y(v)}
            x2={right}
            y2={y(v)}
            stroke="#e2dfd8"
            strokeDasharray="5 4"
          />
          <text x={left - 13} y={y(v) + 5} textAnchor="end" className="mono">
            {v.toFixed(1)}
          </text>
        </g>
      ))}
      {example.eventTimeUs !== null && example.eventTimeUs <= end && (
        <g>
          <line
            x1={x(example.eventTimeUs)}
            y1={top}
            x2={x(example.eventTimeUs)}
            y2={bottom}
            stroke={example.color}
            strokeDasharray="4 6"
            opacity=".65"
          />
          <text
            x={Math.max(
              left + 12,
              Math.min(right - 170, x(example.eventTimeUs) + 10),
            )}
            y={top + 20}
            fill={example.color}
          >
            {example.eventLabel} · {example.eventTimeUs} µs
          </text>
        </g>
      )}
      <path
        d={path}
        fill="none"
        stroke={example.color}
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <text x={(left + right) / 2} y={H - 16} textAnchor="middle">
        Time (µs)
      </text>
      <text
        transform={`translate(20 ${(top + bottom) / 2}) rotate(-90)`}
        textAnchor="middle"
      >
        Voltage (p.u.)
      </text>
    </svg>
  );
}
export default function FailureWaveformDemo() {
  const [example, setExample] = useState(null),
    [points, setPoints] = useState([]),
    [drawCount, setDrawCount] = useState(0),
    [frontDetail, setFrontDetail] = useState(false);
  const generate = () => {
    const selected = chooseDemoCase();
    setExample(selected);
    setPoints(sampleDemo(selected.id));
    setDrawCount((n) => n + 1);
    setFrontDetail(false);
  };
  return (
    <main
      className="demo-workspace"
      aria-label="Independent transformer waveform demonstration"
    >
      <section className="card demo-intro">
        <div>
          <span className="eyebrow">Independent demonstration</span>
          <h2>Transformer impulse-test outcomes</h2>
          <p>
            Generate one of four fixed example waveforms from the reference: a
            pass, front breakdown, tail breakdown or inter-turn / partial
            breakdown.
          </p>
        </div>
        <button type="button" className="btn primary" onClick={generate}>
          <Shuffle size={17} />
          Generate random waveform
        </button>
        <p className="hint demo-scope">
          Illustrative only. Each example has an equal selection chance; these
          chances do not represent transformer failure rates. The waveform and
          its preset classification stay identical whenever that example is
          selected.
        </p>
      </section>
      <section className="card demo-chart" aria-label="Demonstration waveform">
        <div className="demo-classification" aria-live="polite">
          <div>
            <span className="eyebrow">Classification · preset label</span>
            <h2>
              {example?.classification ||
                "Generate a waveform to see its classification"}
            </h2>
          </div>
          {example && (
            <span className={`pill ${example.id === "pass" ? "good" : "bad"}`}>
              {example.outcome}
            </span>
          )}
        </div>
        {example ? (
          <>
            <div className="demo-plot-toolbar">
              <span className="sub">
                Demo draw #{drawCount} · {example.title}
              </span>
              <div className="seg" role="group" aria-label="Demo plot range">
                <button
                  type="button"
                  aria-pressed={!frontDetail}
                  onClick={() => setFrontDetail(false)}
                >
                  Full impulse · 80 µs
                </button>
                <button
                  type="button"
                  aria-pressed={frontDetail}
                  onClick={() => setFrontDetail(true)}
                >
                  Front detail · 10 µs
                </button>
              </div>
            </div>
            <DemoPlot
              example={example}
              points={points}
              frontDetail={frontDetail}
            />
            <div className="demo-description">
              <p>{example.explanation}</p>
              <p className="hint">
                {example.illustration} Actual fault diagnosis requires measured
                test evidence.
              </p>
            </div>
          </>
        ) : (
          <div className="demo-empty">
            <Activity size={38} />
            <p>No demonstration generated yet.</p>
            <span className="hint">Use “Generate random waveform” above.</span>
          </div>
        )}
      </section>
      <section
        className="demo-case-catalogue"
        aria-label="Possible demonstration classifications"
      >
        {DEMO_CASES.map((item) => (
          <article
            className={`card demo-case ${item.id === example?.id ? "selected" : ""}`}
            key={item.id}
          >
            <span className="eyebrow">{item.outcome}</span>
            <h3>{item.classification}</h3>
            <p>{item.explanation}</p>
          </article>
        ))}
      </section>
      <p className="hint">
        Voltage is normalised to the reference crest: 1 p.u. = the example
        reference peak. This tab uses its own fixed templates and makes no
        physics, ML, calibration or Gemini requests.
      </p>
    </main>
  );
}
