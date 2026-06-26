import React from 'react';

/**
 * Bake-off race strip (signature). Plans race as horizontal bars; width =
 * current standing. The leader fills violet; others use --st-2; ruled-out
 * plans drop to 50% opacity; a won plan gets a ✓ WON tag.
 *
 * plans: [{ key:'A', name, standing:0..1, state:'leading'|'ruled-out'|'won'|undefined }]
 */
export function BakeOffStrip({ plans = [], style }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, ...style }}>
      {plans.map((p) => {
        const won = p.state === 'won';
        const lead = p.state === 'leading' || won;
        const ruledOut = p.state === 'ruled-out';
        const pct = Math.round((p.standing ?? 0) * 100);
        return (
          <div key={p.key} style={{ display: 'flex', alignItems: 'center', gap: 10, opacity: ruledOut ? 0.5 : 1 }}>
            <span className="mono" style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: lead ? 'var(--crux)' : 'var(--text-muted)', width: 16, flex: 'none' }}>
              {p.key}
            </span>
            <div style={{ flex: 1, height: 22, background: 'var(--surface-2)', borderRadius: 'var(--radius-sm)', overflow: 'hidden', position: 'relative' }}>
              <div style={{ width: `${pct}%`, height: '100%', background: lead ? 'var(--crux)' : 'var(--st-2)', borderRadius: 'var(--radius-sm)', transition: 'width var(--speed)' }}></div>
              <span style={{ position: 'absolute', left: 10, top: 0, height: '100%', display: 'flex', alignItems: 'center', fontSize: 'var(--text-sm)', fontWeight: 600, color: pct > 22 ? '#fff' : 'var(--text)', textDecoration: ruledOut ? 'line-through' : 'none', mixBlendMode: lead && pct > 22 ? 'normal' : 'normal' }}>
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
