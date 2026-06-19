import React from 'react';
import { Pill } from '../core/Pill.jsx';
import { BakeOffStrip } from './BakeOffStrip.jsx';

const STAGE_NAMES = ['Sharpen', 'Bake-off', 'Gather', 'Weigh', 'Probe'];

/**
 * Case card — a row split into a left stage spine + body. The spine shows
 * the mono stage name, a 5-segment pip row (done/now), and mono meta. On a
 * closed case the spine tints with the verdict color. The body holds the
 * case title, verdict pill, and the bake-off race strip.
 *
 * plans: see BakeOffStrip. verdict: confirmed|killed|inconclusive|awaiting|progress
 */
export function CaseCard({ id, title, stage = 0, verdict = 'awaiting', plans = [], onClick, style }) {
  const closed = verdict === 'confirmed' || verdict === 'killed' || verdict === 'inconclusive';
  const spineColor = verdict === 'confirmed' ? 'var(--green)' : verdict === 'killed' ? 'var(--red)' : verdict === 'inconclusive' ? 'var(--amber)' : 'var(--crux)';
  const spineBg = verdict === 'confirmed' ? 'var(--green-bg)' : verdict === 'killed' ? 'var(--red-bg)' : verdict === 'inconclusive' ? 'var(--amber-bg)' : 'var(--surface-2)';
  const [h, setH] = React.useState(false);

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        display: 'flex', background: 'var(--surface)',
        border: `1px solid ${h ? 'var(--crux)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)', overflow: 'hidden', cursor: onClick ? 'pointer' : 'default',
        boxShadow: h ? 'var(--shadow-hover)' : 'var(--shadow-card)',
        transition: 'box-shadow var(--speed), border-color var(--speed)',
        ...style,
      }}
    >
      {/* Stage spine */}
      <div style={{ width: 118, flex: 'none', background: spineBg, borderRight: '1px solid var(--border)', padding: 'var(--space-3)', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
        <div className="mono" style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: closed ? spineColor : 'var(--crux)' }}>
          {closed ? 'CLOSED' : `STAGE ${stage}`}
        </div>
        <div className="mono" style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text)', margin: '6px 0 10px' }}>
          {STAGE_NAMES[Math.min(stage, 4)]}
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {STAGE_NAMES.map((_, i) => {
            const done = closed || i < stage;
            const now = !closed && i === stage;
            return (
              <div key={i} style={{ flex: 1, height: 5, borderRadius: 3, background: done ? spineColor : now ? 'var(--crux)' : 'var(--border)' }}></div>
            );
          })}
        </div>
        <div className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-sub)', marginTop: 10 }}>{id}</div>
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
