// Concept-node family — 5 variations where the COREX logo connects
// to labeled concept nodes (Plan · Model · Process · View · Plot · Report).
// These present the product's "what it does" alongside the brand.

// Small concept node card — icon box + label + sub
function ConceptNode({ x, y, label, sub, color = COREX.blue, active = false, size = 'md' }) {
  const W = size === 'lg' ? 148 : size === 'sm' ? 96 : 122;
  const H = size === 'lg' ? 52 : size === 'sm' ? 40 : 46;
  return (
    <g style={{ transform: `translate(${x}px, ${y}px)`,
      transition: 'all 350ms cubic-bezier(.2,.8,.2,1)' }}>
      <rect x="0" y="2" width={W} height={H} rx="6" fill="rgba(0,0,0,0.45)"
        filter="blur(5px)" opacity="0.55" />
      <rect x="0" y="0" width={W} height={H} rx="6"
        fill={COREX.bgCardSoft}
        stroke={active ? COREX.cyan : COREX.border}
        strokeWidth={active ? 1.5 : 1} />
      {active && (
        <rect x="-1" y="-1" width={W+2} height={H+2} rx="7" fill="none"
          stroke={COREX.cyan} strokeOpacity="0.4" strokeWidth="2">
          <animate attributeName="stroke-opacity" values="0.15;0.55;0.15" dur="1.4s" repeatCount="indefinite" />
        </rect>
      )}
      {/* Category tick */}
      <rect x="0" y="0" width="3" height={H} rx="1.5" fill={color} />
      {/* Icon dot */}
      <circle cx="14" cy={H/2} r="4" fill={color} opacity={active ? 1 : 0.7} />
      <text x={26} y={size === 'sm' ? 16 : 19}
        fill={COREX.fg} fontSize={size === 'sm' ? 10.5 : 11.5}
        fontFamily="Segoe UI" fontWeight="600" letterSpacing="0.3">
        {label}
      </text>
      {sub && size !== 'sm' && (
        <text x={26} y={H - 12}
          fill={COREX.fgDim} fontSize="9.5"
          fontFamily='"Cascadia Mono", Consolas, monospace'>{sub}</text>
      )}
    </g>
  );
}

// Small mark for the concept-node splashes (no breathing baggage)
function CoreMark({ size = 78 }) {
  const S = size, cx = S/2, cy = S/2, k = S / 260;
  const outer = [
    { x: 56*k, y: 56*k }, { x: 204*k, y: 56*k },
    { x: 56*k, y: 204*k }, { x: 204*k, y: 204*k },
  ];
  return (
    <svg width={S} height={S} style={{ overflow:'visible' }}>
      <defs>
        <linearGradient id={`cm-c-${size}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
        </linearGradient>
        <radialGradient id={`cm-core-${size}`}>
          <stop offset="0%" stopColor={COREX.cyan} /><stop offset="100%" stopColor={COREX.blue} />
        </radialGradient>
      </defs>
      <circle cx={cx} cy={cy} r={36*k} fill={COREX.softBlue} fillOpacity="0.10" />
      <circle cx={cx} cy={cy} r={26*k} fill={COREX.softBlue} fillOpacity="0.22" />
      {outer.map((o,i) => (
        <line key={i} x1={o.x} y1={o.y} x2={cx} y2={cy}
          stroke={`url(#cm-c-${size})`} strokeWidth={7*k} strokeLinecap="round" />
      ))}
      <line x1={92*k} y1={92*k} x2={168*k} y2={168*k}
        stroke={COREX.softBlue} strokeOpacity="0.92" strokeWidth={3*k} strokeLinecap="round" />
      <line x1={168*k} y1={92*k} x2={92*k} y2={168*k}
        stroke={COREX.softBlue} strokeOpacity="0.92" strokeWidth={3*k} strokeLinecap="round" />
      {outer.map((o,i) => (
        <circle key={i} cx={o.x} cy={o.y} r={12*k}
          fill={COREX.bgNode} stroke={COREX.blue} strokeWidth={4*k} />
      ))}
      <circle cx={cx} cy={cy} r={20*k} fill={`url(#cm-core-${size})`}>
        <animate attributeName="r" values={`${18*k};${22*k};${18*k}`} dur="2.4s" repeatCount="indefinite" />
      </circle>
      <circle cx={cx} cy={cy} r={28*k} fill="none"
        stroke={COREX.softBlue} strokeOpacity="0.35" strokeWidth={2.7*k} />
    </svg>
  );
}

function cubicTo(from, to, curve = 0.5) {
  const dx = Math.abs(to.x - from.x) * curve;
  return `M ${from.x} ${from.y} C ${from.x+dx} ${from.y}, ${to.x-dx} ${to.y}, ${to.x} ${to.y}`;
}

// ───────────────────────────────────────────────────────────
// C1 — COMPASS (4 cardinal concepts)
// Plan · Process · View · Plot around the logo. Active node rotates
// through the list; edges light up when active.
// ───────────────────────────────────────────────────────────
function C1_Compass() {
  const concepts = [
    { label:'PLAN',     sub:'scope · define',      color: COREX.blue },
    { label:'PROCESS',  sub:'shape · transform',   color:'#B35BD1'   },
    { label:'VIEW',     sub:'scene · inspect',        color:'#D88C32'   },
    { label:'PLOT',     sub:'view · report',       color:'#22B455'   },
  ];
  const [cur, setCur] = React.useState(0);
  React.useEffect(() => {
    const t = setInterval(() => setCur(c => (c+1) % concepts.length), 900);
    return () => clearInterval(t);
  }, []);
  const boot = useBootSequence(concepts.map(c => `${c.label.charAt(0)}${c.label.slice(1).toLowerCase()}…`), { stepMs: 900 });

  // Stage 672×340 at top 56
  const cx = 672/2, cy = 170;
  const W = 130, H = 44;
  const pos = [
    { x: cx - W/2, y: 10 },        // top  — PLAN
    { x: cx + 150, y: cy - H/2 },  // right — PROCESS
    { x: cx - W/2, y: 320 - H },   // bottom — VIEW
    { x: cx - W - 150, y: cy - H/2 }, // left — PLOT
  ];
  // Fix bottom
  pos[2] = { x: cx - W/2, y: 296 };

  const markPos = { x: cx, y: cy };

  return (
    <SplashFrame>
      <div style={{ position:'absolute', inset:0,
        background:'radial-gradient(circle at 50% 48%, rgba(47,107,255,0.14), transparent 55%)' }} />
      <div style={{ position:'absolute', inset:0, opacity:0.4,
        backgroundImage:`radial-gradient(circle, ${COREX.gridStrong} 1px, transparent 1.2px)`,
        backgroundSize:'22px 22px',
        maskImage: 'radial-gradient(ellipse 80% 80% at 50% 50%, black, transparent 90%)' }} />

      {/* Top-left brand */}
      <div style={{ position:'absolute', top: 20, left: 24, display:'flex', alignItems:'center', gap: 10 }}>
        <CorexWordmark size={18} />
        <span style={{ fontSize:10, color:COREX.fgDim, letterSpacing:1.2,
          textTransform:'uppercase', paddingLeft:8, borderLeft:`1px solid ${COREX.border}` }}>
          Node Editor
        </span>
      </div>

      <svg width="672" height="340" style={{ position:'absolute', top: 52, left: 24 }}>
        <defs>
          <linearGradient id="c1-e" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
          </linearGradient>
        </defs>

        {/* Edges from each concept to mark center */}
        {concepts.map((c, i) => {
          const from = {
            x: pos[i].x + W/2,
            y: pos[i].y + (i === 0 ? H : i === 2 ? 0 : H/2),
          };
          // adjust side for L/R
          if (i === 1) { from.x = pos[i].x; from.y = pos[i].y + H/2; }
          if (i === 3) { from.x = pos[i].x + W; from.y = pos[i].y + H/2; }
          const active = i === cur;
          const d = cubicTo(markPos, from, 0.3);
          return (
            <g key={i}>
              <path d={d} fill="none"
                stroke={active ? 'url(#c1-e)' : COREX.borderSoft}
                strokeWidth={active ? 2.5 : 1.2}
                strokeLinecap="round"
                style={{ transition: 'stroke 200ms, stroke-width 200ms' }} />
              {active && (
                <circle r="4" fill={COREX.cyan}>
                  <animateMotion dur="0.9s" repeatCount="1" path={d} />
                </circle>
              )}
            </g>
          );
        })}

        {/* Mark */}
        <g transform={`translate(${cx - 56}, ${cy - 56})`}>
          <foreignObject x="0" y="0" width="112" height="112">
            <div xmlns="http://www.w3.org/1999/xhtml"><CoreMark size={112} /></div>
          </foreignObject>
        </g>

        {/* Concepts */}
        {concepts.map((c,i) => (
          <ConceptNode key={i} x={pos[i].x} y={pos[i].y}
            label={c.label} sub={c.sub} color={c.color} active={i === cur} />
        ))}
      </svg>

      <div style={{ position:'absolute', left: 28, right: 28, bottom: 20 }}>
        <SplashProgress value={boot.progress} label={boot.step} sub={`${Math.round(boot.progress*100)}%`} />
      </div>
    </SplashFrame>
  );
}

// ───────────────────────────────────────────────────────────
// C2 — ORBIT RING (6 concepts rotating around the logo)
// Plan · Model · Process · View · Plot · Report on a slow ring.
// ───────────────────────────────────────────────────────────
function C2_OrbitRing() {
  const concepts = [
    { label:'PLAN',    color: COREX.blue   },
    { label:'MODEL',   color:'#4AA9D6'     },
    { label:'PROCESS', color:'#B35BD1'     },
    { label:'VIEW',    color:'#D88C32'     },
    { label:'PLOT',    color:'#22B455'     },
    { label:'REPORT',  color:'#C75050'     },
  ];
  const [angle, setAngle] = React.useState(0);
  React.useEffect(() => {
    let raf, start = performance.now();
    const loop = (t) => { setAngle(((t-start)/80) % 360); raf = requestAnimationFrame(loop); };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);
  const [active, setActive] = React.useState(0);
  React.useEffect(() => {
    const t = setInterval(() => setActive(a => (a+1) % concepts.length), 850);
    return () => clearInterval(t);
  }, []);
  const boot = useBootSequence(['Loading workflow', 'Resolving stages','Ready'], { stepMs: 800 });

  const cx = 336, cy = 180, R = 125;

  return (
    <SplashFrame>
      <div style={{ position:'absolute', inset:0,
        background:'radial-gradient(circle at 50% 50%, rgba(47,107,255,0.14), transparent 55%)' }} />

      <div style={{ position:'absolute', top: 20, left: 0, right: 0, textAlign:'center' }}>
        <CorexWordmark size={18} />
      </div>

      <svg width="672" height="360" style={{ position:'absolute', top: 42, left: 24 }}>
        {/* Orbit ring */}
        <circle cx={cx} cy={cy} r={R} fill="none"
          stroke={COREX.border} strokeWidth="1" strokeDasharray="2 5" />

        {/* Edges */}
        <defs>
          <linearGradient id="c2-e" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
          </linearGradient>
        </defs>

        {concepts.map((c, i) => {
          const rad = ((i / concepts.length) * 360 + angle) * Math.PI / 180;
          const nx = cx + Math.cos(rad) * R;
          const ny = cy + Math.sin(rad) * R;
          const isActive = i === active;
          return (
            <g key={i}>
              <line x1={cx} y1={cy} x2={nx} y2={ny}
                stroke={isActive ? 'url(#c2-e)' : COREX.borderSoft}
                strokeOpacity={isActive ? 1 : 0.5}
                strokeWidth={isActive ? 2 : 1}
                style={{ transition:'all 200ms' }} />
              <circle cx={nx} cy={ny} r={isActive ? 18 : 13}
                fill={COREX.bgNode}
                stroke={isActive ? COREX.cyan : c.color}
                strokeWidth={isActive ? 2.5 : 2}
                style={{ transition:'all 200ms' }} />
              {isActive && (
                <circle cx={nx} cy={ny} r="26" fill="none"
                  stroke={COREX.cyan} strokeOpacity="0.4" strokeWidth="1.5">
                  <animate attributeName="r" values="16;30;16" dur="1.4s" repeatCount="indefinite" />
                  <animate attributeName="stroke-opacity" values="0.5;0;0.5" dur="1.4s" repeatCount="indefinite" />
                </circle>
              )}
              {/* Label positioned outside the node */}
              <text x={nx + Math.cos(rad) * 28} y={ny + Math.sin(rad) * 28 + 3}
                fill={isActive ? COREX.fg : COREX.fgMuted}
                fontSize="10.5" fontFamily="Segoe UI" fontWeight="600"
                textAnchor={Math.cos(rad) > 0.3 ? 'start' : Math.cos(rad) < -0.3 ? 'end' : 'middle'}
                letterSpacing="0.8"
                style={{ transition:'fill 200ms' }}>
                {c.label}
              </text>
            </g>
          );
        })}

        {/* Center mark */}
        <g transform={`translate(${cx - 48}, ${cy - 48})`}>
          <foreignObject x="0" y="0" width="96" height="96">
            <div xmlns="http://www.w3.org/1999/xhtml"><CoreMark size={96} /></div>
          </foreignObject>
        </g>
      </svg>

      <div style={{ position:'absolute', left: 28, right: 28, bottom: 20 }}>
        <SplashProgress value={boot.progress} label={boot.step} sub={`${Math.round(boot.progress*100)}%`} />
      </div>
    </SplashFrame>
  );
}

// ───────────────────────────────────────────────────────────
// C3 — LIFECYCLE ARC (concepts along a semicircular arc, sequential)
// The mark anchors the left; concepts arc across the screen like
// stepping stones of a workflow lifecycle.
// ───────────────────────────────────────────────────────────
function C3_LifecycleArc() {
  const steps = [
    { label:'PLAN',    sub:'01', color: COREX.blue },
    { label:'MODEL',   sub:'02', color:'#4AA9D6'   },
    { label:'PROCESS', sub:'03', color:'#B35BD1'   },
    { label:'VIEW',    sub:'04', color:'#D88C32'   },
    { label:'PLOT',    sub:'05', color:'#22B455'   },
  ];
  const [cur, setCur] = React.useState(0);
  React.useEffect(() => {
    const t = setInterval(() => setCur(c => (c+1) % (steps.length+1)), 700);
    return () => clearInterval(t);
  }, []);
  const boot = useBootSequence(['Initialising','Loading registry','Ready'], { stepMs: 780 });

  // Mark at lower-left; 5 stage points laid along a shallow arc across the top.
  // Arc center sits below the frame so the 5 points form a gentle curve
  // that rises from x≈220 (just right of the mark) to x≈680 on the right.
  const xs = [220, 335, 450, 560, 665];
  // vertical: symmetric arc — lowest in the middle, higher at ends
  // baseline y=150, peak dip at center to 200
  const ys = xs.map(x => {
    const t = (x - 220) / (665 - 220); // 0..1
    // parabolic: 0 at ends, 1 in middle
    const dip = 4 * t * (1 - t);
    return 120 + dip * 90; // 120..210
  });
  const pts = xs.map((x, i) => ({ x, y: ys[i] }));

  return (
    <SplashFrame>
      <div style={{ position:'absolute', inset:0,
        background:'radial-gradient(circle at 20% 70%, rgba(47,107,255,0.16), transparent 55%)' }} />

      <div style={{ position:'absolute', top: 20, left: 24, display:'flex', alignItems:'center', gap: 10 }}>
        <CorexWordmark size={18} />
        <span style={{ fontSize:10, color:COREX.fgDim, letterSpacing:1.2,
          textTransform:'uppercase', paddingLeft:8, borderLeft:`1px solid ${COREX.border}` }}>
          Node Editor · lifecycle
        </span>
      </div>

      <svg width="720" height="440" style={{ position:'absolute', inset:0 }}>
        <defs>
          <linearGradient id="c3-e" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
          </linearGradient>
        </defs>

        {/* Arc spine — catmull-ish through the 5 points using smooth quadratics */}
        {(() => {
          let d = `M ${pts[0].x} ${pts[0].y}`;
          for (let i = 1; i < pts.length; i++) {
            const p0 = pts[i-1], p1 = pts[i];
            const cx1 = (p0.x + p1.x) / 2;
            d += ` Q ${cx1} ${p0.y}, ${(p0.x+p1.x)/2} ${(p0.y+p1.y)/2}`;
            d += ` T ${p1.x} ${p1.y}`;
          }
          const idx = Math.min(cur, pts.length) - 1;
          let dActive = '';
          if (cur > 0) {
            dActive = `M ${pts[0].x} ${pts[0].y}`;
            for (let i = 1; i <= idx; i++) {
              const p0 = pts[i-1], p1 = pts[i];
              const cx1 = (p0.x + p1.x) / 2;
              dActive += ` Q ${cx1} ${p0.y}, ${(p0.x+p1.x)/2} ${(p0.y+p1.y)/2}`;
              dActive += ` T ${p1.x} ${p1.y}`;
            }
          }
          return (
            <>
              <path d={d} fill="none" stroke={COREX.borderSoft}
                strokeWidth="1" strokeDasharray="3 4" />
              {cur > 0 && (
                <path d={dActive} fill="none" stroke="url(#c3-e)"
                  strokeWidth="2.5" strokeLinecap="round"
                  style={{ transition:'all 400ms ease' }} />
              )}
            </>
          );
        })()}

        {/* Step dots on arc */}
        {pts.map((p, i) => {
          const done = i < cur;
          const active = i === cur - 1;
          return (
            <g key={i}>
              <circle cx={p.x} cy={p.y} r={active ? 11 : 7}
                fill={done ? COREX.bgNode : COREX.bgCard}
                stroke={done ? COREX.cyan : COREX.border}
                strokeWidth={done ? 2.5 : 1.5}
                style={{ transition:'all 250ms' }} />
              {active && (
                <circle cx={p.x} cy={p.y} r="16" fill="none"
                  stroke={COREX.cyan} strokeOpacity="0.4" strokeWidth="1.5">
                  <animate attributeName="r" values="10;22;10" dur="1.3s" repeatCount="indefinite" />
                </circle>
              )}
              <text x={p.x} y={p.y - 22}
                fill={done ? COREX.fg : COREX.fgMuted}
                fontSize="11" fontFamily="Segoe UI" fontWeight="600" textAnchor="middle"
                letterSpacing="1">
                {steps[i].label}
              </text>
              <text x={p.x} y={p.y + 28}
                fill={COREX.fgDim}
                fontSize="9.5" fontFamily='"Cascadia Mono", Consolas, monospace'
                textAnchor="middle" letterSpacing="1">
                {steps[i].sub}
              </text>
            </g>
          );
        })}

        {/* Connector from mark to first stage */}
        <line x1="108" y1="300" x2={pts[0].x} y2={pts[0].y}
          stroke={cur > 0 ? 'url(#c3-e)' : COREX.borderSoft}
          strokeWidth={cur > 0 ? 2.5 : 1}
          strokeDasharray={cur > 0 ? '0' : '3 4'}
          strokeLinecap="round" />

        {/* Mark at arc anchor (lower left) */}
        <g transform="translate(54, 246)">
          <foreignObject x="0" y="0" width="108" height="108">
            <div xmlns="http://www.w3.org/1999/xhtml"><CoreMark size={108} /></div>
          </foreignObject>
        </g>
      </svg>

      <div style={{ position:'absolute', left: 28, right: 28, bottom: 20 }}>
        <SplashProgress value={boot.progress} label={boot.step} sub={`${Math.round(boot.progress*100)}%`} />
      </div>
    </SplashFrame>
  );
}

// ───────────────────────────────────────────────────────────
// C4 — HEX LATTICE (6 concepts in hexagonal arrangement)
// Plan / Model / Process / View / Plot / Report at hex vertices.
// Active edges light up as execution ripples.
// ───────────────────────────────────────────────────────────
function C4_HexLattice() {
  const concepts = [
    { label:'PLAN',    color: COREX.blue },
    { label:'MODEL',   color:'#4AA9D6'   },
    { label:'PROCESS', color:'#B35BD1'   },
    { label:'VIEW',    color:'#D88C32'   },
    { label:'PLOT',    color:'#22B455'   },
    { label:'REPORT',  color:'#C75050'   },
  ];
  const [cur, setCur] = React.useState(0);
  React.useEffect(() => {
    const t = setInterval(() => setCur(c => (c+1) % concepts.length), 700);
    return () => clearInterval(t);
  }, []);
  const boot = useBootSequence(['Resolving stages','Wiring','Ready'], { stepMs: 800 });

  const cx = 336, cy = 210, R = 135;
  const W = 108, H = 38;
  // Positions at 6 hex corners, starting from top
  const nodePos = concepts.map((_, i) => {
    const a = (-90 + i * 60) * Math.PI / 180;
    return { x: cx + Math.cos(a) * R - W/2, y: cy + Math.sin(a) * R - H/2 };
  });

  return (
    <SplashFrame>
      <div style={{ position:'absolute', inset:0,
        background:'radial-gradient(circle at 50% 50%, rgba(47,107,255,0.13), transparent 55%)' }} />

      <div style={{ position:'absolute', top: 22, left: 0, right: 0, textAlign:'center' }}>
        <CorexWordmark size={20} />
        <div style={{ fontSize: 10, color: COREX.fgDim, letterSpacing: 1.8,
          textTransform:'uppercase', marginTop: 3, fontWeight: 500 }}>
          Node Editor · workflow stages
        </div>
      </div>

      <svg width="672" height="380" style={{ position:'absolute', top: 60, left: 24 }}>
        <defs>
          <linearGradient id="c4-e" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
          </linearGradient>
        </defs>

        {/* Edges from center to each concept */}
        {concepts.map((c, i) => {
          const from = { x: cx, y: cy };
          const to = { x: nodePos[i].x + W/2, y: nodePos[i].y + H/2 };
          const active = i === cur;
          return (
            <line key={i} x1={from.x} y1={from.y} x2={to.x} y2={to.y}
              stroke={active ? 'url(#c4-e)' : COREX.borderSoft}
              strokeOpacity={active ? 1 : 0.5}
              strokeWidth={active ? 2.5 : 1}
              style={{ transition:'all 220ms' }} />
          );
        })}

        {/* Hex outline connecting vertices */}
        <path d={concepts.map((_, i) => {
          const a = (-90 + i * 60) * Math.PI / 180;
          const x = cx + Math.cos(a) * R;
          const y = cy + Math.sin(a) * R;
          return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
        }).join(' ') + ' Z'}
          fill="none" stroke={COREX.border} strokeWidth="1" strokeDasharray="2 4" />

        {/* Concept nodes */}
        {concepts.map((c,i) => (
          <ConceptNode key={i} x={nodePos[i].x} y={nodePos[i].y}
            label={c.label} color={c.color} active={i === cur} size="sm" />
        ))}

        {/* Center mark */}
        <g transform={`translate(${cx - 48}, ${cy - 48})`}>
          <foreignObject x="0" y="0" width="96" height="96">
            <div xmlns="http://www.w3.org/1999/xhtml"><CoreMark size={96} /></div>
          </foreignObject>
        </g>
      </svg>

      <div style={{ position:'absolute', left: 28, right: 28, bottom: 20 }}>
        <SplashProgress value={boot.progress} label={boot.step} sub={`${Math.round(boot.progress*100)}%`} />
      </div>
    </SplashFrame>
  );
}

// ───────────────────────────────────────────────────────────
// C5 — CASCADING COLUMNS
// Concepts in two staggered columns flanking the central mark:
// Left column = INPUT stages (Plan · Model · Process)
// Right column = OUTPUT stages (View · Plot · Report)
// Edges fan in from the left, fan out to the right.
// ───────────────────────────────────────────────────────────
function C5_CascadingColumns() {
  const left = [
    { label:'PLAN',    sub:'scope',    color: COREX.blue },
    { label:'MODEL',   sub:'geometry', color:'#4AA9D6'   },
    { label:'PROCESS', sub:'transform',color:'#B35BD1'   },
  ];
  const right = [
    { label:'VIEW',    sub:'scene',       color:'#D88C32'   },
    { label:'PLOT',    sub:'view',     color:'#22B455'   },
    { label:'REPORT',  sub:'export',   color:'#C75050'   },
  ];
  const [cur, setCur] = React.useState(0);
  const total = left.length + right.length;
  React.useEffect(() => {
    const t = setInterval(() => setCur(c => (c+1) % total), 650);
    return () => clearInterval(t);
  }, []);
  const boot = useBootSequence(['Resolving input stages','Resolving output stages','Ready'], { stepMs: 800 });

  const W = 140, H = 40, gap = 20;
  const colHeight = left.length * H + (left.length - 1) * gap;
  const yTop = 110;
  const cx = 672/2 + 20;
  const leftX = 54;
  const rightX = cx + 120;
  const markY = yTop + colHeight/2;

  return (
    <SplashFrame>
      <div style={{ position:'absolute', inset:0,
        background:'radial-gradient(circle at 50% 50%, rgba(47,107,255,0.12), transparent 55%)' }} />

      <div style={{ position:'absolute', top: 22, left: 0, right: 0, textAlign:'center' }}>
        <CorexWordmark size={20} />
        <div style={{ fontSize: 10, color: COREX.fgDim, letterSpacing: 1.8,
          textTransform:'uppercase', marginTop: 3, fontWeight: 500 }}>
          Node Editor · v0.9.3
        </div>
      </div>

      <svg width="720" height="440" style={{ position:'absolute', inset:0 }}>
        <defs>
          <linearGradient id="c5-e" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
          </linearGradient>
        </defs>

        {/* Edges left → mark */}
        {left.map((_, i) => {
          const from = { x: leftX + W, y: yTop + i * (H + gap) + H/2 };
          const to = { x: cx, y: markY };
          const d = cubicTo(from, to, 0.5);
          const active = i === cur;
          return (
            <g key={`l${i}`}>
              <path d={d} fill="none"
                stroke={active ? 'url(#c5-e)' : COREX.borderSoft}
                strokeWidth={active ? 2.5 : 1}
                strokeLinecap="round"
                style={{ transition:'all 200ms' }} />
              {active && (
                <circle r="4" fill={COREX.cyan}>
                  <animateMotion dur="0.7s" repeatCount="1" path={d} />
                </circle>
              )}
            </g>
          );
        })}

        {/* Edges mark → right */}
        {right.map((_, i) => {
          const from = { x: cx, y: markY };
          const to = { x: rightX, y: yTop + i * (H + gap) + H/2 };
          const d = cubicTo(from, to, 0.5);
          const active = (i + left.length) === cur;
          return (
            <g key={`r${i}`}>
              <path d={d} fill="none"
                stroke={active ? 'url(#c5-e)' : COREX.borderSoft}
                strokeWidth={active ? 2.5 : 1}
                strokeLinecap="round"
                style={{ transition:'all 200ms' }} />
              {active && (
                <circle r="4" fill={COREX.cyan}>
                  <animateMotion dur="0.7s" repeatCount="1" path={d} />
                </circle>
              )}
            </g>
          );
        })}

        {/* Left column */}
        {left.map((c,i) => (
          <ConceptNode key={i} x={leftX} y={yTop + i*(H+gap)}
            label={c.label} sub={c.sub} color={c.color} active={i === cur} />
        ))}

        {/* Right column */}
        {right.map((c,i) => (
          <ConceptNode key={i} x={rightX} y={yTop + i*(H+gap)}
            label={c.label} sub={c.sub} color={c.color} active={i + left.length === cur} />
        ))}

        {/* Central mark */}
        <g transform={`translate(${cx - 52}, ${markY - 52})`}>
          <foreignObject x="0" y="0" width="104" height="104">
            <div xmlns="http://www.w3.org/1999/xhtml"><CoreMark size={104} /></div>
          </foreignObject>
        </g>

        {/* Column headers */}
        <text x={leftX} y={yTop - 14} fill={COREX.fgDim}
          fontSize="9.5" fontFamily='"Cascadia Mono", Consolas, monospace'
          letterSpacing="1.4">INPUT</text>
        <text x={rightX} y={yTop - 14} fill={COREX.fgDim}
          fontSize="9.5" fontFamily='"Cascadia Mono", Consolas, monospace'
          letterSpacing="1.4">OUTPUT</text>
      </svg>

      <div style={{ position:'absolute', left: 28, right: 28, bottom: 20 }}>
        <SplashProgress value={boot.progress} label={boot.step} sub={`${Math.round(boot.progress*100)}%`} />
      </div>
    </SplashFrame>
  );
}

Object.assign(window, {
  C1_Compass, C2_OrbitRing, C3_LifecycleArc, C4_HexLattice, C5_CascadingColumns,
  ConceptNode, CoreMark,
});
