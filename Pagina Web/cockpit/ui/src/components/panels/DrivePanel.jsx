import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Gauge as GaugeIcon,
  Octagon,
  Play,
  Square,
} from "lucide-react";
import { Panel } from "../ui/Panel";

const DIRECTIONS = {
  forward: { left: 1, right: 1, label: "AVANZAR" },
  back: { left: -1, right: -1, label: "RETROCEDER" },
  left: { left: -0.8, right: 0.8, label: "GIRAR IZQ." },
  right: { left: 0.8, right: -0.8, label: "GIRAR DER." },
};

export function DrivePanel({
  state,
  onDrive,
  onStop,
  onMove,
  compact = false,
  notify,
}) {
  const [speed, setSpeed] = useState(150);
  const [held, setHeld] = useState(null);
  const timer = useRef(null);
  const tracking = Boolean(state?.tracking?.enabled);
  const last = state?.last_command;

  const stop = useCallback(() => {
    if (timer.current) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
    setHeld(null);
    onStop?.();
  }, [onStop]);

  useEffect(() => () => {
    if (timer.current) window.clearInterval(timer.current);
  }, []);

  const begin = (direction) => {
    if (tracking) {
      notify?.("Desactivá el seguimiento automático antes de manejar.", "error");
      return;
    }
    const spec = DIRECTIONS[direction];
    if (!spec) return;
    const left = Math.round(spec.left * speed);
    const right = Math.round(spec.right * speed);
    setHeld(direction);
    onDrive?.(left, right);
    if (timer.current) window.clearInterval(timer.current);
    timer.current = window.setInterval(() => onDrive?.(left, right), 300);
  };

  const end = () => {
    if (!held) return;
    stop();
  };

  const timed = (direction) => {
    if (tracking) {
      notify?.("Desactivá el seguimiento automático antes de manejar.", "error");
      return;
    }
    const spec = DIRECTIONS[direction];
    const seconds = direction === "forward" || direction === "back" ? 1 : 0.7;
    onMove?.(
      Math.round(spec.left * speed),
      Math.round(spec.right * speed),
      seconds
    );
  };

  return (
    <Panel
      title="Control de orugas"
      code="DRV-02"
      icon={GaugeIcon}
      className={compact ? "drive-panel drive-panel--compact" : "drive-panel"}
      actions={
        <span className="panel__meta">
          {last ? `ÚLT. ${last[0]} / ${last[1]}` : "DETENIDO"}
        </span>
      }
      bodyClassName="drive__body"
    >
      {tracking ? (
        <div className="inline-warning">
          <Octagon size={14} /> Seguimiento activo: el control manual está bloqueado.
        </div>
      ) : null}

      <div className="drive-layout">
        <div className="joystick" role="group" aria-label="Control de orugas">
          <button
            type="button"
            className={`joy joy--up ${held === "forward" ? "is-held" : ""}`}
            onPointerDown={() => begin("forward")}
            onPointerUp={end}
            onPointerLeave={end}
            onPointerCancel={end}
            aria-label="Avanzar"
          >
            <ArrowUp size={22} />
          </button>
          <button
            type="button"
            className={`joy joy--left ${held === "left" ? "is-held" : ""}`}
            onPointerDown={() => begin("left")}
            onPointerUp={end}
            onPointerLeave={end}
            onPointerCancel={end}
            aria-label="Girar a la izquierda"
          >
            <ArrowLeft size={22} />
          </button>
          <button
            type="button"
            className="joy joy--stop"
            onClick={stop}
            aria-label="Detener"
          >
            <Square size={18} />
          </button>
          <button
            type="button"
            className={`joy joy--right ${held === "right" ? "is-held" : ""}`}
            onPointerDown={() => begin("right")}
            onPointerUp={end}
            onPointerLeave={end}
            onPointerCancel={end}
            aria-label="Girar a la derecha"
          >
            <ArrowRight size={22} />
          </button>
          <button
            type="button"
            className={`joy joy--down ${held === "back" ? "is-held" : ""}`}
            onPointerDown={() => begin("back")}
            onPointerUp={end}
            onPointerLeave={end}
            onPointerCancel={end}
            aria-label="Retroceder"
          >
            <ArrowDown size={22} />
          </button>
        </div>

        <div className="drive-controls">
          <label className="range-field">
            <span>VELOCIDAD <b>{speed}</b></span>
            <input
              type="range"
              min="60"
              max="220"
              step="10"
              value={speed}
              onChange={(event) => setSpeed(Number(event.target.value))}
              style={{ "--fill": `${((speed - 60) / 160) * 100}%` }}
            />
          </label>

          <div className="timed-grid">
            <button type="button" className="mini-button" onClick={() => timed("forward")}>
              <Play size={12} /> AVANZAR 1S
            </button>
            <button type="button" className="mini-button" onClick={() => timed("back")}>
              <Play size={12} /> RETROCEDER 1S
            </button>
            <button type="button" className="mini-button" onClick={() => timed("left")}>
              <Play size={12} /> GIRAR IZQ.
            </button>
            <button type="button" className="mini-button" onClick={() => timed("right")}>
              <Play size={12} /> GIRAR DER.
            </button>
          </div>

          <div className="drive-readout">
            <span>ORUGAS</span>
            <strong>{last ? `${last[0]} / ${last[1]}` : "0 / 0"}</strong>
          </div>

          <button type="button" className="danger-button" onClick={stop}>
            <Octagon size={15} /> PARADA DE EMERGENCIA
          </button>
        </div>
      </div>
    </Panel>
  );
}
