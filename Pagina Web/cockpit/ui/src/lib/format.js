export const CLOCK = new Intl.DateTimeFormat("es-AR", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

export const SHORT_CLOCK = new Intl.DateTimeFormat("es-AR", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export const DATE_LONG = new Intl.DateTimeFormat("es-AR", {
  weekday: "short",
  day: "2-digit",
  month: "short",
  year: "numeric",
});

export function clock(value = new Date()) {
  return CLOCK.format(value);
}

export function shortClock(value = new Date()) {
  return SHORT_CLOCK.format(value);
}

export function dateLong(value = new Date()) {
  return DATE_LONG.format(value).replace(/\./g, "").toUpperCase();
}

export function seconds(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  return `${n.toFixed(n >= 10 ? 0 : 1)} s`;
}

export function uptime(totalSeconds) {
  const total = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h) return `${h}h ${String(m).padStart(2, "0")}m`;
  if (m) return `${m}m ${String(s).padStart(2, "0")}s`;
  return `${s}s`;
}

export function bytes(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(0)} MB`;
  return `${Math.round(n / 1024)} KB`;
}

export function pct(value) {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${Math.round(n)}%`;
}

export function moodLabel(mood) {
  const labels = {
    curioso: "CURIOSO",
    contento: "CONTENTO",
    mimoso: "MIMOSO",
    asustado: "ASUSTADO",
    aburrido: "ABURRIDO",
    cansado: "CANSADO",
    tranquilo: "TRANQUILO",
  };
  return labels[mood] || "TRANQUILO";
}

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
