/**
 * 屯象OS · 间距Token
 * 基准: 8pt Grid — 所有间距是4的倍数
 */

export const spacing = {
  1:  4,
  2:  8,
  3:  12,
  4:  16,
  5:  24,
  6:  32,
  7:  40,
  8:  48,
  9:  64,
  10: 80,
  11: 96,
  12: 128,
} as const;

// 栅格断点
export const breakpoint = {
  mobile:  767,
  tablet:  1279,
  desktop: 1280,
} as const;

// 固定布局尺寸
export const layout = {
  topbarHeight:    52,
  railWidth:       56,
  sidebarWidth:    220,
  aiPanelWidth:    320,
  drawerWidth:     400,
  bottomTabHeight: 56,
  maxContentWidth: 1080,
} as const;
