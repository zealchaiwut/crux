import React from 'react';

/**
 * crux Button — neutral by default; `variant="crux"` spends the violet
 * signature on the one primary action. Optional Tabler icon name.
 */
export function Button({
  children,
  variant = 'default',
  size = 'md',
  icon,
  iconRight,
  type = 'button',
  disabled = false,
  onClick,
  style,
  ...rest
}) {
  const cls = [
    'btn',
    variant === 'crux' ? 'btn-crux' : '',
    size === 'sm' ? 'btn-sm' : '',
  ].filter(Boolean).join(' ');

  return (
    <button
      type={type}
      className={cls}
      disabled={disabled}
      onClick={onClick}
      style={{ opacity: disabled ? 0.5 : 1, cursor: disabled ? 'not-allowed' : 'pointer', ...style }}
      {...rest}
    >
      {icon && <i className={`ti ti-${icon}`} style={{ fontSize: '1.05em' }} aria-hidden="true"></i>}
      {children}
      {iconRight && <i className={`ti ti-${iconRight}`} style={{ fontSize: '1.05em' }} aria-hidden="true"></i>}
    </button>
  );
}
