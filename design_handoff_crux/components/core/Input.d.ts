import React from 'react';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  /** Render a multi-line textarea (e.g. the paste-a-problem box). */
  multiline?: boolean;
  /** Use the mono data register (for IDs, metrics, pasted numbers). */
  mono?: boolean;
}

/**
 * Labelled text field / textarea. Focus shows the violet ring. Use
 * `multiline` for the New Case paste box, `mono` for numeric data entry.
 */
export function Input(props: InputProps): JSX.Element;
