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

function Sidebar({ route, setRoute, counts, theme, onToggleTheme, onOpenSettings }) {
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
          active={route === 'cases' || route.startsWith('case')} onClick={() => setRoute('cases')} />
        <NavItem icon="flask" label="Probes" count={counts.probes}
          active={route === 'probes'} onClick={() => setRoute('probes')} />
        <NavItem icon="gavel" label="Verdicts" count={counts.verdicts}
          active={route === 'verdicts'} onClick={() => setRoute('verdicts')} />
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            onClick={onOpenSettings}
            title="Settings"
            aria-label="Settings"
            style={{
              background: 'transparent', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
              padding: '4px 8px', cursor: 'pointer', color: 'var(--text-muted)',
              fontSize: 'var(--text-sm)', display: 'flex', alignItems: 'center',
              transition: 'background var(--speed)',
            }}
          >
            <i className="ti ti-settings" aria-hidden="true"></i>
          </button>
          <a href="/logout" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)', textDecoration: 'none' }}>logout</a>
        </div>
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

function SettingsModal({ onClose }) {
  const [data, setData] = React.useState(null);
  const [provider, setProvider] = React.useState('cli');
  const [budget, setBudget] = React.useState('5');
  const [status, setStatus] = React.useState('loading'); // loading | ready | saving | error
  const [error, setError] = React.useState(null);

  function apply(d) {
    setData(d);
    setProvider(d.provider);
    setBudget(String(d.api_usd_budget));
  }

  React.useEffect(() => {
    fetch('/api/settings')
      .then((r) => { if (!r.ok) throw new Error('failed to load settings'); return r.json(); })
      .then((d) => { apply(d); setStatus('ready'); })
      .catch((e) => { setError(String(e.message || e)); setStatus('error'); });
  }, []);

  async function save() {
    setStatus('saving');
    setError(null);
    try {
      const resp = await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ provider, api_usd_budget: parseFloat(budget) || 0 }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail ? JSON.stringify(body.detail) : `save failed (${resp.status})`);
      }
      apply(await resp.json());
      onClose();
    } catch (e) {
      setError(String(e.message || e));
      setStatus('ready');
    }
  }

  async function resetSpend() {
    setError(null);
    try {
      const resp = await fetch('/api/settings/reset-spend', { method: 'POST' });
      if (!resp.ok) throw new Error(`reset failed (${resp.status})`);
      apply(await resp.json());
    } catch (e) {
      setError(String(e.message || e));
    }
  }

  const usd = (n) => `$${(n || 0).toFixed(2)}`;
  const overBudget = data && data.api_usd_remaining <= 0;

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 460, maxWidth: '92vw', background: 'var(--surface)',
          border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-5)', boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-4)' }}>
          <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--text)' }}>Settings</div>
          <button onClick={onClose} aria-label="Close" style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 18 }}>
            <i className="ti ti-x" aria-hidden="true"></i>
          </button>
        </div>

        {status === 'loading' && <div style={{ color: 'var(--text-muted)' }}>Loading…</div>}
        {status === 'error' && <div style={{ color: 'var(--red, #c0392b)' }}>{error}</div>}

        {data && status !== 'loading' && status !== 'error' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            <div>
              <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 'var(--space-2)' }}>
                CLAUDE PROVIDER
              </div>
              <label style={{ display: 'flex', gap: 9, alignItems: 'flex-start', padding: '8px 0', cursor: 'pointer' }}>
                <input type="radio" name="provider" checked={provider === 'cli'} onChange={() => setProvider('cli')} style={{ marginTop: 3 }} />
                <span>
                  <span style={{ fontWeight: 600, color: 'var(--text)' }}>CLI (subscription)</span>
                  <span style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-muted)' }}>
                    Runs <code>claude -p</code>. Unmetered, no API key.
                  </span>
                </span>
              </label>
              <label style={{ display: 'flex', gap: 9, alignItems: 'flex-start', padding: '8px 0', cursor: 'pointer' }}>
                <input type="radio" name="provider" checked={provider === 'api'} onChange={() => setProvider('api')} style={{ marginTop: 3 }} />
                <span>
                  <span style={{ fontWeight: 600, color: 'var(--text)' }}>Anthropic API</span>
                  <span style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-muted)' }}>
                    Uses <code>ANTHROPIC_API_KEY</code> up to the budget, then falls back to CLI.
                    {!data.api_key_present && (
                      <span style={{ color: 'var(--red, #c0392b)' }}> No API key set in .env — API calls will fall back to CLI.</span>
                    )}
                  </span>
                </span>
              </label>
            </div>

            <div style={{ opacity: provider === 'api' ? 1 : 0.55 }}>
              <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 'var(--space-2)' }}>
                API BUDGET (USD)
              </div>
              <input
                type="number" min="0" step="0.5" value={budget}
                onChange={(e) => setBudget(e.target.value)}
                disabled={provider !== 'api'}
                style={{
                  width: 140, padding: '6px 10px', borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border)', background: 'var(--bg)', color: 'var(--text)',
                  fontFamily: 'var(--font-mono)', fontSize: 'var(--text-base)',
                }}
              />
              <div style={{ marginTop: 'var(--space-3)', fontSize: 'var(--text-sm)', color: 'var(--text-muted)', display: 'flex', gap: 16, alignItems: 'center' }}>
                <span>Spent <strong style={{ color: 'var(--text)' }}>{usd(data.api_usd_spent)}</strong></span>
                <span>Remaining <strong style={{ color: overBudget ? 'var(--red, #c0392b)' : 'var(--text)' }}>{usd(data.api_usd_remaining)}</strong></span>
                <button onClick={resetSpend} className="btn" style={{ marginLeft: 'auto', fontSize: 'var(--text-sm)' }}>
                  Reset spend
                </button>
              </div>
              {overBudget && provider === 'api' && (
                <div style={{ marginTop: 'var(--space-2)', fontSize: 'var(--text-sm)', color: 'var(--text-muted)' }}>
                  Budget reached — calls fall back to the CLI until you raise the budget or reset spend.
                </div>
              )}
            </div>

            {error && <div style={{ color: 'var(--red, #c0392b)', fontSize: 'var(--text-sm)' }}>{error}</div>}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
              <button onClick={onClose} className="btn">Cancel</button>
              <button onClick={save} className="btn btn-crux" disabled={status === 'saving'}>
                {status === 'saving' ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Parse the URL hash into a route string ('cases' | 'probes' | 'verdicts' |
// 'case/<id>'). Enables deep-linking / refresh-in-place.
function _routeFromHash() {
  const raw = (window.location.hash || '').replace(/^#\/?/, '').trim();
  if (raw.startsWith('case/') && raw.slice(5)) return raw;
  if (raw === 'probes' || raw === 'verdicts') return raw;
  return 'cases';
}

function App() {
  const [theme, setTheme] = React.useState('light');
  const [showSettings, setShowSettings] = React.useState(false);
  // route is either 'cases' | 'probes' | 'verdicts' | 'case/<id>'
  const [route, setRoute] = React.useState(_routeFromHash);
  const [activeCaseId, setActiveCaseId] = React.useState(null);

  React.useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
  }, [theme]);

  // Keep the URL hash in sync with the route so refresh/deep-link works.
  React.useEffect(() => {
    const target = '#/' + route;
    if (window.location.hash !== target) window.location.hash = target;
  }, [route]);

  // React to browser back/forward and manual hash edits.
  React.useEffect(() => {
    function onHashChange() {
      setRoute(_routeFromHash());
    }
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'));

  function openCase(id) {
    setActiveCaseId(id);
    setRoute(`case/${id}`);
  }
  function goToCases() {
    setActiveCaseId(null);
    setRoute('cases');
  }

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
    main = <VerdictScreen onViewCase={(id) => handleCaseOpened(id)} />;
  } else if (route === 'case' && activeCaseId) {
    main = (
      <CaseDetailScreen
        caseId={activeCaseId}
        onBack={goToCases}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
    );
  } else {
    main = (
      <CasesScreen
        theme={theme}
        onToggleTheme={toggleTheme}
        onCaseCreated={openCase}
      />
    );
  }

  return (
    <div style={{ display: 'flex', height: '100%', background: 'var(--bg)' }}>
      <Sidebar route={route} setRoute={setRoute} counts={counts} theme={theme} onToggleTheme={toggleTheme} onOpenSettings={() => setShowSettings(true)} />
      <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        {main}
      </main>
      {showRail && <RightRail onNew={() => setRoute('cases')} />}
      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
    </div>
  );
}

// Mount — shell.js loads last (after cases.js + verdicts.js), so App and every
// screen component it references are in scope here.
ReactDOM.createRoot(document.getElementById('app')).render(<App />);
