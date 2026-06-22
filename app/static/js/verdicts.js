/* crux · Verdicts list screen
   Grouped (Confirmed Causes / Killed Hypotheses / Inconclusive) or flat
   (newest-first) view with real-time keyword search and outcome filter chips.
*/

const OUTCOME_META = [
  { key: 'confirmed',    label: 'Confirmed',    pillClass: 'confirmed',    heading: 'Confirmed Causes',    emptyMsg: 'No confirmed causes match your filters.' },
  { key: 'killed',       label: 'Killed',       pillClass: 'killed',       heading: 'Killed Hypotheses',   emptyMsg: 'No killed hypotheses match your filters.' },
  { key: 'inconclusive', label: 'Inconclusive', pillClass: 'inconclusive', heading: 'Inconclusive',        emptyMsg: 'No inconclusive verdicts match your filters.' },
];

// ---------------------------------------------------------------------------
// VerdictRow
// ---------------------------------------------------------------------------

function VerdictRow({ verdict, onViewCase }) {
  const [hovered, setHovered] = React.useState(false);
  const { outcome, case: c, probe } = verdict;

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 'var(--space-4)',
        background: 'var(--surface)',
        border: `1px solid ${hovered ? 'var(--crux)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)',
        padding: 'var(--space-4)',
        boxShadow: hovered ? 'var(--shadow-hover)' : 'var(--shadow-card)',
        transition: 'box-shadow var(--speed), border-color var(--speed)',
      }}
    >
      <span className={`pill ${outcome}`} aria-label={`Outcome: ${outcome}`}>
        {outcome}
      </span>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--text)', lineHeight: 1.4, textWrap: 'pretty' }}>
          {c ? c.sharpened_snippet : '—'}
        </div>
        {probe && probe.target_metric && (
          <div className="mono" style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)', marginTop: 'var(--space-1)', fontWeight: 700 }}>
            {probe.target_metric}
          </div>
        )}
      </div>

      {c && c.id && (
        <button
          className="btn btn-sm"
          onClick={() => onViewCase && onViewCase(c.id)}
          aria-label={`View Case for: ${c.sharpened_snippet || c.id}`}
        >
          View Case
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// GroupSection — one outcome group in grouped view
// ---------------------------------------------------------------------------

function GroupSection({ meta, verdicts, onViewCase }) {
  return (
    <div style={{ marginBottom: 'var(--space-6)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span className={`pill ${meta.pillClass}`}>{meta.label}</span>
        <span className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)' }}>
          {verdicts.length}
        </span>
        <div style={{ flex: 1, height: 1, background: 'var(--border)' }}></div>
        <span style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--text)', marginLeft: 'var(--space-2)' }}>
          {meta.heading}
        </span>
      </div>
      {verdicts.length === 0 ? (
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: 'var(--space-5)',
          textAlign: 'center', color: 'var(--text-muted)',
          fontSize: 'var(--text-base)',
        }}>
          {meta.emptyMsg}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          {verdicts.map((v) => (
            <VerdictRow key={v.id} verdict={v} onViewCase={onViewCase} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// FilterChip
// ---------------------------------------------------------------------------

function FilterChip({ label, count, active, onClick }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      aria-label={`Filter by ${label}: ${count} verdicts`}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '5px 12px', borderRadius: 'var(--radius-pill)',
        border: `1px solid ${active ? 'var(--crux)' : 'var(--border)'}`,
        background: active ? 'var(--crux-bg)' : 'var(--surface)',
        color: active ? 'var(--crux)' : 'var(--text-muted)',
        fontWeight: active ? 600 : 500,
        fontSize: 'var(--text-sm)',
        cursor: 'pointer',
        transition: 'background var(--speed), border-color var(--speed)',
      }}
    >
      {label}
      <span className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700 }}>
        {count}
      </span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// VerdictScreen
// ---------------------------------------------------------------------------

function VerdictScreen({ onViewCase }) {
  const [verdicts, setVerdicts] = React.useState(null);
  const [viewMode, setViewMode] = React.useState('grouped');
  const [search, setSearch] = React.useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('q') || '';
  });
  const [activeOutcomes, setActiveOutcomes] = React.useState(new Set());

  React.useEffect(() => {
    fetch('/api/verdicts')
      .then((r) => r.json())
      .then((data) => setVerdicts(Array.isArray(data) ? data : []))
      .catch(() => setVerdicts([]));
  }, []);

  React.useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (search) {
      params.set('q', search);
    } else {
      params.delete('q');
    }
    const newUrl = `${window.location.pathname}${params.toString() ? '?' + params.toString() : ''}`;
    window.history.replaceState(null, '', newUrl);
  }, [search]);

  if (verdicts === null) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
        <i className="ti ti-loader-2 crux-spin" aria-hidden="true" style={{ fontSize: 20, color: 'var(--crux)', marginRight: 8 }}></i>
        Loading verdicts…
      </div>
    );
  }

  const keyword = search.trim().toLowerCase();

  function matchesKeyword(v) {
    if (!keyword) return true;
    const inStatement = v.case && v.case.sharpened_snippet && v.case.sharpened_snippet.toLowerCase().includes(keyword);
    const inMetric = v.probe && v.probe.target_metric && v.probe.target_metric.toLowerCase().includes(keyword);
    const inNotes = v.notes && v.notes.toLowerCase().includes(keyword);
    return inStatement || inMetric || inNotes;
  }

  function toggleOutcome(key) {
    setActiveOutcomes((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  const keywordFiltered = verdicts.filter(matchesKeyword);

  const chipCounts = {};
  OUTCOME_META.forEach(({ key }) => {
    chipCounts[key] = keywordFiltered.filter((v) => v.outcome === key).length;
  });

  const fullyFiltered = activeOutcomes.size > 0
    ? keywordFiltered.filter((v) => activeOutcomes.has(v.outcome))
    : keywordFiltered;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <header style={{
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 'var(--space-4)', padding: 'var(--space-5) var(--space-6)',
        borderBottom: '1px solid var(--border)',
      }}>
        <div>
          <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: '-.01em', color: 'var(--text)' }}>
            Verdicts
          </h1>
          <p style={{ fontSize: 'var(--text-base)', color: 'var(--text-muted)', marginTop: 4 }}>
            Confirmed causes, killed hypotheses, and inconclusive outcomes across all cases.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', paddingTop: 4 }}>
          <button
            className={`btn btn-sm${viewMode === 'grouped' ? ' btn-crux' : ''}`}
            onClick={() => setViewMode('grouped')}
            aria-pressed={viewMode === 'grouped'}
            aria-label="Grouped view"
          >
            <i className="ti ti-layout-list" aria-hidden="true"></i> Grouped
          </button>
          <button
            className={`btn btn-sm${viewMode === 'flat' ? ' btn-crux' : ''}`}
            onClick={() => setViewMode('flat')}
            aria-pressed={viewMode === 'flat'}
            aria-label="Flat view"
          >
            <i className="ti ti-list" aria-hidden="true"></i> Flat
          </button>
        </div>
      </header>

      <div style={{
        display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
        padding: 'var(--space-4) var(--space-6)',
        borderBottom: '1px solid var(--border)',
        flexWrap: 'wrap',
      }}>
        <div style={{ position: 'relative', flex: '1 1 220px', minWidth: 180 }}>
          <i className="ti ti-search" aria-hidden="true" style={{
            position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
            color: 'var(--text-muted)', fontSize: 15, pointerEvents: 'none',
          }}></i>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search verdicts…"
            aria-label="Search verdicts by keyword"
            style={{
              width: '100%', padding: '7px 12px 7px 32px',
              border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
              background: 'var(--surface)', color: 'var(--text)',
              fontSize: 'var(--text-base)', outline: 'none',
              transition: 'border-color var(--speed)',
            }}
            onFocus={(e) => { e.target.style.borderColor = 'var(--crux)'; e.target.style.boxShadow = 'var(--ring)'; }}
            onBlur={(e) => { e.target.style.borderColor = 'var(--border)'; e.target.style.boxShadow = 'none'; }}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          {OUTCOME_META.map(({ key, label }) => (
            <FilterChip
              key={key}
              label={label}
              count={chipCounts[key]}
              active={activeOutcomes.has(key)}
              onClick={() => toggleOutcome(key)}
            />
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-6)' }}>
        {viewMode === 'grouped' ? (
          OUTCOME_META.map((meta) => (
            <GroupSection
              key={meta.key}
              meta={meta}
              verdicts={fullyFiltered.filter((v) => v.outcome === meta.key)}
              onViewCase={onViewCase}
            />
          ))
        ) : (
          fullyFiltered.length === 0 ? (
            <div style={{
              flex: 1, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center',
              padding: 'var(--space-7) 0', color: 'var(--text-muted)',
              textAlign: 'center',
            }}>
              <i className="ti ti-inbox" aria-hidden="true" style={{ fontSize: 32, color: 'var(--border)', marginBottom: 'var(--space-3)' }}></i>
              <div style={{ fontSize: 'var(--text-xl)', fontWeight: 600, color: 'var(--text)', marginBottom: 'var(--space-2)' }}>
                No verdicts match
              </div>
              <p style={{ fontSize: 'var(--text-base)', maxWidth: 340, lineHeight: 1.5 }}>
                {verdicts.length === 0
                  ? 'No verdicts have been logged yet. Log a verdict from a Case to see it here.'
                  : 'Try a different keyword or clear the filters.'}
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              {fullyFiltered.map((v) => (
                <VerdictRow key={v.id} verdict={v} onViewCase={onViewCase} />
              ))}
            </div>
          )
        )}
      </div>
    </div>
  );
}
