import { useEffect } from "react";
import { ScanEye, Crosshair, Eye, Radio, Activity } from "lucide-react";
import { VisionPanel } from "../components/panels/VisionPanel";
import { EventsPanel } from "../components/panels/EventsPanel";
import { Panel } from "../components/ui/Panel";
import { Toggle } from "../components/ui/Controls";

const COLORS = [
  { id: "rojo", label: "ROJO", hex: "#e0604d" },
  { id: "verde", label: "VERDE", hex: "#7fbf6a" },
  { id: "azul", label: "AZUL", hex: "#5a8fe0" },
  { id: "amarillo", label: "AMARILLO", hex: "#e2c33f" },
  { id: "naranja", label: "NARANJA", hex: "#dd8a3c" },
];

export function VisionView({
  state,
  events,
  camera,
  color,
  cameraLive,
  onColor,
  onLive,
  onCapture,
  onTracking,
}) {
  const tracking = Boolean(state?.tracking?.enabled);
  const detection = camera?.detection;
  const found = Boolean(detection?.found);

  useEffect(() => {
    if (!camera) onCapture?.();
  }, [camera, onCapture]);

  return (
    <div className="view-grid view-grid--vision">
      <VisionPanel
        camera={camera}
        color={color}
        onColor={onColor}
        live={cameraLive}
        onLive={onLive}
        onCapture={onCapture}
        tracking={tracking}
        onTracking={onTracking}
        expanded
      />

      <div className="vision-stack">
        <Panel
          title="Mesa de análisis"
          code="VIS-05B"
          icon={ScanEye}
          bodyClassName="analysis__body"
        >
          <div className="analysis-hero">
            <div className={`analysis-state ${found ? "is-found" : ""}`}>
              <span className="analysis-state__ring" />
              <Crosshair size={26} />
            </div>
            <div>
              <span>OBJETIVO</span>
              <strong>{found ? `${color.toUpperCase()} DETECTADO` : "SIN OBJETIVO"}</strong>
              <p>
                {found
                  ? `El objeto está a la ${detection.where}. Ocupa ${Math.round(
                      detection.area
                    )} px² y está al ${Math.round((detection.closeness || 0) * 100)}% de cercanía.`
                  : "Poné un objeto de color frente a la cámara y capturá un cuadro."}
              </p>
            </div>
          </div>

          <div className="analysis-grid">
            <div>
              <span>CENTRO X</span>
              <strong>{found ? detection.cx : "—"}</strong>
            </div>
            <div>
              <span>CENTRO Y</span>
              <strong>{found ? detection.cy : "—"}</strong>
            </div>
            <div>
              <span>ANCHO</span>
              <strong>{found ? `${detection.w}px` : "—"}</strong>
            </div>
            <div>
              <span>ALTO</span>
              <strong>{found ? `${detection.h}px` : "—"}</strong>
            </div>
          </div>

          <div className="analysis-colors">
            <span className="vision-label">FILTRO ACTIVO</span>
            <div className="color-grid">
              {COLORS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`color-button ${color === item.id ? "is-active" : ""}`}
                  onClick={() => onColor(item.id)}
                >
                  <i style={{ background: item.hex }} />
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="tracking-row">
            <span>
              <Crosshair size={13} /> SEGUIMIENTO AUTÓNOMO
            </span>
            <Toggle
              checked={tracking}
              onChange={onTracking}
              label="Seguimiento automático"
            />
          </div>
        </Panel>

        <Panel
          title="Cómo ve WALL·E"
          code="VIS-05C"
          icon={Eye}
          bodyClassName="howto__body"
        >
          <ul className="howto-list">
            <li>
              <Radio size={13} />
              <div>
                <strong>Captura</strong>
                <p>OpenCV abre la cámara y convierte el cuadro a HSV.</p>
              </div>
            </li>
            <li>
              <Activity size={13} />
              <div>
                <strong>Umbral</strong>
                <p>Dos bandas de color filtran ruido y buscan el contorno más grande.</p>
              </div>
            </li>
            <li>
              <Crosshair size={13} />
              <div>
                <strong>Reflejo</strong>
                <p>El tracker corrige el rumbo de las orugas 10 veces por segundo.</p>
              </div>
            </li>
          </ul>
          <p className="mono-note">
            {state?.opencv ? "OPENCV OPERATIVO" : "OPENCV NO DISPONIBLE"} ·{" "}
            {cameraLive ? "STREAM EN VIVO" : "STANDBY"}
          </p>
        </Panel>

        <EventsPanel events={events} limit={6} title="Eventos de visión" />
      </div>
    </div>
  );
}
