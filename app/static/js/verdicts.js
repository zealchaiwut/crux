/* crux · Verdicts log screen
   VerdictScreen — read-only list of all logged verdicts, filterable by outcome.
   Adapted from design_handoff_crux/reference_screens/screens.jsx VerdictScreen.
*/

function VerdictScreen({ onOpenCase, theme, onToggleTheme }) {
  const [verdicts, setVerdicts] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [filter, setFilter] = React.useState('all');

  React.useEffect(() => {
    const url = filter === 'all' ? '/api/verdicts' : `/api/verdicts?outcome=${filter}`;
    setLoading(true);
    fetch(url)
      .then((r) => r.json())
      .then((data) => { setVerdicts(data.verdicts || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [filter]);

  const filterOpts = [
    { key: 'all',          label: 'All' },
    { key: 'confirmed',    label: 'Confirmed' },
    { key: 'killed',       label: 'Killed' },
    { key: 'inconclusive', label: 'Inconclusive' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header */}
      <header style={{
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 'var(--space-4)', padding: 'var(--space-5) var(--space-6)',
        borderBottom: '1px solid var(--border)'
      }}>
        <div>
          <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: '-.01em', color: 'var(--text)' }}>
            Verdicts
          </h1>
          <p style={{ fontSize: 'var(--text-base)', color: 'var(--text-muted)', marginTop: 4 }}>
            Confirmed causes and killed hypotheses — your personal knowledge base.
          </p>
        </div>
        <button
          className="btn btn-sm"
          onClick={onToggleTheme}
          aria-label="Toggle theme"
          style={{ padding: '7px 9px' }}
        >
          <i className={`ti ti-${theme === 'dark' ? 'sun' : 'moon'}`} aria-hidden="true"></i>
        </button>
      </header>

      {/* Filter tabs */}
      <div style={{
        display: 'flex', gap: 'var(--space-2)', padding: 'var(--space-4) var(--space-6)',
        borderBottom: '1px solid var(--border)'
      }}>
        {filterOpts.map((opt) => (
          <button
            key={opt.key}
            onClick={() => setFilter(opt.key)}
            className="btn btn-sm"
            style={{
              background: filter === opt.key ? 'var(--crux-bg)' : 'transparent',
              color: filter === opt.key ? 'var(--crux)' : 'var(--text-muted)',
              border: `1px solid ${filter === opt.key ? 'var(--crux)' : 'var(--border)'}`,
              fontWeight: filter === opt.key ? 600 : 400,
            }}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-6)' }}>
        {loading ? (
          <div style={{ textAlign: 'center', color: 'var(--text-sub)', padding: 'var(--space-6)' }}>
            <i className="ti ti-loader crux-spin" aria-hidden="true"></i>
          </div>
        ) : verdicts.length === 0 ? (
          <div style={{
            textAlign: 'center', color: 'var(--text-muted)',
            padding: 'var(--space-6)', display: 'flex', flexDirection: 'column',
            alignItems: 'center', gap: 'var(--space-3)'
          }}>
            <i className="ti ti-gavel" style={{ fontSize: 32, color: 'var(--text-sub)' }} aria-hidden="true"></i>
            <div style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--text)' }}>
              No verdicts yet
            </div>
            <div style={{ fontSize: 'var(--text-base)', color: 'var(--text-muted)' }}>
              {filter === 'all'
                ? 'Complete a probe on a Case to log the first verdict.'
                : `No ${filter} verdicts match this filter.`}
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {verdicts.map((v) => (
              <VerdictRow key={v.id} verdict={v} onOpenCase={onOpenCase} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function VerdictRow({ verdict, onOpenCase }) {
  const [hovered, setHovered] = React.useState(false);

  const shortId = verdict.case_id
    ? verdict.case_id.substring(0, 8).toUpperCase()
    : '—';

  const decidedDate = verdict.decided_at
    ? verdict.decided_at.substring(0, 10)
    : '—';

  return (
    <div
      style={{
        display: 'flex', gap: 'var(--space-4)',
        background: 'var(--surface)',
        border: `1px solid ${hovered ? 'var(--crux)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)', padding: 'var(--space-4)',
        boxShadow: hovered ? 'var(--shadow-hover)' : 'var(--shadow-card)',
        transition: 'box-shadow var(--speed), border-color var(--speed)',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Left: pill + meta */}
      <div style={{ flex: 'none', width: 120 }}>
        <Pill state={verdict.outcome} />
        <div className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)', marginTop: 8, lineHeight: 1.6 }}>
          {shortId}<br />{decidedDate}
        </div>
        {verdict.decided_metric && (
          <div className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)', marginTop: 4 }}>
            {verdict.decided_metric}
          </div>
        )}
      </div>

      {/* Right: case title (link) + notes */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <button
          onClick={() => verdict.case_id && onOpenCase(verdict.case_id)}
          style={{
            background: 'none', border: 'none', padding: 0, cursor: 'pointer',
            textAlign: 'left', fontSize: 'var(--text-lg)', fontWeight: 600,
            color: 'var(--text)', marginBottom: 4, lineHeight: 1.35,
            textDecoration: hovered ? 'underline' : 'none',
          }}
        >
          {verdict.case_title || verdict.case_id}
        </button>
        {verdict.notes ? (
          <p style={{ fontSize: 'var(--text-base)', color: 'var(--text-muted)', lineHeight: 1.5, margin: 0 }}>
            {verdict.notes}
          </p>
        ) : (
          <p style={{ fontSize: 'var(--text-base)', color: 'var(--text-sub)', lineHeight: 1.5, margin: 0 }}>—</p>
        )}
      </div>
    </div>
  );
}
