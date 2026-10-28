import { motion } from "framer-motion";

export function Gauge({
  label,
  value,
  unit = "%",
  hint,
  tone = "cyan",
  size = 92,
  decimals = 0,
}) {
  const numeric = value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
  const safe = numeric ? Math.max(0, Math.min(100, Number(value))) : null;
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const offset = safe == null ? circumference : circumference * (1 - safe / 100);

  return (
    <div className={`gauge gauge--${tone}`}>
      <div className="gauge__ring" style={{ width: size, height: size }}>
        <svg viewBox="0 0 92 92" aria-hidden="true">
          <circle className="gauge__track" cx="46" cy="46" r={radius} />
          <motion.circle
            className="gauge__fill"
            cx="46"
            cy="46"
            r={radius}
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
          />
          <circle className="gauge__inner" cx="46" cy="46" r="30" />
        </svg>
        <div className="gauge__value">
          <strong>{safe == null ? "—" : safe.toFixed(decimals)}</strong>
          <span>{safe == null ? "N/D" : unit}</span>
        </div>
      </div>
      <p className="gauge__label">{label}</p>
      {hint ? <p className="gauge__hint">{hint}</p> : null}
    </div>
  );
}

export function Sparkline({ values = [], tone = "cyan" }) {
  const series = values.length ? values : [0, 0, 0, 0, 0, 0];
  const width = 120;
  const height = 32;
  const max = Math.max(100, ...series);
  const points = series
    .map((value, index) => {
      const x = (index / Math.max(1, series.length - 1)) * width;
      const y = height - (Number(value) / max) * (height - 3) - 1;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const area = `0,${height} ${points} ${width},${height}`;

  return (
    <svg className={`sparkline sparkline--${tone}`} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <polygon points={area} className="sparkline__area" />
      <polyline points={points} className="sparkline__line" />
    </svg>
  );
}
