import React from 'react';

export interface BakeOffPlan {
  /** A / B / C */
  key: string;
  name: string;
  /** Current standing 0..1 — drives bar width. */
  standing: number;
  /** leading=violet fill · ruled-out=50% + strikethrough · won=✓ WON tag */
  state?: 'leading' | 'ruled-out' | 'won';
}

export interface BakeOffStripProps {
  plans: BakeOffPlan[];
  style?: React.CSSProperties;
}

/**
 * THE signature element. Competing Plans as racing bars — one glance tells
 * the whole state of a case. The leader fills violet; losers stay neutral;
 * ruled-out plans fade and strike through; a winner is tagged ✓ WON.
 * Always present on a case card and atop the detail bake-off.
 *
 * @startingPoint section="Case" subtitle="Signature — competing plans race" viewport="700x180"
 */
export function BakeOffStrip(props: BakeOffStripProps): JSX.Element;
