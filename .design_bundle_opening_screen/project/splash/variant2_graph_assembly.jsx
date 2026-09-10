// Variant 2 — "Graph Assembly"
// The splash IS a tiny, live graph. Three category-coded nodes (I/O →
// Core → Viewer) drop in, their ports materialize, then a bezier edge
// snakes between them carrying a bright data pulse. The canvas bg
// matches the real editor's grid + bg, so visually this reads as
// "the editor is already running; these nodes are booting".

function V2GraphAssembly() {
  const [phase, setPhase] = React.useState(0);
  // 0: empty canvas
  // 1: node A lands
  // 2: node B lands
  // 3: node C lands
  // 4: edges draw
  // 5: data pulse travels
  // 6: complete
  React.useEffect(() => {
    const seq = [[300,1],[400,2],[400,3],[500,4],[700,5],[900,6],[800,0]];
    let t, idx = 0;
    const tick = () => {
      const [ms, next] = seq[idx];
      t = setTimeout(() => { setPhase(next); idx = (idx+1) % seq.length; tick(); }, ms);
    };
    tick();
    return () => clearTimeout(t);
  }, []);

  const boot = useBootSequence([
    'Loading node registry…',
    'Registered 142 node types',
    'Restoring workspace',
    'Loading graph theme · Stitch Dark',
    'Warming viewer backend',
    'Canvas ready',
  ], { stepMs: 650 });

  // Mini-node card — a faithful reduction of NodeCard.qml.
  const MiniNode = ({ x, y, title, cat, visible, ports = { in: 1, out: 1 } }) => {
    const W = 152, H = 64;
    return (
      <g transform={`translate(${x} ${y})`}
        style={{
          opacity: visible ? 1 : 0,
          transform: `translate(${x}px, ${visible ? y : y + 8}px)`,
          transition: 'all 380ms cubic-bezier(.2,.8,.2,1)',
        }}>
        {/* Drop shadow */}
        <rect x="0" y="2" width={W} height={H} rx="6" fill="rgba(0,0,0,0.45)" filter="blur(6px)" opacity="0.6" />
        {/* Card */}
        <rect x="0" y="0" width={W} height={H} rx="6" fill={COREX.bgCardSoft}
          stroke={COREX.border} strokeWidth="1" />
        {/* Category stripe */}
        <rect x="0" y="0" width="3" height={H} rx="1.5" fill={cat} />
        {/* Header */}
        <rect x="3" y="0" width={W-3} height="22" rx="0" fill="#2A2B30" opacity="0.6" />
        {/* Title dot */}
        <circle cx="14" cy="11" r="3" fill={cat} />
        <text x="22" y="15" fill={COREX.fg} fontSize="11" fontFamily="Segoe UI" fontWeight="600">{title}</text>
        {/* Body: a fake inline row */}
        <rect x="10" y="32" width={W-20} height="20" rx="3" fill={COREX.border} opacity="0.5" />
        <text x="16" y="46" fill={COREX.fgMuted} fontSize="10" fontFamily="Segoe UI">value</text>
        {/* Ports — signature warm yellow */}
        {ports.in > 0 && (
          <>
            <circle cx="0" cy={H/2} r="7" fill={COREX.portHalo} />
            <circle cx="0" cy={H/2} r="4" fill={COREX.port} stroke={COREX.portBorder} strokeWidth="1.2" />
          </>
        )}
        {ports.out > 0 && (
          <>
            <circle cx={W} cy={H/2} r="7" fill={COREX.portHalo} />
            <circle cx={W} cy={H/2} r="4" fill={COREX.port} stroke={COREX.portBorder} strokeWidth="1.2" />
          </>
        )}
      </g>
    );
  };

  // Node positions (inside 672×220 drawing area)
  const A = { x: 30,  y: 72, cat: COREX.blue,   title: 'Read CSV',   tcat: 'io'     };
  const B = { x: 230, y: 50, cat: '#B35BD1',    title: 'Transform',  tcat: 'logic'  };
  const C = { x: 460, y: 84, cat: '#D88C32',    title: 'Model Viewer', tcat: 'phys'   };

  // Edge path AB + BC (cubic bezier horizontal)
  const edgePath = (from, to) => {
    const dx = Math.abs(to.x - from.x) * 0.5;
    return `M ${from.x} ${from.y} C ${from.x+dx} ${from.y}, ${to.x-dx} ${to.y}, ${to.x} ${to.y}`;
  };
  const A_out = { x: A.x + 152, y: A.y + 32 };
  const B_in  = { x: B.x,       y: B.y + 32 };
  const B_out = { x: B.x + 152, y: B.y + 32 };
  const C_in  = { x: C.x,       y: C.y + 32 };

  return (
    <SplashFrame tone="#1D1F24">
      {/* Canvas grid — matches the real editor */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage:
          `linear-gradient(${COREX.grid} 1px, transparent 1px),` +
          `linear-gradient(90deg, ${COREX.grid} 1px, transparent 1px),` +
          `linear-gradient(rgba(47,107,255,0.10) 1px, transparent 1px),` +
          `linear-gradient(90deg, rgba(47,107,255,0.10) 1px, transparent 1px)`,
        backgroundSize: '24px 24px, 24px 24px, 120px 120px, 120px 120px',
      }} />

      {/* Title strip */}
      <div style={{
        position: 'absolute', top: 20, left: 24, right: 24,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <svg width="26" height="26" viewBox="0 0 120 120">
            <defs>
              <linearGradient id="v2-g" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
              </linearGradient>
            </defs>
            <circle cx="60" cy="60" r="14" fill="url(#v2-g)" />
            <circle cx="20" cy="20" r="6" fill="none" stroke={COREX.blue} strokeWidth="2.5" />
            <circle cx="100" cy="20" r="6" fill="none" stroke={COREX.blue} strokeWidth="2.5" />
            <circle cx="20" cy="100" r="6" fill="none" stroke={COREX.blue} strokeWidth="2.5" />
            <circle cx="100" cy="100" r="6" fill="none" stroke={COREX.blue} strokeWidth="2.5" />
            <line x1="20" y1="20" x2="60" y2="60" stroke="url(#v2-g)" strokeWidth="4" strokeLinecap="round" />
            <line x1="100" y1="20" x2="60" y2="60" stroke="url(#v2-g)" strokeWidth="4" strokeLinecap="round" />
            <line x1="20" y1="100" x2="60" y2="60" stroke="url(#v2-g)" strokeWidth="4" strokeLinecap="round" />
            <line x1="100" y1="100" x2="60" y2="60" stroke="url(#v2-g)" strokeWidth="4" strokeLinecap="round" />
          </svg>
          <CorexWordmark size={20} />
          <span style={{ fontSize: 10, color: COREX.fgDim, letterSpacing: 1,
            textTransform: 'uppercase', paddingLeft: 8, borderLeft: `1px solid ${COREX.border}` }}>
            Node Editor
          </span>
        </div>
        <div style={{ fontSize: 10, color: COREX.fgDim,
          fontFamily: '"Cascadia Mono", Consolas, monospace', letterSpacing: 0.5 }}>
          v0.9.3 · build 2048
        </div>
      </div>

      {/* Graph stage */}
      <svg width="672" height="240" style={{ position: 'absolute', top: 80, left: 24 }}>
        <defs>
          <linearGradient id="v2-edge" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={COREX.blue} />
            <stop offset="100%" stopColor={COREX.cyan} />
          </linearGradient>
        </defs>

        {/* Edges */}
        {[{from: A_out, to: B_in, delay: 0}, {from: B_out, to: C_in, delay: 180}].map((e, idx) => {
          const d = edgePath(e.from, e.to);
          const show = phase >= 4;
          return (
            <g key={idx}>
              <path d={d} fill="none" stroke="url(#v2-edge)" strokeWidth="2"
                strokeLinecap="round"
                strokeDasharray="600"
                strokeDashoffset={show ? 0 : 600}
                style={{ transition: `stroke-dashoffset 600ms cubic-bezier(.2,.8,.2,1) ${e.delay}ms` }} />
              {/* Data pulse */}
              {phase >= 5 && (
                <circle r="4" fill={COREX.cyan}>
                  <animateMotion dur="1.4s" repeatCount="indefinite" path={d} />
                </circle>
              )}
            </g>
          );
        })}

        {/* Nodes */}
        <MiniNode {...A} visible={phase >= 1} />
        <MiniNode {...B} visible={phase >= 2} />
        <MiniNode {...C} visible={phase >= 3} />
      </svg>

      {/* Footer */}
      <div style={{
        position: 'absolute', left: 24, right: 24, bottom: 20,
      }}>
        <SplashProgress value={boot.progress} label={boot.step} sub={`${Math.round(boot.progress * 100)}%`} />
      </div>
    </SplashFrame>
  );
}

window.V2GraphAssembly = V2GraphAssembly;
