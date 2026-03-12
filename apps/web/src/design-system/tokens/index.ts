/**
 * 屯象OS Design Tokens
 * 品牌: 屯象 TUN XIANG · 餐饮人的好伙伴
 *
 * 使用方式:
 *   import { colors, typography, spacing } from '@/design-system/tokens';
 *   // CSS中用 var(--tx-mint-500) 等变量
 */

export { mint, warm, neutral, semantic, dark, colors } from './colors';
export { fontFamily, fontSize, lineHeight, letterSpacing, typography } from './typography';
export { spacing, breakpoint, layout } from './spacing';
export { radius, shadow, zIndex, motion } from './elevation';

import { mint, warm, neutral, semantic, dark } from './colors';
import { fontFamily, fontSize } from './typography';
import { spacing } from './spacing';
import { radius, shadow, zIndex, motion } from './elevation';
import { lightTheme } from '../themes/light';
import { darkTheme } from '../themes/dark';

// ── CSS 变量注入（在 main.tsx 中调用 injectTokens()）──
export function injectTokens() {
  const root = document.documentElement;
  const isDark = root.getAttribute('data-theme') === 'dark' || root.classList.contains('dark');

  // ── 语义变量（主题感知）──
  const themeVars: Record<string, string> = isDark ? {
    // 背景
    '--bg':              dark.bg,
    '--surface':         dark.raised,
    '--surface-hover':   '#112830',
    // 文字
    '--text-primary':    dark.t1,
    '--text-secondary':  dark.t2,
    '--text-tertiary':   dark.t3,
    // 边框
    '--border':          dark.border,
    // 语义色
    '--accent':          mint[500],
    '--accent-soft':     `rgba(10,175,154,0.15)`,
    '--green':           '#34D399',
    '--red':             '#F87171',
    '--yellow':          warm.sun,
    '--blue':            '#60A5FA',
    // Ant Design 兼容
    '--bg-primary':      dark.bg,
    '--bg-secondary':    dark.raised,
    '--bg-tertiary':     dark.sidebar,
    '--bg-elevated':     dark.raised,
    '--border-color':    'rgba(255,255,255,0.10)',
    '--border-light':    dark.border,
    '--divider-color':   dark.border,
    '--text-disabled':   dark.t4,
  } : {
    // 背景
    '--bg':              neutral[50],
    '--surface':         neutral[0],
    '--surface-hover':   neutral[100],
    // 文字
    '--text-primary':    neutral[900],
    '--text-secondary':  neutral[600],
    '--text-tertiary':   neutral[400],
    // 边框
    '--border':          neutral[200],
    // 语义色
    '--accent':          mint[500],
    '--accent-soft':     `rgba(10,175,154,0.08)`,
    '--green':           semantic.success,
    '--red':             semantic.danger,
    '--yellow':          warm.amber,
    '--blue':            '#0A84FF',
    // Ant Design 兼容
    '--bg-primary':      neutral[0],
    '--bg-secondary':    neutral[50],
    '--bg-tertiary':     neutral[100],
    '--bg-elevated':     neutral[0],
    '--border-color':    neutral[200],
    '--border-light':    neutral[100],
    '--divider-color':   neutral[100],
    '--text-disabled':   neutral[300],
  };

  // ── 静态变量（不随主题变化）──
  const staticVars: Record<string, string> = {
    // Mint色阶
    '--tx-mint-50':  mint[50],  '--tx-mint-100': mint[100], '--tx-mint-200': mint[200],
    '--tx-mint-300': mint[300], '--tx-mint-400': mint[400], '--tx-mint-500': mint[500],
    '--tx-mint-600': mint[600], '--tx-mint-700': mint[700], '--tx-mint-800': mint[800],
    '--tx-mint-900': mint[900],
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
  };

  // ── tx-* 主题变量（新规范前缀）──
  const txThemeVars = isDark ? darkTheme : lightTheme;

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
