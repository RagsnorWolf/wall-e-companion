export function Toggle({ checked, onChange, label, disabled = false, id }) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      className={`toggle ${checked ? "is-on" : ""}`}
      onClick={() => onChange?.(!checked)}
    >
      <span className="toggle__thumb" />
    </button>
  );
}

export function StatusChip({ tone = "neutral", children, pulse = false, icon: Icon }) {
  return (
    <span className={`status-chip status-chip--${tone} ${pulse ? "is-pulsing" : ""}`}>
      <span className="status-chip__dot" />
      {Icon ? <Icon size={12} /> : null}
      <span>{children}</span>
    </span>
  );
}
