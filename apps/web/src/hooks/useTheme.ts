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
  return theme === 'auto' ? getSystemTheme() : theme;
};

// 应用主题到DOM，同步更新 theme-color meta
const applyTheme = (theme: 'light' | 'dark') => {
  document.documentElement.setAttribute('data-theme', theme);
  const metaThemeColor = document.querySelector('meta[name="theme-color"]');
  if (metaThemeColor) {
    metaThemeColor.setAttribute('content', theme === 'dark' ? '#1f1f1f' : '#667eea');
  }
};

export const useTheme = () => {
  const [theme, setThemeState] = useState<Theme>(() => {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    return (saved as Theme) || 'auto';
  });

  // 实时跟踪系统主题，auto 模式下驱动重渲染
  const [systemTheme, setSystemTheme] = useState<'light' | 'dark'>(getSystemTheme);

  const appliedTheme = theme === 'auto' ? systemTheme : theme;

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
    localStorage.setItem(THEME_STORAGE_KEY, newTheme);
    applyTheme(getAppliedTheme(newTheme));
  };

  const toggleTheme = () => {
    // auto 模式下切换到与当前系统主题相反的固定主题
    const next = appliedTheme === 'light' ? 'dark' : 'light';
    setTheme(next);
  };

  // 始终监听系统主题变化，auto 模式下同步到 state 触发重渲染
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = (e: MediaQueryListEvent) => {
      const next: 'light' | 'dark' = e.matches ? 'dark' : 'light';
      setSystemTheme(next);
      if (theme === 'auto') {
        applyTheme(next);
      }
    };
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [theme]);

  // 主题变化时同步 DOM
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
