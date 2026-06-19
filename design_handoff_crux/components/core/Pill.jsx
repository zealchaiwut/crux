import React from 'react';

/**
 * Verdict / status pill. The mono "data register" badge for state.
 * state: confirmed | killed | inconclusive | awaiting | progress
 */
export function Pill({ state = 'awaiting', children, style, ...rest }) {
  const label = children ?? {
    confirmed: 'confirmed',
    killed: 'killed',
    inconclusive: 'inconclusive',
    awaiting: 'awaiting',
    progress: 'in progress',
  }[state];

  return (
    <span className={`pill ${state}`} style={style} {...rest}>
      {label}
    </span>
  );
}
