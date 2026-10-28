import {
  Bot,
  Code2,
  Crosshair,
  Heart,
  Shield,
  Sparkles,
  ToggleRight,
} from "lucide-react";
import { Panel } from "../ui/Panel";
import { Toggle } from "../ui/Controls";

const MODES = [
  {
    id: "track",
    name: "Seguir objetivo",
    description: "La cámara persigue un color y las orugas corrigen el rumbo.",
    icon: Crosshair,
    tone: "amber",
  },
  {
    id: "companion",
    name: "Modo compañero",
    description: "Charla, emociones y memoria. Siempre activo.",
    icon: Heart,
    tone: "rose",
    locked: true,
  },
  {
    id: "guardian",
    name: "Modo guardián",
    description: "Vigilancia del escritorio con alertas de movimiento.",
    icon: Shield,
    tone: "cyan",
    badge: "HW",
    disabled: true,
  },
  {
    id: "code",
    name: "Code buddy",
    description: "Ayuda técnica y lectura de archivos del proyecto.",
    icon: Code2,
    tone: "green",
    badge: "BETA",
    disabled: true,
  },
];

export function SkillsPanel({ tracking, onTracking, notify }) {
  const active = (mode) => {
    if (mode.id === "track") return tracking;
    if (mode.id === "companion") return true;
    return false;
  };

  const toggle = (mode) => {
    if (mode.disabled) {
      notify?.("Ese módulo necesita hardware o una versión futura.", "info");
      return;
    }
    if (mode.id === "track") {
      onTracking?.(!tracking);
      return;
    }
    if (mode.locked) {
      notify?.("El modo compañero no se puede apagar: es su personalidad.", "info");
      return;
    }
  };

  return (
    <Panel
      title="Skills / módulos"
      code="SYS-04"
      icon={Sparkles}
      bodyClassName="skills__body"
      actions={<span className="panel__meta">{MODES.filter(active).length} ACTIVOS</span>}
    >
      <div className="skills-list">
        {MODES.map((mode) => {
          const Icon = mode.icon;
          const isActive = active(mode);
          return (
            <div className={`skill ${isActive ? "is-active" : ""}`} key={mode.id}>
              <span className={`skill__icon skill__icon--${mode.tone}`}>
                <Icon size={16} />
              </span>
              <div className="skill__copy">
                <div>
                  <strong>{mode.name}</strong>
                  {mode.badge ? <em>{mode.badge}</em> : null}
                </div>
                <p>{mode.description}</p>
              </div>
              {mode.locked ? (
                <ToggleRight size={18} className="skill__locked" />
              ) : (
                <Toggle
                  checked={isActive}
                  onChange={() => toggle(mode)}
                  label={mode.name}
                  disabled={mode.disabled}
                />
              )}
            </div>
          );
        })}
      </div>
      <div className="skills__foot">
        <Bot size={13} />
        <span>Más módulos llegan con el hardware de Agus.</span>
      </div>
    </Panel>
  );
}
