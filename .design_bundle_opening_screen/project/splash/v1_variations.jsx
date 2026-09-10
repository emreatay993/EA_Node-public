// V1 sub-variations — brand / logo-forward splashes.
// All share the COREX mark as the hero; differ in how it animates in
// and what supporting information sits around it.

// ───────────────────────────────────────────────────────────
// 1A — MONOLITH
// Static, oversized mark. Only the core breathes. Wordmark below,
// progress bar at the bottom edge. Stately, minimal, "engineered".
// ───────────────────────────────────────────────────────────
function V1A_Monolith() {
  const boot = useBootSequence([
    'Initialising runtime…',
    'Loading node registry',
    'Scanning plug-ins',
    'Warming viewer backend',
    'Ready',
  ], { stepMs: 720 });

  return (
    <SplashFrame>
      <div style={{
        position: 'absolute', inset: 0,
        background: 'radial-gradient(ellipse 55% 55% at 50% 45%, rgba(47,107,255,0.16), transparent 60%)',
      }} />

      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}>
        <Mark size={180} breathing />
        <div style={{ marginTop: 28 }}><CorexWordmark size={36} /></div>
        <div style={{
          marginTop: 8, fontSize: 11, color: COREX.fgDim,
          letterSpacing: 2, textTransform: 'uppercase', fontWeight: 500,
        }}>
          Node Editor · v0.9.3
        </div>
      </div>

      <div style={{ position: 'absolute', left: 32, right: 32, bottom: 22 }}>
        <SplashProgress value={boot.progress} label={boot.step}
          sub={`${Math.round(boot.progress * 100)}%`} />
      </div>
    </SplashFrame>
  );
}

// ───────────────────────────────────────────────────────────
// 1B — IGNITION (reverse assembly)
// Core ignites first at center, then the four rings snap outward
// along the connectors. Reads as "the core is lit; it's reaching out".
// ───────────────────────────────────────────────────────────
function V1B_Ignition() {
  const [phase, setPhase] = React.useState(0);
  React.useEffect(() => {
    const seq = [[450, 1], [420, 2], [500, 3], [900, 4], [700, 0]];
    let t, idx = 0;
    const tick = () => {
      const [ms, next] = seq[idx];
      t = setTimeout(() => { setPhase(next); idx = (idx + 1) % seq.length; tick(); }, ms);
    };
    tick(); return () => clearTimeout(t);
  }, []);

  const boot = useBootSequence([
    'Ignite core',
    'Projecting connectors',
    'Registering nodes',
    'Ready',
  ], { stepMs: 700 });

  const S = 260, cx = S/2, cy = S/2;
  const outer = [
    { x: 56, y: 56 }, { x: 204, y: 56 },
    { x: 56, y: 204 }, { x: 204, y: 204 },
  ];

  const coreOn   = phase >= 1;
  const linesOn  = phase >= 2;
  const ringsOn  = phase >= 3;
  const wordOn   = phase >= 4;

  return (
    <SplashFrame>
      {/* Radial flash on ignite */}
      <div style={{
        position: 'absolute', inset: 0,
        background: coreOn
          ? 'radial-gradient(circle at 50% 45%, rgba(0,209,255,0.24), transparent 40%)'
          : 'radial-gradient(circle at 50% 45%, rgba(47,107,255,0.04), transparent 40%)',
        transition: 'background 500ms ease',
      }} />

      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}>
        <svg width={S} height={S} style={{ overflow: 'visible' }}>
          <defs>
            <linearGradient id="v1b-c" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
            </linearGradient>
            <radialGradient id="v1b-core"><stop offset="0%" stopColor={COREX.cyan} /><stop offset="100%" stopColor={COREX.blue} /></radialGradient>
          </defs>

          {/* Ignition halo */}
          <circle cx={cx} cy={cy} r="60" fill={COREX.cyan} opacity={coreOn ? 0.18 : 0}
            style={{ transition: 'opacity 500ms' }} />

          {/* Core bursts in first */}
          <circle cx={cx} cy={cy} r="22"
            fill="url(#v1b-core)"
            opacity={coreOn ? 1 : 0}
            transform={coreOn ? 'scale(1)' : 'scale(0.3)'}
            style={{
              transformOrigin: `${cx}px ${cy}px`,
              transformBox: 'fill-box',
              transition: 'all 400ms cubic-bezier(.2,.8,.2,1)',
            }} />
          <circle cx={cx} cy={cy} r="30" fill="none"
            stroke={COREX.softBlue} strokeOpacity="0.45" strokeWidth="2.5"
            opacity={coreOn ? 1 : 0}
            style={{ transition: 'opacity 300ms ease 100ms' }} />

          {/* Connectors grow OUTWARD from core */}
          {outer.map((o, idx) => {
            const t = linesOn ? 1 : 0;
            return (
              <line key={idx}
                x1={cx} y1={cy}
                x2={cx + (o.x - cx) * t}
                y2={cy + (o.y - cy) * t}
                stroke="url(#v1b-c)" strokeWidth="7" strokeLinecap="round"
                opacity={linesOn ? 1 : 0}
                style={{ transition: `all ${420 + idx*60}ms cubic-bezier(.2,.8,.2,1)` }} />
            );
          })}

          {/* X crossbars */}
          <line x1="92" y1="92" x2="168" y2="168" stroke={COREX.softBlue}
            strokeOpacity="0.9" strokeWidth="3" strokeLinecap="round"
            opacity={coreOn ? 1 : 0} style={{ transition: 'opacity 300ms 160ms' }} />
          <line x1="168" y1="92" x2="92" y2="168" stroke={COREX.softBlue}
            strokeOpacity="0.9" strokeWidth="3" strokeLinecap="round"
            opacity={coreOn ? 1 : 0} style={{ transition: 'opacity 300ms 230ms' }} />

          {/* Rings snap into place last */}
          {outer.map((o, idx) => (
            <g key={idx}
              opacity={ringsOn ? 1 : 0}
              transform={`translate(${o.x} ${o.y}) scale(${ringsOn ? 1 : 1.6})`}
              style={{
                transformOrigin: `${o.x}px ${o.y}px`, transformBox: 'fill-box',
                transition: `all 360ms cubic-bezier(.2,.8,.2,1) ${idx*60}ms`,
              }}>
              <circle r="13" fill={COREX.bgNode} stroke={COREX.blue} strokeWidth="4" />
            </g>
          ))}
        </svg>

        <div style={{
          marginTop: 26,
          opacity: wordOn ? 1 : 0, transition: 'opacity 400ms',
        }}>
          <CorexWordmark size={30} />
        </div>
      </div>

      <div style={{ position: 'absolute', left: 28, right: 28, bottom: 20 }}>
        <SplashProgress value={boot.progress} label={boot.step}
          sub={`${Math.round(boot.progress * 100)}%`} />
      </div>
    </SplashFrame>
  );
}

// ───────────────────────────────────────────────────────────
// 1C — OFFSET MARK
// Logo lives on the left third; right side shows wordmark + a
// ticking task list. More informative — feels like a real dialog.
// ───────────────────────────────────────────────────────────
function V1C_OffsetMark() {
  const tasks = [
    { label: 'Runtime',      sub: 'Python 3.11 · PyQt5' },
    { label: 'Registry',     sub: '142 node types resolved' },
    { label: 'viewer backend',  sub: 'PyVista 2024R2' },
    { label: 'Workspace',    sub: 'Restoring · dene3.cxproj' },
  ];
  const boot = useBootSequence(tasks.map(t => t.label), { stepMs: 720 });
  const cur = Math.min(boot.i, tasks.length - 1);

  return (
    <SplashFrame>
      <div style={{
        position: 'absolute', inset: 0,
        background: 'radial-gradient(circle at 22% 50%, rgba(47,107,255,0.16), transparent 55%)',
      }} />

      {/* Left — mark */}
      <div style={{
        position: 'absolute', left: 40, top: 0, bottom: 0, width: 240,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Mark size={180} breathing />
      </div>

      {/* Vertical rule */}
      <div style={{
        position: 'absolute', left: 298, top: 54, bottom: 72, width: 1,
        background: COREX.border,
      }} />

      {/* Right — text + tasks */}
      <div style={{
        position: 'absolute', left: 326, right: 40, top: 54, bottom: 72,
        display: 'flex', flexDirection: 'column',
      }}>
        <CorexWordmark size={28} />
        <div style={{
          fontSize: 10, color: COREX.fgDim, marginTop: 6,
          letterSpacing: 1.8, textTransform: 'uppercase', fontWeight: 500,
        }}>Node Editor · v0.9.3</div>

        <div style={{ marginTop: 22, display: 'flex', flexDirection: 'column', gap: 11 }}>
          {tasks.map((t, idx) => {
            const done = idx < cur, active = idx === cur;
            return (
              <div key={idx} style={{
                display: 'grid', gridTemplateColumns: '14px 1fr auto',
                alignItems: 'center', gap: 12,
                opacity: done || active ? 1 : 0.45,
              }}>
                <div style={{
                  width: 8, height: 8, borderRadius: '50%',
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
                  fontSize: 10, letterSpacing: 1,
                  color: done ? COREX.ok : active ? COREX.running : COREX.fgDim,
                  fontFamily: '"Cascadia Mono", Consolas, monospace',
                  textTransform: 'uppercase',
                }}>{done ? 'OK' : active ? '…' : ''}</div>
              </div>
            );
          })}
        </div>
      </div>

      <div style={{ position: 'absolute', left: 28, right: 28, bottom: 20 }}>
        <SplashProgress value={boot.progress} label="Starting COREX"
          sub={`${Math.round(boot.progress * 100)}%`} />
      </div>
    </SplashFrame>
  );
}

// ───────────────────────────────────────────────────────────
// 1D — CONSTELLATION (convergence)
// A scatter of ~18 tiny rings on the canvas; four of them are the
// "canonical" logo positions. On each loop tick, the scattered
// rings fade out and pull inward, leaving only the four that snap
// into place and resolve into the full mark.
// ───────────────────────────────────────────────────────────
function V1D_Constellation() {
  const [phase, setPhase] = React.useState(0);
  React.useEffect(() => {
    const seq = [[700, 1], [700, 2], [900, 3], [1000, 0]];
    let t, idx = 0;
    const tick = () => {
      const [ms, next] = seq[idx];
      t = setTimeout(() => { setPhase(next); idx = (idx+1) % seq.length; tick(); }, ms);
    };
    tick(); return () => clearTimeout(t);
  }, []);

  const boot = useBootSequence([
    'Scanning registry',
    'Collapsing graph',
    'Forging core',
    'Ready',
  ], { stepMs: 830 });

  // Deterministic scatter — seeded points in 320×300 box
  const scatter = React.useMemo(() => {
    const rnd = (i) => {
      const x = Math.sin(i * 9301 + 49297) * 233280;
      return x - Math.floor(x);
    };
    const pts = [];
    for (let i = 0; i < 22; i++) {
      pts.push({ x: 20 + rnd(i*2)*280, y: 20 + rnd(i*2+1)*260, r: 3 + rnd(i*3)*4 });
    }
    return pts;
  }, []);

  const S = 320, cx = S/2, cy = S/2;
  const outer = [
    { x: 84, y: 84 }, { x: 236, y: 84 },
    { x: 84, y: 236 }, { x: 236, y: 236 },
  ];

  const scatterVisible = phase <= 1;
  const convergent     = phase >= 1;
  const markVisible    = phase >= 2;
  const coreVisible    = phase >= 3;

  return (
    <SplashFrame>
      <div style={{
        position: 'absolute', inset: 0, opacity: 0.5,
        backgroundImage: `radial-gradient(circle, ${COREX.gridStrong} 1px, transparent 1.2px)`,
        backgroundSize: '20px 20px',
        maskImage: 'radial-gradient(ellipse 70% 70% at 50% 50%, black, transparent 80%)',
      }} />

      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}>
        <svg width={S} height={S} style={{ overflow: 'visible' }}>
          <defs>
            <linearGradient id="v1d-c" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
            </linearGradient>
            <radialGradient id="v1d-core"><stop offset="0%" stopColor={COREX.cyan} /><stop offset="100%" stopColor={COREX.blue} /></radialGradient>
          </defs>

          {/* Scattered rings — fade + drift inward */}
          {scatter.map((p, i) => {
            const drift = convergent ? 0.6 : 1; // pull toward center
            const x = cx + (p.x - cx) * drift;
            const y = cy + (p.y - cy) * drift;
            return (
              <circle key={i} cx={x} cy={y} r={p.r}
                fill={COREX.bgNode} stroke={COREX.blue} strokeWidth="1.5"
                opacity={scatterVisible ? 0.55 : 0}
                style={{ transition: 'all 700ms cubic-bezier(.4,.0,.2,1)' }}
              />
            );
          })}

          {/* Connectors appear with the mark */}
          {outer.map((o, idx) => (
            <line key={idx}
              x1={o.x} y1={o.y} x2={cx} y2={cy}
              stroke="url(#v1d-c)" strokeWidth="6" strokeLinecap="round"
              opacity={markVisible ? 1 : 0}
              strokeDasharray="200" strokeDashoffset={markVisible ? 0 : 200}
              style={{ transition: `all ${500 + idx*60}ms cubic-bezier(.2,.8,.2,1)` }}
            />
          ))}

          {/* X crossbars */}
          <line x1="120" y1="120" x2="200" y2="200" stroke={COREX.softBlue}
            strokeOpacity="0.9" strokeWidth="3" strokeLinecap="round"
            opacity={coreVisible ? 1 : 0} style={{ transition: 'opacity 300ms' }} />
          <line x1="200" y1="120" x2="120" y2="200" stroke={COREX.softBlue}
            strokeOpacity="0.9" strokeWidth="3" strokeLinecap="round"
            opacity={coreVisible ? 1 : 0} style={{ transition: 'opacity 300ms 80ms' }} />

          {/* Canonical rings */}
          {outer.map((o, idx) => (
            <g key={idx}
              opacity={markVisible ? 1 : 0}
              transform={`translate(${o.x} ${o.y}) scale(${markVisible ? 1 : 0.6})`}
              style={{
                transformOrigin: `${o.x}px ${o.y}px`, transformBox: 'fill-box',
                transition: `all 360ms cubic-bezier(.2,.8,.2,1) ${idx*60}ms`,
              }}>
              <circle r="14" fill={COREX.bgNode} stroke={COREX.blue} strokeWidth="4" />
            </g>
          ))}

          {/* Core */}
          <circle cx={cx} cy={cy} r="22" fill="url(#v1d-core)"
            opacity={coreVisible ? 1 : 0}
            style={{ transition: 'opacity 400ms' }} />
          <circle cx={cx} cy={cy} r="30" fill="none"
            stroke={COREX.softBlue} strokeOpacity="0.4" strokeWidth="2.5"
            opacity={coreVisible ? 1 : 0}
            style={{ transition: 'opacity 400ms 120ms' }} />
        </svg>

        <div style={{
          marginTop: 14,
          opacity: coreVisible ? 1 : 0, transition: 'opacity 500ms',
        }}>
          <CorexWordmark size={26} />
        </div>
      </div>

      <div style={{ position: 'absolute', left: 28, right: 28, bottom: 20 }}>
        <SplashProgress value={boot.progress} label={boot.step}
          sub={`${Math.round(boot.progress * 100)}%`} />
      </div>
    </SplashFrame>
  );
}

// ───────────────────────────────────────────────────────────
// Shared Mark — the canonical COREX mark, with optional breathing.
// ───────────────────────────────────────────────────────────
function Mark({ size = 180, breathing = false, breatheDur = 2.4 }) {
  const S = size, cx = S/2, cy = S/2;
  const k = S / 260; // scale from the 260 layout
  const outer = [
    { x: 56*k, y: 56*k }, { x: 204*k, y: 56*k },
    { x: 56*k, y: 204*k }, { x: 204*k, y: 204*k },
  ];
  return (
    <svg width={S} height={S} style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={`mark-c-${size}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
        </linearGradient>
        <radialGradient id={`mark-core-${size}`}>
          <stop offset="0%" stopColor={COREX.cyan} /><stop offset="100%" stopColor={COREX.blue} />
        </radialGradient>
      </defs>

      <circle cx={cx} cy={cy} r={36*k} fill={COREX.softBlue} fillOpacity="0.10" />
      <circle cx={cx} cy={cy} r={26*k} fill={COREX.softBlue} fillOpacity="0.22" />

      {outer.map((o, i) => (
        <line key={i} x1={o.x} y1={o.y} x2={cx} y2={cy}
          stroke={`url(#mark-c-${size})`} strokeWidth={7*k} strokeLinecap="round" />
      ))}
      <line x1={92*k} y1={92*k} x2={168*k} y2={168*k}
        stroke={COREX.softBlue} strokeOpacity="0.92" strokeWidth={3*k} strokeLinecap="round" />
      <line x1={168*k} y1={92*k} x2={92*k} y2={168*k}
        stroke={COREX.softBlue} strokeOpacity="0.92" strokeWidth={3*k} strokeLinecap="round" />

      {outer.map((o, i) => (
        <circle key={i} cx={o.x} cy={o.y} r={12*k}
          fill={COREX.bgNode} stroke={COREX.blue} strokeWidth={4*k} />
      ))}

      <circle cx={cx} cy={cy} r={20*k} fill={`url(#mark-core-${size})`}>
        {breathing && <animate attributeName="r" values={`${18*k};${22*k};${18*k}`} dur={`${breatheDur}s`} repeatCount="indefinite" />}
      </circle>
      <circle cx={cx} cy={cy} r={28*k} fill="none"
        stroke={COREX.softBlue} strokeOpacity="0.35" strokeWidth={2.7*k} />
    </svg>
  );
}

Object.assign(window, { V1A_Monolith, V1B_Ignition, V1C_OffsetMark, V1D_Constellation, Mark });
