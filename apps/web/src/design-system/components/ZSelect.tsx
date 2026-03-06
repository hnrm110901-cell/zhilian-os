import React, { useState, useRef, useEffect } from 'react';
import styles from './ZSelect.module.css';

export interface SelectOption {
  value: string | number;
  label: string;
  icon?: React.ReactNode;
}

interface ZSelectProps {
  options:      SelectOption[];
  value?:       string | number | null;
  onChange?:    (value: string | number) => void;
  placeholder?: string;
  style?:       React.CSSProperties;
}

export default function ZSelect({ options, value, onChange, placeholder = '请选择', style }: ZSelectProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const selected = options.find(o => o.value === value);

  return (
    <div ref={wrapRef} className={styles.wrap} style={style}>
      <button
        type="button"
        className={`${styles.trigger} ${open ? styles.open : ''}`}
        onClick={() => setOpen(v => !v)}
      >
        {selected ? (
          <span>{selected.icon && <>{selected.icon} </>}{selected.label}</span>
        ) : (
          <span className={styles.placeholder}>{placeholder}</span>
        )}
      </button>
      <span className={`${styles.arrow} ${open ? styles.open : ''}`}>▼</span>

      {open && (
        <div className={styles.dropdown}>
          {options.map(opt => (
            <div
              key={opt.value}
              className={`${styles.option} ${opt.value === value ? styles.selected : ''}`}
              onClick={() => { onChange?.(opt.value); setOpen(false); }}
            >
              {opt.icon && opt.icon}
              {opt.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
