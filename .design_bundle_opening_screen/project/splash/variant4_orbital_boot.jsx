// Variant 4 — "Orbital Boot"
// The core pulses at center while three orbital nodes rotate around
// it, each representing a subsystem being warmed (Runtime · Registry ·
// engineering viewer). Active orbit node lights up; others are dim rings. Beneath
// the orbit: a checklist of boot tasks ticks off. This variant trades
// raw "graph vocabulary" for a more contemplative brand moment —
// closer to a hero-splash than a canvas.

function V4OrbitalBoot() {
  const [angle, setAngle] = React.useState(0);
  React.useEffect(() => {
    let raf;
    let start = performance.now();
    const loop = (t) => {
      setAngle(((t - start) / 40) % 360); // slow, dignified
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  const tasks = [
    { label: 'Runtime',       sub: 'Python · PyQt · QML' },
    { label: 'Node registry', sub: '142 node types' },
    { label: 'viewer backend',   sub: 'PyVista 2024 R2' },
    { label: 'Workspace',     sub: 'Restored from session' },
  ];
  const boot = useBootSequence(tasks.map(t => t.label), { stepMs: 700 });
  const curTask = Math.min(boot.i, tasks.length - 1);

  const cx = 120, cy = 120, R = 78;
  const orbits = [0, 120, 240];

  return (
    <SplashFrame>
      {/* Ambient radial */}
      <div style={{
        position: 'absolute', inset: 0,
        background: `radial-gradient(circle at 22% 50%, rgba(47,107,255,0.18), transparent 55%)`,
      }} />
      {/* Dot grid */}
      <div style={{
        position: 'absolute', inset: 0, opacity: 0.4,
        backgroundImage:
          `radial-gradient(circle, ${COREX.gridStrong} 1px, transparent 1.2px)`,
        backgroundSize: '22px 22px',
      }} />

      <div style={{
        position: 'absolute', top: 0, bottom: 0, left: 40,
        display: 'flex', alignItems: 'center',
      }}>
        <svg width="240" height="240" style={{ overflow: 'visible' }}>
          <defs>
            <radialGradient id="v4-core"><stop offset="0" stopColor={COREX.cyan} /><stop offset="1" stopColor={COREX.blue} /></radialGradient>
            <filter id="v4-glow" x="-80%" y="-80%" width="260%" height="260%">
              <feGaussianBlur stdDeviation="8" />
            </filter>
          </defs>
          {/* Orbit ring */}
          <circle cx={cx} cy={cy} r={R} fill="none"
            stroke={COREX.border} strokeWidth="1" strokeDasharray="2 4" />
          <circle cx={cx} cy={cy} r={R - 16} fill="none"
            stroke={COREX.borderSoft} strokeWidth="1" />

          {/* Core halo + core */}
          <circle cx={cx} cy={cy} r="36" fill="url(#v4-core)" opacity="0.22" filter="url(#v4-glow)" />
          <circle cx={cx} cy={cy} r="16" fill="url(#v4-core)">
            <animate attributeName="r" values="14;18;14" dur="2.2s" repeatCount="indefinite" />
          </circle>
          <circle cx={cx} cy={cy} r="22" fill="none" stroke={COREX.softBlue} strokeOpacity="0.4" strokeWidth="2" />

          {/* Orbit nodes */}
          {orbits.map((base, idx) => {
            const rad = ((base + angle) * Math.PI) / 180;
            const nx = cx + Math.cos(rad) * R;
            const ny = cy + Math.sin(rad) * R;
            const active = idx === curTask % orbits.length;
            return (
              <g key={idx}>
                {/* Connector from core */}
                <line x1={cx} y1={cy} x2={nx} y2={ny}
                  stroke={active ? 'url(#v4-edge)' : COREX.borderSoft}
                  strokeOpacity={active ? 0.9 : 0.5}
                  strokeWidth={active ? 2 : 1} />
                <circle cx={nx} cy={ny} r={active ? 11 : 7}
                  fill={COREX.bgNode}
                  stroke={active ? COREX.cyan : COREX.blue}
                  strokeWidth={active ? 3 : 2}
                />
                {active && (
                  <circle cx={nx} cy={ny} r="15" fill="none"
                    stroke={COREX.cyan} strokeOpacity="0.4" strokeWidth="1.5">
                    <animate attributeName="r" values="12;20;12" dur="1.4s" repeatCount="indefinite" />
                    <animate attributeName="stroke-opacity" values="0.6;0;0.6" dur="1.4s" repeatCount="indefinite" />
                  </circle>
                )}
              </g>
            );
          })}
          <defs>
            <linearGradient id="v4-edge" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
            </linearGradient>
          </defs>
        </svg>
      </div>

      {/* Right-side: brand + checklist */}
      <div style={{
        position: 'absolute', top: 44, right: 40, bottom: 68, width: 340,
        display: 'flex', flexDirection: 'column',
      }}>
        <CorexWordmark size={30} />
        <div style={{
          fontSize: 10, color: COREX.fgDim, marginTop: 4,
          letterSpacing: 1.4, textTransform: 'uppercase', fontWeight: 500,
        }}>Node Editor · v0.9.3</div>

        <div style={{
          marginTop: 28, display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          {tasks.map((t, idx) => {
            const done = idx < curTask;
            const active = idx === curTask;
            return (
              <div key={idx} style={{
                display: 'grid', gridTemplateColumns: '16px 1fr auto',
                alignItems: 'center', gap: 12,
                opacity: done || active ? 1 : 0.5,
                transition: 'opacity 200ms',
              }}>
                <div style={{
                  width: 10, height: 10, borderRadius: '50%',
                  background: done ? COREX.ok : active ? COREX.running : 'transparent',
                  border: `1.5px solid ${done ? COREX.ok : active ? COREX.running : COREX.border}`,
                  boxShadow: active ? `0 0 10px ${COREX.running}` : 'none',
                  justifySelf: 'center',
                }} />
                <div>
                  <div style={{ fontSize: 12, fontWeight: 500, color: COREX.fg }}>{t.label}</div>
                  <div style={{ fontSize: 10, color: COREX.fgDim, marginTop: 2,
                    fontFamily: '"Cascadia Mono", Consolas, monospace' }}>{t.sub}</div>
                </div>
                <div style={{
                  fontSize: 10, color: done ? COREX.ok : active ? COREX.running : COREX.fgDim,
                  fontFamily: '"Cascadia Mono", Consolas, monospace',
                  textTransform: 'uppercase', letterSpacing: 1,
                }}>
                  {done ? 'OK' : active ? '…' : ''}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div style={{
        position: 'absolute', left: 24, right: 24, bottom: 20,
      }}>
        <SplashProgress value={boot.progress}
          label={`Starting COREX`}
          sub={`${Math.round(boot.progress * 100)}%`} />
      </div>
    </SplashFrame>
  );
}

window.V4OrbitalBoot = V4OrbitalBoot;
