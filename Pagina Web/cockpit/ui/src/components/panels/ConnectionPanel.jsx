import { Cable, RefreshCw, ShieldCheck, Unplug } from "lucide-react";
import { Panel } from "../ui/Panel";

export function ConnectionPanel({ state, ports, onRefresh, onConnect, onDisconnect, busy }) {
  const connected = Boolean(state?.connected);
  const selected = ports.find((port) => port.device === state?.port);

  return (
    <Panel
      title="Enlace serial"
      code="LNK-01"
      icon={Cable}
      actions={<span className={`live-tag ${connected ? "is-live" : "is-warn"}`}><span className="live-tag__dot" />{connected ? "CONECTADO" : "SIMULACIÓN"}</span>}
      bodyClassName="connection__body"
    >
      <p className="muted-copy">
        Solo se conecta al puerto que elijas. Nunca autodetecta el ESP32.
      </p>

      <label className="field">
        <span>PUERTO</span>
        <div className="field-inline">
          <select value={state?.port || ""} onChange={(event) => onConnect(event.target.value)} disabled={busy}>
            <option value="">— elegí un puerto —</option>
            {ports.map((port) => (
              <option key={port.device} value={port.device}>
                {port.device} {port.description ? `· ${port.description}` : ""}
              </option>
            ))}
            {state?.port && !selected ? <option value={state.port}>{state.port}</option> : null}
          </select>
          <button type="button" className="icon-button" onClick={onRefresh} title="Actualizar puertos">
            <RefreshCw size={15} />
          </button>
        </div>
      </label>

      <div className="connection__actions">
        <button type="button" className="primary-button" onClick={() => onConnect(state?.port)} disabled={busy || !state?.port}>
          <Cable size={15} /> CONECTAR
        </button>
        <button type="button" className="ghost-button" onClick={onDisconnect} disabled={busy || !connected}>
          <Unplug size={15} /> DESCONECTAR
        </button>
      </div>

      <div className="safety-list">
        <span><ShieldCheck size={13} /> Watchdog 1,2 s</span>
        <span><ShieldCheck size={13} /> Límite ±220</span>
        <span><ShieldCheck size={13} /> Parada de emergencia</span>
      </div>

      <p className="mono-note">
        {connected ? `ENLACE ACTIVO · ${state?.port}` : "SIN ENLACE FÍSICO · COMANDOS SIMULADOS"}
      </p>
    </Panel>
  );
}
