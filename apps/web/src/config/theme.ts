/**
 * 屯象OS · Ant Design 主题覆盖
 */
import { theme as antdTheme } from 'antd';
import type { ThemeConfig } from 'antd';

const fontFamily = "'Noto Sans SC', 'PingFang SC', -apple-system, BlinkMacSystemFont, sans-serif";

// 亮色主题
export const lightTheme: ThemeConfig = {
  token: {
    colorPrimary:      '#0AAF9A',  // mint-500
    colorSuccess:      '#1A7A52',  // tx-success
    colorWarning:      '#C8923A',  // tx-warning
    colorError:        '#C53030',  // tx-danger
    colorInfo:         '#0AAF9A',  // mint-500
    colorBgContainer:  '#FFFFFF',
    colorBgLayout:     '#F7FAFA',  // n-50
    colorText:         '#0D1E1E',  // n-900
    colorTextSecondary:'#4A6B6B',  // n-600
    colorBorder:       '#D8E4E4',  // n-200
    borderRadius: 8,
    fontSize: 14,
    fontFamily,
  },
  components: {
    Layout: {
      headerBg: '#FFFFFF',
      bodyBg: '#F7FAFA',
      siderBg: '#032E27',          // mint-900 (深绿侧边栏)
    },
    Menu: {
      darkItemBg: '#032E27',
      darkItemSelectedBg: '#0AAF9A',
    },
    Card: { borderRadiusLG: 12 },
    Button: { borderRadius: 8, controlHeight: 36 },
    Input: { borderRadius: 8, controlHeight: 36 },
    Table: { borderRadius: 8 },
  },
};

// 暗色主题
export const darkTheme: ThemeConfig = {
  token: {
    colorPrimary:      '#0AAF9A',
    colorSuccess:      '#34D399',
    colorWarning:      '#FFC244',
    colorError:        '#F87171',
    colorInfo:         '#0AAF9A',
    colorBgContainer:  '#0D2029',  // dark-raised
    colorBgLayout:     '#0B1A20',  // dark-bg
    colorText:         'rgba(255,255,255,0.92)',
    colorTextSecondary:'rgba(255,255,255,0.50)',
    colorBorder:       'rgba(255,255,255,0.10)',
    borderRadius: 8,
    fontSize: 14,
    fontFamily,
    colorBgBase: '#0B1A20',
    colorTextBase: 'rgba(255,255,255,0.92)',
  },
  components: {
    Layout: {
      headerBg: '#08141A',
      bodyBg: '#0B1A20',
      siderBg: '#08131A',
    },
    Menu: {
      darkItemBg: '#08131A',
      darkItemSelectedBg: '#0AAF9A',
    },
    Card: { borderRadiusLG: 12 },
    Button: { borderRadius: 8, controlHeight: 36 },
    Input: { borderRadius: 8, controlHeight: 36 },
    Table: { borderRadius: 8 },
  },
  algorithm: antdTheme.darkAlgorithm,
};
