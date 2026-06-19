import React from 'react';

export interface CardProps {
  children?: React.ReactNode;
  /** Violet border + tint wash — marks the leading plan / focused item. */
  lead?: boolean;
  /** Enables the violet-tinted hover lift. */
  hover?: boolean;
  /** Inner padding in px. Default 16. */
  padding?: number;
  style?: React.CSSProperties;
}

/**
 * The neutral surface container. Quiet by default; `lead` applies the
 * violet wash crux uses to mark the one thing that matters.
 *
 * @startingPoint section="Core" subtitle="Surface card, default & lead" viewport="700x180"
 */
export function Card(props: CardProps): JSX.Element;
