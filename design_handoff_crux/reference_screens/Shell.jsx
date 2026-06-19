/* crux UI kit — app shell: brand wordmark, sidebar, right rail. */

function Wordmark({ size = 18 }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 1, fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: size, letterSpacing: '.02em', color: 'var(--text)' }}>
      <span>crux</span>
      <span style={{ width: size * 0.28, height: size * 0.28, borderRadius: '50%', background: 'var(--crux)', display: 'inline-block', marginLeft: 3, transform: 'translateY(-1px)' }}></span>
    </div>
  );
}

function NavItem({ icon, label, count, active, onClick }) {
  const [h, setH] = React.useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setH(true)} onMouseLeave={() => setH(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 10, width: '100%', textAlign: 'left',
        padding: '8px 10px', borderRadius: 'var(--radius-sm)', border: 'none', cursor: 'pointer',
        background: active ? 'var(--crux-bg)' : h ? 'var(--surface-hover)' : 'transparent',
        color: active ? 'var(--crux)' : 'var(--text)', fontSize: 'var(--text-base)', fontWeight: active ? 600 : 500,
        transition: 'background var(--speed)',
      }}
    >
      <i className={`ti ti-${icon}`} style={{ fontSize: 17, color: active ? 'var(--crux)' : 'var(--text-muted)' }} aria-hidden="true"></i>
      <span style={{ flex: 1 }}>{label}</span>
      {count != null && <span className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: active ? 'var(--crux)' : 'var(--text-sub)' }}>{count}</span>}
    </button>
  );
}

function Sidebar({ route, setRoute, counts }) {
  const { projects } = window.CRUX_DATA;
  return (
    <aside style={{ width: 208, flex: 'none', background: 'var(--surface)', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', padding: 'var(--space-4)', height: '100%' }}>
      <div style={{ padding: '4px 6px var(--space-5)' }}><Wordmark /></div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <NavItem icon="folder" label="Cases" count={counts.cases} active={route === 'cases' || route === 'case'} onClick={() => setRoute('cases')} />
        <NavItem icon="flask" label="Probes" count={counts.probes} active={route === 'probes'} onClick={() => setRoute('cases')} />
        <NavItem icon="gavel" label="Verdicts" count={counts.verdicts} active={route === 'verdicts'} onClick={() => setRoute('verdicts')} />
      </div>

      <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', margin: 'var(--space-5) 6px var(--space-2)' }}>PROJECTS</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {projects.map((p) => (
          <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '6px 10px', borderRadius: 'var(--radius-sm)', background: p.active ? 'var(--surface-2)' : 'transparent' }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: p.accent }}></span>
            <span style={{ fontSize: 'var(--text-base)', color: p.active ? 'var(--text)' : 'var(--text-muted)', fontWeight: p.active ? 600 : 400 }}>{p.name}</span>
          </div>
        ))}
      </div>

      <div style={{ flex: 1 }}></div>
      <div className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)', padding: '0 6px', lineHeight: 1.7 }}>
        single-user · render<br/>crux v1 · M1
      </div>
    </aside>
  );
}

function RailPromptCard({ onNew }) {
  return (
    <div style={{ background: 'var(--crux-tint)', border: '1px solid var(--crux)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-4)' }}>
      <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>Got a problem worth solving?</div>
      <div style={{ fontSize: 'var(--text-base)', color: 'var(--text-muted)', lineHeight: 1.5, marginBottom: 'var(--space-3)' }}>Paste the messy version. crux sharpens it into a falsifiable bake-off.</div>
      <button className="btn btn-crux" style={{ width: '100%', justifyContent: 'center' }} onClick={onNew}>
        <i className="ti ti-plus" aria-hidden="true"></i> New case
      </button>
    </div>
  );
}

function RailSection({ title, children }) {
  return (
    <div>
      <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 'var(--space-2)' }}>{title}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>{children}</div>
    </div>
  );
}

function RightRail({ onNew, onOpen }) {
  const { cases } = window.CRUX_DATA;
  const running = cases.filter((c) => c.probe && c.probe.status === 'running');
  const recent = cases.filter((c) => c.verdictLog);
  return (
    <aside style={{ width: 288, flex: 'none', borderLeft: '1px solid var(--border)', padding: 'var(--space-4)', display: 'flex', flexDirection: 'column', gap: 'var(--space-5)', overflowY: 'auto' }}>
      <RailPromptCard onNew={onNew} />

      <RailSection title="PROBES RUNNING">
        {running.length === 0 && <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-sub)' }}>None running.</div>}
        {running.map((c) => (
          <button key={c.id} onClick={() => onOpen(c.id)} style={{ textAlign: 'left', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: 'var(--space-3)', cursor: 'pointer' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <i className="ti ti-loader-2 crux-spin" style={{ fontSize: 13, color: 'var(--blue)' }} aria-hidden="true"></i>
              <span className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--blue)' }}>{c.probe.type}</span>
            </div>
            <div className="mono" style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text)' }}>{c.probe.targetMetric}</div>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)', marginTop: 2 }}>{c.id} · due {c.probe.time}</div>
          </button>
        ))}
      </RailSection>

      <RailSection title="RECENT VERDICTS">
        {recent.map((c) => (
          <button key={c.id} onClick={() => onOpen(c.id)} style={{ textAlign: 'left', background: 'transparent', border: 'none', cursor: 'pointer', display: 'flex', gap: 9, padding: '2px 0' }}>
            <span className={`pill ${c.verdict}`} style={{ marginTop: 1 }}></span>
            <span style={{ flex: 1 }}>
              <span style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text)', lineHeight: 1.4 }}>{c.title}</span>
              <span className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)' }}>{c.id} · {c.verdictLog.decidedAt}</span>
            </span>
          </button>
        ))}
      </RailSection>
    </aside>
  );
}

Object.assign(window, { Wordmark, Sidebar, RightRail, NavItem });
