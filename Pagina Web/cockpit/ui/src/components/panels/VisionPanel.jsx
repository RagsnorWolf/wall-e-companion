import {
  Aperture,
  Camera,
  Crosshair,
  Eye,
  Play,
  ScanEye,
  Square,
  Video,
} from "lucide-react";
import { Panel } from "../ui/Panel";
import { Toggle } from "../ui/Controls";

const COLORS = [
  { id: "rojo", label: "ROJO", hex: "#e0604d" },
  { id: "verde", label: "VERDE", hex: "#7fbf6a" },
  { id: "azul", label: "AZUL", hex: "#5a8fe0" },
  { id: "amarillo", label: "AMARILLO", hex: "#e2c33f" },
  { id: "naranja", label: "NARANJA", hex: "#dd8a3c" },
];

export function VisionPanel({
  camera,
  color,
  onColor,
  live,
  onLive,
  onCapture,
  tracking,
  onTracking,
  className = "",
  expanded = false,
}) {
  const detection = camera?.detection;
  const found = Boolean(detection?.found);
  const frameWidth = camera?.width || 640;
  const frameHeight = camera?.height || 480;
  const box = found
    ? {
        left: `${(detection.x / frameWidth) * 100}%`,
        top: `${(detection.y / frameHeight) * 100}%`,
        width: `${(detection.w / frameWidth) * 100}%`,
        height: `${(detection.h / frameHeight) * 100}%`,
      }
    : null;

  return (
    <Panel
      title="Visión computacional"
      code="VIS-05"
      icon={ScanEye}
      className={`vision-panel ${expanded ? "vision-panel--expanded" : ""} ${className}`}
      bodyClassName="vision__body"
      actions={
        <div className="vision__head-actions">
          <span className={`live-tag ${live ? "is-live" : ""}`}>
            <span className="live-tag__dot" />
            {live ? "LIVE" : "STANDBY"}
          </span>
          <button type="button" className="icon-button icon-button--small" onClick={onLive} title={live ? "Detener cámara" : "Activar cámara"}>
            {live ? <Square size={13} /> : <Play size={13} />}
          </button>
        </div>
      }
    >
      <div className="vision-layout">
        <div className="vision-feed">
          {camera?.image ? (
            <img src={camera.image} alt="Vista de la cámara de WALL-E" />
          ) : (
            <div className="vision-placeholder">
              <div className="vision-placeholder__grid" />
              <Aperture size={34} />
              <strong>SIN SEÑAL DE VIDEO</strong>
              <span>Activá la cámara o apretá capturar.</span>
            </div>
          )}

          <div className="vision-overlay">
            <span className="vision-corner vision-corner--tl" />
            <span className="vision-corner vision-corner--tr" />
            <span className="vision-corner vision-corner--bl" />
            <span className="vision-corner vision-corner--br" />
            <span className="vision-crosshair" />
            <span className="vision-scanline" />
            <div className="vision-hud vision-hud--top">
              <span>CAM-01</span>
              <span>{frameWidth}×{frameHeight}</span>
              <span>{live ? "STREAM" : "FRAME"}</span>
            </div>
            <div className="vision-hud vision-hud--bottom">
              <span>RGB / HSV</span>
              <span>{found ? `OBJETO ${color?.toUpperCase()}` : "SIN OBJETIVO"}</span>
            </div>
            {box ? (
              <div className={`detection-box ${found ? "is-found" : ""}`} style={box}>
                <span>{color?.toUpperCase()} · {detection.where}</span>
              </div>
            ) : null}
          </div>
        </div>

        <div className="vision-side">
          <div className="vision-colors">
            <span className="vision-label">FILTRO CROMÁTICO</span>
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

          <dl className="vision-data">
            <div><dt>OBJETIVO</dt><dd className={found ? "is-ok" : ""}>{found ? "DETECTADO" : "—"}</dd></div>
            <div><dt>POSICIÓN</dt><dd>{found ? detection.where : "—"}</dd></div>
            <div><dt>CENTRO</dt><dd>{found ? `${detection.cx}, ${detection.cy}` : "—"}</dd></div>
            <div><dt>ÁREA</dt><dd>{found ? `${Math.round(detection.area)} px²` : "—"}</dd></div>
            <div><dt>CERCANÍA</dt><dd>{found ? `${Math.round((detection.closeness || 0) * 100)}%` : "—"}</dd></div>
          </dl>

          <div className="vision-actions">
            <button type="button" className="mini-button" onClick={onCapture}>
              <Camera size={13} /> CAPTURAR
            </button>
            <button type="button" className={`mini-button ${live ? "is-active" : ""}`} onClick={onLive}>
              <Video size={13} /> {live ? "DETENER" : "EN VIVO"}
            </button>
          </div>

          <div className="tracking-row">
            <span><Crosshair size={13} /> SEGUIMIENTO</span>
            <Toggle checked={tracking} onChange={onTracking} label="Seguimiento automático" />
          </div>
          <p className="vision-note">
            <Eye size={11} /> El tracking mueve las orugas para centrar el color. No pasa por el modelo.
          </p>
        </div>
      </div>
    </Panel>
  );
}
