import { useEffect, useRef } from "react";
import { clamp } from "../../lib/format";

const DUST = [
  [8, 18, 2.2, 0], [22, 42, 1.4, 1.2], [12, 68, 1.8, 2.4], [30, 12, 1.2, 0.8],
  [78, 22, 1.6, 1.8], [88, 54, 2.4, 0.4], [70, 74, 1.2, 2.8], [92, 80, 1.8, 1.6],
  [44, 6, 1.4, 3.2], [58, 88, 2.0, 0.2], [6, 84, 1.6, 2.2], [96, 8, 1.2, 3.6],
];

function LensBarrel({ cx, tilt, clipId, eyeRef }) {
  const left = cx - 89;
  return (
    <g transform={`rotate(${tilt} ${cx} 126)`} className="lens-barrel">
      <rect x={left} y="56" width="178" height="136" rx="58" fill="url(#metalHead)" stroke="#4e3d29" strokeWidth="3" />
      <rect x={left + 12} y="64" width="154" height="34" rx="17" fill="#f0dfbd" opacity=".18" />
      <path d={`M${left + 20} 74 Q${cx} 58 ${left + 158} 74`} fill="none" stroke="#f6e6c6" strokeWidth="2" opacity=".25" />
      <circle cx={cx} cy="126" r="58" fill="#211a12" stroke="#6e5a40" strokeWidth="3" />
      <circle cx={cx} cy="126" r="50" fill="url(#lensGlass)" stroke="#2b2117" strokeWidth="2" />
      <g clipPath={`url(#${clipId})`}>
        <circle cx={cx} cy="126" r="49" fill="url(#lensGlass)" />
        <g className="eyeball" data-cx={cx} data-cy="126" ref={eyeRef}>
          <circle cx={cx} cy="126" r="30" fill="url(#lensIris)" />
          <circle cx={cx} cy="126" r="30" fill="none" stroke="#7a4312" strokeWidth="2" opacity=".55" />
          <circle cx={cx} cy="126" r="12" fill="#100a05" />
          <circle cx={cx - 8} cy="115" r="5.5" fill="#fff6e4" opacity=".9" />
          <circle cx={cx + 11} cy="137" r="2.4" fill="#fff6e4" opacity=".4" />
          <path d={`M${cx - 22} 138 Q${cx - 8} 154 ${cx + 15} 145`} fill="none" stroke="#ffd18a" strokeWidth="1.4" opacity=".35" />
        </g>
        <rect className="lid" x={cx - 50} y="76" width="100" height="100" fill="#090604" />
        <circle className="eye-scan" cx={cx} cy="126" r="39" fill="none" stroke="#7ef0e2" strokeWidth="1.4" strokeDasharray="6 9" opacity="0" />
        <path d={`M${cx - 34} 82 Q${cx} 64 ${cx + 38} 86`} fill="none" stroke="#ffffff" strokeWidth="2" opacity=".12" />
      </g>
      <circle cx={cx} cy="126" r="53" fill="none" stroke="#a58b63" strokeWidth="1.2" opacity=".7" />
      <circle cx={left + 22} cy="78" r="3.2" fill="#5b4932" />
      <circle cx={left + 156} cy="78" r="3.2" fill="#5b4932" />
      <circle cx={left + 22} cy="172" r="3.2" fill="#5b4932" />
      <circle cx={left + 156} cy="172" r="3.2" fill="#5b4932" />
      <path d={`M${left + 26} 154 q8 8 2 18`} stroke="#7a4a22" strokeWidth="2" fill="none" opacity=".6" />
      <path d={`M${left + 148} 96 q-6 10 2 18`} stroke="#7a4a22" strokeWidth="2" fill="none" opacity=".5" />
      <path d={`M${left + 34} 90 q14 5 9 18`} stroke="#f2d7a8" strokeWidth="1" fill="none" opacity=".25" />
    </g>
  );
}

export function WallE({ mood = "tranquilo", thinking = false, speaking = false, onPet }) {
  const svgRef = useRef(null);
  const headRef = useRef(null);
  const eyeLeft = useRef(null);
  const eyeRight = useRef(null);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return undefined;
    const eyes = [eyeLeft.current, eyeRight.current].filter(Boolean);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const pointer = { x: window.innerWidth * 0.5, y: window.innerHeight * 0.32 };
    const pose = { x: 0, y: 0, r: 0 };
    let lastMove = performance.now();
    let frame = 0;
    let idleAt = 0;

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
      const matrix = svg.getScreenCTM();
      if (matrix) {
        const point = new DOMPoint(pointer.x, pointer.y).matrixTransform(matrix.inverse());
        eyes.forEach((eye) => {
          const cx = Number(eye.dataset.cx);
          const cy = Number(eye.dataset.cy);
          const dx = point.x - cx;
          const dy = point.y - cy;
          const distance = Math.hypot(dx, dy) || 1;
          const reach = Math.min(11, distance / 12);
          const tx = (dx / distance) * reach;
          const ty = (dy / distance) * reach;
          const current = eye.__pose || { x: 0, y: 0 };
          current.x += (tx - current.x) * (reduce ? 1 : 0.18);
          current.y += (ty - current.y) * (reduce ? 1 : 0.18);
          eye.__pose = current;
          eye.setAttribute("transform", `translate(${current.x.toFixed(2)} ${current.y.toFixed(2)})`);
        });

        const head = headRef.current;
        if (head) {
          const gx = clamp((point.x - 280) * 0.012, -5, 5);
          const gy = clamp((point.y - 130) * 0.008, -4, 4);
          const gr = clamp((point.x - 280) * 0.006, -3.2, 3.2);
          pose.x += (gx - pose.x) * (reduce ? 1 : 0.12);
          pose.y += (gy - pose.y) * (reduce ? 1 : 0.12);
          pose.r += (gr - pose.r) * (reduce ? 1 : 0.12);
          head.style.transform = `translate(${pose.x.toFixed(2)}px, ${pose.y.toFixed(2)}px) rotate(${pose.r.toFixed(2)}deg)`;
        }
      }
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
      className={`walle-stage ${thinking ? "is-thinking" : ""} ${speaking ? "is-speaking" : ""}`}
      data-mood={mood}
      onDoubleClick={onPet}
    >
      <div className="walle-stage__grid" aria-hidden="true" />
      <div className="walle-stage__glow" aria-hidden="true" />
      <div className="walle-stage__scan" aria-hidden="true" />

      <div className="walle-hud walle-hud--left" aria-hidden="true">
        <span>OPTICAL LINK</span>
        <i /><i /><i /><i /><i />
        <b>BINOCULAR</b>
      </div>
      <div className="walle-hud walle-hud--right" aria-hidden="true">
        <span>UNIT 01</span>
        <b>{mood.toUpperCase()}</b>
        <em>SOLAR / 92%</em>
      </div>

      <svg
        ref={svgRef}
        className="walle-svg"
        viewBox="0 0 560 680"
        role="img"
        aria-label="WALL-E, el robot de Pixar, con ojos binocular que siguen el cursor"
      >
        <defs>
          <linearGradient id="metalBody" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#e0ad5b" />
            <stop offset="42%" stopColor="#c58a38" />
            <stop offset="100%" stopColor="#8a5721" />
          </linearGradient>
          <linearGradient id="metalBodyDark" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#a86e2b" />
            <stop offset="100%" stopColor="#6b3f17" />
          </linearGradient>
          <linearGradient id="metalHead" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#d9c7a3" />
            <stop offset="48%" stopColor="#b49b74" />
            <stop offset="100%" stopColor="#806846" />
          </linearGradient>
          <linearGradient id="treadMetal" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b3730" />
            <stop offset="50%" stopColor="#211e19" />
            <stop offset="100%" stopColor="#0b0a08" />
          </linearGradient>
          <linearGradient id="armMetal" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#8e5620" />
            <stop offset="45%" stopColor="#d59a48" />
            <stop offset="100%" stopColor="#7c4a1c" />
          </linearGradient>
          <linearGradient id="clawMetal" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#c9c1ad" />
            <stop offset="100%" stopColor="#6f6a5d" />
          </linearGradient>
          <radialGradient id="lensGlass" cx="38%" cy="30%" r="75%">
            <stop offset="0%" stopColor="#3a2a1c" />
            <stop offset="45%" stopColor="#150e09" />
            <stop offset="100%" stopColor="#050302" />
          </radialGradient>
          <radialGradient id="lensIris" cx="38%" cy="32%" r="70%">
            <stop offset="0%" stopColor="#fff0c9" />
            <stop offset="34%" stopColor="#f7bd62" />
            <stop offset="72%" stopColor="#d07b23" />
            <stop offset="100%" stopColor="#6e350a" />
          </radialGradient>
          <radialGradient id="shadow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#000000" stopOpacity=".72" />
            <stop offset="100%" stopColor="#000000" stopOpacity="0" />
          </radialGradient>
          <pattern id="rustSpeckle" width="46" height="46" patternUnits="userSpaceOnUse">
            <circle cx="6" cy="8" r="3" fill="#6b3313" opacity=".55" />
            <circle cx="18" cy="22" r="1.8" fill="#8d4a1c" opacity=".5" />
            <circle cx="36" cy="12" r="2.4" fill="#5d2c10" opacity=".45" />
            <circle cx="28" cy="38" r="3.6" fill="#7a3d15" opacity=".4" />
            <circle cx="43" cy="31" r="1.5" fill="#4e240b" opacity=".5" />
            <path d="M8 34 q6 2 4 8" stroke="#5a2a0e" strokeWidth="1.2" fill="none" opacity=".45" />
          </pattern>
          <pattern id="treadPattern" width="26" height="17" patternUnits="userSpaceOnUse">
            <rect width="19" height="7" rx="2" fill="#3b352b" opacity=".85" />
            <rect x="4" y="9" width="16" height="5" rx="2" fill="#24201a" opacity=".9" />
          </pattern>
          <filter id="amberGlow" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="7" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <filter id="softShadow" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="8" stdDeviation="10" floodColor="#000000" floodOpacity=".45" />
          </filter>
          <clipPath id="lensClipL"><circle cx="205" cy="126" r="50" /></clipPath>
          <clipPath id="lensClipR"><circle cx="355" cy="126" r="50" /></clipPath>
          <clipPath id="bodyClip">
            <path d="M126 238 H434 L452 260 V436 Q452 462 426 462 H134 Q108 462 108 436 V260 Z" />
          </clipPath>
          <clipPath id="treadClipL"><rect x="42" y="438" width="172" height="204" rx="54" /></clipPath>
          <clipPath id="treadClipR"><rect x="346" y="438" width="172" height="204" rx="54" /></clipPath>
          <g id="treadUnit">
            <rect x="42" y="438" width="172" height="204" rx="54" fill="url(#treadMetal)" stroke="#3a342b" strokeWidth="3" />
            <rect x="56" y="452" width="144" height="176" rx="42" fill="#0c0a08" stroke="#2a251e" strokeWidth="2" />
            <rect x="56" y="452" width="144" height="176" rx="42" fill="url(#treadPattern)" opacity=".92" />
            <g clipPath="url(#treadClipL)">
              <rect x="38" y="444" width="180" height="192" fill="url(#rustSpeckle)" opacity=".35" />
            </g>
            <circle cx="128" cy="500" r="29" fill="#17130f" stroke="#4b4235" strokeWidth="3" />
            <circle cx="128" cy="500" r="17" fill="#211b15" stroke="#5a4d3b" strokeWidth="2" />
            <circle cx="128" cy="500" r="6" fill="#0b0907" stroke="#6b5a43" strokeWidth="1.5" />
            <circle cx="128" cy="570" r="34" fill="#17130f" stroke="#4b4235" strokeWidth="3" />
            <circle cx="128" cy="570" r="20" fill="#211b15" stroke="#5a4d3b" strokeWidth="2" />
            <circle cx="128" cy="570" r="7" fill="#0b0907" stroke="#6b5a43" strokeWidth="1.5" />
            <g fill="#6a5c46">
              <circle cx="128" cy="478" r="2" /><circle cx="128" cy="522" r="2" />
              <circle cx="106" cy="570" r="2" /><circle cx="150" cy="570" r="2" />
            </g>
            <path d="M56 468 q10 8 6 22" stroke="#7a4a22" strokeWidth="2" fill="none" opacity=".45" />
            <path d="M178 540 q-8 12 2 24" stroke="#8a5528" strokeWidth="2" fill="none" opacity=".4" />
          </g>
        </defs>

        <ellipse cx="280" cy="646" rx="208" ry="20" fill="url(#shadow)" />

        {DUST.map(([x, y, r, delay], index) => (
          <circle
            key={index}
            className="walle-dust"
            cx={(x / 100) * 560}
            cy={80 + (y / 100) * 520}
            r={r}
            fill="#f2b45a"
            style={{ animationDelay: `${delay}s` }}
          />
        ))}

        <g className="walle-breathe">
          <use href="#treadUnit" />
          <use href="#treadUnit" transform="translate(560 0) scale(-1 1)" />
          <rect x="106" y="424" width="348" height="22" rx="11" fill="#241b12" stroke="#3b2c1c" strokeWidth="2" />
          <rect x="120" y="418" width="320" height="14" rx="7" fill="#5c3d20" opacity=".55" />

          {/* cuerpo */}
          <g filter="url(#softShadow)">
            <path d="M126 238 H434 L452 260 V436 Q452 462 426 462 H134 Q108 462 108 436 V260 Z" fill="url(#metalBody)" stroke="#4b2f14" strokeWidth="3" />
            <g clipPath="url(#bodyClip)">
              <rect x="108" y="238" width="344" height="224" fill="url(#rustSpeckle)" opacity=".7" />
              <path d="M112 300 q36 18 26 54 q-8 30 10 54" stroke="#6b3614" strokeWidth="8" fill="none" opacity=".25" />
              <path d="M430 284 q-24 26 -8 58 q12 24 -2 52" stroke="#5a2b0e" strokeWidth="6" fill="none" opacity=".22" />
              <path d="M138 444 q44 -18 86 2" stroke="#f6d79b" strokeWidth="1.5" fill="none" opacity=".18" />
              <path d="M300 250 q26 12 18 34" stroke="#6a3614" strokeWidth="3" fill="none" opacity=".3" />
            </g>
            <path d="M126 238 H434 L452 260 V272 H108 V260 Z" fill="#e5b463" opacity=".18" />
            <path d="M108 436 Q108 462 134 462 H426 Q452 462 452 436" fill="none" stroke="#3f2812" strokeWidth="3" />

            {/* bandeja superior */}
            <rect x="118" y="222" width="324" height="42" rx="9" fill="url(#metalBodyDark)" stroke="#5a3717" strokeWidth="2" />
            <rect x="126" y="228" width="308" height="9" rx="4.5" fill="#f2d19a" opacity=".16" />
            <rect x="138" y="236" width="82" height="22" rx="3" fill="#2a2117" stroke="#6c5433" strokeWidth="1.2" />
            {[0, 1, 2, 3, 4].map((line) => (
              <line key={line} x1="143" y1={240 + line * 3.4} x2="215" y2={240 + line * 3.4} stroke="#8a7147" strokeWidth="1" opacity=".55" />
            ))}
            <rect x="320" y="234" width="104" height="25" rx="4" fill="#16140d" stroke="#6a5b36" strokeWidth="1.4" />
            <circle cx="334" cy="246.5" r="5.5" fill="none" stroke="#d9c34c" strokeWidth="1.2" />
            {[0, 1, 2, 3, 4, 5, 6, 7].map((ray) => (
              <line
                key={ray}
                x1={334 + Math.cos((ray / 8) * Math.PI * 2) * 8}
                y1={246.5 + Math.sin((ray / 8) * Math.PI * 2) * 8}
                x2={334 + Math.cos((ray / 8) * Math.PI * 2) * 10.5}
                y2={246.5 + Math.sin((ray / 8) * Math.PI * 2) * 10.5}
                stroke="#d9c34c"
                strokeWidth="1.2"
              />
            ))}
            {[0, 1, 2, 3].map((bar) => (
              <rect key={bar} x={350 + bar * 15} y={242} width="9" height="9" rx="1.5" fill={bar < 3 ? "#d9c34c" : "#3b3621"} />
            ))}
            <text x="350" y="257" fill="#9d8a55" fontFamily="var(--font-mono)" fontSize="4.2" letterSpacing=".18em">SOLAR CHARGE LEVEL</text>

            {/* puerta compactadora */}
            <rect x="132" y="284" width="296" height="162" rx="10" fill="#c88d3d" stroke="#6b431c" strokeWidth="2.4" />
            <rect x="146" y="298" width="268" height="132" rx="6" fill="#b57a30" stroke="#7a4a1d" strokeWidth="1.6" />
            <rect x="154" y="306" width="252" height="116" rx="4" fill="url(#rustSpeckle)" opacity=".55" />
            <path d="M154 330 h252 M154 398 h252" stroke="#7a4a1d" strokeWidth="1" opacity=".45" />
            <path d="M176 306 q18 30 8 62 q-8 28 4 54" stroke="#6d3a16" strokeWidth="4" fill="none" opacity=".28" />
            <path d="M380 306 q-12 34 2 58 q10 22 -2 58" stroke="#5f3212" strokeWidth="3" fill="none" opacity=".24" />
            <g fill="#6b4a25">
              <circle cx="140" cy="292" r="2.4" /><circle cx="420" cy="292" r="2.4" />
              <circle cx="140" cy="438" r="2.4" /><circle cx="420" cy="438" r="2.4" />
            </g>
            <g fontFamily="var(--font-display)" fontWeight="700" fill="#3c2611" letterSpacing=".12em">
              <text x="190" y="424" fontSize="31">WALL</text>
              <circle cx="360" cy="413" r="16" fill="#a83426" />
              <text x="352" y="422" fontSize="22" fill="#f7e7d2">E</text>
            </g>
            <g className="walle-chest-led">
              <circle cx="160" cy="340" r="8" fill="#ff9a45" opacity=".2" filter="url(#amberGlow)" />
              <circle cx="160" cy="340" r="4.2" fill="#ffb15c" stroke="#8a4b1a" strokeWidth="1" />
              <circle cx="160" cy="340" r="1.5" fill="#fff3d8" />
            </g>
            <text x="171" y="343" fill="#6b4a25" fontFamily="var(--font-mono)" fontSize="5" letterSpacing=".12em">PWR</text>
            <rect x="396" y="332" width="8" height="8" rx="1" fill="#7fbf6a" opacity=".8" />
            <rect x="396" y="344" width="8" height="8" rx="1" fill="#d9c34c" opacity=".55" />
          </g>

          {/* brazos */}
          <g className="walle-arms">
            <g>
              <circle cx="112" cy="304" r="19" fill="#6f421a" stroke="#42270f" strokeWidth="3" />
              <circle cx="112" cy="304" r="8" fill="#d59a48" stroke="#5a3412" strokeWidth="1.5" />
              <path d="M112 318 C88 340 78 372 86 400" fill="none" stroke="#4a2a10" strokeWidth="27" strokeLinecap="round" />
              <path d="M112 318 C88 340 78 372 86 400" fill="none" stroke="url(#armMetal)" strokeWidth="19" strokeLinecap="round" />
              <path d="M96 342 l-8 4 M91 358 l-9 2 M88 374 l-9 1" stroke="#f4d6a0" strokeWidth="3" opacity=".35" />
              <circle cx="86" cy="404" r="14" fill="#6f421a" stroke="#42270f" strokeWidth="2.5" />
              <circle cx="86" cy="404" r="5" fill="#d59a48" />
              <path d="M88 412 C92 434 102 448 114 456" fill="none" stroke="#4a2a10" strokeWidth="20" strokeLinecap="round" />
              <path d="M88 412 C92 434 102 448 114 456" fill="none" stroke="url(#armMetal)" strokeWidth="13" strokeLinecap="round" />
              <g fill="url(#clawMetal)" stroke="#4f4a3e" strokeWidth="2">
                <path d="M112 448 l20 4 l8 12 l-10 9 l-16 -8 z" />
                <path d="M106 458 l14 8 l2 14 l-12 4 l-9 -12 z" />
              </g>
              <circle cx="118" cy="460" r="4" fill="#2c2820" />
            </g>
            <g transform="translate(560 0) scale(-1 1)">
              <circle cx="112" cy="304" r="19" fill="#6f421a" stroke="#42270f" strokeWidth="3" />
              <circle cx="112" cy="304" r="8" fill="#d59a48" stroke="#5a3412" strokeWidth="1.5" />
              <path d="M112 318 C88 340 78 372 86 400" fill="none" stroke="#4a2a10" strokeWidth="27" strokeLinecap="round" />
              <path d="M112 318 C88 340 78 372 86 400" fill="none" stroke="url(#armMetal)" strokeWidth="19" strokeLinecap="round" />
              <path d="M96 342 l-8 4 M91 358 l-9 2 M88 374 l-9 1" stroke="#f4d6a0" strokeWidth="3" opacity=".35" />
              <circle cx="86" cy="404" r="14" fill="#6f421a" stroke="#42270f" strokeWidth="2.5" />
              <circle cx="86" cy="404" r="5" fill="#d59a48" />
              <path d="M88 412 C92 434 102 448 114 456" fill="none" stroke="#4a2a10" strokeWidth="20" strokeLinecap="round" />
              <path d="M88 412 C92 434 102 448 114 456" fill="none" stroke="url(#armMetal)" strokeWidth="13" strokeLinecap="round" />
              <g fill="url(#clawMetal)" stroke="#4f4a3e" strokeWidth="2">
                <path d="M112 448 l20 4 l8 12 l-10 9 l-16 -8 z" />
                <path d="M106 458 l14 8 l2 14 l-12 4 l-9 -12 z" />
              </g>
              <circle cx="118" cy="460" r="4" fill="#2c2820" />
            </g>
          </g>

          {/* cuello */}
          <g className="walle-neck">
            <rect x="246" y="218" width="68" height="24" rx="8" fill="#5a3717" stroke="#3d240e" strokeWidth="2" />
            <rect x="256" y="188" width="48" height="34" rx="7" fill="url(#armMetal)" stroke="#4a2a10" strokeWidth="2" />
            {[0, 1, 2].map((ring) => (
              <rect key={ring} x="254" y={192 + ring * 10} width="52" height="4" rx="2" fill="#6b3f17" opacity=".7" />
            ))}
            <path d="M252 218 q-12 -16 -4 -32" fill="none" stroke="#3b2a1a" strokeWidth="3" />
            <path d="M308 218 q12 -16 4 -32" fill="none" stroke="#3b2a1a" strokeWidth="3" />
            <circle cx="280" cy="236" r="13" fill="#6f421a" stroke="#3d240e" strokeWidth="2" />
            <circle cx="280" cy="236" r="5" fill="#d59a48" />
          </g>

          {/* cabeza binocular */}
          <g id="walle-head" ref={headRef}>
            <rect x="250" y="86" width="60" height="76" rx="18" fill="#7d6342" stroke="#4e3d29" strokeWidth="2" />
            <rect x="260" y="96" width="40" height="58" rx="12" fill="#a88c63" opacity=".55" />
            <rect x="246" y="44" width="68" height="18" rx="9" fill="#8f7754" stroke="#4e3d29" strokeWidth="2" />
            <rect x="256" y="38" width="48" height="10" rx="5" fill="#6c563b" />
            <path d="M258 54 v30 M302 54 v30" stroke="#5f4b34" strokeWidth="5" />
            <LensBarrel cx={205} tilt={-7} clipId="lensClipL" eyeRef={eyeLeft} />
            <LensBarrel cx={355} tilt={7} clipId="lensClipR" eyeRef={eyeRight} />
            <rect x="252" y="100" width="56" height="44" rx="12" fill="#9b8158" stroke="#4e3d29" strokeWidth="2" />
            <circle cx="280" cy="122" r="5" fill="#4e3d29" />
            <path d="M252 108 q28 12 56 0" fill="none" stroke="#e2cda6" strokeWidth="2" opacity=".25" />
            <path d="M270 160 q10 6 20 0" fill="none" stroke="#5f4b34" strokeWidth="2" opacity=".5" />
          </g>

          {/* planta */}
          <g className="walle-plant">
            <path d="M38 602 h44 l-7 28 h-30 z" fill="#4c321a" stroke="#2f1d0d" strokeWidth="2" />
            <ellipse cx="60" cy="602" rx="22" ry="5" fill="#2c1a0b" />
            <path d="M60 602 q-2 -34 2 -56" stroke="#527a33" strokeWidth="3" fill="none" />
            <path d="M61 570 q-24 -10 -22 -32 q24 6 22 32" fill="#79a84e" stroke="#476b2c" strokeWidth="1.5" />
            <path d="M61 558 q20 -12 21 -30 q-22 4 -21 30" fill="#5f8c3a" stroke="#3f6027" strokeWidth="1.5" />
            <path d="M62 582 q-16 -6 -18 -20 q17 3 18 20" fill="#8ab95a" opacity=".8" />
          </g>
        </g>
      </svg>

      <div className="walle-stage__floor" aria-hidden="true" />
      <span className="walle-stage__tag">UNIT 01 // WALL·E // SOLAR</span>
    </div>
  );
}
