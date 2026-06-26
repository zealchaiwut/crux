/* crux UI kit — screens: Cases list, Case detail, Verdict log, New Case modal. */

function TopBar({ title, subtitle, right, theme, onToggleTheme }) {
  return (
    <header style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--space-4)', padding: 'var(--space-5) var(--space-6)', borderBottom: '1px solid var(--border)' }}>
      <div>
        <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: '-.01em', color: 'var(--text)' }}>{title}</h1>
        {subtitle && <p style={{ fontSize: 'var(--text-base)', color: 'var(--text-muted)', marginTop: 4 }}>{subtitle}</p>}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
        {right}
        <button className="btn btn-sm" onClick={onToggleTheme} aria-label="Toggle theme" style={{ padding: '7px 9px' }}>
          <i className={`ti ti-${theme === 'dark' ? 'sun' : 'moon'}`} aria-hidden="true"></i>
        </button>
      </div>
    </header>
  );
}

function CasesScreen({ onOpen, onNew, theme, onToggleTheme }) {
  const { CaseCard } = window.CruxDesignSystem_bd6ca7;
  const { cases } = window.CRUX_DATA;
  const open = cases.filter((c) => c.verdict === 'progress' || c.verdict === 'awaiting');
  const closed = cases.filter((c) => c.verdictLog);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <TopBar title="Cases" subtitle="Open problems racing toward a verdict." theme={theme} onToggleTheme={onToggleTheme}
        right={<button className="btn btn-crux" onClick={onNew}><i className="ti ti-plus" aria-hidden="true"></i> New case</button>} />
      <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-6)' }}>
        <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 'var(--space-3)' }}>OPEN · {open.length}</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', marginBottom: 'var(--space-6)' }}>
          {open.map((c) => <CaseCard key={c.id} {...c} onClick={() => onOpen(c.id)} />)}
        </div>
        <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 'var(--space-3)' }}>CLOSED · {closed.length}</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          {closed.map((c) => <CaseCard key={c.id} {...c} onClick={() => onOpen(c.id)} />)}
        </div>
      </div>
    </div>
  );
}

function SectionLabel({ children, n }) {
  return <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', margin: '0 0 var(--space-3)' }}>{children}{n != null ? ` · ${n}` : ''}</div>;
}

function CaseScreen({ caseId, onBack, onLogVerdict, theme, onToggleTheme }) {
  const { StageBar, PlanCard, ProbeCard, LockedPlan, Pill, Button } = window.CruxDesignSystem_bd6ca7;
  const c = window.CRUX_DATA.cases.find((x) => x.id === caseId);
  const leadKey = (c.plans.find((p) => p.state === 'leading' || p.state === 'won') || {}).key;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <header style={{ padding: 'var(--space-4) var(--space-6)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-4)' }}>
        <button className="btn btn-sm" onClick={onBack}><i className="ti ti-arrow-left" aria-hidden="true"></i> Cases</button>
        <span className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)', fontWeight: 700 }}>{c.id}</span>
        <button className="btn btn-sm" onClick={onToggleTheme} aria-label="Toggle theme" style={{ padding: '7px 9px' }}><i className={`ti ti-${theme === 'dark' ? 'sun' : 'moon'}`} aria-hidden="true"></i></button>
      </header>

      <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-6)', maxWidth: 820, width: '100%', margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--space-4)', marginBottom: 'var(--space-5)' }}>
          <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: '-.01em', lineHeight: 1.25, color: 'var(--text)', textWrap: 'pretty' }}>{c.title}</h1>
          <Pill state={c.verdict} />
        </div>

        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 'var(--space-5)', marginBottom: 'var(--space-6)' }}>
          <StageBar current={c.stage} />
        </div>

        <SectionLabel>SHARPENED PROBLEM</SectionLabel>
        <p style={{ fontSize: 'var(--text-lg)', color: 'var(--text)', lineHeight: 1.55, marginBottom: 'var(--space-3)' }}>{c.sharpened}</p>
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', marginBottom: 'var(--space-6)' }}>
          <span className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)', fontWeight: 700, alignSelf: 'center' }}>NOT INVESTIGATING:</span>
          {c.notInvestigating.map((x) => <span key={x} className="src" style={{ textDecoration: 'line-through' }}>{x}</span>)}
        </div>

        <SectionLabel n={c.plans.length}>BAKE-OFF · COMPETING PLANS</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', marginBottom: 'var(--space-6)' }}>
          {c.plans.map((p) => <PlanCard key={p.key} planKey={p.key} name={p.name} prior={p.prior} mechanism={p.mechanism} sources={p.sources} lead={p.key === leadKey} />)}
        </div>

        <SectionLabel>THE PROBE · CHEAPEST DECISIVE TEST</SectionLabel>
        <div style={{ marginBottom: 'var(--space-6)' }}>
          <ProbeCard {...c.probe} onSendToCommander={() => alert('commander spec copied to clipboard')} />
        </div>

        <SectionLabel>ACTION PLAN</SectionLabel>
        {c.verdictLog ? (
          <LockedPlan unlocked>
            <PlanCard planKey={c.actionPlan.planKey} name={c.actionPlan.name} mechanism={c.actionPlan.mechanism} />
          </LockedPlan>
        ) : (
          <div>
            <LockedPlan />
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 'var(--space-4)' }}>
              <Button variant="crux" icon="gavel" onClick={() => onLogVerdict(c.id)}>Log verdict</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function VerdictScreen({ onOpen, theme, onToggleTheme }) {
  const { Pill } = window.CruxDesignSystem_bd6ca7;
  const log = window.CRUX_DATA.cases.filter((c) => c.verdictLog);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <TopBar title="Verdicts" subtitle="Confirmed causes and killed hypotheses — your personal knowledge base." theme={theme} onToggleTheme={onToggleTheme} />
      <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-6)' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          {log.map((c) => (
            <button key={c.id} onClick={() => onOpen(c.id)} style={{ textAlign: 'left', cursor: 'pointer', display: 'flex', gap: 'var(--space-4)', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 'var(--space-4)', boxShadow: 'var(--shadow-card)' }}>
              <div style={{ flex: 'none', width: 110 }}>
                <Pill state={c.verdict} />
                <div className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)', marginTop: 8 }}>{c.id}<br/>{c.verdictLog.decidedAt}</div>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>{c.title}</div>
                <p style={{ fontSize: 'var(--text-base)', color: 'var(--text-muted)', lineHeight: 1.5 }}>{c.verdictLog.notes}</p>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function NewCaseModal({ onClose, onCreate }) {
  const { Input, Button } = window.CruxDesignSystem_bd6ca7;
  const [step, setStep] = React.useState(0);
  const [raw, setRaw] = React.useState('');
  const sharpened = 'Aerobic pace regressed ~20s/km over 14 weeks at stable mileage — find the single dominant cause before changing training.';
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 'var(--space-5)', zIndex: 50 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 560, maxWidth: '100%', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-card)', padding: 'var(--space-6)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-4)' }}>
          <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 800, color: 'var(--text)' }}>New case</h2>
          <button className="btn btn-sm" onClick={onClose} aria-label="Close" style={{ padding: '6px 8px' }}><i className="ti ti-x" aria-hidden="true"></i></button>
        </div>

        {step === 0 ? (
          <div>
            <Input label="Paste the messy problem" multiline value={raw} onChange={(e) => setRaw(e.target.value)}
              placeholder="Dump everything you know — symptoms, timeline, what you've tried…" />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)', marginTop: 'var(--space-5)' }}>
              <Button onClick={onClose}>Cancel</Button>
              <Button variant="crux" iconRight="arrow-right" onClick={() => setStep(1)}>Sharpen</Button>
            </div>
          </div>
        ) : (
          <div>
            <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--crux)', marginBottom: 'var(--space-2)' }}>SHARPENED STATEMENT</div>
            <div style={{ background: 'var(--crux-tint)', border: '1px solid var(--crux)', borderRadius: 'var(--radius)', padding: 'var(--space-4)', fontSize: 'var(--text-lg)', color: 'var(--text)', lineHeight: 1.5, marginBottom: 'var(--space-4)' }}>{sharpened}</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-2)' }}>
              <Button onClick={() => setStep(0)}><i className="ti ti-arrow-left" aria-hidden="true"></i> Edit</Button>
              <Button variant="crux" icon="check" onClick={onCreate}>Create case</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { TopBar, CasesScreen, CaseScreen, VerdictScreen, NewCaseModal });
