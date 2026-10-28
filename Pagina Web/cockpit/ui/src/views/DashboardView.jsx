import { TelemetryPanel } from "../components/panels/TelemetryPanel";
import { DrivePanel } from "../components/panels/DrivePanel";
import { ServoPanel } from "../components/panels/ServoPanel";
import { EventsPanel } from "../components/panels/EventsPanel";
import { WallEPanel } from "../components/panels/WallEPanel";
import { VisionPanel } from "../components/panels/VisionPanel";
import { ChatPanel } from "../components/panels/ChatPanel";
import { SkillsPanel } from "../components/panels/SkillsPanel";

export function DashboardView({
  state,
  events,
  history,
  messages,
  thinking,
  speaking,
  latency,
  sound,
  camera,
  color,
  cameraLive,
  busy,
  onSound,
  onSend,
  onDrive,
  onMove,
  onStop,
  onPet,
  onTracking,
  onColor,
  onCapture,
  onLive,
  onChatSeed,
  notify,
  chatSeed,
  onSeedUsed,
}) {
  const tracking = Boolean(state?.tracking?.enabled);

  return (
    <div className="dashboard">
      <div className="dashboard__left">
        <TelemetryPanel state={state} history={history} />
        <DrivePanel
          state={state}
          onDrive={onDrive}
          onMove={onMove}
          onStop={onStop}
          notify={notify}
          compact
        />
        <ServoPanel notify={notify} />
        <EventsPanel events={events} limit={5} />
      </div>

      <div className="dashboard__center">
        <WallEPanel
          state={state}
          thinking={thinking}
          speaking={speaking}
          onPet={onPet}
          onChat={() => onChatSeed("Hola WALL·E, ¿cómo estás?")}
        />
        <VisionPanel
          camera={camera}
          color={color}
          onColor={onColor}
          live={cameraLive}
          onLive={onLive}
          onCapture={onCapture}
          tracking={tracking}
          onTracking={onTracking}
        />
      </div>

      <div className="dashboard__right">
        <ChatPanel
          messages={messages}
          thinking={thinking}
          onSend={onSend}
          sound={sound}
          onSound={onSound}
          latency={latency}
          model={state?.model}
          notify={notify}
          seed={chatSeed}
          onSeedUsed={onSeedUsed}
        />
        <SkillsPanel
          tracking={tracking}
          onTracking={onTracking}
          notify={notify}
        />
      </div>
    </div>
  );
}
