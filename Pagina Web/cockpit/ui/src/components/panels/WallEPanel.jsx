import { Heart, MessageSquare, ScanEye, Sparkles } from "lucide-react";
import { motion } from "framer-motion";
import { Panel } from "../ui/Panel";
import { WallE } from "../walle/WallE";
import { moodLabel } from "../../lib/format";
import "../walle/WallE.css";

export function WallEPanel({ state, thinking, speaking, onPet, onChat }) {
  const emotion = state?.emotion || {};
  const mood = emotion.mood || "tranquilo";
  const meters = [
    { label: "Energía", value: emotion.energy ?? 0, tone: "amber" },
    { label: "Afecto", value: emotion.affection ?? 0, tone: "rose" },
    { label: "Curiosidad", value: emotion.curiosity ?? 0, tone: "cyan" },
  ];

  return (
    <Panel
      title="Asistente visual"
      code="UNIT-01"
      icon={ScanEye}
      className="walle-panel"
      bodyClassName="walle-panel__body"
      actions={
        <span className={`live-tag ${thinking ? "is-busy" : ""}`}>
          <span className="live-tag__dot" />
          {thinking ? "PROCESANDO" : speaking ? "HABLANDO" : "EN LÍNEA"}
        </span>
      }
    >
      <WallE mood={mood} thinking={thinking} speaking={speaking} onPet={onPet} />

      <div className="walle-panel__footer">
        <div className="walle-id">
          <div className="walle-id__mark" aria-hidden="true"><span /><span /></div>
          <div>
            <strong>WALL·E</strong>
            <span>UNIDAD 01 · COMPAÑERO DE ESCRITORIO</span>
          </div>
        </div>

        <div className="walle-meters">
          {meters.map((meter) => (
            <div className="mini-meter" key={meter.label}>
              <span>{meter.label}</span>
              <div className="mini-meter__track">
                <motion.i
                  className={`mini-meter__fill mini-meter__fill--${meter.tone}`}
                  animate={{ width: `${Math.max(3, Math.min(100, meter.value))}%` }}
                  transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
                />
              </div>
              <b>{Math.round(meter.value)}%</b>
            </div>
          ))}
        </div>

        <div className="walle-panel__actions">
          <span className="mood-badge">
            <Sparkles size={12} />
            {moodLabel(mood)}
          </span>
          <button type="button" className="action-button" onClick={onPet}>
            <Heart size={15} />
            <span>CARICIA</span>
          </button>
          <button type="button" className="action-button action-button--primary" onClick={onChat}>
            <MessageSquare size={15} />
            <span>HABLAR</span>
          </button>
        </div>
      </div>
    </Panel>
  );
}
