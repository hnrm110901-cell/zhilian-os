import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import styles from './ZModal.module.css';

interface ZModalProps {
  open:       boolean;
  title?:     string;
  onClose?:   () => void;
  children?:  React.ReactNode;
  footer?:    React.ReactNode;
  width?:     number | string;
}

export default function ZModal({ open, title, onClose, children, footer, width }: ZModalProps) {
  // Close on ESC
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose?.();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  // Prevent body scroll while open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div
      className={styles.overlay}
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
      role="dialog"
      aria-modal="true"
    >
      <div className={styles.modal} style={width ? { maxWidth: width } : undefined}>
        {(title || onClose) && (
          <div className={styles.header}>
            <span className={styles.title}>{title}</span>
            {onClose && (
              <button className={styles.closeBtn} onClick={onClose} aria-label="关闭">✕</button>
            )}
          </div>
        )}
        <div className={styles.body}>{children}</div>
        {footer && <div className={styles.footer}>{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
