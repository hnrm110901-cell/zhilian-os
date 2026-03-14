/**
 * 屯象OS · 色彩Token
 * 品牌色: Mint #0AAF9A — v2 设计系统
 * 基于 v2 prototype workspace.html 设计规范
 */

// ── Mint 品牌主色阶 ──
export const brand = {
  50:  '#E6F7F5',
  100: '#B3EBE4',
  200: '#80DFD3',
  300: '#4DD3C2',
  400: '#26C9B4',
  500: '#0AAF9A',  // Primary — --color-primary
  600: '#099987',  // Hover
  700: '#078070',  // Active/Pressed
  800: '#056659',
  900: '#034D43',
} as const;

// ── 保留旧名 mint 作为别名，兼容现有引用 ──
export const mint = brand;

// ── Navy 文字/导航色阶 ──
export const navy = {
  50:  '#F0F2F5',
  100: '#D9DEE4',
  200: '#B3BFCC',
  300: '#8C9FB3',
  400: '#667F99',
  500: '#3D5A80',
  600: '#2E4666',
  700: '#1E2A3A',  // 主标题色 — --color-navy-900
  800: '#151E2A',
  900: '#0D131C',
} as const;

// ── Warm 暖色辅助 ──
export const warm = {
  sun:   '#FFC244',  // 希望金
  fire:  '#FF7A3D',  // 晨炉暖橙
  blush: '#FF9B6A',  // 柔和点缀
  amber: '#F2994A',  // 琥珀金（Warning色）
} as const;

// ── Neutral 中性色阶（偏暖灰）──
export const neutral = {
  0:   '#FFFFFF',
  50:  '#FAFAFA',
  100: '#F5F5F5',
  200: '#E8E8E8',
  300: '#D9D9D9',
  400: '#BFBFBF',
  500: '#8C8C8C',
  600: '#595959',
  700: '#434343',
  800: '#262626',
  900: '#1D1D1F',
} as const;

// ── Semantic 语义色 ──
export const semantic = {
  success: '#27AE60',
  warning: '#F2994A',
  danger:  '#EB5757',
  info:    '#2D9CDB',
} as const;

// ── Dark Mode 深色模式专用（v2 prototype 色板）──
export const dark = {
  bg:      '#0B1A20',   // v2 主背景
  raised:  '#0D2029',   // v2 raised surface
  sidebar: '#0B1A20',   // sidebar 同主背景
  topbar:  '#0B1A20',   // topbar 同主背景
  t1:      'rgba(255,255,255,0.92)',   // 主文字
  t2:      'rgba(255,255,255,0.65)',   // 次要文字
  t3:      'rgba(255,255,255,0.38)',   // 辅助文字
  t4:      'rgba(255,255,255,0.08)',   // 禁用/分割线
  t5:      'rgba(255,255,255,0.04)',   // 微弱
  border:  'rgba(255,255,255,0.08)',   // 边框
} as const;

// ── 快捷常量 ──
export const colors = {
  accent:  brand[500],   // #0AAF9A
  green:   semantic.success,
  red:     semantic.danger,
  yellow:  warm.sun,
  amber:   warm.amber,
  orange:  warm.fire,
  info:    semantic.info,
  navy:    navy[700],
} as const;
