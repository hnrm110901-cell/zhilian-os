import React from 'react';
import styles from './QuoteBlock.module.css';

interface QuoteBlockProps {
  children: React.ReactNode;
  style?: React.CSSProperties;
}

export default function QuoteBlock({ children, style }: QuoteBlockProps) {
  return <div className={styles.quote} style={style}>{children}</div>;
}
