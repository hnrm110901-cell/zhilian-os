/**
 * 屯象OS Design System · 统一导出
 *
 * import { ZCard, ZKpi, mint, spacing } from '@/design-system';
 */

// Tokens
export { mint, warm, neutral, semantic, dark, colors } from './tokens/colors';
export { fontFamily, fontSize, lineHeight, letterSpacing, typography } from './tokens/typography';
export { spacing, breakpoint, layout } from './tokens/spacing';
export { radius, shadow, zIndex, motion } from './tokens/elevation';
export { injectTokens } from './tokens';

// Themes
export { lightTheme } from './themes/light';
export { darkTheme } from './themes/dark';

// Chart
export { txChartDefaults, registerTxChartTheme, txChartTheme, TX_CHART_THEME, TX_CHART_THEME_DARK } from './chartTheme';

// Components
export {
  ZCard, ZKpi, ZBadge, ZButton, ZInput, ZEmpty, ZSkeleton, ZAvatar,
  ZTabs, ZTable, ZModal, ZSelect,
  ZTag, ZAlert, ZTimeline, ZDrawer,
  DecisionCard, AIMessageCard, QuoteBlock,
  HealthRing, UrgencyList, ChartTrend, DetailDrawer,
  AISuggestionCard, OpsTimeline,
} from './components';

export type {
  ZTableColumn, ZTableProps,
  DetailDrawerProps, DrawerMetric, DrawerSection, DrawerAction,
  AISuggestionCardProps, Difficulty,
  OpsTimelineProps, OpsPhase,
  TimelineItem,
} from './components';
