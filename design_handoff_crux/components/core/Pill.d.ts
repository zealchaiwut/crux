import React from 'react';

export interface PillProps {
  /** confirmed=green · killed=red · inconclusive=amber · awaiting=neutral · progress=blue */
  state?: 'confirmed' | 'killed' | 'inconclusive' | 'awaiting' | 'progress';
  /** Override the default label text for the state. */
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

/**
 * The verdict / status pill — the one consistent way crux shows the state
 * of a Case or Probe. Mono, dot-prefixed, color paired with a word so it
 * survives colorblind viewing.
 *
 * @startingPoint section="Core" subtitle="Verdict & status pills" viewport="700x120"
 */
export function Pill(props: PillProps): JSX.Element;
