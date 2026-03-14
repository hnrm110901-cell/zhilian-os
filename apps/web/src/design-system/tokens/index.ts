/**
 * 屯象OS Design Tokens
 * 品牌: 屯象 TUN XIANG · 餐饮人的好伙伴
 * v2 设计系统 — 深色主题 + Mint #0AAF9A 主色
 *
 * 使用方式:
 *   import { colors, typography, spacing } from '@/design-system/tokens';
 *   // CSS中用 var(--tx-brand-500) 等变量
 */

export { brand, mint, warm, neutral, semantic, dark, navy, colors } from './colors';
export { fontFamily, fontSize, lineHeight, letterSpacing, typography } from './typography';
export { spacing, breakpoint, layout } from './spacing';
export { radius, shadow, zIndex, motion } from './elevation';

import { brand, warm, neutral, semantic, dark, navy } from './colors';
import { fontFamily, fontSize } from './typography';
import { spacing } from './spacing';
import { radius, shadow, zIndex, motion } from './elevation';
import { lightTheme } from '../themes/light';
import { darkTheme } from '../themes/dark';

// ── CSS 变量注入（在 main.tsx 中调用 injectTokens()）──
export function injectTokens() {
  const root = document.documentElement;

  // v2 设计系统默认使用深色主题
  // 除非显式设置 data-theme="light"，否则默认 dark
  const isLight = root.getAttribute('data-theme') === 'light';
  if (!root.getAttribute('data-theme')) {
    root.setAttribute('data-theme', 'dark');
  }

  // ── 语义变量（主题感知）──
  const themeVars: Record<string, string> = isLight ? {
    // 背景
    '--bg':              neutral[50],
    '--surface':         neutral[0],
    '--surface-hover':   neutral[100],
    // 文字
    '--text-primary':    navy[700],
    '--text-secondary':  neutral[600],
    '--text-tertiary':   neutral[400],
    // 边框
    '--border':          neutral[200],
    // 语义色
    '--accent':          brand[500],
    '--accent-soft':     'rgba(10,175,154,0.08)',
    '--accent-hover':    brand[600],
    '--accent-active':   brand[700],
    '--accent-bg':       brand[50],
    '--green':           semantic.success,
    '--red':             semantic.danger,
    '--yellow':          warm.amber,
    '--blue':            semantic.info,
    // Ant Design 兼容
    '--bg-primary':      neutral[0],
    '--bg-secondary':    neutral[50],
    '--bg-tertiary':     neutral[100],
    '--bg-elevated':     neutral[0],
    '--border-color':    neutral[200],
    '--border-light':    neutral[100],
    '--divider-color':   neutral[100],
    '--text-disabled':   neutral[300],
  } : {
    // 背景 (v2 prototype)
    '--bg':              dark.bg,         // #0B1A20
    '--surface':         dark.raised,     // #0D2029
    '--surface-hover':   '#132830',
    // 文字 (opacity-based)
    '--text-primary':    dark.t1,         // 92%
    '--text-secondary':  dark.t2,         // 65%
    '--text-tertiary':   dark.t3,         // 38%
    // 边框
    '--border':          dark.border,     // 8%
    // 语义色 (Mint accent)
    '--accent':          brand[500],      // #0AAF9A
    '--accent-soft':     'rgba(10,175,154,0.15)',
    '--accent-hover':    brand[400],
    '--accent-active':   brand[300],
    '--accent-bg':       'rgba(10,175,154,0.10)',
    '--green':           '#34D399',
    '--red':             '#F87171',
    '--yellow':          '#FBBF24',
    '--blue':            '#60A5FA',
    // Ant Design 兼容
    '--bg-primary':      dark.bg,
    '--bg-secondary':    dark.raised,
    '--bg-tertiary':     '#091518',
    '--bg-elevated':     dark.raised,
    '--border-color':    'rgba(255,255,255,0.10)',
    '--border-light':    dark.border,
    '--divider-color':   dark.border,
    '--text-disabled':   dark.t4,
  };

  // ── 静态变量（不随主题变化）──
  const staticVars: Record<string, string> = {
    // Brand色阶（mint主色）
    '--tx-mint-50':  brand[50],  '--tx-mint-100': brand[100], '--tx-mint-200': brand[200],
    '--tx-mint-300': brand[300], '--tx-mint-400': brand[400], '--tx-mint-500': brand[500],
    '--tx-mint-600': brand[600], '--tx-mint-700': brand[700], '--tx-mint-800': brand[800],
    '--tx-mint-900': brand[900],
    // Brand色阶（新命名）
    '--tx-brand-50':  brand[50],  '--tx-brand-100': brand[100], '--tx-brand-200': brand[200],
    '--tx-brand-300': brand[300], '--tx-brand-400': brand[400], '--tx-brand-500': brand[500],
    '--tx-brand-600': brand[600], '--tx-brand-700': brand[700], '--tx-brand-800': brand[800],
    '--tx-brand-900': brand[900],
    // Navy
    '--tx-navy-700': navy[700], '--tx-navy-900': navy[900],
    // Warm
    '--tx-warm-sun':   warm.sun,   '--tx-warm-fire': warm.fire,
    '--tx-warm-blush': warm.blush, '--tx-warm-amber': warm.amber,
    // Neutral色阶
    '--tx-n-0':   neutral[0],   '--tx-n-50':  neutral[50],
    '--tx-n-100': neutral[100], '--tx-n-200': neutral[200], '--tx-n-300': neutral[300],
    '--tx-n-400': neutral[400], '--tx-n-500': neutral[500], '--tx-n-600': neutral[600],
    '--tx-n-700': neutral[700], '--tx-n-800': neutral[800], '--tx-n-900': neutral[900],
    // 语义
    '--tx-success': semantic.success, '--tx-warning': semantic.warning,
    '--tx-danger':  semantic.danger,  '--tx-info':    semantic.info,
    // 圆角
    '--radius-2xs':  `${radius['2xs']}px`, '--radius-xs':   `${radius.xs}px`,
    '--radius-sm':   `${radius.sm}px`,     '--radius-md':   `${radius.md}px`,
    '--radius-lg':   `${radius.lg}px`,     '--radius-xl':   `${radius.xl}px`,
    '--radius-2xl':  `${radius['2xl']}px`, '--radius-full': `${radius.full}px`,
    // 阴影
    '--shadow-0': shadow[0], '--shadow-1': shadow[1], '--shadow-2': shadow[2],
    '--shadow-3': shadow[3], '--shadow-4': shadow[4],
    // 旧变量兼容
    '--shadow-sm': shadow[1], '--shadow-md': shadow[2],
    '--shadow-lg': shadow[3], '--shadow-xl': shadow[4],
    // 间距
    '--sp-1': `${spacing[1]}px`,  '--sp-2': `${spacing[2]}px`,
    '--sp-3': `${spacing[3]}px`,  '--sp-4': `${spacing[4]}px`,
    '--sp-5': `${spacing[5]}px`,  '--sp-6': `${spacing[6]}px`,
    '--sp-7': `${spacing[7]}px`,  '--sp-8': `${spacing[8]}px`,
    // 旧间距兼容
    '--spacing-xs':  `${spacing[1]}px`, '--spacing-sm':  `${spacing[2]}px`,
    '--spacing-md':  `${spacing[4]}px`, '--spacing-lg':  `${spacing[5]}px`,
    '--spacing-xl':  `${spacing[6]}px`, '--spacing-2xl': `${spacing[8]}px`,
    // 动效
    '--motion-fast':   motion.fast,   '--motion-normal': motion.normal,
    '--motion-slow':   motion.slow,   '--motion-spring': motion.spring,
    '--transition-fast': `0.15s cubic-bezier(0.4, 0, 0.2, 1)`,
    '--transition-base': `0.2s cubic-bezier(0.4, 0, 0.2, 1)`,
    '--transition-slow': `0.3s cubic-bezier(0.4, 0, 0.2, 1)`,
    // v2 主色快捷变量
    '--primary-color':    brand[500],
    '--primary-hover':    brand[600],
    '--primary-active':   brand[700],
  };

  // ── tx-* 主题变量（新规范前缀）──
  const txThemeVars = isLight ? lightTheme : darkTheme;

  Object.entries({ ...themeVars, ...staticVars, ...txThemeVars }).forEach(([k, v]) => {
    root.style.setProperty(k, v);
  });

  // ── 监听 data-theme 切换，自动重注入 ──
  if (!(window as any).__txThemeObserver) {
    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.type === 'attributes' && m.attributeName === 'data-theme') {
          injectTokens();
          break;
        }
      }
    });
    observer.observe(root, { attributes: true, attributeFilter: ['data-theme'] });
    (window as any).__txThemeObserver = observer;
  }
}
