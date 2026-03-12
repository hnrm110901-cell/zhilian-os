/**
 * 屯象OS · 字体Token
 * 字号阶梯: Perfect Fourth (×1.333), Base 14px
 */

// ── Font Families ──
export const fontFamily = {
  serif: "'Noto Serif SC', 'STSong', Georgia, serif",
  sans:  "'Noto Sans SC', 'PingFang SC', sans-serif",
  ui:    "'Inter', 'Helvetica Neue', system-ui, sans-serif",
  mono:  "'JetBrains Mono', 'Fira Code', monospace",
} as const;

// ── Type Scale (Perfect Fourth × 1.333) ──
export const fontSize = {
  '2xs': 10,
  xs:    12,
  sm:    14,   // UI base
  md:    18,
  lg:    24,
  xl:    32,
  '2xl': 42,
  '3xl': 56,
} as const;

// ── Line Heights ──
export const lineHeight = {
  tight:   1.2,
  snug:    1.4,
  base:    1.6,
  relaxed: 1.75,
  loose:   2.0,
} as const;

// ── Letter Spacing ──
export const letterSpacing = {
  tight:   '-0.02em',
  normal:  '0em',
  wide:    '0.04em',
  wider:   '0.08em',
  widest:  '0.16em',
} as const;

// ── Preset Styles ──
export const typography = {
  display:  { fontSize: fontSize['3xl'], fontWeight: 900, lineHeight: lineHeight.tight },
  hero:     { fontSize: fontSize['2xl'], fontWeight: 700, lineHeight: lineHeight.tight },
  title1:   { fontSize: fontSize.xl,     fontWeight: 700, lineHeight: lineHeight.snug },
  title2:   { fontSize: fontSize.lg,     fontWeight: 700, lineHeight: lineHeight.snug },
  title3:   { fontSize: fontSize.md,     fontWeight: 600, lineHeight: lineHeight.snug },
  body:     { fontSize: fontSize.sm,     fontWeight: 400, lineHeight: lineHeight.base },
  caption:  { fontSize: fontSize.xs,     fontWeight: 500, lineHeight: lineHeight.snug },
  overline: { fontSize: fontSize['2xs'], fontWeight: 600, lineHeight: lineHeight.tight, letterSpacing: letterSpacing.widest, textTransform: 'uppercase' as const },
  kpiValue: { fontSize: fontSize.lg,     fontWeight: 700, lineHeight: lineHeight.tight },
  fontStack: fontFamily.sans,
} as const;
