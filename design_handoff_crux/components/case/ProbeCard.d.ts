import React from 'react';

export interface ProbeCardProps {
  /** The four honest probe types. */
  type?: 'measurement' | 'lab-test' | 'behaviour-experiment' | 'prototype';
  /** The single metric that decides the case, in mono. e.g. "VO2 < 48". */
  targetMetric: string;
  status?: 'designed' | 'running' | 'confirmed' | 'killed';
  /** Foot-line cost, e.g. "$40". */
  cost?: string;
  /** Foot-line time, e.g. "2 weeks". */
  time?: string;
  /** Plain-language instruction (e.g. "Order a ferritin panel — see a doctor"). */
  note?: string;
  /** Only meaningful for type="prototype". */
  onSendToCommander?: () => void;
  style?: React.CSSProperties;
}

/**
 * The cheapest decisive test for the leading plan. One type chip, one big
 * mono target metric, a cost/time foot line. Prototype-shaped probes get
 * "Send to commander"; everything else states the real-world action plainly.
 *
 * @startingPoint section="Case" subtitle="The single decisive test" viewport="700x260"
 */
export function ProbeCard(props: ProbeCardProps): JSX.Element;
