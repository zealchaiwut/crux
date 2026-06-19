/* crux · Cases list screen components
   CaseCard, BakeOffStrip, Pill, CasesScreen, NewCaseModal
   Adapted from design_handoff_crux/components/case/ and reference_screens/screens.jsx
*/

const STAGE_NAMES = ['Sharpen', 'Bake-off', 'Gather', 'Weigh', 'Probe'];

// Stage ramp: pip at position i uses --st-(i+1)
const STAGE_COLORS = ['var(--st-1)', 'var(--st-2)', 'var(--st-3)', 'var(--st-4)', 'var(--st-5)'];

function Pill({ state }) {
  const labels = {
    confirmed:    'confirmed',
    killed:       'killed',
    inconclusive: 'inconclusive',
    awaiting:     'awaiting',
    progress:     'in progress',
  };
  return (
    <span className={`pill ${state || 'awaiting'}`}>
      {labels[state] || state}
    </span>
  );
}

function BakeOffStrip({ plans }) {
  if (!plans || plans.length === 0) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {plans.map((p) => {
        const won     = p.state === 'won';
        const lead    = p.state === 'leading' || won;
        const ruledOut = p.state === 'ruled-out';
        const pct = Math.round((p.standing || 0) * 100);
        return (
          <div key={p.key} style={{ display: 'flex', alignItems: 'center', gap: 10, opacity: ruledOut ? 0.5 : 1 }}>
            <span className="mono" style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: lead ? 'var(--crux)' : 'var(--text-muted)', width: 16, flex: 'none' }}>
              {p.key}
            </span>
            <div style={{ flex: 1, height: 22, background: 'var(--surface-2)', borderRadius: 'var(--radius-sm)', overflow: 'hidden', position: 'relative' }}>
              <div style={{ width: `${pct}%`, height: '100%', background: lead ? 'var(--crux)' : 'var(--st-2)', borderRadius: 'var(--radius-sm)', transition: 'width var(--speed)' }}></div>
              <span style={{ position: 'absolute', left: 10, top: 0, height: '100%', display: 'flex', alignItems: 'center', fontSize: 'var(--text-sm)', fontWeight: 600, color: pct > 22 && lead ? '#fff' : 'var(--text)', textDecoration: ruledOut ? 'line-through' : 'none' }}>
                {p.name}
              </span>
            </div>
            <span className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, width: 52, textAlign: 'right', flex: 'none', color: won ? 'var(--green)' : 'var(--text-sub)' }}>
              {won ? '✓ WON' : `${pct}%`}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function CaseCard({ id, title, stage, verdict, plans, onClick }) {
  const [hovered, setHovered] = React.useState(false);
  const closed = verdict === 'confirmed' || verdict === 'killed' || verdict === 'inconclusive';

  // Verdict tint colours for closed spine
  const spineColor = verdict === 'confirmed'    ? 'var(--green)'
                   : verdict === 'killed'       ? 'var(--red)'
                   : verdict === 'inconclusive' ? 'var(--amber)'
                   : 'var(--crux)';
  const spineBg    = verdict === 'confirmed'    ? 'var(--green-bg)'
                   : verdict === 'killed'       ? 'var(--red-bg)'
                   : verdict === 'inconclusive' ? 'var(--amber-bg)'
                   : 'var(--surface-2)';

  // 5-pip row: done pips use --st-(i+1) colour; current pip uses --st-(stage+1)
  const safeStage = Math.max(0, Math.min(stage || 0, 4));
  const stagePips = STAGE_NAMES.map((_, i) => {
    const done = closed || i < safeStage;
    const now  = !closed && i === safeStage;
    const bg   = done ? STAGE_COLORS[i]
               : now  ? STAGE_COLORS[i]
               : 'var(--border)';
    return (
      <div key={i} style={{ flex: 1, height: 5, borderRadius: 3, background: bg }}></div>
    );
  });

  const stageLabel = closed ? 'CLOSED' : `STAGE ${safeStage + 1}`;
  const stageName  = STAGE_NAMES[Math.min(safeStage, 4)];

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex', background: 'var(--surface)',
        border: `1px solid ${hovered ? 'var(--crux)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)', overflow: 'hidden',
        cursor: onClick ? 'pointer' : 'default',
        boxShadow: hovered ? 'var(--shadow-hover)' : 'var(--shadow-card)',
        transition: 'box-shadow var(--speed), border-color var(--speed)',
      }}
    >
      {/* Stage spine */}
      <div style={{ width: 118, flex: 'none', background: spineBg, borderRight: '1px solid var(--border)', padding: 'var(--space-3)', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
        <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: closed ? spineColor : 'var(--crux)' }}>
          {stageLabel}
        </div>
        <div className="mono" style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text)', margin: '6px 0 10px' }}>
          {stageName}
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {stagePips}
        </div>
        <div className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)', marginTop: 10 }}>
          {id && id.length > 12 ? id.substring(0, 8).toUpperCase() : id}
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, minWidth: 0, padding: 'var(--space-4)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
          <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--text)', lineHeight: 1.35, textWrap: 'pretty' }}>{title}</h3>
          <Pill state={verdict} />
        </div>
        <BakeOffStrip plans={plans} />
      </div>
    </div>
  );
}

function NewCaseModal({ onClose }) {
  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 'var(--space-5)', zIndex: 50 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ width: 560, maxWidth: '100%', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-card)', padding: 'var(--space-6)' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-4)' }}>
          <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 800, color: 'var(--text)' }}>New case</h2>
          <button className="btn btn-sm" onClick={onClose} aria-label="Close" style={{ padding: '6px 8px' }}>
            <i className="ti ti-x" aria-hidden="true"></i>
          </button>
        </div>
        <p style={{ fontSize: 'var(--text-base)', color: 'var(--text-muted)', lineHeight: 1.55 }}>
          New case creation coming soon.
        </p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--space-5)' }}>
          <button className="btn" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

function CasesScreen({ theme, onToggleTheme }) {
  const [cases, setCases] = React.useState(null);
  const [showModal, setShowModal] = React.useState(false);

  React.useEffect(() => {
    fetch('/api/cases')
      .then((r) => r.json())
      .then((data) => setCases(data.cases))
      .catch(() => setCases([]));
  }, []);

  if (cases === null) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
        Loading…
      </div>
    );
  }

  const open   = cases.filter((c) => c.verdict === 'progress' || c.verdict === 'awaiting');
  const closed = cases.filter((c) => c.verdict_log);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Top bar */}
      <header style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--space-4)', padding: 'var(--space-5) var(--space-6)', borderBottom: '1px solid var(--border)' }}>
        <div>
          <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: '-.01em', color: 'var(--text)' }}>Cases</h1>
          <p style={{ fontSize: 'var(--text-base)', color: 'var(--text-muted)', marginTop: 4 }}>Open problems racing toward a verdict.</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <button className="btn btn-crux" onClick={() => setShowModal(true)}>
            <i className="ti ti-plus" aria-hidden="true"></i> New case
          </button>
          <button className="btn btn-sm" onClick={onToggleTheme} aria-label="Toggle theme" style={{ padding: '7px 9px' }}>
            <i className={`ti ti-${theme === 'dark' ? 'sun' : 'moon'}`} aria-hidden="true"></i>
          </button>
        </div>
      </header>

      {/* Case list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-6)' }}>
        {cases.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 'var(--space-7) 0', color: 'var(--text-muted)' }}>
            <div style={{ fontSize: 'var(--text-xl)', fontWeight: 600, color: 'var(--text)', marginBottom: 'var(--space-2)' }}>
              No cases yet
            </div>
            <p style={{ fontSize: 'var(--text-base)', lineHeight: 1.55 }}>
              Got a problem worth solving? Start a case.
            </p>
          </div>
        ) : (
          <>
            {open.length > 0 && (
              <>
                <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 'var(--space-3)' }}>
                  OPEN · {open.length}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', marginBottom: 'var(--space-6)' }}>
                  {open.map((c) => (
                    <CaseCard key={c.id} {...c} />
                  ))}
                </div>
              </>
            )}

            {closed.length > 0 && (
              <>
                <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 'var(--space-3)' }}>
                  CLOSED · {closed.length}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                  {closed.map((c) => (
                    <CaseCard key={c.id} {...c} />
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>

      {showModal && <NewCaseModal onClose={() => setShowModal(false)} />}
    </div>
  );
}
