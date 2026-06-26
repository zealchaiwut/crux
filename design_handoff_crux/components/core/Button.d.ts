import React from 'react';

export interface ButtonProps {
  children?: React.ReactNode;
  /** `crux` = the violet primary action; `default` = neutral. */
  variant?: 'default' | 'crux';
  size?: 'md' | 'sm';
  /** Tabler icon name without the `ti-` prefix, e.g. "plus". */
  icon?: string;
  /** Trailing Tabler icon, e.g. "arrow-right". */
  iconRight?: string;
  type?: 'button' | 'submit' | 'reset';
  disabled?: boolean;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  style?: React.CSSProperties;
}

/**
 * The crux button. Reserve `variant="crux"` for the single primary action
 * on a screen; everything else stays neutral.
 *
 * @startingPoint section="Core" subtitle="Buttons — neutral & violet primary" viewport="700x150"
 */
export function Button(props: ButtonProps): JSX.Element;
