import React from 'react';

/**
 * Surface container. The neutral box everything sits in. `lead` gives it
 * the violet border + tint wash used to mark the leading plan / focus.
 */
export function Card({ children, lead = false, hover = false, padding = 16, style, ...rest }) {
  const [h, setH] = React.useState(false);
  return (
    <div
      onMouseEnter={() => hover && setH(true)}
      onMouseLeave={() => hover && setH(false)}
      style={{
        background: lead ? 'var(--crux-tint)' : 'var(--surface)',
        border: `1px solid ${lead || h ? 'var(--crux)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)',
        padding,
        boxShadow: h ? 'var(--shadow-hover)' : 'var(--shadow-card)',
        transition: 'box-shadow var(--speed), border-color var(--speed)',
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}
