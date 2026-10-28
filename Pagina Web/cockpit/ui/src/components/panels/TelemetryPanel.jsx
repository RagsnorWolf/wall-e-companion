import {
  Activity,
  BatteryMedium,
  Cpu,
  Database,
  MemoryStick,
  Radio,
  Thermometer,
  Timer,
  Wifi,
} from "lucide-react";
import { Panel } from "../ui/Panel";
import { Gauge, Sparkline } from "../ui/Gauge";
import { pct, uptime } from "../../lib/format";

export function TelemetryPanel({ state, history = [] }) {
  const system = state?.system || {};
  const cpu = system.cpu ?? null;
  const ram = system.ram ?? null;
  const temp = system.temp ?? null;
  const battery = state?.battery ?? null;
  const connected = Boolean(state?.connected);
  const mode = state?.mode === "real" ? "ENLACE FÍSICO" : "SIMULACIÓN";

  return (
    <Panel
      title="Telemetría"
      code="TLM-01"
      icon={Activity}
      actions={<span className={`live-tag ${connected ? "is-live" : "is-warn"}`}><span className="live-tag__dot" />{connected ? "ONLINE" : "SIM"}</span>}
      bodyClassName="telemetry__body"
    >
      <div className="gauge-grid">
        <Gauge label="CPU" value={cpu} unit="%" hint="carga del núcleo" tone="cyan" />
        <Gauge label="RAM" value={ram} unit="%" hint="memoria del sistema" tone="amber" />
        <Gauge label="TEMP" value={temp} unit="°C" hint={temp == null ? "sensor N/D" : "procesador"} tone={temp != null && temp > 75 ? "red" : "green"} />
        <Gauge label="BATERÍA" value={battery} unit="%" hint={battery == null ? "ESP32 pendiente" : "paquete 2S"} tone="green" />
      </div>

      <div className="telemetry__spark">
        <div className="telemetry__spark-head">
          <span>CARGA DEL NÚCLEO</span>
          <b>{pct(cpu)}</b>
        </div>
        <Sparkline values={history} tone="cyan" />
      </div>

      <dl className="data-rows">
        <div className="data-row">
          <dt><Radio size={12} /> ENLACE</dt>
          <dd className={connected ? "is-ok" : "is-warn"}>{mode}</dd>
        </div>
        <div className="data-row">
          <dt><Wifi size={12} /> PUERTO</dt>
          <dd>{state?.port || "—"}</dd>
        </div>
        <div className="data-row">
          <dt><Timer size={12} /> UPTIME</dt>
          <dd>{uptime(state?.uptime)}</dd>
        </div>
        <div className="data-row">
          <dt><Database size={12} /> MEMORIA</dt>
          <dd>{state?.memory ?? 0} recuerdos</dd>
        </div>
        <div className="data-row">
          <dt><Cpu size={12} /> MODELO</dt>
          <dd className="is-truncate">{state?.model || "walle"}</dd>
        </div>
        <div className="data-row">
          <dt><MemoryStick size={12} /> OLLAMA</dt>
          <dd className={state?.ollama ? "is-ok" : "is-bad"}>{state?.ollama ? "RESPONDE" : "SIN ENLACE"}</dd>
        </div>
      </dl>

      <div className="telemetry__foot">
        <span><BatteryMedium size={12} /> {battery == null ? "Batería sin sensor" : `${battery}%`}</span>
        <span><Thermometer size={12} /> {temp == null ? "Temp. N/D" : `${temp} °C`}</span>
      </div>
    </Panel>
  );
}
