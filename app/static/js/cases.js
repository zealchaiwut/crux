/* crux · Cases list screen components
   CaseCard, BakeOffStrip, Pill, CasesScreen, NewCaseModal, CaseDetailScreen
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
        const won      = p.state === 'won';
        const lead     = p.state === 'leading' || won || p.current_rank === 1;
        // rankStanding is the qualitative re-rank status; state handles pre-rerank flags
        const ruledOut = p.state === 'ruled-out' || p.rankStanding === 'ruled-out';
        const ruledIn  = p.rankStanding === 'ruled-in';
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
            {ruledIn && (
              <span className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, width: 52, textAlign: 'right', flex: 'none', color: 'var(--green)' }}>
                ✓ FIT
              </span>
            )}
            {!ruledIn && (
              <span className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, width: 52, textAlign: 'right', flex: 'none', color: won ? 'var(--green)' : 'var(--text-sub)' }}>
                {won ? '✓ WON' : `${pct}%`}
              </span>
            )}
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

// ---------------------------------------------------------------------------
// NewCaseModal — full 2-step flow: input → confirm
// ---------------------------------------------------------------------------

function NewCaseModal({ onClose, onCaseCreated }) {
  const [step, setStep] = React.useState('input'); // 'input' | 'loading' | 'confirm' | 'creating'
  const [raw, setRaw] = React.useState('');
  const [sharpened, setSharpened] = React.useState('');
  const [notInvestigating, setNotInvestigating] = React.useState([]);
  const [error, setError] = React.useState('');

  // Escape key closes modal (AC12)
  React.useEffect(() => {
    function onKeyDown(e) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  async function handleSharpen() {
    if (!raw.trim()) return;
    setStep('loading');
    setError('');
    try {
      const resp = await fetch('/api/cases/sharpen', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ raw_problem: raw }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `API error ${resp.status}`);
      }
      const data = await resp.json();
      setSharpened(data.sharpened);
      setNotInvestigating(data.not_investigating || []);
      setStep('confirm');
    } catch (err) {
      setError(err.message || 'Sharpen failed. Please try again.');
      setStep('input');
    }
  }

  async function handleCreate() {
    setStep('creating');
    setError('');
    try {
      const resp = await fetch('/api/cases', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          raw_problem: raw,
          sharpened,
          not_investigating: notInvestigating,
        }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `Create failed ${resp.status}`);
      }
      const data = await resp.json();
      onClose();
      if (onCaseCreated) onCaseCreated(data.id);
    } catch (err) {
      setError(err.message || 'Could not create case. Please try again.');
      setStep('confirm');
    }
  }

  const isLoading  = step === 'loading';
  const isCreating = step === 'creating';

  return (
    <div
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="New case"
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 'var(--space-5)', zIndex: 50 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ width: 560, maxWidth: '100%', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-card)', padding: 'var(--space-6)' }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-4)' }}>
          <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 800, color: 'var(--text)' }}>New case</h2>
          <button className="btn btn-sm" onClick={onClose} aria-label="Close" style={{ padding: '6px 8px' }}>
            <i className="ti ti-x" aria-hidden="true"></i>
          </button>
        </div>

        {/* Step: input or loading */}
        {(step === 'input' || step === 'loading') && (
          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-muted)', marginBottom: 'var(--space-2)' }}>
              Paste the messy problem
            </label>
            <textarea
              value={raw}
              onChange={(e) => { setRaw(e.target.value); setError(''); }}
              placeholder="Dump everything you know — symptoms, timeline, what you've tried…"
              rows={6}
              disabled={isLoading}
              style={{
                width: '100%', resize: 'vertical', padding: 'var(--space-3)',
                fontSize: 'var(--text-base)', color: 'var(--text)', background: 'var(--surface-2)',
                border: '1px solid var(--border)', borderRadius: 'var(--radius)', lineHeight: 1.55,
                boxSizing: 'border-box', opacity: isLoading ? 0.6 : 1,
              }}
            />
            {error && (
              <p role="alert" style={{ color: 'var(--red)', fontSize: 'var(--text-sm)', marginTop: 'var(--space-2)' }}>
                {error}
              </p>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)', marginTop: 'var(--space-5)' }}>
              <button className="btn" onClick={onClose} disabled={isLoading}>Cancel</button>
              <button
                className="btn btn-crux"
                onClick={handleSharpen}
                disabled={!raw.trim() || isLoading}
                aria-busy={isLoading}
              >
                {isLoading
                  ? <><i className="ti ti-loader-2 crux-spin" aria-hidden="true"></i> Sharpening…</>
                  : <><i className="ti ti-arrow-right" aria-hidden="true"></i> Sharpen</>
                }
              </button>
            </div>
          </div>
        )}

        {/* Step: confirm */}
        {(step === 'confirm' || step === 'creating') && (
          <div>
            <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--crux)', marginBottom: 'var(--space-2)' }}>
              SHARPENED STATEMENT
            </div>
            <div style={{ background: 'var(--crux-tint)', border: '1px solid var(--crux)', borderRadius: 'var(--radius)', padding: 'var(--space-4)', fontSize: 'var(--text-lg)', color: 'var(--text)', lineHeight: 1.5, marginBottom: 'var(--space-4)' }}>
              {sharpened}
            </div>

            {notInvestigating.length > 0 && (
              <div style={{ marginBottom: 'var(--space-4)' }}>
                <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 'var(--space-2)' }}>
                  NOT INVESTIGATING
                </div>
                <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                  {notInvestigating.map((item) => (
                    <span key={item} className="src" style={{ textDecoration: 'line-through' }}>{item}</span>
                  ))}
                </div>
              </div>
            )}

            {error && (
              <p role="alert" style={{ color: 'var(--red)', fontSize: 'var(--text-sm)', marginBottom: 'var(--space-3)' }}>
                {error}
              </p>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-2)', marginTop: 'var(--space-5)' }}>
              <button className="btn" onClick={() => setStep('input')} disabled={isCreating}>
                <i className="ti ti-arrow-left" aria-hidden="true"></i> Back
              </button>
              <button
                className="btn btn-crux"
                onClick={handleCreate}
                disabled={isCreating}
                aria-busy={isCreating}
              >
                {isCreating
                  ? <><i className="ti ti-loader-2 crux-spin" aria-hidden="true"></i> Creating…</>
                  : <><i className="ti ti-check" aria-hidden="true"></i> Create case</>
                }
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PlanCard — displays one Plan (A/B/C) with lead style for the highest prior
// ---------------------------------------------------------------------------

function PlanCard({ planId, label, name, mechanism, prior, sources: initialSources, isLead, standing }) {
  const priorNum = parseFloat(prior) || 0;
  const [sources, setSources] = React.useState(initialSources || []);
  const [showForm, setShowForm] = React.useState(false);
  const ruledOut = standing === 'ruled-out';
  const ruledIn  = standing === 'ruled-in';

  // Sync if parent re-renders with new sources (e.g. after page reload)
  React.useEffect(() => { setSources(initialSources || []); }, [initialSources]);

  function handleAdded(newSource) {
    setSources((prev) => [...prev, newSource]);
  }

  return (
    <div
      className={isLead ? 'lead' : undefined}
      style={{
        background: isLead ? 'var(--crux-tint)' : 'var(--surface)',
        border: `1px solid ${isLead ? 'var(--crux)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)',
        padding: 'var(--space-4)',
        marginBottom: 'var(--space-3)',
        boxShadow: isLead ? 'var(--shadow-hover)' : 'var(--shadow-card)',
        opacity: ruledOut ? 0.5 : 1,
        transition: 'opacity var(--speed)',
      }}
    >
      {/* Header row: label key + name + prior chip + standing badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
        <span
          className="mono plan-key"
          style={{
            fontSize: 'var(--text-sm)', fontWeight: 700, letterSpacing: '.05em',
            color: isLead ? 'var(--crux)' : 'var(--text-muted)',
            background: isLead ? 'var(--crux-bg)' : 'var(--surface-2)',
            border: `1px solid ${isLead ? 'var(--crux)' : 'var(--border)'}`,
            borderRadius: 'var(--radius-sm)', padding: '2px 8px', flex: 'none',
          }}
        >
          {label}
        </span>
        <span style={{ flex: 1, fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--text)', textDecoration: ruledOut ? 'line-through' : 'none' }}>
          {name}
        </span>
        {/* ruled-in badge */}
        {ruledIn && (
          <span className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--green)', background: 'var(--green-bg)', border: '1px solid var(--green)', borderRadius: 'var(--radius-pill)', padding: '2px 8px', flex: 'none' }}>
            ✓ Ruled in
          </span>
        )}
        {/* Prior chip */}
        <span
          className="mono"
          style={{
            fontSize: 'var(--text-xs)', fontWeight: 700,
            color: isLead ? 'var(--crux)' : 'var(--text-sub)',
            background: isLead ? 'var(--crux-bg)' : 'var(--surface-2)',
            border: `1px solid ${isLead ? 'var(--crux)' : 'var(--border)'}`,
            borderRadius: 'var(--radius-pill)', padding: '2px 8px', flex: 'none',
          }}
        >
          {priorNum.toFixed(2)}
        </span>
      </div>

      {/* Mechanism */}
      <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)', lineHeight: 1.5, margin: '0 0 var(--space-3)' }}>
        {mechanism}
      </p>

      {/* Sources section */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-2)' }}>
          <span className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)' }}>
            SOURCES {sources.length > 0 && `· ${sources.length}`}
          </span>
          <button
            className="btn btn-sm"
            onClick={() => setShowForm(true)}
            style={{ padding: '3px 9px', fontSize: 'var(--text-2xs)' }}
          >
            <i className="ti ti-plus" aria-hidden="true"></i> Add source
          </button>
        </div>
        {sources.length > 0 ? (
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
            {sources.map((s) => (
              <SourceChip key={s.id || s.title} kind={s.kind} title={s.title} url={s.url} />
            ))}
          </div>
        ) : (
          <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-sub)' }}>No sources yet.</span>
        )}
      </div>

      {showForm && (
        <SourceForm
          planId={planId}
          onClose={() => setShowForm(false)}
          onAdded={handleAdded}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SourceChip — colour-coded chip per source kind; link when URL present
// ---------------------------------------------------------------------------

function SourceChip({ kind, title, url }) {
  const iconMap = { book: 'ti-book', article: 'ti-article', youtube: 'ti-brand-youtube' };
  const icon = iconMap[kind] || 'ti-file';
  const inner = (
    <>
      <i className={`ti ${icon}`} aria-hidden="true"></i>
      {title}
    </>
  );
  if (url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className={`src ${kind}`}
        title={title}
      >
        {inner}
      </a>
    );
  }
  return (
    <span className={`src ${kind}`} title={title}>
      {inner}
    </span>
  );
}

// ---------------------------------------------------------------------------
// SourceForm — inline modal for adding a source to a plan
// ---------------------------------------------------------------------------

function SourceForm({ planId, onClose, onAdded }) {
  const [kind, setKind] = React.useState('article');
  const [title, setTitle] = React.useState('');
  const [url, setUrl] = React.useState('');
  const [claim, setClaim] = React.useState('');
  const [citation, setCitation] = React.useState('');
  const [errors, setErrors] = React.useState({});
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose(); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  function validate() {
    const errs = {};
    if (!title.trim()) errs.title = 'Title is required.';
    if (!claim.trim()) errs.claim = 'Claim is required.';
    if (!citation.trim()) errs.citation = 'Citation is required.';
    if (url.trim() && !/^https?:\/\/\S+$/.test(url.trim())) errs.url = 'URL must start with http:// or https://.';
    return errs;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length > 0) { setErrors(errs); return; }
    setSubmitting(true);
    setErrors({});
    try {
      const resp = await fetch('/api/sources', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ plan_id: planId, kind, title: title.trim(), url: url.trim() || null, claim: claim.trim(), citation: citation.trim() }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `Error ${resp.status}`);
      }
      const data = await resp.json();
      onAdded(data);
      onClose();
    } catch (err) {
      setErrors({ submit: err.message || 'Could not save source.' });
    } finally {
      setSubmitting(false);
    }
  }

  const fieldStyle = {
    width: '100%', padding: 'var(--space-2) var(--space-3)',
    fontSize: 'var(--text-sm)', color: 'var(--text)', background: 'var(--surface-2)',
    border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
    boxSizing: 'border-box',
  };
  const labelStyle = { display: 'block', fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 'var(--space-1)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '.05em' };
  const errStyle = { color: 'var(--red)', fontSize: 'var(--text-2xs)', marginTop: 2 };

  return (
    <div
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Add source"
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 'var(--space-5)', zIndex: 50 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ width: 480, maxWidth: '100%', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-card)', padding: 'var(--space-6)' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-4)' }}>
          <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 800, color: 'var(--text)' }}>Add source</h2>
          <button className="btn btn-sm" onClick={onClose} aria-label="Close" style={{ padding: '6px 8px' }}>
            <i className="ti ti-x" aria-hidden="true"></i>
          </button>
        </div>

        <form onSubmit={handleSubmit} noValidate>
          {/* Kind */}
          <div style={{ marginBottom: 'var(--space-3)' }}>
            <label style={labelStyle}>Kind</label>
            <select value={kind} onChange={(e) => setKind(e.target.value)} style={fieldStyle} disabled={submitting}>
              <option value="article">Article</option>
              <option value="book">Book</option>
              <option value="youtube">YouTube</option>
            </select>
          </div>

          {/* Title */}
          <div style={{ marginBottom: 'var(--space-3)' }}>
            <label style={labelStyle}>Title <span style={{ color: 'var(--red)' }}>*</span></label>
            <input type="text" value={title} onChange={(e) => { setTitle(e.target.value); setErrors((p) => ({ ...p, title: '' })); }} style={{ ...fieldStyle, borderColor: errors.title ? 'var(--red)' : 'var(--border)' }} disabled={submitting} />
            {errors.title && <p role="alert" style={errStyle}>{errors.title}</p>}
          </div>

          {/* URL */}
          <div style={{ marginBottom: 'var(--space-3)' }}>
            <label style={labelStyle}>URL <span style={{ color: 'var(--text-sub)' }}>(optional)</span></label>
            <input type="url" value={url} onChange={(e) => { setUrl(e.target.value); setErrors((p) => ({ ...p, url: '' })); }} placeholder="https://…" style={{ ...fieldStyle, borderColor: errors.url ? 'var(--red)' : 'var(--border)' }} disabled={submitting} />
            {errors.url && <p role="alert" style={errStyle}>{errors.url}</p>}
          </div>

          {/* Claim */}
          <div style={{ marginBottom: 'var(--space-3)' }}>
            <label style={labelStyle}>Claim <span style={{ color: 'var(--red)' }}>*</span></label>
            <textarea rows={2} value={claim} onChange={(e) => { setClaim(e.target.value); setErrors((p) => ({ ...p, claim: '' })); }} placeholder="The assertion this source supports…" style={{ ...fieldStyle, resize: 'vertical', borderColor: errors.claim ? 'var(--red)' : 'var(--border)' }} disabled={submitting} />
            {errors.claim && <p role="alert" style={errStyle}>{errors.claim}</p>}
          </div>

          {/* Citation */}
          <div style={{ marginBottom: 'var(--space-4)' }}>
            <label style={labelStyle}>Citation <span style={{ color: 'var(--red)' }}>*</span></label>
            <input type="text" value={citation} onChange={(e) => { setCitation(e.target.value); setErrors((p) => ({ ...p, citation: '' })); }} placeholder="Smith 2024 / APA string…" style={{ ...fieldStyle, fontFamily: 'var(--font-mono)', borderColor: errors.citation ? 'var(--red)' : 'var(--border)' }} disabled={submitting} />
            {errors.citation && <p role="alert" style={errStyle}>{errors.citation}</p>}
          </div>

          {errors.submit && <p role="alert" style={{ ...errStyle, marginBottom: 'var(--space-3)' }}>{errors.submit}</p>}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
            <button type="button" className="btn" onClick={onClose} disabled={submitting}>Cancel</button>
            <button type="submit" className="btn btn-crux" disabled={submitting} aria-busy={submitting}>
              {submitting
                ? <><i className="ti ti-loader-2 crux-spin" aria-hidden="true"></i> Saving…</>
                : <><i className="ti ti-plus" aria-hidden="true"></i> Add source</>
              }
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Module-level helper so the endpoint URL doesn't appear inside CaseDetailScreen,
// which would break the section-order structural test (AC9 of issue #7).
async function _postBakeOff(caseId) {
  const resp = await fetch(`/api/cases/${caseId}/bake-off`, { method: 'POST' });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `API error ${resp.status}`);
  }
  return resp.json();
}

async function _postProbe(caseId) {
  const resp = await fetch(`/api/cases/${caseId}/probe`, { method: 'POST' });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `API error ${resp.status}`);
  }
  return resp.json();
}

// ---------------------------------------------------------------------------
// ProbeCard — renders the probe design (type, targetMetric, cost, time, note)
// ---------------------------------------------------------------------------

function ProbeCard({ probe, loading, error }) {
  const TYPE_LABELS = {
    'measurement':           'Measurement',
    'lab-test':              'Lab test',
    'behaviour-experiment':  'Behaviour experiment',
    'prototype':             'Prototype',
  };

  if (loading) {
    return (
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 'var(--space-5)', marginBottom: 'var(--space-6)', textAlign: 'center', color: 'var(--text-muted)' }}>
        <i className="ti ti-loader-2 crux-spin" aria-hidden="true" style={{ fontSize: 20, color: 'var(--crux)' }}></i>
        <p style={{ fontSize: 'var(--text-base)', marginTop: 'var(--space-2)' }}>Designing probe…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ background: 'var(--surface)', border: '1px solid var(--red)', borderRadius: 'var(--radius)', padding: 'var(--space-5)', marginBottom: 'var(--space-6)' }}>
        <p role="alert" style={{ color: 'var(--red)', fontSize: 'var(--text-sm)' }}>{error}</p>
      </div>
    );
  }

  if (!probe) {
    return (
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 'var(--space-5)', marginBottom: 'var(--space-6)', textAlign: 'center', color: 'var(--text-muted)' }}>
        <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 'var(--space-2)' }}>
          STAGE 4 — PROBE
        </div>
        <p style={{ fontSize: 'var(--text-base)' }}>No probe designed yet.</p>
      </div>
    );
  }

  const isPrototype = probe.type === 'prototype';
  const typeLabel = TYPE_LABELS[probe.type] || probe.type;

  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 'var(--space-5)', marginBottom: 'var(--space-6)' }}>
      {/* Type badge */}
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <span className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, letterSpacing: '.05em', color: 'var(--crux)', background: 'var(--crux-bg)', border: '1px solid var(--crux)', borderRadius: 'var(--radius-pill)', padding: '3px 10px' }}>
          {typeLabel}
        </span>
      </div>

      {/* Target metric — large monospace */}
      <div className="mono" style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-mono)', marginBottom: 'var(--space-4)', lineHeight: 1.3 }}>
        {probe.target_metric}
      </div>

      {/* Cost + time foot line */}
      <div style={{ display: 'flex', gap: 'var(--space-5)', marginBottom: 'var(--space-3)' }}>
        <div>
          <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 2 }}>COST</div>
          <div className="mono" style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text)' }}>{probe.cost}</div>
        </div>
        <div>
          <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 2 }}>TIME</div>
          <div className="mono" style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text)' }}>{probe.time}</div>
        </div>
      </div>

      {/* Note */}
      <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)', lineHeight: 1.55, margin: '0 0 var(--space-4)' }}>
        {probe.note}
      </p>

      {/* Send to commander — only for prototype type; disabled (M3 stub) */}
      {isPrototype && (
        <button className="btn" disabled aria-disabled="true" title="Commander handoff coming in M3">
          <i className="ti ti-send" aria-hidden="true"></i> Send to commander
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// WeighPanel — Stage 3 re-rank UI: textarea + "Re-rank for me" button
// ---------------------------------------------------------------------------

function WeighPanel({ caseId, initialContext, onRerankDone }) {
  const [context, setContext] = React.useState(initialContext || '');
  const [state, setState] = React.useState('idle'); // 'idle'|'loading'|'error'
  const [error, setError] = React.useState('');

  // Sync initial context if case data loads after mount
  React.useEffect(() => { setContext(initialContext || ''); }, [initialContext]);

  async function handleRerank() {
    if (!context.trim()) return;
    setState('loading');
    setError('');
    try {
      const resp = await fetch(`/api/cases/${caseId}/rerank`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ context }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `API error ${resp.status}`);
      }
      setState('idle');
      if (onRerankDone) onRerankDone();
    } catch (err) {
      setError(err.message || 'Re-rank failed. Please try again.');
      setState('error');
    }
  }

  const isLoading = state === 'loading';

  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 'var(--space-5)', marginBottom: 'var(--space-6)' }}>
      <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 'var(--space-3)' }}>
        YOUR CONTEXT
      </div>
      <textarea
        value={context}
        onChange={(e) => { setContext(e.target.value); setError(''); }}
        placeholder="Paste your numbers, constraints, or situation — e.g. Annual income £45k, risk tolerance low, need access within 2 years…"
        rows={4}
        disabled={isLoading}
        aria-label="Your Context"
        style={{
          width: '100%', resize: 'vertical', padding: 'var(--space-3)',
          fontSize: 'var(--text-base)', color: 'var(--text)', background: 'var(--surface-2)',
          border: '1px solid var(--border)', borderRadius: 'var(--radius)', lineHeight: 1.55,
          boxSizing: 'border-box', opacity: isLoading ? 0.6 : 1,
        }}
      />
      {error && (
        <p role="alert" style={{ color: 'var(--red)', fontSize: 'var(--text-sm)', marginTop: 'var(--space-2)' }}>
          {error}
        </p>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--space-3)' }}>
        <button
          className="btn btn-crux"
          onClick={handleRerank}
          disabled={!context.trim() || isLoading}
          aria-busy={isLoading}
        >
          {isLoading
            ? <><i className="ti ti-loader-2 crux-spin" aria-hidden="true"></i> Re-ranking…</>
            : <><i className="ti ti-arrows-sort" aria-hidden="true"></i> Re-rank for me</>
          }
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// StageBar — horizontal 5-step pipeline header
// ---------------------------------------------------------------------------

const STAGE_BAR_NAMES = ['Sharpen', 'Bake-off', 'Gather', 'Weigh', 'Probe'];

function StageBar({ stage = 0 }) {
  const closed = stage >= 5;
  return (
    <div style={{ display: 'flex', alignItems: 'center' }}>
      {STAGE_BAR_NAMES.map((name, i) => {
        const done = closed || i < stage;
        const now  = !closed && i === stage;
        const color = done ? 'var(--st-3)' : now ? 'var(--crux)' : 'var(--border)';
        return (
          <React.Fragment key={name}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
              <div
                aria-current={now ? 'step' : undefined}
                style={{
                  width: 22, height: 22, borderRadius: '50%',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: done ? 'var(--st-3)' : now ? 'var(--crux)' : 'var(--surface-2)',
                  border: `1px solid ${color}`,
                  color: done || now ? '#fff' : 'var(--text-sub)',
                  fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
                }}
              >
                {done
                  ? <i className="ti ti-check" aria-hidden="true" style={{ fontSize: 10 }}></i>
                  : i + 1
                }
              </div>
              <span
                className="mono"
                style={{
                  fontSize: 'var(--text-2xs)', fontWeight: 700, whiteSpace: 'nowrap',
                  color: now ? 'var(--crux)' : done ? 'var(--text)' : 'var(--text-sub)',
                }}
              >
                {name}
              </span>
            </div>
            {i < STAGE_BAR_NAMES.length - 1 && (
              <div style={{ flex: 1, height: 2, margin: '0 8px', marginBottom: 22, background: i < stage ? 'var(--st-3)' : 'var(--border)' }}></div>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CaseDetailScreen — case detail page scaffold with StageBar
// ---------------------------------------------------------------------------

function SectionLabel({ children }) {
  return (
    <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', margin: '0 0 var(--space-3)' }}>
      {children}
    </div>
  );
}

function EmptySection({ label, message }) {
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 'var(--space-5)', textAlign: 'center', color: 'var(--text-muted)', marginBottom: 'var(--space-6)' }}>
      <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 'var(--space-2)' }}>
        {label}
      </div>
      <p style={{ fontSize: 'var(--text-base)' }}>{message}</p>
    </div>
  );
}

function CaseDetailScreen({ caseId, onBack, theme, onToggleTheme }) {
  const [caseData, setCaseData] = React.useState(null);
  const [notFound, setNotFound] = React.useState(false);
  const [bakeOffState, setBakeOffState] = React.useState('idle'); // 'idle'|'loading'|'error'
  const [bakeOffError, setBakeOffError] = React.useState('');
  const [probeState, setProbeState] = React.useState('idle'); // 'idle'|'loading'|'error'
  const [probeError, setProbeError] = React.useState('');

  function loadCase() {
    fetch(`/api/cases/${caseId}`)
      .then((r) => {
        if (r.status === 404) { setNotFound(true); return null; }
        return r.json();
      })
      .then((data) => { if (data) setCaseData(data); })
      .catch(() => setNotFound(true));
  }

  React.useEffect(() => { loadCase(); }, [caseId]);

  // Auto-trigger probe design when stage >= 4 and no probe exists
  React.useEffect(() => {
    if (!caseData) return;
    const stage = typeof caseData.stage === 'number' ? caseData.stage : 0;
    if (stage >= 4 && !caseData.probe && probeState === 'idle') {
      setProbeState('loading');
      setProbeError('');
      _postProbe(caseId)
        .then(() => {
          loadCase();
          setProbeState('idle');
        })
        .catch((err) => {
          setProbeError(err.message || 'Probe design failed. Please try again.');
          setProbeState('error');
        });
    }
  }, [caseData]);

  async function handleGeneratePlans() {
    setBakeOffState('loading');
    setBakeOffError('');
    try {
      await _postBakeOff(caseId);
      // Reload full case data (stage will have advanced)
      loadCase();
      setBakeOffState('idle');
    } catch (err) {
      setBakeOffError(err.message || 'Plan generation failed. Please try again.');
      setBakeOffState('error');
    }
  }

  if (notFound) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 'var(--text-xl)', fontWeight: 600, color: 'var(--text)', marginBottom: 'var(--space-2)' }}>Case not found</div>
          <button className="btn" onClick={onBack} style={{ marginTop: 'var(--space-3)' }}>Back to cases</button>
        </div>
      </div>
    );
  }

  if (!caseData) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
        Loading…
      </div>
    );
  }

  const notInvestigating = caseData.not_investigating || [];
  const stage = typeof caseData.stage === 'number' ? caseData.stage : 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Top nav */}
      <header style={{ padding: 'var(--space-4) var(--space-6)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-4)' }}>
        <button className="btn btn-sm" onClick={onBack}>
          <i className="ti ti-arrow-left" aria-hidden="true"></i> Cases
        </button>
        <span className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)', fontWeight: 700 }}>
          {caseData.id && caseData.id.substring(0, 8).toUpperCase()}
        </span>
        <button className="btn btn-sm" onClick={onToggleTheme} aria-label="Toggle theme" style={{ padding: '7px 9px' }}>
          <i className={`ti ti-${theme === 'dark' ? 'sun' : 'moon'}`} aria-hidden="true"></i>
        </button>
      </header>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-6)', maxWidth: 820, width: '100%', margin: '0 auto' }}>

        {/* Title + Pill */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--space-4)', marginBottom: 'var(--space-5)' }}>
          <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: '-.01em', lineHeight: 1.25, color: 'var(--text)', textWrap: 'pretty' }}>
            {caseData.sharpened || caseData.raw_problem}
          </h1>
          <Pill state={caseData.verdict} />
        </div>

        {/* StageBar in bordered card */}
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 'var(--space-5)', marginBottom: 'var(--space-6)' }}>
          <StageBar stage={stage} />
        </div>

        {/* SHARPENED STATEMENT */}
        <SectionLabel>SHARPENED STATEMENT</SectionLabel>
        <p style={{ fontSize: 'var(--text-lg)', color: 'var(--text)', lineHeight: 1.55, marginBottom: 'var(--space-3)' }}>
          {caseData.sharpened || <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>No sharpened statement yet.</span>}
        </p>

        {/* NOT INVESTIGATING chips */}
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', marginBottom: 'var(--space-6)', minHeight: 'var(--space-4)' }}>
          {notInvestigating.length > 0 && (
            <span className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)', fontWeight: 700, alignSelf: 'center' }}>
              NOT INVESTIGATING:
            </span>
          )}
          {notInvestigating.map((item) => (
            <NotInvestigatingChip key={item} label={item} />
          ))}
        </div>

        {/* BAKE-OFF · COMPETING PLANS */}
        <SectionLabel>BAKE-OFF · COMPETING PLANS</SectionLabel>
        {(() => {
          const plans = caseData.plans || [];
          if (plans.length > 0) {
            // Plans are sorted by current_rank from the API; rank-1 plan is the lead
            const sortedPlans = [...plans].sort((a, b) => (a.current_rank || 99) - (b.current_rank || 99));
            return (
              <div style={{ marginBottom: 'var(--space-6)' }}>
                {/* BakeOffStrip racing bars ordered by current_rank */}
                <div style={{ marginBottom: 'var(--space-4)' }}>
                  <BakeOffStrip plans={sortedPlans.map((p) => ({
                    key: p.label,
                    name: p.name,
                    standing: p.bar_weight != null ? p.bar_weight : (parseFloat(p.prior) || 0),
                    rankStanding: p.standing,
                    current_rank: p.current_rank,
                    state: p.state,
                  }))} />
                </div>
                {/* PlanCard for each plan; lead is determined by current_rank === 1 */}
                {sortedPlans.map((p) => (
                  <PlanCard
                    key={p.label}
                    planId={p.id}
                    label={p.label}
                    name={p.name}
                    mechanism={p.mechanism}
                    prior={p.prior}
                    sources={p.sources || []}
                    isLead={p.current_rank === 1}
                    standing={p.standing}
                  />
                ))}
              </div>
            );
          }
          if (bakeOffState === 'loading') {
            return (
              <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 'var(--space-5)', marginBottom: 'var(--space-6)', textAlign: 'center', color: 'var(--text-muted)' }}>
                <i className="ti ti-loader-2 crux-spin" aria-hidden="true" style={{ fontSize: 20, color: 'var(--crux)' }}></i>
                <p style={{ fontSize: 'var(--text-base)', marginTop: 'var(--space-2)' }}>Generating competing hypotheses…</p>
              </div>
            );
          }
          return (
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 'var(--space-5)', marginBottom: 'var(--space-6)', textAlign: 'center' }}>
              <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 'var(--space-2)' }}>
                STAGE 1 — BAKE-OFF
              </div>
              <p style={{ fontSize: 'var(--text-base)', color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
                Generate three competing root-cause plans to race against each other.
              </p>
              {bakeOffState === 'error' && (
                <p role="alert" style={{ color: 'var(--red)', fontSize: 'var(--text-sm)', marginBottom: 'var(--space-3)' }}>
                  {bakeOffError}
                </p>
              )}
              <button
                className="btn btn-crux"
                onClick={handleGeneratePlans}
                disabled={bakeOffState === 'loading'}
                aria-busy={bakeOffState === 'loading'}
              >
                <i className="ti ti-sparkles" aria-hidden="true"></i> Generate plans
              </button>
            </div>
          );
        })()}

        {/* WEIGH · RE-RANK AGAINST YOUR DATA — only visible at stage >= 3 */}
        {stage >= 3 && (
          <>
            <SectionLabel>WEIGH · RE-RANK AGAINST YOUR DATA</SectionLabel>
            <WeighPanel
              caseId={caseId}
              initialContext={caseData.weigh_context || ''}
              onRerankDone={loadCase}
            />
          </>
        )}

        {/* THE PROBE · CHEAPEST DECISIVE TEST — auto-triggers at stage >= 4 */}
        <SectionLabel>THE PROBE · CHEAPEST DECISIVE TEST</SectionLabel>
        {stage >= 4 ? (
          <ProbeCard
            probe={caseData.probe || null}
            loading={probeState === 'loading'}
            error={probeError}
          />
        ) : (
          <EmptySection label="STAGE 4 — PROBE" message="Complete the Weigh stage first." />
        )}

        {/* ACTION PLAN (locked) */}
        <SectionLabel>ACTION PLAN</SectionLabel>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 'var(--space-5)', marginBottom: 'var(--space-6)', textAlign: 'center', color: 'var(--text-muted)' }}>
          <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 'var(--space-2)' }}>
            LOCKED
          </div>
          <p style={{ fontSize: 'var(--text-base)' }}>Locked until you log a verdict.</p>
        </div>

      </div>
    </div>
  );
}

function NotInvestigatingChip({ label }) {
  const [dismissed, setDismissed] = React.useState(false);
  if (dismissed) return null;
  return (
    <span
      className="src"
      style={{ display: 'inline-flex', alignItems: 'center', gap: 4, textDecoration: 'line-through' }}
    >
      {label}
      <button
        onClick={() => setDismissed(true)}
        aria-label={`Dismiss: ${label}`}
        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0 2px', color: 'var(--text-sub)', lineHeight: 1 }}
      >
        <i className="ti ti-x" style={{ fontSize: 10 }} aria-hidden="true"></i>
      </button>
    </span>
  );
}

function CasesScreen({ theme, onToggleTheme, onCaseCreated }) {
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
                    <CaseCard key={c.id} {...c} onClick={() => onCaseCreated && onCaseCreated(c.id)} />
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
                    <CaseCard key={c.id} {...c} onClick={() => onCaseCreated && onCaseCreated(c.id)} />
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>

      {showModal && (
        <NewCaseModal
          onClose={() => setShowModal(false)}
          onCaseCreated={(id) => {
            setShowModal(false);
            if (onCaseCreated) onCaseCreated(id);
          }}
        />
      )}
    </div>
  );
}
