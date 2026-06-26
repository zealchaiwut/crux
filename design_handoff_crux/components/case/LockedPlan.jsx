import React from 'react';

/**
 * Locked action plan (signature B). The action plan stays behind a hatched,
 * lock-iconed panel until a Verdict is logged — "crux researches; you test."
 * When `unlocked`, it renders its children (the revealed plan) instead.
 */
export function LockedPlan({ unlocked = false, children, style }) {
  if (unlocked) {
    return (
      <div style={{ border: '1px solid var(--green)', background: 'var(--green-bg)', borderRadius: 'var(--radius)', padding: 'var(--space-4)', ...style }}>
        <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--green)', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 'var(--space-3)' }}>
          <i className="ti ti-lock-open" aria-hidden="true"></i> ACTION PLAN UNLOCKED
        </div>
        {children}
      </div>
    );
  }
  return (
    <div
      style={{
        position: 'relative', borderRadius: 'var(--radius)',
        border: '1px dashed var(--border)',
        backgroundColor: 'var(--surface-2)',
        backgroundImage: 'repeating-linear-gradient(45deg, transparent, transparent 9px, var(--border) 9px, var(--border) 10px)',
        padding: 'var(--space-6)',
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        textAlign: 'center', gap: 'var(--space-2)', minHeight: 120,
        ...style,
      }}
    >
      <i className="ti ti-lock" style={{ fontSize: 22, color: 'var(--text-sub)' }} aria-hidden="true"></i>
      <div style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--text-muted)' }}>Action plan locked</div>
      <div className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)' }}>Locked until you log a verdict.</div>
    </div>
  );
}
