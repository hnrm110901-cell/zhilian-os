/**
 * 屯象OS · Dark Theme Token Map
 * 基于 v2 prototype workspace.html 设计规范
 * 深色主题：#0B1A20 深青色背景 + #FF6B2C 品牌橙主色
 */
import { brand, dark as darkColors, semantic } from '../tokens/colors';

export const darkTheme = {
  // Backgrounds (v2 prototype)
  '--tx-bg':              darkColors.bg,        // #0B1A20
  '--tx-bg-primary':      darkColors.bg,
  '--tx-bg-secondary':    darkColors.raised,    // #0D2029
  '--tx-bg-tertiary':     '#091518',
  '--tx-bg-elevated':     darkColors.raised,

  // Text (opacity-based hierarchy from v2)
  '--tx-text-primary':    darkColors.t1,        // 92%
  '--tx-text-secondary':  darkColors.t2,        // 65%
  '--tx-text-tertiary':   darkColors.t3,        // 38%
  '--tx-text-disabled':   darkColors.t4,        // 8%

  // Border
  '--tx-border':          'rgba(255,255,255,0.10)',
  '--tx-border-light':    darkColors.border,     // 8%
  '--tx-divider':         darkColors.border,

  // Accent (Orange #FF6B2C)
  '--tx-accent':          brand[500],            // #FF6B2C
  '--tx-accent-hover':    brand[400],            // #FF9160
  '--tx-accent-active':   brand[300],            // #FFB494
  '--tx-accent-soft':     'rgba(255,107,44,0.15)',
  '--tx-accent-bg':       'rgba(255,107,44,0.10)',

  // Semantic (brighter in dark for contrast)
  '--tx-success':         '#34D399',
  '--tx-warning':         '#FBBF24',
  '--tx-danger':          '#F87171',
  '--tx-info':            '#60A5FA',

  // Warm
  '--tx-sun':             '#FFC244',
  '--tx-fire':            '#FF9B6A',
  '--tx-amber':           '#FFB86C',

  // Surface
  '--tx-surface':         darkColors.raised,
  '--tx-surface-hover':   '#132830',

  // Shadows (high opacity for dark theme, v2 style)
  '--tx-shadow-sm':       '0 1px 2px rgba(0,0,0,0.3)',
  '--tx-shadow-md':       '0 2px 8px rgba(0,0,0,0.4)',
  '--tx-shadow-lg':       '0 4px 16px rgba(0,0,0,0.5)',
  '--tx-shadow-xl':       '0 8px 24px rgba(0,0,0,0.6)',

  // Chart
  '--tx-chart-grid':      'rgba(255,255,255,0.06)',
  '--tx-chart-axis':      'rgba(255,255,255,0.25)',
  '--tx-chart-tooltip-bg': darkColors.raised,
} as const;
