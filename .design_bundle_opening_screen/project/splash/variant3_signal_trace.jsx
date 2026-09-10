// Variant 3 — "Signal Trace"
// A single horizontal pipeline of port handles — the signature warm-
// yellow — lights up left-to-right as boot tasks complete. Between
// ports, a thin gradient edge fills in. Reads as a progress indicator,
// but the progress indicator IS the editor's visual vocabulary.
// Typographic, restrained, the most minimal of the five.

function V3SignalTrace() {
  const N = 8;
  const boot = useBootSequence([
    'Initialising runtime',
    'Loading theme · Stitch Dark',
    'Registering node types',
    'Scanning plug-ins',
    'Warming viewer backend',
    'Restoring last workspace',
    'Preparing canvas',
    'Ready',
  ], { stepMs: 520 });

  const cur = boot.i;
  const W = 600, H = 60;
  const margin = 30;
  const step = (W - margin * 2) / (N - 1);

  return (
    <SplashFrame>
      {/* Very subtle vignette */}
      <div style={{
        position: 'absolute', inset: 0,
        background: 'radial-gradient(ellipse 80% 60% at 50% 50%, rgba(47,107,255,0.08), transparent 70%)',
      }} />

      {/* Top-left mark + wordmark */}
      <div style={{
        position: 'absolute', top: 36, left: 48,
        display: 'flex', alignItems: 'center', gap: 14,
      }}>
        <svg width="36" height="36" viewBox="0 0 120 120">
          <defs>
            <linearGradient id="v3-g" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
            </linearGradient>
          </defs>
          <circle cx="60" cy="60" r="12" fill="url(#v3-g)" />
          <circle cx="60" cy="60" r="20" fill="none" stroke={COREX.softBlue} strokeOpacity="0.35" strokeWidth="2" />
        </svg>
        <CorexWordmark size={26} />
      </div>

      <div style={{
        position: 'absolute', top: 42, right: 48,
        textAlign: 'right',
      }}>
        <div style={{
          fontSize: 10, color: COREX.fgDim, letterSpacing: 1.4,
          textTransform: 'uppercase', fontWeight: 500,
        }}>Node Editor</div>
        <div style={{
          fontSize: 10, color: COREX.fgDim, marginTop: 4,
          fontFamily: '"Cascadia Mono", Consolas, monospace',
        }}>v0.9.3 · build 2048</div>
      </div>

      {/* Centered signal pipeline */}
      <div style={{
        position: 'absolute', left: 0, right: 0, top: '50%',
        transform: 'translateY(-50%)',
        display: 'flex', flexDirection: 'column', alignItems: 'center',
      }}>
        <svg width={W} height={H} style={{ overflow: 'visible' }}>
          <defs>
            <linearGradient id="v3-edge" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor={COREX.blue} /><stop offset="100%" stopColor={COREX.cyan} />
            </linearGradient>
          </defs>

          {/* Inactive spine */}
          <line x1={margin} y1={H/2} x2={W-margin} y2={H/2}
            stroke={COREX.borderSoft} strokeWidth="2" />

          {/* Active spine up to current port */}
          <line x1={margin} y1={H/2}
            x2={margin + Math.max(0, cur) * step}
            y2={H/2}
            stroke="url(#v3-edge)" strokeWidth="2.5" strokeLinecap="round"
            style={{ transition: 'all 300ms cubic-bezier(.2,.8,.2,1)' }} />

          {/* Ports */}
          {Array.from({ length: N }).map((_, i) => {
            const x = margin + i * step;
            const state = i < cur ? 'done' : i === cur ? 'active' : 'idle';
            return (
              <g key={i}>
                {state === 'active' && (
                  <circle cx={x} cy={H/2} r="14" fill={COREX.portHalo}>
                    <animate attributeName="r" values="10;16;10" dur="1.2s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.8;0.2;0.8" dur="1.2s" repeatCount="indefinite" />
                  </circle>
                )}
                <circle cx={x} cy={H/2}
                  r={state === 'idle' ? 4 : 6}
                  fill={state === 'idle' ? COREX.border : COREX.port}
                  stroke={state === 'idle' ? COREX.borderSoft : COREX.portBorder}
                  strokeWidth="1.2"
                  style={{ transition: 'all 280ms ease' }}
                />
                {state === 'done' && (
                  <circle cx={x} cy={H/2} r="2" fill={COREX.bgCard} />
                )}
              </g>
            );
          })}
        </svg>

        {/* Current task label, centered under the active port */}
        <div style={{
          marginTop: 30, textAlign: 'center',
          minHeight: 36,
        }}>
          <div style={{
            fontSize: 11, color: COREX.fgDim, letterSpacing: 1.4,
            textTransform: 'uppercase', marginBottom: 6, fontWeight: 500,
          }}>
            {cur < N - 1 ? `Step ${cur + 1} of ${N}` : 'Complete'}
          </div>
          <div style={{
            fontSize: 15, color: COREX.fg, fontWeight: 500,
            fontFamily: '"Cascadia Mono", Consolas, monospace',
          }}>
            {boot.step}<span style={{ color: COREX.cyan, marginLeft: 2,
              animation: 'corexCaret 1s steps(2) infinite' }}>│</span>
          </div>
        </div>
      </div>
    </SplashFrame>
  );
}

window.V3SignalTrace = V3SignalTrace;
