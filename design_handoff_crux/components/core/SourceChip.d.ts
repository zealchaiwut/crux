import React from 'react';

export interface SourceChipProps {
  /** book=amber · article=blue · youtube=red */
  kind?: 'book' | 'article' | 'youtube';
  /** The citation label (title / author / short ref). */
  children?: React.ReactNode;
  /** Makes the chip a link to the source. */
  href?: string;
  style?: React.CSSProperties;
}

/**
 * A single cited source attached to a Plan's evidence. One chip per real
 * citation — the colored icon encodes the source kind.
 */
export function SourceChip(props: SourceChipProps): JSX.Element;
