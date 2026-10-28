import { DrivePanel } from "../components/panels/DrivePanel";
import { ServoPanel } from "../components/panels/ServoPanel";
import { ConnectionPanel } from "../components/panels/ConnectionPanel";
import { TelemetryPanel } from "../components/panels/TelemetryPanel";
import { EventsPanel } from "../components/panels/EventsPanel";
import { Panel } from "../components/ui/Panel";
import { ShieldCheck, TriangleAlert } from "lucide-react";

export function ControlView({
  state,
  events,
  history,
  ports,
  busy,
  onDrive,
  onMove,
  onStop,
  onConnect,
  onDisconnect,
  onRefreshPorts,
  notify,
}) {
  return (
    <div className="view-grid view-grid--control">
      <DrivePanel
        state={state}
        onDrive={onDrive}
        onMove={onMove}
        onStop={onStop}
        notify={notify}
      />
      <TelemetryPanel state={state} history={history} />
      <ServoPanel notify={notify} />
      <ConnectionPanel
        state={state}
        ports={ports}
        onRefresh={onRefreshPorts}
        onConnect={onConnect}
        onDisconnect={onDisconnect}
        busy={busy}
      />
      <Panel
        title="Protocolo del cuerpo"
        code="HW-00"
        icon={ShieldCheck}
        className="protocol-panel"
        bodyClassName="protocol__body"
      >
        <div className="protocol-grid">
          <div>
            <span>ENLACE</span>
            <strong>Serial 9600 baud</strong>
          </div>
          <div>
            <span>TRAMA</span>
            <strong>{"M:izq,der\\n"}</strong>
          </div>
          <div>
            <span>PUERTO</span>
            <strong>{state?.port || "COM3"}</strong>
          </div>
          <div>
            <span>WATCHDOG</span>
            <strong>1,2 s</strong>
          </div>
        </div>
        <p className="protocol-note">
          <TriangleAlert size={13} />
          Los controles de servos quedan en simulación hasta que Agus entregue el
          protocolo definitivo. Las orugas ya respetan el límite ±220 y la parada
          de emergencia.
        </p>
      </Panel>
      <EventsPanel events={events} limit={14} className="control-events" />
    </div>
  );
}
