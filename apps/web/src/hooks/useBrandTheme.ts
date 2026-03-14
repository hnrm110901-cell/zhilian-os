/**
 * 品牌主题 Hook — 根据当前用户 brand_id 加载品牌配色/Logo
 *
 * 用法:
 *   const { brandName, logoUrl, accentColor } = useBrandTheme();
 */
import { useEffect, useState } from 'react';
import { apiClient } from '../services/api';

interface BrandTheme {
  brandId: string;
  brandName: string;
  logoUrl: string;
  accentColor: string;
  cuisineType: string;
  loading: boolean;
}

// 品牌 → 主色调默认映射
const BRAND_COLORS: Record<string, string> = {
  guizhou: '#D4380D',   // 贵州菜 — 辣椒红
  sichuan: '#CF1322',   // 川菜 — 正红
  cantonese: '#D4B106', // 粤菜 — 金色
  hunan: '#FA541C',     // 湘菜 — 橙红
  default: '#0AAF9A',   // 默认 — 屯象mint
};

const DEFAULT_THEME: BrandTheme = {
  brandId: '',
  brandName: '屯象OS',
  logoUrl: '/logo-icon.svg',
  accentColor: '#0AAF9A',
  cuisineType: '',
  loading: false,
};

export function useBrandTheme(): BrandTheme {
  const [theme, setTheme] = useState<BrandTheme>({ ...DEFAULT_THEME, loading: true });

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      setTheme(DEFAULT_THEME);
      return;
    }

    // 解析 JWT 获取 brand_id（不验证签名，仅解码 payload）
    let brandId = '';
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      brandId = payload.brand_id || '';
    } catch {
      setTheme(DEFAULT_THEME);
      return;
    }

    if (!brandId) {
      // 平台管理员无 brand_id
      setTheme(DEFAULT_THEME);
      return;
    }

    // 从 API 加载品牌信息
    let cancelled = false;
    apiClient
      .get<{
        brand_name: string;
        cuisine_type: string;
        logo_url?: string;
        accent_color?: string;
      }>(`/api/v1/merchants/${brandId}`)
      .then((data) => {
        if (cancelled) return;
        const cuisineType = data.cuisine_type || 'default';
        const accentColor = data.accent_color || BRAND_COLORS[cuisineType] || BRAND_COLORS.default;

        // 注入 CSS 变量
        document.documentElement.style.setProperty('--accent', accentColor);
        document.documentElement.style.setProperty('--brand-name', `"${data.brand_name}"`);

        setTheme({
          brandId,
          brandName: data.brand_name || '屯象OS',
          logoUrl: data.logo_url || '/logo-icon.svg',
          accentColor,
          cuisineType,
          loading: false,
        });
      })
      .catch(() => {
        if (!cancelled) setTheme({ ...DEFAULT_THEME, brandId });
      });

    return () => { cancelled = true; };
  }, []);

  return theme;
}
