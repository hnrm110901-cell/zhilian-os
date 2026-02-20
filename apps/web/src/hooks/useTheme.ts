import { useState, useEffect } from 'react';

export type Theme = 'light' | 'dark' | 'auto';

const THEME_STORAGE_KEY = 'zhilian-theme';

// 获取系统主题偏好
const getSystemTheme = (): 'light' | 'dark' => {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

// 获取实际应用的主题
const getAppliedTheme = (theme: Theme): 'light' | 'dark' => {
  if (theme === 'auto') {
    return getSystemTheme();
  }
  return theme;
};

// 应用主题到DOM
const applyTheme = (theme: 'light' | 'dark') => {
  const root = document.documentElement;
  root.setAttribute('data-theme', theme);
};

export const useTheme = () => {
  // 从localStorage读取保存的主题，默认为auto
  const [theme, setThemeState] = useState<Theme>(() => {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    return (saved as Theme) || 'auto';
  });

  // 计算实际应用的主题
  const appliedTheme = getAppliedTheme(theme);

  // 设置主题
  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
    localStorage.setItem(THEME_STORAGE_KEY, newTheme);
    applyTheme(getAppliedTheme(newTheme));
  };

  // 切换主题
  const toggleTheme = () => {
    const newTheme = appliedTheme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
  };

  // 监听系统主题变化
  useEffect(() => {
    if (theme !== 'auto') return;

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => {
      applyTheme(getSystemTheme());
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [theme]);

  // 初始化时应用主题
  useEffect(() => {
    applyTheme(appliedTheme);
  }, [appliedTheme]);

  return {
    theme,
    appliedTheme,
    setTheme,
    toggleTheme,
    isDark: appliedTheme === 'dark',
  };
};
