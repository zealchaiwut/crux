import React from 'react';

/**
 * Text input / textarea with a label. Focus shows the violet ring.
 */
export function Input({ label, hint, multiline = false, mono = false, style, id, ...rest }) {
  const autoId = React.useId();
  const inputId = id || autoId;
  const Field = multiline ? 'textarea' : 'input';
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {label && (
        <label htmlFor={inputId} style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text)' }}>
          {label}
        </label>
      )}
      <Field
        id={inputId}
        style={{
          font: 'inherit',
          fontFamily: mono ? 'var(--font-mono)' : 'var(--font-sans)',
          fontSize: 'var(--text-base)',
          color: 'var(--text)',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          padding: multiline ? '10px 12px' : '8px 12px',
          minHeight: multiline ? 96 : undefined,
          resize: multiline ? 'vertical' : undefined,
          outline: 'none',
          width: '100%',
          ...style,
        }}
        {...rest}
      />
      {hint && <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)' }}>{hint}</span>}
    </div>
  );
}
