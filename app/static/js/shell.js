/* crux · app shell components
   Wordmark, NavItem, Sidebar, RightRail — all style via CSS custom properties.
   Adapted from design_handoff_crux/reference_screens/Shell.jsx
*/

function Wordmark({ size = 18 }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'baseline', gap: 1,
      fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: size,
      letterSpacing: '.02em', color: 'var(--text)'
    }}>
      <span>crux</span>
      <span style={{
        width: size * 0.28, height: size * 0.28, borderRadius: '50%',
        background: 'var(--crux)', display: 'inline-block',
        marginLeft: 3, transform: 'translateY(-1px)'
      }}></span>
    </div>
  );
}

function NavItem({ icon, label, count, active, onClick }) {
  const [hovered, setHovered] = React.useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 10, width: '100%', textAlign: 'left',
        padding: 'var(--space-2) 10px', borderRadius: 'var(--radius-sm)', border: 'none', cursor: 'pointer',
        background: active ? 'var(--crux-bg)' : hovered ? 'var(--surface-hover)' : 'transparent',
        color: active ? 'var(--crux)' : 'var(--text)',
        fontSize: 'var(--text-base)', fontWeight: active ? 600 : 500,
        transition: 'background var(--speed)',
      }}
    >
      <i className={`ti ti-${icon}`} style={{ fontSize: 17, color: active ? 'var(--crux)' : 'var(--text-muted)' }} aria-hidden="true"></i>
      <span style={{ flex: 1 }}>{label}</span>
      {count != null && (
        <span className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: active ? 'var(--crux)' : 'var(--text-sub)' }}>
          {count}
        </span>
      )}
    </button>
  );
}

function Sidebar({ route, setRoute, counts, theme, onToggleTheme }) {
  const projects = [
    { id: 'commander', name: 'commander', accent: 'var(--blue)' },
    { id: 'perf-coach', name: 'perf-coach', accent: 'var(--green)' },
    { id: 'crux', name: 'crux', accent: 'var(--crux)', active: true },
  ];
  return (
    <aside style={{
      width: 208, flex: 'none',
      background: 'var(--surface)', borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column', padding: 'var(--space-4)', height: '100%'
    }}>
      <div style={{ padding: '4px 6px var(--space-5)' }}>
        <Wordmark />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <NavItem icon="folder" label="Cases" count={counts.cases}
          active={route === 'cases' || route === 'case'} onClick={() => setRoute('cases')} />
        <NavItem icon="flask" label="Probes" count={counts.probes}
          active={route === 'probes'} onClick={() => setRoute('probes')} />
        <NavItem icon="gavel" label="Verdicts" count={counts.verdicts}
          active={route === 'verdicts'} onClick={() => setRoute('verdicts')} />
      </div>

      <div className="mono" style={{
        fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)',
        margin: 'var(--space-5) 6px var(--space-2)'
      }}>PROJECTS</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {projects.map((p) => (
          <div key={p.id} style={{
            display: 'flex', alignItems: 'center', gap: 9, padding: '6px 10px',
            borderRadius: 'var(--radius-sm)',
            background: p.active ? 'var(--surface-2)' : 'transparent'
          }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: p.accent }}></span>
            <span style={{
              fontSize: 'var(--text-base)',
              color: p.active ? 'var(--text)' : 'var(--text-muted)',
              fontWeight: p.active ? 600 : 400
            }}>{p.name}</span>
          </div>
        ))}
      </div>

      <div style={{ flex: 1 }}></div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 6px', marginBottom: 'var(--space-2)' }}>
        <button
          onClick={onToggleTheme}
          title={theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
          style={{
            background: 'transparent', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
            padding: '4px 8px', cursor: 'pointer', color: 'var(--text-muted)',
            fontSize: 'var(--text-sm)', display: 'flex', alignItems: 'center', gap: 5,
            transition: 'background var(--speed)',
          }}
        >
          <i className={`ti ti-${theme === 'dark' ? 'sun' : 'moon'}`} aria-hidden="true"></i>
        </button>
        <a href="/logout" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)', textDecoration: 'none' }}>logout</a>
      </div>

      <div className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)', padding: '0 6px', lineHeight: 1.7 }}>
        single-user · render<br />crux v1 · M0
      </div>
    </aside>
  );
}

function RailPromptCard({ onNew }) {
  return (
    <div style={{
      background: 'var(--crux-tint)', border: '1px solid var(--crux)',
      borderRadius: 'var(--radius-lg)', padding: 'var(--space-4)'
    }}>
      <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>
        Got a problem worth solving?
      </div>
      <div style={{ fontSize: 'var(--text-base)', color: 'var(--text-muted)', lineHeight: 1.5, marginBottom: 'var(--space-3)' }}>
        Paste the messy version. crux sharpens it into a falsifiable bake-off.
      </div>
      <button className="btn btn-crux" style={{ width: '100%', justifyContent: 'center' }} onClick={onNew}>
        <i className="ti ti-plus" aria-hidden="true"></i> New case
      </button>
    </div>
  );
}

function RailSection({ title, children }) {
  return (
    <div>
      <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 'var(--space-2)' }}>
        {title}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        {children}
      </div>
    </div>
  );
}

function RightRail({ onNew }) {
  return (
    <aside style={{
      width: 288, flex: 'none', borderLeft: '1px solid var(--border)',
      padding: 'var(--space-4)', display: 'flex', flexDirection: 'column',
      gap: 'var(--space-5)', overflowY: 'auto'
    }}>
      <RailPromptCard onNew={onNew} />
      <RailSection title="PROBES RUNNING">
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-sub)' }}>None running.</div>
      </RailSection>
      <RailSection title="RECENT VERDICTS">
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-sub)' }}>No verdicts yet.</div>
      </RailSection>
    </aside>
  );
}

function PlaceholderScreen({ title }) {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 'var(--text-xl)', fontWeight: 600, color: 'var(--text)', marginBottom: 'var(--space-2)' }}>{title}</div>
        <div style={{ fontSize: 'var(--text-base)', color: 'var(--text-muted)' }}>Coming in M1.</div>
      </div>
    </div>
  );
}

function App() {
  const [theme, setTheme] = React.useState('light');
  // route is either 'cases' | 'probes' | 'verdicts' | 'case/<id>'
  const [route, setRoute] = React.useState('cases');

  React.useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
  }, [theme]);

  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'));

  const counts = { cases: 0, probes: 0, verdicts: 0 };

  const isCaseDetail = route.startsWith('case/');
  const showRail = !isCaseDetail;

  function handleCaseOpened(id) {
    setRoute(`case/${id}`);
  }

  let main;
  if (isCaseDetail) {
    const caseId = route.slice('case/'.length);
    main = (
      <CaseDetailScreen
        caseId={caseId}
        onBack={() => setRoute('cases')}
        onNavigateToCase={handleCaseOpened}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
    );
  } else if (route === 'probes') {
    main = <PlaceholderScreen title="Probes" />;
  } else if (route === 'verdicts') {
    main = <PlaceholderScreen title="Verdicts" />;
  } else {
    main = (
      <CasesScreen
        theme={theme}
        onToggleTheme={toggleTheme}
        onCaseCreated={handleCaseOpened}
      />
    );
  }

  return (
    <div style={{ display: 'flex', height: '100%', background: 'var(--bg)' }}>
      <Sidebar route={route} setRoute={setRoute} counts={counts} theme={theme} onToggleTheme={toggleTheme} />
      <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        {main}
      </main>
      {showRail && <RightRail onNew={() => setRoute('cases')} />}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('app')).render(<App />);
