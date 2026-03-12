/**
 * 屯象OS · Light Theme Token Map
 * 由 injectTokens() 注入为 CSS 变量
 */
import { mint, neutral, semantic, warm } from '../tokens/colors';

export const lightTheme = {
  // Backgrounds
  '--tx-bg':              neutral[50],
  '--tx-bg-primary':      neutral[0],
  '--tx-bg-secondary':    neutral[50],
  '--tx-bg-tertiary':     neutral[100],
  '--tx-bg-elevated':     neutral[0],

  // Text
  '--tx-text-primary':    neutral[900],
  '--tx-text-secondary':  neutral[600],
  '--tx-text-tertiary':   neutral[400],
  '--tx-text-disabled':   neutral[300],

  // Border
  '--tx-border':          neutral[200],
  '--tx-border-light':    neutral[100],
  '--tx-divider':         neutral[100],

  // Accent
  '--tx-accent':          mint[500],
  '--tx-accent-hover':    mint[600],
  '--tx-accent-active':   mint[700],
  '--tx-accent-soft':     'rgba(10,175,154,0.08)',

  // Semantic
  '--tx-success':         semantic.success,
  '--tx-warning':         semantic.warning,
  '--tx-danger':          semantic.danger,
  '--tx-info':            semantic.info,

  // Warm
  '--tx-sun':             warm.sun,
  '--tx-fire':            warm.fire,
  '--tx-amber':           warm.amber,

  // Surface
  '--tx-surface':         neutral[0],
  '--tx-surface-hover':   neutral[100],

  // Shadows
  '--tx-shadow-sm':       '0 1px 3px rgba(13,30,30,0.06)',
  '--tx-shadow-md':       '0 2px 8px rgba(13,30,30,0.08)',
  '--tx-shadow-lg':       '0 4px 16px rgba(13,30,30,0.10)',
  '--tx-shadow-xl':       '0 8px 24px rgba(13,30,30,0.12)',

  // Chart
  '--tx-chart-grid':      neutral[100],
  '--tx-chart-axis':      neutral[400],
  '--tx-chart-tooltip-bg': neutral[0],
} as const;
