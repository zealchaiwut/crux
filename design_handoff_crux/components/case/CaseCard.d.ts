import React from 'react';
import { BakeOffPlan } from './BakeOffStrip';

export interface CaseCardProps {
  /** Mono case ID, e.g. "CASE-0148". */
  id: string;
  /** The sharpened problem statement. */
  title: string;
  /** Current pipeline stage, 0–4. */
  stage?: number;
  /** Verdict / status — drives the spine color and pill. */
  verdict?: 'confirmed' | 'killed' | 'inconclusive' | 'awaiting' | 'progress';
  /** The racing plans (see BakeOffStrip). */
  plans?: BakeOffPlan[];
  onClick?: () => void;
  style?: React.CSSProperties;
}

/**
 * The primary row in the Cases list: a stage spine (mono stage + 5-pip
 * position + ID) beside a body (sharpened title, verdict pill, bake-off
 * race strip). A closed case tints its spine with the verdict color.
 *
 * @startingPoint section="Case" subtitle="The Cases-list row" viewport="700x180"
 */
export function CaseCard(props: CaseCardProps): JSX.Element;
