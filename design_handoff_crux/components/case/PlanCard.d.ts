import React from 'react';

export interface PlanSource {
  kind: 'book' | 'article' | 'youtube';
  label: string;
  href?: string;
}

export interface PlanCardProps {
  /** A / B / C */
  planKey?: string;
  name: string;
  /** Prior probability, e.g. 0.62 — shown as a mono chip. */
  prior?: number;
  /** One-line root-cause mechanism. */
  mechanism?: string;
  sources?: PlanSource[];
  /** The leading plan — violet border + tint wash. */
  lead?: boolean;
  style?: React.CSSProperties;
}

/**
 * A competing root-cause bet in the detail view: mono key, name, prior
 * chip, mechanism, and one source chip per real citation. The leader is
 * marked with the violet wash.
 *
 * @startingPoint section="Case" subtitle="Plan A/B/C with prior & sources" viewport="700x220"
 */
export function PlanCard(props: PlanCardProps): JSX.Element;
