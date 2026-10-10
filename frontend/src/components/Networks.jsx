import { useState } from "react";
import { number, percentage } from "../lib/config.js";
import { api } from "../lib/api.js";
export function expression(tree) {
  if (!tree) return "—";
  if (tree.op === "resistor") return `${number(tree.ohm, 3)} Ω`;
  return `(${tree.children.map(expression).join(tree.op === "series" ? " + " : " ∥ ")})`;
}
function dimension(tree) {
  if (tree.op === "resistor") return { w: 112, h: 100 };
  const children = tree.children.map(dimension);
  return tree.op === "series"
    ? {
        w: children.reduce((s, c) => s + c.w, 0),
        h: Math.max(...children.map((c) => c.h)),
      }
    : {
        w: Math.max(...children.map((c) => c.w)) + 70,
        h: children.reduce((s, c) => s + c.h, 0) + 30,
      };
}
function leaves(tree) {
  return tree.op === "resistor"
    ? 1
    : tree.children.reduce((sum, child) => sum + leaves(child), 0);
}
function Drawing({ tree, x, y, w, leafOffset = 0, role }) {
  const ink = "#23272b";
  if (tree.op === "resistor") {
    const index = leafOffset;
    return (
      <g>
        <line x1={x} x2={x + w} y1={y} y2={y} stroke={ink} strokeWidth="1.6" />
        <rect
          x={x + w / 2 - 27}
          y={y - 10}
          width="54"
          height="20"
          rx="2"
          fill="white"
          stroke={ink}
          strokeWidth="1.6"
        />
        <text
          x={x + w / 2}
          y={y - 18}
          textAnchor="middle"
          fontSize="14"
          fontWeight="600"
        >
          {role === "front" ? "Rf" : "Rt"}
          {index + 1}
        </text>
        <text
          x={x + w / 2}
          y={y + 31}
          textAnchor="middle"
          fontFamily="var(--mono)"
          fontSize="13"
        >
          {number(tree.ohm, 2)} Ω
        </text>
      </g>
    );
  }
  const sizes = tree.children.map(dimension);
  if (tree.op === "series") {
    const scale = w / sizes.reduce((s, c) => s + c.w, 0);
    let cursor = x;
    return (
      <g>
        {tree.children.map((child, i) => {
          const cx = cursor;
          cursor += sizes[i].w * scale;
          return (
            <Drawing
              key={i}
              tree={child}
              x={cx}
              y={y}
              w={sizes[i].w * scale}
              leafOffset={
                leafOffset +
                tree.children
                  .slice(0, i)
                  .reduce((sum, node) => sum + leaves(node), 0)
              }
              role={role}
            />
          );
        })}
      </g>
    );
  }
  const h = sizes.reduce((s, c) => s + c.h, 0);
  let cursor = y - h / 2;
  const children = tree.children.map((child, i) => {
    const cy = cursor + sizes[i].h / 2;
    cursor += sizes[i].h;
    return { child, cy };
  });
  const top = children[0].cy,
    bottom = children.at(-1).cy;
  return (
    <g>
      <rect
        x={x + 20}
        y={top - 43}
        width={w - 40}
        height={bottom - top + 82}
        fill="#f1f6f5"
        stroke="#9dc4bf"
        strokeDasharray="4 3"
        rx="7"
      />
      <text
        x={x + 28}
        y={top - 27}
        fontSize="11"
        fill="var(--teal)"
        letterSpacing=".06em"
      >
        PARALLEL
      </text>
      <path
        d={`M${x},${y}H${x + 35} M${x + w - 35},${y}H${x + w} M${x + 35},${top}V${bottom} M${x + w - 35},${top}V${bottom}`}
        stroke={ink}
        fill="none"
        strokeWidth="1.6"
      />
      {children.map(({ child, cy }, i) => (
        <Drawing
          key={i}
          tree={child}
          x={x + 35}
          y={cy}
          w={w - 70}
          leafOffset={
            leafOffset +
            tree.children
              .slice(0, i)
              .reduce((sum, node) => sum + leaves(node), 0)
          }
          role={role}
        />
      ))}
      <circle cx={x + 35} cy={y} r="3.5" />
      <circle cx={x + w - 35} cy={y} r="3.5" />
    </g>
  );
}
export function Schematic({ assembly, role }) {
  if (!assembly)
    return (
      <div className="schem loading-shell min-h-52">
        Calculate to see exact resistor connections.
      </div>
    );
  const size = dimension(assembly.recipe),
    W = Math.max(440, size.w + 90),
    H = Math.max(190, size.h + 70),
    y = H / 2;
  return (
    <div className="schem">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`${role} resistor network: ${expression(assembly.recipe)}`}
      >
        <line x1="28" x2="45" y1={y} y2={y} stroke="#23272b" />
        <Drawing
          tree={assembly.recipe}
          x={45}
          y={y}
          w={W - 90}
          role={role}
          leafOffset={0}
        />
        <line x1={W - 45} x2={W - 28} y1={y} y2={y} stroke="#23272b" />
        {[28, W - 28].map((x, i) => (
          <g key={x}>
            <circle
              cx={x}
              cy={y}
              r="5.5"
              fill="white"
              stroke="#23272b"
              strokeWidth="1.6"
            />
            <text
              x={x}
              y={y + 27}
              fontSize="13"
              fill="#7d8389"
              textAnchor="middle"
            >
              {i ? "b" : "a"}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
export default function Networks({ record, rank, inventory }) {
  const [stages, setStages] = useState(null),
    [error, setError] = useState("");
  const candidate = record?.candidate;
  return (
    <div className="nets">
      {["front", "tail"].map((role) => {
        const assembly = candidate?.[role];
        const required =
          candidate?.proposal?.[
            role === "front" ? "Rf_required_ohm" : "Rt_required_ohm"
          ];
        return (
          <section
            className="card"
            key={role}
            aria-label={`${role === "front" ? "Front" : "Tail"} resistor network`}
          >
            <div className="card-head">
              <h2>{role === "front" ? "Front" : "Tail"} resistor network</h2>
              <span className="sub">
                {candidate
                  ? `Case #${rank} · one stage of ${candidate.N}`
                  : "Exact inventory wiring"}
              </span>
            </div>
            <Schematic assembly={assembly} role={role} />
            <p className="hint mt-2">
              Terminals a–b of one stage. The same network is fitted in every
              active stage.
            </p>
            <dl className="facts">
              <dt>Equivalent Req</dt>
              <dd>
                <b className="num">{number(assembly?.equivalent_ohm)} Ω</b> per
                stage
              </dd>
              <dt>Expression</dt>
              <dd className="num">{expression(assembly?.recipe)}</dd>
              <dt>Components</dt>
              <dd>
                {assembly
                  ? `${assembly.total_resistors} per stage · ${assembly.total_resistors * candidate.N} total`
                  : "—"}
              </dd>
              <dt>Ideal required</dt>
              <dd className="num">
                {number(required)} Ω ·{" "}
                {assembly
                  ? percentage(
                      (100 * (assembly.equivalent_ohm - required)) / required,
                    )
                  : "—"}
              </dd>
              <dt>Inventory</dt>
              <dd>
                <div className="chips">
                  {assembly
                    ? Object.entries(assembly.type_counts).map(
                        ([typeId, count]) => {
                          const type = inventory?.[role]?.find(
                            (r) => r.type_id === typeId,
                          );
                          return (
                            <span className="chip" key={typeId}>
                              {number(type?.nominal_ohm, 2)} Ω · {count} of{" "}
                              {type?.available_quantity ?? "—"} used
                            </span>
                          );
                        },
                      )
                    : "—"}
                </div>
              </dd>
            </dl>
            {assembly && (
              <details className="trace-detail">
                <summary className="hint cursor-pointer">
                  Exact wiring and component identities
                </summary>
                <pre>{JSON.stringify(assembly.netlist, null, 2)}</pre>
                <button
                  type="button"
                  className="btn small"
                  onClick={async () => {
                    try {
                      setStages(
                        await api(
                          `/v1/candidates/${record.candidate_id}/generator-stages`,
                        ),
                      );
                      setError("");
                    } catch (e) {
                      setError(e.message);
                    }
                  }}
                >
                  Inspect all generator stages
                </button>
                {error && <p className="error-text">{error}</p>}
                {stages && <pre>{JSON.stringify(stages, null, 2)}</pre>}
              </details>
            )}
          </section>
        );
      })}
    </div>
  );
}
