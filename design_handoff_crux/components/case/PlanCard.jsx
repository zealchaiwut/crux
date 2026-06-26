import React from 'react';
import { SourceChip } from '../core/SourceChip.jsx';

/**
 * Plan card (detail view). A competing root-cause bet: mono A/B/C key +
 * name + prior chip + one-line mechanism + source chips. The leading plan
 * gets the violet border + tint wash.
 *
 * sources: [{ kind, label, href }]
 */
export function PlanCard({ planKey = 'A', name, prior, mechanism, sources = [], lead = false, style }) {
  return (
    <div
      style={{
        background: lead ? 'var(--crux-tint)' : 'var(--surface)',
        border: `1px solid ${lead ? 'var(--crux)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)',
        padding: 'var(--space-4)',
        display: 'flex', gap: 'var(--space-3)',
        ...style,
      }}
    >
      <div
        className="mono"
        style={{
          width: 30, height: 30, flex: 'none', borderRadius: 'var(--radius-sm)',
          background: lead ? 'var(--crux)' : 'var(--surface-2)',
          color: lead ? '#fff' : 'var(--text-muted)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontWeight: 700, fontSize: 'var(--text-md)',
        }}
      >
        {planKey}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <span style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--text)' }}>{name}</span>
          {prior != null && (
            <span className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: lead ? 'var(--crux)' : 'var(--text-muted)', background: lead ? 'var(--crux-bg)' : 'var(--surface-2)', padding: '2px 7px', borderRadius: 'var(--radius-pill)' }}>
              prior {prior}
            </span>
          )}
        </div>
        {mechanism && <p style={{ fontSize: 'var(--text-base)', color: 'var(--text-muted)', marginTop: 4, lineHeight: 1.5 }}>{mechanism}</p>}
        {sources.length > 0 && (
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', marginTop: 'var(--space-3)' }}>
            {sources.map((s, i) => (
              <SourceChip key={i} kind={s.kind} href={s.href}>{s.label}</SourceChip>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
