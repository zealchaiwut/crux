import React from 'react';
import { Button } from '../core/Button.jsx';
import { Pill } from '../core/Pill.jsx';

const TYPE_LABEL = {
  measurement: 'measurement',
  'lab-test': 'lab-test',
  'behaviour-experiment': 'behaviour-experiment',
  prototype: 'prototype',
};

/**
 * Probe card — the cheapest decisive test for the leading plan(s). A type
 * chip, a big mono target metric, and a foot line (cost / time). Prototype
 * probes offer "Send to commander"; non-app probes say so plainly.
 */
export function ProbeCard({
  type = 'measurement',
  targetMetric,
  status = 'designed',
  cost,
  time,
  note,
  onSendToCommander,
  style,
}) {
  const statePill = { designed: 'awaiting', running: 'progress', confirmed: 'confirmed', killed: 'killed' }[status];
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 'var(--space-4)', boxShadow: 'var(--shadow-card)', ...style }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-2)' }}>
        <span className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--crux)', background: 'var(--crux-bg)', padding: '3px 9px', borderRadius: 'var(--radius-pill)' }}>
          {TYPE_LABEL[type]}
        </span>
        <Pill state={statePill}>{status === 'designed' ? 'designed' : undefined}</Pill>
      </div>

      <div style={{ margin: 'var(--space-4) 0 var(--space-2)' }}>
        <div className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)', fontWeight: 700, marginBottom: 4 }}>TARGET METRIC</div>
        <div className="mono" style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: 'var(--text)' }}>{targetMetric}</div>
      </div>

      {note && <p style={{ fontSize: 'var(--text-base)', color: 'var(--text-muted)', lineHeight: 1.5, marginBottom: 'var(--space-3)' }}>{note}</p>}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)', borderTop: '1px solid var(--border)', paddingTop: 'var(--space-3)' }}>
        <div className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-muted)', display: 'flex', gap: 'var(--space-4)' }}>
          {cost && <span><i className="ti ti-coin" aria-hidden="true"></i> {cost}</span>}
          {time && <span><i className="ti ti-clock" aria-hidden="true"></i> {time}</span>}
        </div>
        {type === 'prototype' && (
          <Button size="sm" variant="crux" iconRight="arrow-right" onClick={onSendToCommander}>Send to commander</Button>
        )}
      </div>
    </div>
  );
}
