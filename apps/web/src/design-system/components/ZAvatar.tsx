import React from 'react';
import styles from './ZAvatar.module.css';

type AvatarSize = 'sm' | 'md' | 'lg' | 'xl';
type AvatarColor = 'mint' | 'blue' | 'green' | 'purple' | 'red';

interface ZAvatarProps {
  src?: string;
  name?: string;
  size?: AvatarSize;
  color?: AvatarColor;
  style?: React.CSSProperties;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2);
}

export default function ZAvatar({ src, name, size = 'md', color = 'mint', style }: ZAvatarProps) {
  return (
    <div
      className={`${styles.avatar} ${styles[size]} ${src ? '' : styles[color]}`}
      style={style}
      title={name}
    >
      {src ? <img src={src} alt={name ?? ''} /> : (name ? initials(name) : '?')}
    </div>
  );
}
