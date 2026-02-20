import React, { createContext, useContext, ReactNode } from 'react';
import { useTheme as useThemeHook, Theme } from '../hooks/useTheme';

interface ThemeContextType {
  theme: Theme;
  appliedTheme: 'light' | 'dark';
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  isDark: boolean;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export const ThemeProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const themeValue = useThemeHook();

  return <ThemeContext.Provider value={themeValue}>{children}</ThemeContext.Provider>;
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};
