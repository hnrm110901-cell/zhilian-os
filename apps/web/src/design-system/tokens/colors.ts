/**
 * 屯象OS · 色彩Token
 * 品牌色: Mint薄荷 #0AAF9A
 */

// ── Mint 品牌主色阶 ──
export const mint = {
  50:  '#EDFCF9',
  100: '#CBFAF2',
  200: '#9CF4E5',
  300: '#5FE8D4',
  400: '#2DD4BC',
  500: '#0AAF9A',  // Primary
  600: '#088F7A',
  700: '#066E5D',
  800: '#054E42',
  900: '#032E27',
} as const;

// ── Warm 暖色辅助 ──
export const warm = {
  sun:   '#FFC244',  // 希望金
  fire:  '#FF7A3D',  // 晨炉暖橙
  blush: '#FF9B6A',  // 柔和点缀
  amber: '#C8923A',  // 琥珀金
} as const;

// ── Neutral 中性色阶（偏冷） ──
export const neutral = {
  0:   '#FFFFFF',
  50:  '#F7FAFA',
  100: '#EEF3F3',
  200: '#D8E4E4',
  300: '#B8CCCC',
  400: '#8AABAB',
  500: '#628A8A',
  600: '#4A6B6B',
  700: '#344E4E',
  800: '#1E3232',
  900: '#0D1E1E',
} as const;

// ── Semantic 语义色 ──
export const semantic = {
  success: '#1A7A52',
  warning: '#C8923A',
  danger:  '#C53030',
  info:    '#0AAF9A',
} as const;

// ── Dark Mode 深色模式专用 ──
export const dark = {
  bg:      '#0B1A20',
  raised:  '#0D2029',
  sidebar: '#08131A',
  topbar:  '#08141A',
  t1:      'rgba(255,255,255,0.92)',
  t2:      'rgba(255,255,255,0.50)',
  t3:      'rgba(255,255,255,0.25)',
  t4:      'rgba(255,255,255,0.08)',
  border:  'rgba(255,255,255,0.06)',
} as const;

// ── 快捷常量 ──
export const colors = {
  accent:  mint[500],
  green:   semantic.success,
  red:     semantic.danger,
  yellow:  warm.sun,
  amber:   warm.amber,
  orange:  warm.fire,
} as const;
