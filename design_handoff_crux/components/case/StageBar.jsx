import React from 'react';

const STAGES = ['Sharpen', 'Bake-off', 'Gather', 'Weigh', 'Probe'];

/**
 * Stage bar — the horizontal 5-step pipeline header. `current` (0–4) is
 * the active stage; earlier steps are done, later steps are pending.
 * Set `current={5}` once a verdict closes the case (all done).
 */
export function StageBar({ current = 0, stages = STAGES, style }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', ...style }}>
      {stages.map((name, i) => {
        const done = i < current;
        const now = i === current;
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
                {done ? <i className="ti ti-check" aria-hidden="true"></i> : i + 1}
              </div>
              <span
                className="mono"
                style={{
                  fontSize: 'var(--text-2xs)', fontWeight: 700,
                  color: now ? 'var(--crux)' : done ? 'var(--text)' : 'var(--text-sub)',
                  whiteSpace: 'nowrap',
                }}
              >
                {name}
              </span>
            </div>
            {i < stages.length - 1 && (
              <div style={{ flex: 1, height: 2, margin: '0 8px', marginBottom: 22, background: i < current ? 'var(--st-3)' : 'var(--border)' }}></div>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}
