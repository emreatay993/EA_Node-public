// Shared splash tokens — derived from the COREX app icon palette,
// not the Stitch Dark shell. The logo uses a deeper, more saturated
// navy (#0B0F1A) and a blue→cyan gradient (#2F6BFF → #00D1FF) with
// #6FA8FF as the soft accent. The splash lives in this color world.

const COREX = {
  // Surface
  bgDeep:      '#05080F',   // outside the splash card
  bgCard:      '#0B0F1A',   // splash background (matches logo plate)
  bgCardSoft:  '#10172A',   // raised tier
  bgNode:      '#1A2130',   // matches the node rings in the logo
  grid:        'rgba(47, 107, 255, 0.06)',
  gridStrong:  'rgba(47, 107, 255, 0.12)',
  border:      '#1F2A40',
  borderSoft:  '#182138',

  // Text
  fg:          '#E6EEFB',
  fgMuted:     '#8895B2',
  fgDim:       '#4A566F',

  // Brand
  blue:        '#2F6BFF',
  cyan:        '#00D1FF',
  softBlue:    '#6FA8FF',
  port:        '#FFDA6B',   // keep the signature warm-yellow port
  portBorder:  '#FFE48B',
  portHalo:    'rgba(255, 218, 107, 0.35)',

  // Motion/semantic
  running:     '#60CDFF',
  ok:          '#67D487',
  warn:        '#E8A838',
};

const SPLASH_W = 720;
const SPLASH_H = 440;

// Frameless splash "window" — 8px radius, 1px border, heavy drop shadow
// like a popup surface over the OS. All variants wrap in this.
function SplashFrame({ children, style = {}, tone = COREX.bgCard }) {
  return (
    <div style={{
      width: SPLASH_W, height: SPLASH_H,
      background: tone,
      border: `1px solid ${COREX.border}`,
      borderRadius: 8,
      boxShadow: '0 1px 0 rgba(0,0,0,0.4), 0 24px 64px rgba(0,0,0,0.6), 0 0 0 1px rgba(111,168,255,0.04)',
      position: 'relative',
      overflow: 'hidden',
      fontFamily: '"Segoe UI", "Segoe UI Variable", Inter, system-ui, sans-serif',
      color: COREX.fg,
      ...style,
    }}>
      {children}
    </div>
  );
}

// Tiny component: the COREX wordmark set in a refined, technical style.
// The "X" picks up the brand gradient; the rest is in fg.
function CorexWordmark({ size = 28, muted = false }) {
  return (
    <div style={{
      fontFamily: '"Segoe UI", "Segoe UI Variable", Inter, system-ui, sans-serif',
      fontWeight: 600,
      fontSize: size,
      letterSpacing: size * 0.08,
      color: muted ? COREX.fgMuted : COREX.fg,
      lineHeight: 1,
      display: 'inline-flex',
      alignItems: 'baseline',
      userSelect: 'none',
    }}>
      <span>CORE</span>
      <span style={{
        background: `linear-gradient(135deg, ${COREX.blue}, ${COREX.cyan})`,
        WebkitBackgroundClip: 'text',
        backgroundClip: 'text',
        color: 'transparent',
      }}>X</span>
    </div>
  );
}

// Thin progress bar, Qt-flat, with an animated "running" sheen.
function SplashProgress({ value = 0.42, label, sub, width = '100%', running = true }) {
  return (
    <div style={{ width }}>
      {(label || sub) && (
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
          fontSize: 11, color: COREX.fgMuted, marginBottom: 8,
          fontVariantNumeric: 'tabular-nums',
        }}>
          <span style={{ textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 500 }}>{label}</span>
          <span style={{ color: COREX.fgDim, fontFamily: '"Cascadia Mono", Consolas, monospace' }}>{sub}</span>
        </div>
      )}
      <div style={{
        height: 2,
        background: COREX.borderSoft,
        position: 'relative',
        overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute', left: 0, top: 0, bottom: 0,
          width: `${value * 100}%`,
          background: `linear-gradient(90deg, ${COREX.blue}, ${COREX.cyan})`,
          transition: 'width 120ms linear',
          boxShadow: `0 0 12px ${COREX.cyan}`,
        }} />
        {running && (
          <div style={{
            position: 'absolute', left: 0, top: 0, bottom: 0,
            width: `${value * 100}%`,
            overflow: 'hidden',
          }}>
            <div style={{
              position: 'absolute', top: 0, bottom: 0, width: 80,
              background: `linear-gradient(90deg, transparent, rgba(255,255,255,0.55), transparent)`,
              animation: 'corexSheen 1.6s linear infinite',
            }} />
          </div>
        )}
      </div>
    </div>
  );
}

// Hook: a fake loading sequence that drives progress + the current task label.
function useBootSequence(steps, { loop = true, stepMs = 420 } = {}) {
  const [i, setI] = React.useState(0);
  const [progress, setProgress] = React.useState(0);
  React.useEffect(() => {
    let t;
    const tick = () => {
      setI(prev => {
        const next = prev + 1;
        if (next >= steps.length) {
          if (loop) { setProgress(0); return 0; }
          setProgress(1); return prev;
        }
        setProgress(next / (steps.length - 1));
        return next;
      });
      t = setTimeout(tick, stepMs);
    };
    t = setTimeout(tick, stepMs);
    return () => clearTimeout(t);
  }, []);
  return { i, step: steps[i], progress };
}

Object.assign(window, {
  COREX, SPLASH_W, SPLASH_H,
  SplashFrame, CorexWordmark, SplashProgress,
  useBootSequence,
});
