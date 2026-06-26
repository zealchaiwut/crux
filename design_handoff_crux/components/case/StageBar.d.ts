import React from 'react';

export interface StageBarProps {
  /** Active stage index, 0–4. Use 5 (= all done) for a closed case. */
  current?: number;
  /** Override the five stage labels. */
  stages?: string[];
  style?: React.CSSProperties;
}

/**
 * The 5-stage pipeline header (Sharpen → Bake-off → Gather → Weigh → Probe).
 * Done steps fill the violet ramp; the current step is full violet; pending
 * steps are neutral. The horizontal sibling of the case-card stage spine.
 *
 * @startingPoint section="Case" subtitle="5-stage pipeline header" viewport="700x120"
 */
export function StageBar(props: StageBarProps): JSX.Element;
