/**
 * 屯象OS · Ant Design 主题覆盖
 * 品牌色 Orange #FF6B2C — 品牌识别指南 v1.0
 */
import { theme as antdTheme } from 'antd';
import type { ThemeConfig } from 'antd';

const fontFamily = "'Inter', 'Noto Sans SC', 'PingFang SC', 'HarmonyOS Sans SC', -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif";

// 亮色主题
export const lightTheme: ThemeConfig = {
  token: {
    colorPrimary:      '#FF6B2C',  // mint-500
    colorSuccess:      '#27AE60',
    colorWarning:      '#F2994A',
    colorError:        '#EB5757',
    colorInfo:         '#2D9CDB',
    colorBgContainer:  '#FFFFFF',
    colorBgLayout:     '#FAFAFA',
    colorText:         '#1E2A3A',
    colorTextSecondary:'#595959',
    colorBorder:       '#E8E8E8',
    borderRadius: 8,
    fontSize: 14,
    fontFamily,
  },
  components: {
    Layout: {
      headerBg: '#FFFFFF',
      bodyBg: '#FAFAFA',
      siderBg: '#0B1A20',
    },
    Menu: {
      darkItemBg: '#0B1A20',
      darkItemSelectedBg: '#FF6B2C',
    },
    Card: { borderRadiusLG: 12 },
    Button: { borderRadius: 8, controlHeight: 36 },
    Input: { borderRadius: 8, controlHeight: 36 },
    Table: { borderRadius: 8 },
  },
};

// 暗色主题（默认）
export const darkTheme: ThemeConfig = {
  token: {
    colorPrimary:      '#FF6B2C',  // mint-500
    colorSuccess:      '#34D399',
    colorWarning:      '#FBBF24',
    colorError:        '#F87171',
    colorInfo:         '#60A5FA',
    colorBgContainer:  '#0D2029',  // v2 raised
    colorBgLayout:     '#0B1A20',  // v2 bg
    colorText:         'rgba(255,255,255,0.92)',
    colorTextSecondary:'rgba(255,255,255,0.65)',
    colorBorder:       'rgba(255,255,255,0.10)',
    borderRadius: 8,
    fontSize: 14,
    fontFamily,
    colorBgBase: '#0B1A20',
    colorTextBase: 'rgba(255,255,255,0.92)',
  },
  components: {
    Layout: {
      headerBg: '#0B1A20',
      bodyBg: '#0B1A20',
      siderBg: '#0B1A20',
    },
    Menu: {
      darkItemBg: '#0B1A20',
      darkItemSelectedBg: '#FF6B2C',
    },
    Card: { borderRadiusLG: 12 },
    Button: { borderRadius: 8, controlHeight: 36 },
    Input: { borderRadius: 8, controlHeight: 36 },
    Table: { borderRadius: 8 },
  },
  algorithm: antdTheme.darkAlgorithm,
};
