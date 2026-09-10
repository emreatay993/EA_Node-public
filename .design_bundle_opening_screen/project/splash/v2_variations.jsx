// V2 sub-variations — canvas-native splashes that present the editor
// as already running. All share the real canvas grid, category-coded
// node cards, and the signature warm-yellow ports.

// Mini node card — shared across all V2 variations.
function V2Node({ x, y, w = 148, h = 58, title, cat, visible = true,
                  ports = { in: 1, out: 1 }, state = 'idle', label = 'value' }) {
  const running   = state === 'running';
  const completed = state === 'completed';
  const borderColor = running ? COREX.cyan : completed ? COREX.ok : COREX.border;
  return (
    <g style={{
      opacity: visible ? 1 : 0,
      transform: `translate(${x}px, ${visible ? y : y + 8}px)`,
      transition: 'all 380ms cubic-bezier(.2,.8,.2,1)',
    }}>
      <rect x="0" y="2" width={w} height={h} rx="6" fill="rgba(0,0,0,0.45)"
        filter="blur(6px)" opacity="0.6" />
      <rect x="0" y="0" width={w} height={h} rx="6" fill={COREX.bgCardSoft}
        stroke={borderColor} strokeWidth={running ? 1.5 : 1} />
      {running && (
        <rect x="-1" y="-1" width={w+2} height={h+2} rx="7" fill="none"
          stroke={COREX.cyan} strokeOpacity="0.5" strokeWidth="2">
          <animate attributeName="stroke-opacity" values="0.2;0.6;0.2" dur="1.2s" repeatCount="indefinite" />
        </rect>
      )}
      <rect x="0" y="0" width="3" height={h} rx="1.5" fill={cat} />
      <rect x="3" y="0" width={w-3} height="20" fill="#2A2B30" opacity="0.6" />
      <circle cx="14" cy="10" r="3" fill={cat} />
      <text x="22" y="14" fill={COREX.fg} fontSize="11" fontFamily="Segoe UI" fontWeight="600">{title}</text>
      <rect x="10" y="28" width={w-20} height="20" rx="3" fill={COREX.border} opacity="0.5" />
      <text x="16" y="42" fill={COREX.fgMuted} fontSize="10" fontFamily="Segoe UI">{label}</text>
      {ports.in > 0 && (<>
        <circle cx="0" cy={h/2} r="7" fill={COREX.portHalo} />
        <circle cx="0" cy={h/2} r="4" fill={COREX.port} stroke={COREX.portBorder} strokeWidth="1.2" />
      </>)}
      {ports.out > 0 && (<>
        <circle cx={w} cy={h/2} r="7" fill={COREX.portHalo} />
        <circle cx={w} cy={h/2} r="4" fill={COREX.port} stroke={COREX.portBorder} strokeWidth="1.2" />
      </>)}
    </g>
  );
}

function bezier(from, to) {
  const dx = Math.abs(to.x - from.x) * 0.5;
  return `M ${from.x} ${from.y} C ${from.x+dx} ${from.y}, ${to.x-dx} ${to.y}, ${to.x} ${to.y}`;
}

function V2CanvasBg() {
  return (
    <div style={{
      position: 'absolute', inset: 0,
      backgroundImage:
        `linear-gradient(${COREX.grid} 1px, transparent 1px),` +
        `linear-gradient(90deg, ${COREX.grid} 1px, transparent 1px),` +
        `linear-gradient(rgba(47,107,255,0.10) 1px, transparent 1px),` +
        `linear-gradient(90deg, rgba(47,107,255,0.10) 1px, transparent 1px)`,
      backgroundSize: '24px 24px, 24px 24px, 120px 120px, 120px 120px',
    }} />
  );
}

function V2Header({ title = 'Node Editor' }) {
  return (
    <div style={{
      position: 'absolute', top: 16, left: 20, right: 20,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <MiniGlyph size={22} />
        <CorexWordmark size={18} />
        <span style={{
          fontSize: 10, color: COREX.fgDim, letterSpacing: 1,
          textTransform: 'uppercase', paddingLeft: 8,
          borderLeft: `1px solid ${COREX.border}`, fontWeight: 500,
        }}>{title}</span>
      </div>
      <div style={{ fontSize: 10, color: COREX.fgDim,
        fontFamily: '"Cascadia Mono", Consolas, monospace' }}>v0.9.3 · build 2048</div>
    </div>
  );
}

function MiniGlyph({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 120">
      <defs>
        <linearGradient id={`mg-${size}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
        </linearGradient>
      </defs>
      <circle cx="60" cy="60" r="14" fill={`url(#mg-${size})`} />
      {[[20,20],[100,20],[20,100],[100,100]].map(([x,y],i) => (
        <g key={i}>
          <line x1={x} y1={y} x2="60" y2="60" stroke={`url(#mg-${size})`} strokeWidth="4" strokeLinecap="round" />
          <circle cx={x} cy={y} r="6" fill="none" stroke={COREX.blue} strokeWidth="2.5" />
        </g>
      ))}
    </svg>
  );
}

// ───────────────────────────────────────────────────────────
// 2A — LINEAR PIPELINE (4 nodes, horizontal)
// Classic left-to-right dataflow. Reads as a real workflow.
// ───────────────────────────────────────────────────────────
function V2A_Linear() {
  const [phase, setPhase] = React.useState(0);
  React.useEffect(() => {
    const seq = [[280,1],[280,2],[280,3],[280,4],[420,5],[900,6],[700,0]];
    let t, idx = 0;
    const tick = () => { const [ms,n]=seq[idx]; t=setTimeout(()=>{setPhase(n); idx=(idx+1)%seq.length; tick();}, ms); };
    tick(); return () => clearTimeout(t);
  }, []);
  const boot = useBootSequence([
    'Loading registry','Registering I/O nodes','Registering Logic nodes',
    'Registering Physics nodes','Connecting edges','Canvas ready',
  ], { stepMs: 540 });

  const nodes = [
    { x: 14,  y: 92, cat: COREX.blue,    title: 'Read CSV',   ports:{in:0,out:1} },
    { x: 178, y: 92, cat: '#B35BD1',     title: 'Transform',  ports:{in:1,out:1} },
    { x: 342, y: 92, cat: '#D88C32',     title: 'MARS · Batch Solve',ports:{in:1,out:1} },
    { x: 506, y: 92, cat: '#22B455',     title: 'Plot',       ports:{in:1,out:0} },
  ];
  const W = 148, H = 58;

  return (
    <SplashFrame tone="#1D1F24">
      <V2CanvasBg />
      <V2Header />
      <svg width="672" height="240" style={{ position: 'absolute', top: 70, left: 24 }}>
        <defs>
          <linearGradient id="v2a-e" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
          </linearGradient>
        </defs>
        {[0,1,2].map(i => {
          const from = { x: nodes[i].x + W,   y: nodes[i].y + H/2 };
          const to   = { x: nodes[i+1].x,     y: nodes[i+1].y + H/2 };
          const d = bezier(from, to);
          const show = phase >= 4;
          return (
            <g key={i}>
              <path d={d} fill="none" stroke="url(#v2a-e)" strokeWidth="2"
                strokeLinecap="round" strokeDasharray="400"
                strokeDashoffset={show ? 0 : 400}
                style={{ transition: `stroke-dashoffset 500ms cubic-bezier(.2,.8,.2,1) ${i*120}ms` }} />
              {phase >= 5 && (
                <circle r="4" fill={COREX.cyan}>
                  <animateMotion dur="1.6s" repeatCount="indefinite" path={d} begin={`${i*0.4}s`} />
                </circle>
              )}
            </g>
          );
        })}
        {nodes.map((n,i) => (
          <V2Node key={i} {...n} w={W} h={H} visible={phase >= i+1}
            state={phase >= 5 && phase <= 6 && i === phase - 5 + (phase===6?3:0) ? 'running' : 'idle'} />
        ))}
      </svg>
      <div style={{ position: 'absolute', left: 24, right: 24, bottom: 20 }}>
        <SplashProgress value={boot.progress} label={boot.step}
          sub={`${Math.round(boot.progress*100)}%`} />
      </div>
    </SplashFrame>
  );
}

// ───────────────────────────────────────────────────────────
// 2B — VERTICAL FLOW (top-down waterfall)
// Nodes stack vertically, edges drop in between them.
// ───────────────────────────────────────────────────────────
function V2B_Vertical() {
  const [phase, setPhase] = React.useState(0);
  React.useEffect(() => {
    const seq = [[300,1],[300,2],[300,3],[450,4],[1000,5],[700,0]];
    let t, idx = 0;
    const tick = () => { const [ms,n]=seq[idx]; t=setTimeout(()=>{setPhase(n); idx=(idx+1)%seq.length; tick();}, ms); };
    tick(); return () => clearTimeout(t);
  }, []);
  const boot = useBootSequence([
    'Initialising runtime','Loading registry','Loading viewer',
    'Restoring session','Canvas ready',
  ], { stepMs: 680 });

  const W = 180, H = 54;
  // Stage box: 310×330 starting at x=205, y=60
  const col = 60; // center x inside the stage
  const nodes = [
    { x: col - W/2, y: 0,   cat: COREX.blue, title: 'Read Input',  ports:{in:0,out:1} },
    { x: col - W/2, y: 90,  cat: '#B35BD1',  title: 'Validate',    ports:{in:1,out:1} },
    { x: col - W/2, y: 180, cat: '#D88C32',  title: 'MARS · Batch Solve', ports:{in:1,out:1} },
    { x: col - W/2, y: 270, cat: '#22B455',  title: 'Export',      ports:{in:1,out:0} },
  ];

  const pathV = (from, to) => {
    const my = (from.y + to.y) / 2;
    return `M ${from.x} ${from.y} C ${from.x} ${my}, ${to.x} ${my}, ${to.x} ${to.y}`;
  };

  return (
    <SplashFrame tone="#1D1F24">
      <V2CanvasBg />
      <V2Header title="Waterfall" />

      {/* Left: brand + tasks */}
      <div style={{
        position: 'absolute', left: 32, top: 66, width: 220, bottom: 64,
        display: 'flex', flexDirection: 'column', justifyContent: 'center',
      }}>
        <CorexWordmark size={24} />
        <div style={{
          fontSize: 10, color: COREX.fgDim, marginTop: 6,
          letterSpacing: 1.6, textTransform: 'uppercase', fontWeight: 500,
        }}>Restoring session</div>
        <div style={{
          marginTop: 18, fontSize: 11, color: COREX.fgMuted, lineHeight: 1.8,
          fontFamily: '"Cascadia Mono", Consolas, monospace',
        }}>
          <div>file <span style={{ color: COREX.fg }}>dene3.cxproj</span></div>
          <div>nodes <span style={{ color: COREX.fg }}>14</span></div>
          <div>edges <span style={{ color: COREX.fg }}>18</span></div>
          <div>theme <span style={{ color: COREX.fg }}>stitch_dark</span></div>
        </div>
      </div>

      {/* Stage */}
      <svg width="300" height="340" style={{ position: 'absolute', top: 60, right: 40 }}>
        <defs>
          <linearGradient id="v2b-e" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
          </linearGradient>
        </defs>
        {[0,1,2].map(i => {
          const from = { x: nodes[i].x + W/2,   y: nodes[i].y + H };
          const to   = { x: nodes[i+1].x + W/2, y: nodes[i+1].y };
          const d = pathV(from, to);
          const show = phase >= 4;
          return (
            <g key={i}>
              <path d={d} fill="none" stroke="url(#v2b-e)" strokeWidth="2"
                strokeDasharray="200" strokeDashoffset={show ? 0 : 200}
                style={{ transition: `stroke-dashoffset 500ms ease ${i*140}ms` }} />
              {phase >= 5 && (
                <circle r="4" fill={COREX.cyan}>
                  <animateMotion dur="2s" repeatCount="indefinite" path={d} begin={`${i*0.5}s`} />
                </circle>
              )}
            </g>
          );
        })}
        {nodes.map((n,i) => (
          <V2Node key={i} {...n} w={W} h={H} visible={phase >= Math.min(i+1, 3)}
            ports={i===0?{in:0,out:1}:i===3?{in:1,out:0}:{in:1,out:1}} />
        ))}
      </svg>

      <div style={{ position: 'absolute', left: 24, right: 24, bottom: 20 }}>
        <SplashProgress value={boot.progress} label={boot.step}
          sub={`${Math.round(boot.progress*100)}%`} />
      </div>
    </SplashFrame>
  );
}

// ───────────────────────────────────────────────────────────
// 2C — FAN-IN CLUSTER
// A central Solver node with 4 satellite feeders. Edges land
// from all directions; the solver "runs" last.
// ───────────────────────────────────────────────────────────
function V2C_FanIn() {
  const [phase, setPhase] = React.useState(0);
  React.useEffect(() => {
    const seq = [[700,1],[600,2],[1200,3],[800,0]];
    let t, idx = 0;
    const tick = () => { const [ms,n]=seq[idx]; t=setTimeout(()=>{setPhase(n); idx=(idx+1)%seq.length; tick();}, ms); };
    tick(); return () => clearTimeout(t);
  }, []);
  const boot = useBootSequence([
    'Resolving 4 input operators',
    'Linking to solver',
    'Running MARS solver',
    'Ready',
  ], { stepMs: 800 });

  const W = 130, H = 52;
  const center = { x: 336 - W/2, y: 170 - H/2, cat: '#D88C32', title: 'MARS · Batch Solve', ports:{in:1,out:1} };
  const sats = [
    { x: 40,  y: 40,  cat: COREX.blue,  title: 'Mesh In',    ports:{in:0,out:1} },
    { x: 40,  y: 260, cat: COREX.blue,  title: 'Materials',  ports:{in:0,out:1} },
    { x: 510, y: 40,  cat: '#B35BD1',   title: 'Loads',      ports:{in:0,out:1} },
    { x: 510, y: 260, cat: '#22B455',   title: 'Constraints',ports:{in:0,out:1} },
  ];

  return (
    <SplashFrame tone="#1D1F24">
      <V2CanvasBg />
      <V2Header title="Subgraph" />

      <svg width="672" height="340" style={{ position: 'absolute', top: 55, left: 24 }}>
        <defs>
          <linearGradient id="v2c-e" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
          </linearGradient>
        </defs>
        {sats.map((s, i) => {
          const from = { x: s.x + W,        y: s.y + H/2 };
          const to   = { x: center.x,       y: center.y + H/2 };
          const d = bezier(from, to);
          const show = phase >= 2;
          return (
            <g key={i}>
              <path d={d} fill="none" stroke="url(#v2c-e)" strokeWidth="2"
                strokeDasharray="600" strokeDashoffset={show ? 0 : 600}
                style={{ transition: `stroke-dashoffset 600ms ease ${i*100}ms` }} />
              {phase >= 3 && (
                <circle r="4" fill={COREX.cyan}>
                  <animateMotion dur="1.8s" repeatCount="indefinite" path={d} begin={`${i*0.2}s`} />
                </circle>
              )}
            </g>
          );
        })}
        {sats.map((s,i) => (
          <V2Node key={i} {...s} w={W} h={H} visible={phase >= 1} />
        ))}
        <V2Node {...center} w={W} h={H} visible={phase >= 1}
          state={phase >= 3 ? 'running' : 'idle'} label="solve" />
      </svg>

      <div style={{ position: 'absolute', left: 24, right: 24, bottom: 20 }}>
        <SplashProgress value={boot.progress} label={boot.step}
          sub={`${Math.round(boot.progress*100)}%`} />
      </div>
    </SplashFrame>
  );
}

// ───────────────────────────────────────────────────────────
// 2D — CANVAS ZOOM (pre-built graph, execution ripples through)
// A larger, already-wired graph fills the frame; edges pulse
// sequentially to show execution order. Feels like zooming into
// a running workspace.
// ───────────────────────────────────────────────────────────
function V2D_CanvasZoom() {
  const [tick, setTick] = React.useState(0);
  React.useEffect(() => {
    const t = setInterval(() => setTick(v => v + 1), 450);
    return () => clearInterval(t);
  }, []);

  const boot = useBootSequence([
    'Loading workspace',
    'Resolving nodes · 14',
    'Resolving edges · 18',
    'Executing · ordered',
    'Ready',
  ], { stepMs: 620 });

  const W = 118, H = 48;
  // 6-node graph, stage 672×290 at top 55
  const nodes = [
    { id:'r', x: 16,  y: 30,  cat: COREX.blue,  title: 'Read',       ports:{in:0,out:1} },
    { id:'p', x: 16,  y: 170, cat: COREX.blue,  title: 'Params',     ports:{in:0,out:1} },
    { id:'t', x: 178, y: 100, cat: '#B35BD1',   title: 'Transform',  ports:{in:1,out:1} },
    { id:'s', x: 350, y: 100, cat: '#D88C32',   title: 'MARS Batch Solve',  ports:{in:1,out:1} },
    { id:'v', x: 520, y: 30,  cat: '#22B455',   title: 'Viewer',     ports:{in:1,out:0} },
    { id:'x', x: 520, y: 170, cat: '#C75050',   title: 'Export',     ports:{in:1,out:0} },
  ];
  const find = id => nodes.find(n => n.id === id);
  const edges = [
    ['r','t'], ['p','t'], ['t','s'], ['s','v'], ['s','x'],
  ].map(([a,b]) => ({
    from: { x: find(a).x + W, y: find(a).y + H/2 },
    to:   { x: find(b).x,     y: find(b).y + H/2 },
  }));
  const activeEdge = tick % edges.length;

  return (
    <SplashFrame tone="#1D1F24">
      <V2CanvasBg />
      <V2Header title="Workspace" />

      {/* Subtle vignette */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        boxShadow: 'inset 0 0 80px rgba(0,0,0,0.5)',
      }} />

      <svg width="672" height="260" style={{ position: 'absolute', top: 55, left: 24 }}>
        <defs>
          <linearGradient id="v2d-e" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
          </linearGradient>
        </defs>
        {edges.map((e,i) => {
          const d = bezier(e.from, e.to);
          const active = i === activeEdge;
          return (
            <g key={i}>
              <path d={d} fill="none"
                stroke={active ? 'url(#v2d-e)' : COREX.borderSoft}
                strokeWidth={active ? 2.5 : 1.5}
                strokeLinecap="round"
                style={{ transition: 'stroke 250ms, stroke-width 250ms' }} />
              {active && (
                <circle r="4.5" fill={COREX.cyan}>
                  <animateMotion dur="0.9s" repeatCount="1" path={d} />
                </circle>
              )}
            </g>
          );
        })}
        {nodes.map((n,i) => {
          // Propagation-ordered states based on activeEdge
          const order = ['r','p','t','s','v','x'];
          const reached = order.indexOf(n.id) <= activeEdge + 1;
          const running = order.indexOf(n.id) === activeEdge + 1;
          return (
            <V2Node key={i} {...n} w={W} h={H} visible={true}
              state={running ? 'running' : reached ? 'completed' : 'idle'} label="compute" />
          );
        })}
      </svg>

      {/* Minimap in lower right of stage */}
      <div style={{
        position: 'absolute', right: 28, bottom: 56,
        width: 96, height: 56, border: `1px solid ${COREX.border}`,
        background: 'rgba(10,14,24,0.85)', padding: 4, borderRadius: 3,
      }}>
        <svg width="88" height="48" viewBox="0 0 672 260">
          {edges.map((e,i) => (
            <path key={i} d={bezier(e.from, e.to)} fill="none"
              stroke={COREX.borderSoft} strokeWidth="6" />
          ))}
          {nodes.map((n,i) => (
            <rect key={i} x={n.x} y={n.y} width={W} height={H}
              fill={n.cat} opacity="0.8" />
          ))}
          <rect x="0" y="0" width="672" height="260" fill="none"
            stroke={COREX.cyan} strokeWidth="4" />
        </svg>
      </div>

      <div style={{ position: 'absolute', left: 24, right: 140, bottom: 20 }}>
        <SplashProgress value={boot.progress} label={boot.step}
          sub={`${Math.round(boot.progress*100)}%`} />
      </div>
    </SplashFrame>
  );
}

Object.assign(window, { V2A_Linear, V2B_Vertical, V2C_FanIn, V2D_CanvasZoom });
