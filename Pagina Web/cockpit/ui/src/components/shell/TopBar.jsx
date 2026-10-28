import { useEffect, useState } from "react";
import { BatteryMedium, Cpu, Radio, ScanEye, Volume2, VolumeX, Wifi } from "lucide-react";
import { StatusChip } from "../ui/Controls";
import { clock, dateLong, moodLabel } from "../../lib/format";

const TITLES = {
  dashboard: {
    kicker: "PANEL DE MANDO / 00",
    title: "Centro de comando",
    sub: "Telemetría, visión y conversación en tiempo real.",
  },
  control: {
    kicker: "SUBSISTEMA / 01",
    title: "Control de vuelo",
    sub: "Orugas, servos y enlace serial con el cuerpo.",
  },
  vision: {
    kicker: "SUBSISTEMA / 02",
    title: "Visión computacional",
    sub: "Óptica, detección de color y seguimiento autónomo.",
  },
  memory: {
    kicker: "SUBSISTEMA / 03",
    title: "Memoria persistente",
    sub: "Todo lo que WALL·E guardó, en tu propia máquina.",
  },
  agenda: {
    kicker: "SUBSISTEMA / 04",
    title: "Agenda local",
    sub: "Eventos, recordatorios y rutinas.",
  },
  settings: {
    kicker: "SUBSISTEMA / 05",
    title: "Ajustes del núcleo",
    sub: "Modelo, cámara, puerto y diagnóstico.",
  },
};

export function TopBar({ view, state, online, sound, onSound }) {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const meta = TITLES[view] || TITLES.dashboard;
  const ready = state?.ready;
  const warming = state?.warming;
  const connected = state?.connected;
  const tracking = state?.tracking?.enabled;
  const mood = state?.emotion?.mood;

  return (
    <header className="topbar">
      <div className="topbar__title">
        <span className="topbar__kicker">{meta.kicker}</span>
        <h1>{meta.title}</h1>
        <p>{meta.sub}</p>
      </div>

      <div className="topbar__right">
        <div className="topbar__chips">
          <StatusChip
            tone={!online ? "bad" : ready ? "ok" : warming ? "warn" : "bad"}
            pulse={!ready}
            icon={Cpu}
          >
            {!online ? "SIN ENLACE" : ready ? "NÚCLEO ACTIVO" : warming ? "CALENTANDO" : "NÚCLEO FRÍO"}
          </StatusChip>
          <StatusChip tone={connected ? "ok" : "warn"} icon={Radio}>
            {connected ? state?.port || "CUERPO" : "SIMULACIÓN"}
          </StatusChip>
          <StatusChip tone={state?.opencv ? "cyan" : "bad"} icon={ScanEye}>
            {state?.opencv ? (tracking ? "TRACKING" : "ÓPTICA OK") : "SIN CÁMARA"}
          </StatusChip>
          <StatusChip tone="neutral" icon={Wifi}>LOCAL</StatusChip>
          {mood ? <StatusChip tone="amber" icon={BatteryMedium}>{moodLabel(mood)}</StatusChip> : null}
        </div>

        <div className="topbar__clock">
          <strong>{clock(now)}</strong>
          <span>{dateLong(now)}</span>
        </div>

        <button
          type="button"
          className="icon-button"
          onClick={onSound}
          title={sound ? "Silenciar voz" : "Activar voz"}
          aria-pressed={sound}
        >
          {sound ? <Volume2 size={17} /> : <VolumeX size={17} />}
        </button>
      </div>
    </header>
  );
}
