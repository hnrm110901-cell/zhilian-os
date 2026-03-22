/**
 * 屯象OS · ECharts 主题配置
 * 用法: <ReactECharts option={option} theme={txChartTheme(isDark)} />
 *       或合并: { ...option, ...txChartDefaults(isDark) }
 */

const LIGHT_PALETTE = [
  '#FF6B2C', '#3B82F6', '#FFC244', '#FF7A3D', '#8B5CF6',
  '#EC4899', '#1A7A52', '#C8923A', '#6366F1', '#84CC16',
];

const DARK_PALETTE = [
  '#2DD4BC', '#60A5FA', '#FFC244', '#FF9B6A', '#A78BFA',
  '#F472B6', '#34D399', '#FFB86C', '#818CF8', '#A3E635',
];

export function txChartDefaults(isDark = false) {
  const textColor = isDark ? 'rgba(255,255,255,0.50)' : '#8AABAB';
  const splitLineColor = isDark ? 'rgba(255,255,255,0.06)' : '#EEF3F3';
  const axisLineColor = isDark ? 'rgba(255,255,255,0.10)' : '#D8E4E4';

  return {
    color: isDark ? DARK_PALETTE : LIGHT_PALETTE,
    textStyle: { fontFamily: "'Inter', 'Noto Sans SC', sans-serif" },
    tooltip: {
      backgroundColor: isDark ? '#0D2029' : '#FFFFFF',
      borderColor: isDark ? 'rgba(255,255,255,0.10)' : '#D8E4E4',
      textStyle: { color: isDark ? 'rgba(255,255,255,0.92)' : '#0D1E1E', fontSize: 12 },
    },
    legend: {
      textStyle: { color: textColor, fontSize: 11 },
    },
    xAxis: {
      axisLabel: { color: textColor, fontSize: 11 },
      axisLine: { lineStyle: { color: axisLineColor } },
      splitLine: { lineStyle: { color: splitLineColor, type: 'dashed' as const } },
    },
    yAxis: {
      axisLabel: { color: textColor, fontSize: 11 },
      axisLine: { lineStyle: { color: axisLineColor } },
      splitLine: { lineStyle: { color: splitLineColor, type: 'dashed' as const } },
    },
  };
}

/** ECharts registered theme names (for theme prop) */
export const TX_CHART_THEME = 'tunxiang';
export const TX_CHART_THEME_DARK = 'tunxiang-dark';

/** Get the correct theme name for current mode */
export function txChartTheme(isDark = false) {
  return isDark ? TX_CHART_THEME_DARK : TX_CHART_THEME;
}

/** Register the屯象 theme with ECharts (call once per mode) */
export function registerTxChartTheme(echarts: any, isDark = false) {
  const themeName = isDark ? TX_CHART_THEME_DARK : TX_CHART_THEME;
  const defaults = txChartDefaults(isDark);
  echarts.registerTheme(themeName, {
    color: defaults.color,
    backgroundColor: 'transparent',
    textStyle: defaults.textStyle,
    title: { textStyle: { color: isDark ? 'rgba(255,255,255,0.92)' : '#0D1E1E' } },
    tooltip: defaults.tooltip,
    legend: defaults.legend,
    categoryAxis: { ...defaults.xAxis },
    valueAxis: { ...defaults.yAxis },
  });
}
