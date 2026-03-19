/**
 * 屯象OS · 阴影/圆角/z-index Token
 * v4 Apple Aesthetics — 更大圆角 + 多层柔和阴影
 */

// ── Border Radius (Apple-style) ──
export const radius = {
  '2xs':  4,
  xs:     6,     // --radius-xs: small tag, badge
  sm:     8,     // --radius-sm: button, input, sidebar item
  md:     12,    // --radius-md: card, table, alert
  lg:     16,    // --radius-lg: modal, drawer, content wrapper
  xl:     20,    // --radius-xl: bottom sheet (mobile), floating panel
  '2xl':  24,
  full:   9999,
} as const;

// ── Elevation Shadows (Apple-style multi-layer) ──
export const shadow = {
  0: 'none',
  1: '0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02)',
  2: '0 4px 12px rgba(0,0,0,0.05), 0 1px 3px rgba(0,0,0,0.03)',
  3: '0 8px 24px rgba(0,0,0,0.06), 0 2px 8px rgba(0,0,0,0.03)',
  4: '0 16px 48px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.04)',
} as const;

// ── Z-index ──
export const zIndex = {
  base:    0,
  raised:  10,
  overlay: 100,
  modal:   200,
  toast:   300,
} as const;

// ── Motion (Apple-style spring) ──
export const motion = {
  fast:   '150ms cubic-bezier(0.22, 1, 0.36, 1)',
  normal: '250ms cubic-bezier(0.22, 1, 0.36, 1)',
  slow:   '400ms cubic-bezier(0.22, 1, 0.36, 1)',
  spring: '300ms cubic-bezier(0.22, 1, 0.36, 1)',
} as const;
