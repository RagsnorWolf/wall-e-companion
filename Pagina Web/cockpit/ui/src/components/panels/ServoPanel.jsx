import { useState } from "react";
import { Move3d, RotateCcw, SlidersHorizontal } from "lucide-react";
import { Panel } from "../ui/Panel";

const SERVOS = [
  { id: "neck", label: "CUELLO", value: 50 },
  { id: "left", label: "BRAZO IZQ.", value: 42 },
  { id: "right", label: "BRAZO DER.", value: 58 },
];

export function ServoPanel({ notify }) {
  const [values, setValues] = useState(() => Object.fromEntries(SERVOS.map((servo) => [servo.id, servo.value])));

  const update = (id, value) => {
    setValues((current) => ({ ...current, [id]: Number(value) }));
  };

  const reset = () => {
    setValues(Object.fromEntries(SERVOS.map((servo) => [servo.id, servo.value])));
    notify?.("Servos reseteados en simulación.", "info");
  };

  return (
    <Panel
      title="Servos / articulaciones"
      code="SRV-03"
      icon={Move3d}
      actions={<span className="panel__meta">SIMULACIÓN</span>}
      bodyClassName="servo__body"
    >
      <div className="servo-list">
        {SERVOS.map((servo) => (
          <label className="servo" key={servo.id}>
            <div>
              <span>{servo.label}</span>
              <b>{values[servo.id]}°</b>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={values[servo.id]}
              onChange={(event) => update(servo.id, event.target.value)}
              style={{ "--fill": `${values[servo.id]}%` }}
            />
          </label>
        ))}
      </div>
      <div className="servo__foot">
        <span><SlidersHorizontal size={12} /> Protocolo de servos pendiente de Agus.</span>
        <button type="button" className="mini-button" onClick={reset}><RotateCcw size={12} /> RESET</button>
      </div>
    </Panel>
  );
}
