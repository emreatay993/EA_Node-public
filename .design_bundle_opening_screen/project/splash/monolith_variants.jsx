// Monolith family — 5 variations on the "static hero" splash.
// All use the COREX mark as the hero; no assembly choreography.

// M1 — Breathe (baseline refined)
function M1_Breathe({ size = 180, breatheDur = 2.4 } = {}) {
  const boot = useBootSequence(['Initialising runtime…','Loading registry','Scanning plug-ins','Loading viewer','Ready'], { stepMs: 720 });
  return (
    <SplashFrame>
      <div style={{ position:'absolute', inset:0,
        background:'radial-gradient(ellipse 55% 55% at 50% 45%, rgba(47,107,255,0.16), transparent 60%)' }} />
      <div style={{ position:'absolute', inset:0, display:'flex', flexDirection:'column',
        alignItems:'center', justifyContent:'center' }}>
        <Mark size={size} breathing breatheDur={breatheDur} />
        <div style={{ marginTop: 28 }}><CorexWordmark size={36} /></div>
        <div style={{ marginTop: 8, fontSize: 11, color: COREX.fgDim,
          letterSpacing: 2, textTransform:'uppercase', fontWeight: 500 }}>Node Editor · v0.9.3</div>
      </div>
      <div style={{ position:'absolute', left: 32, right: 32, bottom: 22 }}>
        <SplashProgress value={boot.progress} label={boot.step} sub={`${Math.round(boot.progress*100)}%`} />
      </div>
    </SplashFrame>
  );
}

// M6 — Schematic (PCB-trace backdrop behind a breathing mark)
function M6_Schematic({ size = 180, breatheDur = 2.4 } = {}) {
  const boot = useBootSequence(['Initialising runtime…','Loading registry','Scanning plug-ins','Loading viewer','Ready'], { stepMs: 720 });
  return (
    <SplashFrame>
      <div style={{ position:'absolute', inset:0,
        background:'radial-gradient(ellipse 55% 55% at 50% 45%, rgba(47,107,255,0.16), transparent 60%)' }} />

      {/* Schematic / PCB background — orthogonal traces + vias + component pads */}
      <SchematicBackdrop />

      <div style={{ position:'absolute', inset:0, display:'flex', flexDirection:'column',
        alignItems:'center', justifyContent:'center' }}>
        <Mark size={size} breathing breatheDur={breatheDur} />
        <div style={{ marginTop: 28 }}><CorexWordmark size={36} /></div>
        <div style={{ marginTop: 8, fontSize: 11, color: COREX.fgDim,
          letterSpacing: 2, textTransform:'uppercase', fontWeight: 500 }}>Node Editor · v0.9.3</div>
      </div>
      <div style={{ position:'absolute', left: 32, right: 32, bottom: 22 }}>
        <SplashProgress value={boot.progress} label={boot.step} sub={`${Math.round(boot.progress*100)}%`} />
      </div>
    </SplashFrame>
  );
}

// Schematic / PCB-style trace backdrop. Muted COREX blue, kept behind
// the mark so the logo stays hero. A few "live" traces carry a slow
// pulse — echoes the breathing of the mark without distracting.
function SchematicBackdrop() {
  // Logo sits centered; keep a clear ~150px radius around center.
  // Canvas is 720×440. We mask out a center circle.
  const W = 720, H = 440;
  const cx = W/2, cy = H/2 - 10; // logo center offset slightly up
  const clearR = 170; // clear radius around mark

  // Traces: each is a polyline in right-angle style. Endpoints get a "pad"
  // (small square or rounded rect), joints get a small "via" dot.
  const traces = [
    // Upper-left cluster
    { pts: [[40,60],[120,60],[120,110],[230,110]], live: true,  speed: 3.2, delay: 0 },
    { pts: [[40,110],[80,110],[80,170],[190,170]], live: false },
    { pts: [[40,180],[90,180],[90,220]],           live: false },
    { pts: [[60,250],[160,250],[160,300]],         live: true,  speed: 3.8, delay: 1.1 },
    // Upper-right cluster
    { pts: [[680,60],[600,60],[600,100],[490,100]],live: false },
    { pts: [[680,120],[640,120],[640,180],[530,180]],live: true,  speed: 3.5, delay: 0.6 },
    { pts: [[680,200],[620,200],[620,230]],        live: false },
    { pts: [[680,260],[560,260],[560,310]],        live: false },
    // Bottom row
    { pts: [[80,340],[200,340]],                   live: false },
    { pts: [[280,350],[400,350],[400,390]],        live: true,  speed: 4.2, delay: 1.8 },
    { pts: [[520,340],[640,340]],                  live: false },
    // Header row (thin top strip)
    { pts: [[180,30],[360,30],[360,70]],           live: false },
    { pts: [[500,30],[540,30],[540,70]],           live: false },
  ];

  // Small "components" — rectangular pads with labels
  const components = [
    { x: 220, y: 98,  w: 36, h: 20, label: 'R12' },
    { x: 470, y: 88,  w: 36, h: 20, label: 'C03' },
    { x: 170, y: 240, w: 40, h: 20, label: 'IC1' },
    { x: 480, y: 300, w: 40, h: 20, label: 'U4'  },
    { x: 280, y: 378, w: 50, h: 14, label: null  }, // resistor
    { x: 390, y: 14,  w: 50, h: 14, label: null  },
  ];

  function pathFromPts(pts) {
    return pts.map((p,i) => `${i===0?'M':'L'} ${p[0]} ${p[1]}`).join(' ');
  }

  function traceLen(pts) {
    let d = 0;
    for (let i = 1; i < pts.length; i++) {
      d += Math.hypot(pts[i][0]-pts[i-1][0], pts[i][1]-pts[i-1][1]);
    }
    return d;
  }

  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}
      style={{ position:'absolute', inset: 0, pointerEvents: 'none' }}>
      <defs>
        <mask id="sch-mask">
          <rect x="0" y="0" width={W} height={H} fill="white" />
          <radialGradient id="sch-clear">
            <stop offset="0%" stopColor="black" stopOpacity="1" />
            <stop offset="70%" stopColor="black" stopOpacity="1" />
            <stop offset="100%" stopColor="black" stopOpacity="0" />
          </radialGradient>
          <circle cx={cx} cy={cy} r={clearR} fill="url(#sch-clear)" />
        </mask>
        <linearGradient id="sch-live" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%"  stopColor={COREX.blue}  stopOpacity="0" />
          <stop offset="50%" stopColor={COREX.cyan}  stopOpacity="0.9" />
          <stop offset="100%" stopColor={COREX.blue} stopOpacity="0" />
        </linearGradient>
      </defs>

      <g mask="url(#sch-mask)" opacity="0.85">
        {/* Subtle dot-grid markers (PCB fiducials) */}
        {Array.from({ length: 10 }).map((_, i) => (
          Array.from({ length: 6 }).map((_, j) => (
            <circle key={`${i}-${j}`}
              cx={60 + i * 68} cy={50 + j * 68} r="1"
              fill={COREX.softBlue} fillOpacity="0.18" />
          ))
        ))}

        {/* Component pads */}
        {components.map((c, i) => (
          <g key={`c${i}`}>
            <rect x={c.x} y={c.y} width={c.w} height={c.h} rx="2"
              fill="rgba(11,15,26,0.9)"
              stroke={COREX.border} strokeWidth="1" />
            {/* pin stripes (resistor style) if no label */}
            {!c.label && (
              <>
                <line x1={c.x+8}  y1={c.y+2} x2={c.x+8}  y2={c.y+c.h-2}
                  stroke={COREX.softBlue} strokeOpacity="0.5" strokeWidth="1.5" />
                <line x1={c.x+16} y1={c.y+2} x2={c.x+16} y2={c.y+c.h-2}
                  stroke={COREX.cyan}     strokeOpacity="0.6" strokeWidth="1.5" />
                <line x1={c.x+24} y1={c.y+2} x2={c.x+24} y2={c.y+c.h-2}
                  stroke={COREX.softBlue} strokeOpacity="0.5" strokeWidth="1.5" />
                <line x1={c.x+32} y1={c.y+2} x2={c.x+32} y2={c.y+c.h-2}
                  stroke={COREX.cyan}     strokeOpacity="0.6" strokeWidth="1.5" />
              </>
            )}
            {c.label && (
              <text x={c.x + c.w/2} y={c.y + c.h/2 + 3.5}
                fill={COREX.softBlue} fillOpacity="0.7"
                fontSize="8.5" fontFamily='"Cascadia Mono", Consolas, monospace'
                textAnchor="middle" letterSpacing="0.5" fontWeight="600">
                {c.label}
              </text>
            )}
          </g>
        ))}

        {/* Traces */}
        {traces.map((t, i) => {
          const d = pathFromPts(t.pts);
          const len = traceLen(t.pts);
          return (
            <g key={`t${i}`}>
              {/* Base trace */}
              <path d={d} fill="none"
                stroke={COREX.softBlue} strokeOpacity={t.live ? 0.55 : 0.35}
                strokeWidth="1.25" strokeLinecap="square" strokeLinejoin="miter" />
              {/* Joints (vias) at every interior point */}
              {t.pts.slice(1, -1).map((p, j) => (
                <circle key={j} cx={p[0]} cy={p[1]} r="2.2"
                  fill={COREX.bgCard} stroke={COREX.softBlue}
                  strokeOpacity="0.7" strokeWidth="1" />
              ))}
              {/* Endpoint pads */}
              {[t.pts[0], t.pts[t.pts.length-1]].map((p, j) => (
                <rect key={j} x={p[0]-3} y={p[1]-3} width="6" height="6" rx="1"
                  fill={COREX.bgCard} stroke={COREX.softBlue}
                  strokeOpacity={t.live ? 0.95 : 0.65} strokeWidth="1.25" />
              ))}
              {/* Live pulse — a glowing dashed overlay that marches along */}
              {t.live && (
                <path d={d} fill="none"
                  stroke={COREX.cyan} strokeOpacity="0.85"
                  strokeWidth="1.4" strokeLinecap="round"
                  strokeDasharray={`${Math.max(16, len*0.08)} ${len}`}>
                  <animate attributeName="stroke-dashoffset"
                    from="0" to={-len}
                    dur={`${t.speed || 3.5}s`}
                    begin={`${t.delay || 0}s`}
                    repeatCount="indefinite" />
                </path>
              )}
            </g>
          );
        })}
      </g>
    </svg>
  );
}

// M2 — Pulse-out (concentric rings emit on each step)
function M2_PulseOut() {
  const boot = useBootSequence(['Ignite runtime','Resolve registry','Load viewer','Ready'], { stepMs: 820 });
  // On every step change, emit a new ring from center
  const [rings, setRings] = React.useState([]);
  React.useEffect(() => {
    const id = Date.now();
    setRings(r => [...r, id].slice(-3));
    const t = setTimeout(() => setRings(r => r.filter(x => x !== id)), 2000);
    return () => clearTimeout(t);
  }, [boot.i]);

  return (
    <SplashFrame>
      <div style={{ position:'absolute', inset:0,
        background:'radial-gradient(circle at 50% 45%, rgba(47,107,255,0.14), transparent 55%)' }} />
      <div style={{ position:'absolute', inset:0, display:'flex', flexDirection:'column',
        alignItems:'center', justifyContent:'center' }}>
        <div style={{ position:'relative', width: 220, height: 220,
          display:'flex', alignItems:'center', justifyContent:'center' }}>
          <svg width="220" height="220" style={{ position:'absolute', inset:0, overflow:'visible' }}>
            {rings.map((id,i) => (
              <circle key={id} cx="110" cy="110" r="30" fill="none"
                stroke={COREX.cyan} strokeWidth="1.5" opacity="0.5"
                style={{ animation: 'm2Pulse 2s ease-out forwards' }} />
            ))}
          </svg>
          <Mark size={160} breathing />
        </div>
        <div style={{ marginTop: 24 }}><CorexWordmark size={32} /></div>
        <div style={{ marginTop: 6, fontSize: 11, color: COREX.fgDim,
          letterSpacing: 1.8, textTransform:'uppercase' }}>Node Editor</div>
      </div>
      <div style={{ position:'absolute', left: 32, right: 32, bottom: 22 }}>
        <SplashProgress value={boot.progress} label={boot.step} sub={`${Math.round(boot.progress*100)}%`} />
      </div>
      <style>{`@keyframes m2Pulse {
        0% { r: 30; opacity: 0.7; stroke-width: 2; }
        100% { r: 160; opacity: 0; stroke-width: 0.5; }
      }`}</style>
    </SplashFrame>
  );
}

// M3 — Rotating halo (orbit ring slowly rotates)
function M3_Halo() {
  const boot = useBootSequence(['Booting','Resolving','Warming','Ready'], { stepMs: 900 });
  return (
    <SplashFrame>
      <div style={{ position:'absolute', inset:0,
        background:'radial-gradient(ellipse 50% 50% at 50% 45%, rgba(0,209,255,0.14), transparent 60%)' }} />
      <div style={{ position:'absolute', inset:0, display:'flex', flexDirection:'column',
        alignItems:'center', justifyContent:'center' }}>
        <div style={{ position:'relative', width: 260, height: 260 }}>
          {/* Orbit ring — slowly rotates */}
          <svg width="260" height="260" style={{ position:'absolute', inset:0, overflow:'visible',
            animation: 'm3Spin 24s linear infinite' }}>
            <circle cx="130" cy="130" r="122" fill="none"
              stroke={COREX.border} strokeWidth="1" strokeDasharray="3 5" />
            <circle cx="130" cy="130" r="122" fill="none"
              stroke="url(#m3-arc)" strokeWidth="2" strokeDasharray="80 380"
              strokeLinecap="round" />
            <defs>
              <linearGradient id="m3-arc" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor={COREX.cyan} /><stop offset="100%" stopColor={COREX.blue} stopOpacity="0" />
              </linearGradient>
            </defs>
          </svg>
          <div style={{ position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center' }}>
            <Mark size={170} breathing />
          </div>
        </div>
        <div style={{ marginTop: 18 }}><CorexWordmark size={30} /></div>
        <div style={{ marginTop: 6, fontSize: 11, color: COREX.fgDim,
          letterSpacing: 1.8, textTransform:'uppercase' }}>Node Editor · v0.9.3</div>
      </div>
      <div style={{ position:'absolute', left: 32, right: 32, bottom: 22 }}>
        <SplashProgress value={boot.progress} label={boot.step} sub={`${Math.round(boot.progress*100)}%`} />
      </div>
      <style>{`@keyframes m3Spin { to { transform: rotate(360deg); transform-origin: 50% 50%; } }`}</style>
    </SplashFrame>
  );
}

// M4 — Huge (oversized mark bleeds past top/bottom; wordmark stacked at right)
function M4_Huge() {
  const boot = useBootSequence(['Starting COREX','Loading','Ready'], { stepMs: 1000 });
  return (
    <SplashFrame>
      <div style={{ position:'absolute', inset:0,
        background:'radial-gradient(ellipse 70% 80% at 28% 50%, rgba(47,107,255,0.18), transparent 60%)' }} />

      <div style={{ position:'absolute', left: -60, top: '50%', transform:'translateY(-50%)',
        pointerEvents:'none' }}>
        <Mark size={520} breathing />
      </div>

      <div style={{ position:'absolute', right: 44, top: 0, bottom: 64,
        display:'flex', flexDirection:'column', justifyContent:'center', alignItems:'flex-end',
        textAlign:'right' }}>
        <div style={{ fontSize: 10, color: COREX.fgDim, letterSpacing: 2.4,
          textTransform:'uppercase', fontWeight: 600, marginBottom: 14,
          fontFamily:'"Cascadia Mono", Consolas, monospace' }}>v0.9.3 · build 2048</div>
        <CorexWordmark size={44} />
        <div style={{ fontSize: 13, color: COREX.fgMuted, marginTop: 10,
          letterSpacing: 1.2, textTransform:'uppercase', fontWeight: 500 }}>Node Editor</div>
        <div style={{ width: 160, height: 1, background: COREX.border, margin: '20px 0' }} />
        <div style={{ fontSize: 11, color: COREX.fgDim, lineHeight: 1.7,
          fontFamily:'"Cascadia Mono", Consolas, monospace' }}>
          visual dataflow<br/>for engineers
        </div>
      </div>

      <div style={{ position:'absolute', left: 320, right: 44, bottom: 22 }}>
        <SplashProgress value={boot.progress} label={boot.step} sub={`${Math.round(boot.progress*100)}%`} />
      </div>
    </SplashFrame>
  );
}

// M5 — Scan (horizontal scan-line sweeps the mark)
function M5_Scan() {
  const boot = useBootSequence(['Scanning','Resolving','Ready'], { stepMs: 900 });
  return (
    <SplashFrame>
      <div style={{ position:'absolute', inset:0,
        background:'radial-gradient(ellipse 55% 55% at 50% 45%, rgba(47,107,255,0.14), transparent 60%)' }} />
      {/* Horizontal scan band */}
      <div style={{ position:'absolute', inset:0, overflow:'hidden', pointerEvents:'none' }}>
        <div style={{
          position:'absolute', left: 0, right: 0, height: 4,
          background: `linear-gradient(90deg, transparent, ${COREX.cyan}, transparent)`,
          boxShadow: `0 0 20px ${COREX.cyan}`,
          animation: 'm5Scan 3.2s cubic-bezier(.4,.0,.6,1) infinite',
        }} />
      </div>

      <div style={{ position:'absolute', inset:0, display:'flex', flexDirection:'column',
        alignItems:'center', justifyContent:'center' }}>
        <div style={{ position:'relative' }}>
          {/* Mono ghost underneath */}
          <div style={{ filter:'grayscale(1) brightness(0.7)', opacity: 0.5 }}>
            <Mark size={180} />
          </div>
          {/* Real mark on top with clip animating vertically */}
          <div style={{
            position:'absolute', inset:0,
            animation: 'm5Reveal 3.2s cubic-bezier(.4,.0,.6,1) infinite',
          }}>
            <Mark size={180} breathing />
          </div>
        </div>
        <div style={{ marginTop: 24 }}><CorexWordmark size={30} /></div>
        <div style={{ marginTop: 8, fontSize: 10, color: COREX.fgDim,
          letterSpacing: 2, textTransform:'uppercase',
          fontFamily:'"Cascadia Mono", Consolas, monospace' }}>
          [ SCAN ] initialising · v0.9.3
        </div>
      </div>
      <div style={{ position:'absolute', left: 32, right: 32, bottom: 22 }}>
        <SplashProgress value={boot.progress} label={boot.step} sub={`${Math.round(boot.progress*100)}%`} />
      </div>
      <style>{`
        @keyframes m5Scan {
          0% { top: -4%; } 100% { top: 104%; }
        }
        @keyframes m5Reveal {
          0% { clip-path: inset(100% 0 0 0); }
          50% { clip-path: inset(0 0 0 0); }
          100% { clip-path: inset(0 0 100% 0); }
        }
      `}</style>
    </SplashFrame>
  );
}

Object.assign(window, { M1_Breathe, M2_PulseOut, M3_Halo, M4_Huge, M5_Scan, M6_Schematic, SchematicBackdrop });
