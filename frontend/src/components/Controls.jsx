export function Field({
  id,
  label,
  value,
  unit,
  onChange,
  min = 0,
  step = "any",
  disabled = false,
  hint,
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="ctl">
        <input
          id={id}
          type="number"
          value={value}
          min={min}
          step={step}
          disabled={disabled}
          required
          onChange={(e) => onChange?.(e.target.value)}
        />
        {unit && <span className="unit">{unit}</span>}
      </div>
      {hint && <p className="hint">{hint}</p>}
    </div>
  );
}
export function Select({ id, label, value, onChange, options, hint }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="ctl">
        <select
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          {options.map(([val, text]) => (
            <option key={val} value={val}>
              {text}
            </option>
          ))}
        </select>
      </div>
      {hint && <p className="hint">{hint}</p>}
    </div>
  );
}
export function Segment({ label, value, onChange, options }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(([val, text, sub]) => (
        <button
          key={val}
          type="button"
          aria-pressed={value === val}
          onClick={() => onChange(val)}
        >
          {text}
          {sub && <small>{sub}</small>}
        </button>
      ))}
    </div>
  );
}
export function Group({ label, children }) {
  return (
    <fieldset className="group">
      <legend>{label}</legend>
      {children}
    </fieldset>
  );
}
export function Pill({ status = "neutral", children }) {
  return <span className={`pill ${status}`}>{children}</span>;
}
