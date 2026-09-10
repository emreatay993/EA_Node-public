// Variant 1 — "Forging Core"
// The logo literally assembles itself. Four outer node rings fade in,
// four connector lines grow from each ring toward the center, then
// the core lights up and the wordmark resolves. This is the most
// brand-forward of the five — it's a re-performance of the app icon
// as a boot ceremony.

function V1ForgingCore() {
  const [phase, setPhase] = React.useState(0);
  // 0: outer rings appear → 1: connectors draw in → 2: core ignites →
  // 3: wordmark fades in → 4: settle & progress to 100 → loop
  React.useEffect(() => {
    const seq = [
      [500, 1], [800, 2], [500, 3], [900, 4], [900, 0],
    ];
    let t;
    let idx = 0;
    const tick = () => {
      const [ms, next] = seq[idx];
      t = setTimeout(() => {
        setPhase(next);
        idx = (idx + 1) % seq.length;
        tick();
      }, ms);
    };
    tick();
    return () => clearTimeout(t);
  }, []);

  const boot = useBootSequence([
    'Initialising runtime…',
    'Loading node registry',
    'Registering 142 node types',
    'Scanning plug-ins',
    'Connecting viewer backend',
    'Warming canvas',
    'Ready',
  ], { loop: true, stepMs: 700 });

  // Coordinates in a 260×260 box (logo geometry from corex_app.svg: 1024 canvas,
  // outer rings at 286.72 and 737.28, core at 512). Scaled down to 260.
  const S = 260;
  const outer = [
    { x: 56, y: 56 }, { x: 204, y: 56 },
    { x: 56, y: 204 }, { x: 204, y: 204 },
  ];
  const cx = S / 2, cy = S / 2;
  const ringsVisible = phase >= 0;
  const linesVisible = phase >= 1;
  const coreVisible  = phase >= 2;
  const wordVisible  = phase >= 3;

  return (
    <SplashFrame>
      {/* Ambient radial lift behind the mark */}
      <div style={{
        position: 'absolute', inset: 0,
        background: `radial-gradient(ellipse 60% 60% at 50% 45%, rgba(47,107,255,0.14), transparent 60%)`,
        pointerEvents: 'none',
      }} />
      {/* Subtle grid */}
      <div style={{
        position: 'absolute', inset: 0, opacity: 0.6,
        backgroundImage:
          `linear-gradient(${COREX.grid} 1px, transparent 1px),` +
          `linear-gradient(90deg, ${COREX.grid} 1px, transparent 1px)`,
        backgroundSize: '32px 32px',
        maskImage: 'radial-gradient(ellipse 70% 70% at 50% 50%, black, transparent 80%)',
      }} />

      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexDirection: 'column',
      }}>
        {/* The mark */}
        <svg width={S} height={S} viewBox={`0 0 ${S} ${S}`} style={{ overflow: 'visible' }}>
          <defs>
            <linearGradient id="v1-conn" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor={COREX.blue} />
              <stop offset="100%" stopColor={COREX.cyan} />
            </linearGradient>
            <radialGradient id="v1-core">
              <stop offset="0%" stopColor={COREX.cyan} />
              <stop offset="100%" stopColor={COREX.blue} />
            </radialGradient>
            <filter id="v1-glow" x="-60%" y="-60%" width="220%" height="220%">
              <feGaussianBlur stdDeviation="6" />
            </filter>
          </defs>

          {/* Core halo — only when ignited */}
          <circle cx={cx} cy={cy} r="38" fill="url(#v1-core)"
            opacity={coreVisible ? 0.28 : 0} filter="url(#v1-glow)"
            style={{ transition: 'opacity 500ms ease' }} />

          {/* Connectors from each outer node to the core */}
          {outer.map((o, idx) => {
            const dx = cx - o.x, dy = cy - o.y;
            const len = Math.hypot(dx, dy);
            return (
              <line key={idx}
                x1={o.x} y1={o.y}
                x2={o.x + dx * (linesVisible ? 1 : 0.05)}
                y2={o.y + dy * (linesVisible ? 1 : 0.05)}
                stroke="url(#v1-conn)"
                strokeWidth="7" strokeLinecap="round"
                opacity={linesVisible ? 1 : 0}
                style={{
                  transition: `all ${600 + idx * 80}ms cubic-bezier(.2,.8,.2,1)`,
                }}
              />
            );
          })}

          {/* X crossbars through the core, like the logo */}
          <line x1="92" y1="92" x2="168" y2="168"
            stroke={COREX.softBlue} strokeOpacity="0.92" strokeWidth="3" strokeLinecap="round"
            opacity={coreVisible ? 1 : 0}
            style={{ transition: 'opacity 400ms ease 150ms' }} />
          <line x1="168" y1="92" x2="92" y2="168"
            stroke={COREX.softBlue} strokeOpacity="0.92" strokeWidth="3" strokeLinecap="round"
            opacity={coreVisible ? 1 : 0}
            style={{ transition: 'opacity 400ms ease 220ms' }} />

          {/* Outer node rings */}
          {outer.map((o, idx) => (
            <g key={idx}
              opacity={ringsVisible ? 1 : 0}
              transform={`translate(${o.x} ${o.y}) scale(${ringsVisible ? 1 : 0.5})`}
              style={{
                transformOrigin: `${o.x}px ${o.y}px`,
                transformBox: 'fill-box',
                transition: `all 420ms cubic-bezier(.2,.8,.2,1) ${idx * 90}ms`,
              }}>
              <circle r="13" fill={COREX.bgNode} stroke={COREX.blue} strokeWidth="4" />
            </g>
          ))}

          {/* Core */}
          <circle cx={cx} cy={cy} r="20" fill="url(#v1-core)"
            opacity={coreVisible ? 1 : 0}
            style={{ transition: 'opacity 400ms ease' }} />
          <circle cx={cx} cy={cy} r="28" fill="none"
            stroke={COREX.softBlue} strokeOpacity="0.35" strokeWidth="2.7"
            opacity={coreVisible ? 1 : 0}
            style={{ transition: 'opacity 500ms ease 120ms' }} />
        </svg>

        {/* Wordmark */}
        <div style={{
          marginTop: 24,
          opacity: wordVisible ? 1 : 0,
          transform: wordVisible ? 'translateY(0)' : 'translateY(4px)',
          transition: 'all 500ms cubic-bezier(.2,.8,.2,1)',
        }}>
          <CorexWordmark size={32} />
        </div>
        <div style={{
          marginTop: 6, fontSize: 11, color: COREX.fgDim, letterSpacing: 1.2,
          textTransform: 'uppercase',
          opacity: wordVisible ? 1 : 0,
          transition: 'opacity 400ms ease 200ms',
        }}>
          Node Editor
        </div>
      </div>

      {/* Footer strip */}
      <div style={{
        position: 'absolute', left: 24, right: 24, bottom: 20,
      }}>
        <SplashProgress value={boot.progress} label={boot.step} sub={`${Math.round(boot.progress * 100)}%`} />
      </div>

      {/* Version corner */}
      <div style={{
        position: 'absolute', top: 16, right: 20,
        fontSize: 10, color: COREX.fgDim, fontFamily: '"Cascadia Mono", Consolas, monospace',
        letterSpacing: 0.5,
      }}>
        v0.9.3 · build 2048
      </div>
    </SplashFrame>
  );
}

window.V1ForgingCore = V1ForgingCore;
