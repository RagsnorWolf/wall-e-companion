import {
  BrainCircuit,
  CalendarClock,
  LayoutDashboard,
  ScanEye,
  Settings2,
  SlidersHorizontal,
  Terminal,
} from "lucide-react";
import { motion } from "framer-motion";
import { StatusChip } from "../ui/Controls";

const NAV = [
  { id: "dashboard", label: "Comando", icon: LayoutDashboard, code: "00" },
  { id: "control", label: "Control", icon: SlidersHorizontal, code: "01" },
  { id: "vision", label: "Visión", icon: ScanEye, code: "02" },
  { id: "memory", label: "Memoria", icon: BrainCircuit, code: "03" },
  { id: "agenda", label: "Agenda", icon: CalendarClock, code: "04" },
  { id: "settings", label: "Ajustes", icon: Settings2, code: "05" },
];

export function Sidebar({ view, onView, state, online }) {
  const ready = state?.ready;
  const connected = state?.connected;

  return (
    <aside className="sidebar">
      <div className="sidebar__brand" title="WALL·E">
        <div className="brand-eyes" aria-hidden="true">
          <span />
          <span />
        </div>
        <div className="brand-copy">
          <strong>WALL·E</strong>
          <span>COMMAND CENTER</span>
        </div>
      </div>

      <div className="sidebar__section-label">SISTEMA</div>
      <nav className="sidebar__nav" aria-label="Secciones">
        {NAV.map((item) => {
          const Icon = item.icon;
          const active = view === item.id;
          return (
            <button
              key={item.id}
              type="button"
              className={`nav-button ${active ? "is-active" : ""}`}
              onClick={() => onView(item.id)}
              aria-current={active ? "page" : undefined}
            >
              {active ? (
                <motion.span
                  layoutId="nav-active"
                  className="nav-button__glow"
                  transition={{ type: "spring", stiffness: 420, damping: 34 }}
                />
              ) : null}
              <span className="nav-button__code">{item.code}</span>
              <Icon size={18} strokeWidth={1.7} />
              <span className="nav-button__label">{item.label}</span>
              {item.id === "vision" && state?.tracking?.enabled ? (
                <span className="nav-button__badge">REC</span>
              ) : null}
            </button>
          );
        })}
      </nav>

      <div className="sidebar__spacer" />

      <div className="sidebar__terminal">
        <Terminal size={14} />
        <div>
          <span>NÚCLEO LOCAL</span>
          <strong>{online ? (ready ? "EN LÍNEA" : "CALENTANDO") : "SIN ENLACE"}</strong>
        </div>
      </div>

      <div className="sidebar__status">
        <StatusChip tone={connected ? "ok" : "warn"} pulse={!connected}>
          {connected ? state?.port || "CUERPO" : "SIMULACIÓN"}
        </StatusChip>
        <span className="sidebar__version">v2.0 · BUILD 026</span>
      </div>
    </aside>
  );
}
