import { useCallback, useEffect, useRef, useState } from "react";
import { clamp } from "../../lib/format";
import frontPhoto from "../../assets/walle/walle-front.png";
import cityPhoto from "../../assets/walle/walle-city.jpg";
import "./WallE.css";

const DUST = [
  [8, 18, 2.2, 0], [22, 42, 1.4, 1.2], [12, 68, 1.8, 2.4], [30, 12, 1.2, 0.8],
  [78, 22, 1.6, 1.8], [88, 54, 2.4, 0.4], [70, 74, 1.2, 2.8], [92, 80, 1.8, 1.6],
  [44, 6, 1.4, 3.2], [58, 88, 2.0, 0.2], [6, 84, 1.6, 2.2], [96, 8, 1.2, 3.6],
];

const MASK = {
  WebkitMaskImage: `url(${frontPhoto})`,
  maskImage: `url(${frontPhoto})`,
  WebkitMaskSize: "100% 100%",
  maskSize: "100% 100%",
  WebkitMaskRepeat: "no-repeat",
  maskRepeat: "no-repeat",
};

export function WallE({
  mood = "tranquilo",
  thinking = false,
  speaking = false,
  petSignal = 0,
  onPet,
}) {
  const stageRef = useRef(null);
  const avatarRef = useRef(null);
  const petTimer = useRef(null);
  const [petting, setPetting] = useState(false);

  const pet = useCallback(() => {
    setPetting(true);
    if (petTimer.current) window.clearTimeout(petTimer.current);
    petTimer.current = window.setTimeout(() => setPetting(false), 1100);
    onPet?.();
  }, [onPet]);

  useEffect(() => {
    if (!petSignal) return undefined;
    setPetting(true);
    if (petTimer.current) window.clearTimeout(petTimer.current);
    petTimer.current = window.setTimeout(() => setPetting(false), 1100);
    return undefined;
  }, [petSignal]);

  useEffect(
    () => () => {
      if (petTimer.current) window.clearTimeout(petTimer.current);
    },
    []
  );

  useEffect(() => {
    const stage = stageRef.current;
    const avatar = avatarRef.current;
    if (!stage || !avatar) return undefined;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const pointer = { x: window.innerWidth * 0.5, y: window.innerHeight * 0.32 };
    const pose = { x: 0, y: 0, r: 0, gazeX: 0, gazeY: 0 };
    let lastMove = performance.now();
    let idleAt = 0;
    let frame = 0;

    const onMove = (event) => {
      pointer.x = event.clientX;
      pointer.y = event.clientY;
      lastMove = performance.now();
    };

    const loop = (now) => {
      if (now - lastMove > 6200 && now - idleAt > 3200) {
        idleAt = now;
        pointer.x = window.innerWidth * (0.35 + Math.random() * 0.3);
        pointer.y = window.innerHeight * (0.25 + Math.random() * 0.25);
      }

      const rect = stage.getBoundingClientRect();
      const cx = rect.left + rect.width * 0.5;
      const cy = rect.top + rect.height * 0.42;
      const nx = clamp((pointer.x - cx) / Math.max(1, rect.width * 0.5), -1, 1);
      const ny = clamp((pointer.y - cy) / Math.max(1, rect.height * 0.5), -1, 1);

      const targetX = nx * 5.2;
      const targetY = ny * 3.6;
      const targetR = nx * 1.15;
      const targetGazeX = nx * 7.5;
      const targetGazeY = ny * 5.0;
      const ease = reduce ? 1 : 0.09;

      pose.x += (targetX - pose.x) * ease;
      pose.y += (targetY - pose.y) * ease;
      pose.r += (targetR - pose.r) * ease;
      pose.gazeX += (targetGazeX - pose.gazeX) * (reduce ? 1 : 0.12);
      pose.gazeY += (targetGazeY - pose.gazeY) * (reduce ? 1 : 0.12);

      avatar.style.transform = `translate3d(${pose.x.toFixed(2)}px, ${pose.y.toFixed(2)}px, 0) rotate(${pose.r.toFixed(2)}deg)`;
      stage.style.setProperty("--gaze-x", `${pose.gazeX.toFixed(2)}px`);
      stage.style.setProperty("--gaze-y", `${pose.gazeY.toFixed(2)}px`);
      frame = window.requestAnimationFrame(loop);
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    frame = window.requestAnimationFrame(loop);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <div
      ref={stageRef}
      className={`walle-stage ${thinking ? "is-thinking" : ""} ${speaking ? "is-speaking" : ""} ${petting ? "is-petting" : ""}`}
      data-mood={mood}
      onDoubleClick={pet}
      role="img"
      aria-label="WALL-E, un robotito curioso, de frente. Sus lentes siguen el cursor."
    >
      <div
        className="walle-stage__backdrop"
        style={{ backgroundImage: `url(${cityPhoto})` }}
        aria-hidden="true"
      />
      <div className="walle-stage__vignette" aria-hidden="true" />
      <div className="walle-stage__grid" aria-hidden="true" />
      <div className="walle-stage__glow" aria-hidden="true" />
      <div className="walle-stage__scan" aria-hidden="true" />

      <div className="walle-dust" aria-hidden="true">
        {DUST.map(([x, y, size, delay], index) => (
          <i
            key={index}
            style={{
              left: `${x}%`,
              top: `${y}%`,
              width: `${size}px`,
              height: `${size}px`,
              animationDelay: `${delay}s`,
            }}
          />
        ))}
      </div>

      <div className="walle-avatar" ref={avatarRef}>
        <div className="walle-orbit" aria-hidden="true">
          <i />
          <i />
        </div>

        <div className="walle-breathe">
          <div className="walle-figure">
            <img
              className="walle-photo"
              src={frontPhoto}
              alt=""
              draggable="false"
              decoding="async"
            />

            <span className="walle-rim walle-rim--cool" style={MASK} aria-hidden="true" />
            <span className="walle-rim walle-rim--warm" style={MASK} aria-hidden="true" />
            <span className="walle-scan" style={MASK} aria-hidden="true" />

            <span className="walle-glint walle-glint--left" aria-hidden="true" />
            <span className="walle-glint walle-glint--right" aria-hidden="true" />
          </div>
        </div>

        <div className="walle-contact-shadow" aria-hidden="true" />

        {petting ? (
          <div className="walle-hearts" aria-hidden="true">
            <span>♥</span><span>♥</span><span>♥</span>
          </div>
        ) : null}
      </div>

      <div className="walle-stage__floor" aria-hidden="true" />
      <span className="walle-stage__hint">doble clic para acariciar</span>
    </div>
  );
}
