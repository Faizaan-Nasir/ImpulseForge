import { useEffect, useRef, useState } from "react";
import { Plus, Minus } from "lucide-react";
import { number } from "../lib/config.js";
import { Segment } from "./Controls.jsx";
export default function Waveform({ bundle, selectedId, rank }) {
  const [view, setView] = useState("full"),
    [domain, setDomain] = useState(null),
    [all, setAll] = useState(false),
    [hover, setHover] = useState(null),
    [drag, setDrag] = useState(null);
  const plotRef = useRef(null),
    [plotWidth, setPlotWidth] = useState(800);
  useEffect(() => {
    if (!plotRef.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width > 0) setPlotWidth(Math.max(320, width));
    });
    observer.observe(plotRef.current);
    return () => observer.disconnect();
  }, []);
  const curves =
    bundle?.curves?.filter(
      (c) => c.voltage_V && c.reconstruction_status === "complete",
    ) || [];
  const target = curves.find((c) => c.curve_id === "target"),
    selected = selectedId
      ? curves.find((c) => c.candidate_id === selectedId)
      : null;
  const times = bundle?.time_s || [];
  const valid = times.length > 0 && curves.length > 0;
  const fullEnd = valid
    ? Math.min(
        times.at(-1),
        Math.max(...curves.map((c) => c.metrics.tail_s)) * 2.5,
      )
    : 125e-6;
  const frontEnd = valid
    ? Math.max(...curves.map((c) => c.metrics.front_s)) * 8
    : 10e-6;
  const range = domain || [0, view === "front" ? frontEnd : fullEnd];
  const maxV = valid
    ? Math.max(...curves.map((c) => c.metrics.crest_V)) * 1.1
    : 1500000;
  const W = plotWidth,
    H = 330,
    L = 64,
    R = W - 25,
    T = 22,
    B = 283;
  const x = (v) => L + ((v - range[0]) / (range[1] - range[0])) * (R - L),
    y = (v) => B - (v / maxV) * (B - T);
  const shown = curves.filter(
    (c) => c.curve_id === "target" || all || c.candidate_id === selectedId,
  );
  const colors = ["#3b5d8a", "#65856a", "#795c89"];
  const zoom = (factor) => {
    const mid = (range[0] + range[1]) / 2,
      half = ((range[1] - range[0]) * factor) / 2;
    setDomain([Math.max(0, mid - half), Math.min(fullEnd, mid + half)]);
  };
  const coordinate = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    return Math.max(L, Math.min(R, ((e.clientX - rect.left) / rect.width) * W));
  };
  const timeFor = (px) =>
    range[0] + ((px - L) / (R - L)) * (range[1] - range[0]);
  const pointerMove = (e) => {
    if (!valid) return;
    const t = timeFor(coordinate(e));
    let index = 0;
    while (index < times.length - 1 && times[index] < t) index++;
    setHover({ index, px: coordinate(e) });
  };
  const path = (c) => {
    const points = times
      .map((t, i) => [t, c.voltage_V[i]])
      .filter(([t, v]) => t >= range[0] && t <= range[1] && Number.isFinite(v));
    const step = Math.max(1, Math.floor(points.length / 900));
    return points
      .filter((_, i) => i % step === 0 || i === points.length - 1)
      .map(
        ([t, v], i) => `${i ? "L" : "M"}${x(t).toFixed(2)},${y(v).toFixed(2)}`,
      )
      .join(" ");
  };
  const marks = selected?.fit?.landmarks;
  return (
    <section className="card" aria-label="Waveform comparison">
      <div className="card-head">
        <h2>Waveform comparison</h2>
        <span className="sub">
          {selected ? `Case #${rank}` : "Target reference"} ·{" "}
          {view === "front" ? "front detail" : "full impulse"}
        </span>
      </div>
      <div className="toolbar">
        <Segment
          label="Plot range"
          value={view}
          onChange={(v) => {
            setView(v);
            setDomain(null);
          }}
          options={[
            ["full", "Full impulse"],
            ["front", "Front detail"],
          ]}
        />
        <div className="zoom">
          <button
            type="button"
            className="iconbtn"
            aria-label="Zoom in"
            onClick={() => zoom(0.6)}
          >
            <Plus size={14} />
          </button>
          <button
            type="button"
            className="iconbtn"
            aria-label="Zoom out"
            onClick={() => zoom(1.6)}
          >
            <Minus size={14} />
          </button>
          <button
            className="btn small"
            type="button"
            onClick={() => setDomain(null)}
          >
            Reset
          </button>
        </div>
      </div>
      <div className="legend">
        <span>
          <i className="ln target" />
          Target ·{" "}
          {target
            ? `${number(target.metrics.front_s * 1e6, 1)}/${number(target.metrics.tail_s * 1e6, 0)} µs, ${number(target.metrics.crest_V / 1000, 0)} kV`
            : "awaiting backend"}
        </span>
        {shown
          .filter((c) => c.curve_id !== "target")
          .map((c) => (
            <span key={c.curve_id}>
              <i
                className="ln"
                style={{ borderColor: colors[(c.rank - 1) % 3] }}
              />
              {c.origin === "ml_parameter_reconstruction"
                ? "ML corrected"
                : "Physics baseline"}{" "}
              · Case #{c.rank}
            </span>
          ))}
      </div>
      <label className="hint flex items-center gap-2 mb-2">
        <input
          type="checkbox"
          checked={all}
          onChange={(e) => setAll(e.target.checked)}
        />
        Compare all evaluated cases
      </label>
      <div className="plot" ref={plotRef}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label="Target and predicted impulse waveforms, voltage in kilovolts against time in microseconds"
          onPointerMove={pointerMove}
          onPointerLeave={() => setHover(null)}
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId);
            setDrag(coordinate(e));
          }}
          onPointerUp={(e) => {
            if (drag !== null && Math.abs(coordinate(e) - drag) > 12) {
              setDomain([
                timeFor(Math.min(drag, coordinate(e))),
                timeFor(Math.max(drag, coordinate(e))),
              ]);
            }
            setDrag(null);
          }}
        >
          <defs>
            <clipPath id="plot-clip">
              <rect x={L} y={T} width={R - L} height={B - T} />
            </clipPath>
          </defs>
          <rect
            x={L}
            y={T}
            width={R - L}
            height={B - T}
            fill="#fcfcfa"
            stroke="var(--line-strong)"
          />
          {Array.from({ length: 21 }, (_, i) => {
            const px = L + (i * (R - L)) / 20;
            return (
              <line
                key={`mx${i}`}
                x1={px}
                x2={px}
                y1={T}
                y2={B}
                stroke={i % 4 === 0 ? "#e6e3dc" : "#f1efea"}
              />
            );
          })}
          {Array.from({ length: 11 }, (_, i) => {
            const py = T + (i * (B - T)) / 10;
            return (
              <line
                key={`my${i}`}
                x1={L}
                x2={R}
                y1={py}
                y2={py}
                stroke={i % 2 === 0 ? "#e6e3dc" : "#f1efea"}
              />
            );
          })}
          {Array.from({ length: 6 }, (_, i) => {
            const t = range[0] + (i * (range[1] - range[0])) / 5;
            return (
              <text
                key={i}
                x={x(t)}
                y={B + 20}
                textAnchor="middle"
                fontSize="12"
                fontFamily="var(--mono)"
                fill="#798086"
              >
                {number(t * 1e6, view === "front" ? 1 : 0)}
              </text>
            );
          })}
          {Array.from({ length: 5 }, (_, i) => {
            const v = (i * maxV) / 4;
            return (
              <text
                key={i}
                x={L - 10}
                y={y(v) + 4}
                textAnchor="end"
                fontSize="12"
                fontFamily="var(--mono)"
                fill="#798086"
              >
                {number(v / 1000, 0)}
              </text>
            );
          })}
          <text
            x={(L + R) / 2}
            y={H - 6}
            textAnchor="middle"
            fontSize="12"
            fill="#798086"
            letterSpacing=".07em"
          >
            TIME (µs)
          </text>
          <text
            transform={`translate(16 ${(T + B) / 2}) rotate(-90)`}
            textAnchor="middle"
            fontSize="12"
            fill="#798086"
            letterSpacing=".07em"
          >
            VOLTAGE (kV)
          </text>
          <g clipPath="url(#plot-clip)">
            {shown.map((c) => (
              <path
                key={c.curve_id}
                d={path(c)}
                fill="none"
                stroke={
                  c.curve_id === "target" ? "#c46a1c" : colors[(c.rank - 1) % 3]
                }
                strokeWidth={
                  c.curve_id === "target"
                    ? 2
                    : c.candidate_id === selectedId
                      ? 2.5
                      : 1.5
                }
                strokeDasharray={c.curve_id === "target" ? "7 5" : undefined}
              />
            ))}
            {marks &&
              ["t30_s", "t90_s", "peak_s", "half_s"].map((key, i) => {
                const t = marks[key];
                return t >= range[0] && t <= range[1] ? (
                  <g key={key}>
                    <line
                      x1={x(t)}
                      x2={x(t)}
                      y1={T}
                      y2={B}
                      stroke="#3b5d8a"
                      strokeDasharray="3 5"
                      opacity=".35"
                    />
                    <text
                      x={x(t) + 3}
                      y={T + 14 + i * 14}
                      fontSize="11"
                      fill="#3b5d8a"
                    >
                      {key.replace("_s", "")}
                    </text>
                  </g>
                ) : null;
              })}
            {hover && (
              <line
                x1={hover.px}
                x2={hover.px}
                y1={T}
                y2={B}
                stroke="var(--ink-3)"
              />
            )}
          </g>
          {!valid && (
            <text
              x={W / 2}
              y={H / 2}
              textAnchor="middle"
              fill="#798086"
              fontSize="14"
            >
              Waiting for waveform data from the backend
            </text>
          )}
        </svg>
        {hover && (
          <div
            className="tip"
            style={{ top: 18, left: `${Math.min(65, (hover.px / W) * 100)}%` }}
          >
            <div className="t">{number(times[hover.index] * 1e6, 3)} µs</div>
            {shown.map((c) => (
              <div className="r" key={c.curve_id}>
                <b>{number(c.voltage_V[hover.index] / 1000, 2)} kV</b>
                <span>
                  {c.curve_id === "target" ? "Target" : `Case #${c.rank}`}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
      <p className="plot-note">
        {marks
          ? `Markers: t30 ${number(marks.t30_s * 1e6)} µs · t90 ${number(marks.t90_s * 1e6)} µs · virtual origin ${number(marks.origin_s * 1e6)} µs · t50 ${number(marks.half_s * 1e6)} µs · peak ${number(marks.peak_s * 1e6)} µs. `
          : ""}
        Drag across the plot to zoom. Curves are parameter reconstructions, not
        measured traces or pointwise ML output.
      </p>
    </section>
  );
}
