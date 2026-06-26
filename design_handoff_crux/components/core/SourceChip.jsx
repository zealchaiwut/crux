import React from 'react';

const ICON = { book: 'book-2', article: 'file-text', youtube: 'brand-youtube' };

/**
 * Source chip — one per real citation. The colored icon marks the
 * source kind (book=amber, article=blue, youtube=red).
 */
export function SourceChip({ kind = 'article', children, href, style, ...rest }) {
  const Tag = href ? 'a' : 'span';
  return (
    <Tag
      className={`src ${kind}`}
      href={href}
      target={href ? '_blank' : undefined}
      rel={href ? 'noreferrer' : undefined}
      style={{ textDecoration: 'none', ...style }}
      {...rest}
    >
      <i className={`ti ti-${ICON[kind]}`} aria-hidden="true"></i>
      {children}
    </Tag>
  );
}
