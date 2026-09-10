// Variant 5 — "Diagnostic"
// The most technical of the five. A matrix of port handles occupies
// the left; ports light up row-by-row as registry modules resolve.
// The right side is a live, scrolling boot log in monospace.
// This leans into COREX's "dry, technical, precise" voice and its
// engineer audience. Reads like a Houdini / DCC tool warming up.

function V5Diagnostic() {
  const ROWS = 6, COLS = 10;
  const [lit, setLit] = React.useState(0);
  React.useEffect(() => {
    let t;
    const step = () => {
      setLit(prev => (prev + 1) % (ROWS * COLS + 12));
      t = setTimeout(step, 80);
    };
    t = setTimeout(step, 80);
    return () => clearTimeout(t);
  }, []);

  const logLines = [
    { t: 'INFO',  msg: 'runtime: Python and Qt ready' },
    { t: 'INFO',  msg: 'theme: stitch_dark · graph=stitch_dark' },
    { t: 'OK',    msg: 'registry: node catalogue ready' },
    { t: 'OK',    msg: 'registry: engineering viewer registered' },
    { t: 'INFO',  msg: 'bridges: shellLibraryBridge attached' },
    { t: 'INFO',  msg: 'bridges: shellWorkspaceBridge attached' },
    { t: 'INFO',  msg: 'bridges: graphCanvasStateBridge attached' },
    { t: 'INFO',  msg: 'viewer: backend readiness checked' },
    { t: 'OK',    msg: 'viewer: transport contract verified' },
    { t: 'INFO',  msg: 'workspace: restoring session' },
    { t: 'OK',    msg: 'workspace: graph loaded' },
    { t: 'INFO',  msg: 'canvas: renderer ready' },
    { t: 'OK',    msg: 'ready' },
  ];
  const [visibleLines, setVisibleLines] = React.useState(1);
  React.useEffect(() => {
    let t;
    const step = () => {
      setVisibleLines(v => (v >= logLines.length ? 1 : v + 1));
      t = setTimeout(step, 340);
    };
    t = setTimeout(step, 340);
    return () => clearTimeout(t);
  }, []);

  const tagColor = (t) => t === 'OK' ? COREX.ok : t === 'WARN' ? COREX.warn : COREX.softBlue;

  return (
    <SplashFrame tone="#0A0D16">
      {/* Subtle top border glow matching running state */}
      <div style={{
        position: 'absolute', left: 0, right: 0, top: 0, height: 1,
        background: `linear-gradient(90deg, transparent, ${COREX.cyan}, transparent)`,
        opacity: 0.5,
      }} />

      {/* Header */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: 38,
        borderBottom: `1px solid ${COREX.border}`,
        display: 'flex', alignItems: 'center',
        padding: '0 18px', gap: 14,
        background: 'rgba(47,107,255,0.04)',
      }}>
        <div style={{
          width: 8, height: 8, borderRadius: '50%',
          background: COREX.running, boxShadow: `0 0 8px ${COREX.running}`,
        }} />
        <CorexWordmark size={15} />
        <span style={{ fontSize: 10, color: COREX.fgDim, letterSpacing: 1.4,
          textTransform: 'uppercase', paddingLeft: 10, borderLeft: `1px solid ${COREX.border}` }}>
          Node Editor · boot diagnostic
        </span>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 10, color: COREX.fgDim,
          fontFamily: '"Cascadia Mono", Consolas, monospace' }}>
          local process · development build
        </span>
      </div>

      {/* Two-pane body */}
      <div style={{
        position: 'absolute', top: 38, left: 0, right: 0, bottom: 40,
        display: 'grid', gridTemplateColumns: '260px 1fr',
      }}>
        {/* Left pane: port matrix */}
        <div style={{
          borderRight: `1px solid ${COREX.border}`,
          padding: '20px 22px',
          display: 'flex', flexDirection: 'column',
        }}>
          <div style={{
            fontSize: 10, color: COREX.fgMuted, letterSpacing: 1.2,
            textTransform: 'uppercase', fontWeight: 500, marginBottom: 16,
          }}>Node registry</div>
          <svg width="216" height="146" style={{ overflow: 'visible' }}>
            {Array.from({ length: ROWS }).map((_, r) =>
              Array.from({ length: COLS }).map((_, c) => {
                const idx = r * COLS + c;
                const active = idx < lit;
                const pulsing = idx === lit - 1;
                return (
                  <g key={`${r}-${c}`}>
                    {pulsing && (
                      <circle cx={c * 22 + 6} cy={r * 22 + 6} r="10" fill={COREX.portHalo}>
                        <animate attributeName="r" values="6;12;6" dur="0.6s" repeatCount="indefinite" />
                      </circle>
                    )}
                    <circle
                      cx={c * 22 + 6} cy={r * 22 + 6} r="3.5"
                      fill={active ? COREX.port : COREX.border}
                      stroke={active ? COREX.portBorder : COREX.borderSoft}
                      strokeWidth="1"
                      style={{ transition: 'all 160ms' }}
                    />
                  </g>
                );
              })
            )}
          </svg>
          <div style={{ flex: 1 }} />
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
            fontFamily: '"Cascadia Mono", Consolas, monospace', fontSize: 10,
          }}>
            <span style={{ color: COREX.fgDim }}>resolved</span>
            <span style={{ color: COREX.fg }}>
              {Math.min(lit, ROWS * COLS)}<span style={{ color: COREX.fgDim }}> / {ROWS * COLS}</span>
            </span>
          </div>
        </div>

        {/* Right pane: scrolling log */}
        <div style={{
          padding: '16px 20px',
          fontFamily: '"Cascadia Mono", Consolas, monospace',
          fontSize: 11, lineHeight: 1.65,
          overflow: 'hidden',
          display: 'flex', flexDirection: 'column',
        }}>
          <div style={{
            fontSize: 10, color: COREX.fgMuted, letterSpacing: 1.2,
            textTransform: 'uppercase', fontWeight: 500, marginBottom: 12,
            fontFamily: '"Segoe UI", sans-serif',
          }}>Console</div>
          <div style={{ flex: 1, overflow: 'hidden' }}>
            {logLines.slice(0, visibleLines).map((l, idx) => (
              <div key={idx} style={{
                display: 'grid', gridTemplateColumns: '44px 48px 1fr',
                gap: 8, color: COREX.fg,
                opacity: idx === visibleLines - 1 ? 1 : 0.7,
                animation: idx === visibleLines - 1 ? 'corexLogIn 180ms ease' : 'none',
              }}>
                <span style={{ color: COREX.fgDim }}>
                  {String(idx).padStart(4, '0')}
                </span>
                <span style={{
                  color: tagColor(l.t), fontWeight: 600,
                }}>[{l.t}]</span>
                <span>{l.msg}</span>
              </div>
            ))}
            {/* Cursor */}
            <div style={{ marginTop: 4, color: COREX.cyan }}>
              <span style={{ color: COREX.fgDim }}>$</span>{' '}
              <span style={{ animation: 'corexCaret 1s steps(2) infinite' }}>█</span>
            </div>
          </div>
        </div>
      </div>

      {/* Footer progress */}
      <div style={{
        position: 'absolute', left: 0, right: 0, bottom: 0, height: 40,
        borderTop: `1px solid ${COREX.border}`,
        display: 'flex', alignItems: 'center', padding: '0 18px', gap: 14,
      }}>
        <span style={{
          fontSize: 10, color: COREX.fgDim, letterSpacing: 1.2,
          textTransform: 'uppercase', fontWeight: 500,
        }}>Starting</span>
        <div style={{ flex: 1 }}>
          <SplashProgress value={Math.min(visibleLines / logLines.length, 1)} width="100%" />
        </div>
        <span style={{
          fontSize: 10, color: COREX.fgDim,
          fontFamily: '"Cascadia Mono", Consolas, monospace',
          minWidth: 40, textAlign: 'right',
        }}>{Math.round(Math.min(visibleLines / logLines.length, 1) * 100)}%</span>
      </div>
    </SplashFrame>
  );
}

window.V5Diagnostic = V5Diagnostic;
