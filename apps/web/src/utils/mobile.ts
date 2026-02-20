/**
 * 移动端工具函数和Hooks
 * Mobile utility functions and hooks
 */

import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * 检测是否为移动设备
 */
export const isMobileDevice = (): boolean => {
  if (typeof window === 'undefined') return false;

  return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
    navigator.userAgent
  ) || window.innerWidth < 768;
};

/**
 * 检测是否为iOS设备
 */
export const isIOS = (): boolean => {
  if (typeof window === 'undefined') return false;

  return /iPad|iPhone|iPod/.test(navigator.userAgent);
};

/**
 * 检测是否为Android设备
 */
export const isAndroid = (): boolean => {
  if (typeof window === 'undefined') return false;

  return /Android/.test(navigator.userAgent);
};

/**
 * 获取设备类型
 */
export const getDeviceType = (): 'mobile' | 'tablet' | 'desktop' => {
  if (typeof window === 'undefined') return 'desktop';

  const width = window.innerWidth;

  if (width < 768) return 'mobile';
  if (width < 1024) return 'tablet';
  return 'desktop';
};

/**
 * 下拉刷新Hook
 */
export const usePullToRefresh = (onRefresh: () => Promise<void>) => {
  const [isPulling, setIsPulling] = useState(false);
  const [pullDistance, setPullDistance] = useState(0);
  const startY = useRef(0);
  const isRefreshing = useRef(false);

  const handleTouchStart = useCallback((e: TouchEvent) => {
    if (window.scrollY === 0 && !isRefreshing.current) {
      startY.current = e.touches[0].clientY;
    }
  }, []);

  const handleTouchMove = useCallback((e: TouchEvent) => {
    if (startY.current === 0 || isRefreshing.current) return;

    const currentY = e.touches[0].clientY;
    const distance = currentY - startY.current;

    if (distance > 0 && window.scrollY === 0) {
      e.preventDefault();
      setPullDistance(Math.min(distance, 100));
      setIsPulling(distance > 60);
    }
  }, []);

  const handleTouchEnd = useCallback(async () => {
    if (isPulling && !isRefreshing.current) {
      isRefreshing.current = true;
      try {
        await onRefresh();
      } finally {
        isRefreshing.current = false;
        setIsPulling(false);
        setPullDistance(0);
        startY.current = 0;
      }
    } else {
      setPullDistance(0);
      startY.current = 0;
    }
  }, [isPulling, onRefresh]);

  useEffect(() => {
    if (!isMobileDevice()) return;

    document.addEventListener('touchstart', handleTouchStart, { passive: false });
    document.addEventListener('touchmove', handleTouchMove, { passive: false });
    document.addEventListener('touchend', handleTouchEnd);

    return () => {
      document.removeEventListener('touchstart', handleTouchStart);
      document.removeEventListener('touchmove', handleTouchMove);
      document.removeEventListener('touchend', handleTouchEnd);
    };
  }, [handleTouchStart, handleTouchMove, handleTouchEnd]);

  return { isPulling, pullDistance };
};

/**
 * 触摸滑动Hook
 */
export const useSwipe = (
  onSwipeLeft?: () => void,
  onSwipeRight?: () => void,
  threshold: number = 50
) => {
  const startX = useRef(0);
  const startY = useRef(0);

  const handleTouchStart = useCallback((e: TouchEvent) => {
    startX.current = e.touches[0].clientX;
    startY.current = e.touches[0].clientY;
  }, []);

  const handleTouchEnd = useCallback((e: TouchEvent) => {
    const endX = e.changedTouches[0].clientX;
    const endY = e.changedTouches[0].clientY;

    const deltaX = endX - startX.current;
    const deltaY = endY - startY.current;

    // 确保是水平滑动而不是垂直滑动
    if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > threshold) {
      if (deltaX > 0 && onSwipeRight) {
        onSwipeRight();
      } else if (deltaX < 0 && onSwipeLeft) {
        onSwipeLeft();
      }
    }
  }, [onSwipeLeft, onSwipeRight, threshold]);

  useEffect(() => {
    if (!isMobileDevice()) return;

    document.addEventListener('touchstart', handleTouchStart);
    document.addEventListener('touchend', handleTouchEnd);

    return () => {
      document.removeEventListener('touchstart', handleTouchStart);
      document.removeEventListener('touchend', handleTouchEnd);
    };
  }, [handleTouchStart, handleTouchEnd]);
};

/**
 * 视口尺寸Hook
 */
export const useViewport = () => {
  const [viewport, setViewport] = useState({
    width: typeof window !== 'undefined' ? window.innerWidth : 0,
    height: typeof window !== 'undefined' ? window.innerHeight : 0,
    isMobile: isMobileDevice(),
    deviceType: getDeviceType(),
  });

  useEffect(() => {
    const handleResize = () => {
      setViewport({
        width: window.innerWidth,
        height: window.innerHeight,
        isMobile: isMobileDevice(),
        deviceType: getDeviceType(),
      });
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return viewport;
};

/**
 * 触觉反馈
 */
export const hapticFeedback = (type: 'light' | 'medium' | 'heavy' = 'medium') => {
  if ('vibrate' in navigator) {
    const patterns = {
      light: 10,
      medium: 20,
      heavy: 30,
    };
    navigator.vibrate(patterns[type]);
  }
};

/**
 * 防止iOS橡皮筋效果
 */
export const preventIOSBounce = () => {
  if (!isIOS()) return;

  let startY = 0;

  document.addEventListener('touchstart', (e) => {
    startY = e.touches[0].pageY;
  });

  document.addEventListener('touchmove', (e) => {
    const target = e.target as HTMLElement;
    const scrollable = target.closest('[data-scrollable]');

    if (!scrollable) {
      e.preventDefault();
      return;
    }

    const currentY = e.touches[0].pageY;
    const scrollTop = scrollable.scrollTop;
    const scrollHeight = scrollable.scrollHeight;
    const clientHeight = scrollable.clientHeight;

    if (
      (scrollTop === 0 && currentY > startY) ||
      (scrollTop + clientHeight >= scrollHeight && currentY < startY)
    ) {
      e.preventDefault();
    }
  }, { passive: false });
};

/**
 * 添加到主屏幕提示
 */
export const canAddToHomeScreen = (): boolean => {
  if (typeof window === 'undefined') return false;

  // iOS Safari
  if (isIOS()) {
    return !('standalone' in navigator && (navigator as any).standalone);
  }

  // Android Chrome
  return 'BeforeInstallPromptEvent' in window;
};

/**
 * 获取安全区域insets (用于刘海屏等)
 */
export const getSafeAreaInsets = () => {
  if (typeof window === 'undefined') return { top: 0, bottom: 0, left: 0, right: 0 };

  const style = getComputedStyle(document.documentElement);

  return {
    top: parseInt(style.getPropertyValue('--sat') || '0'),
    bottom: parseInt(style.getPropertyValue('--sab') || '0'),
    left: parseInt(style.getPropertyValue('--sal') || '0'),
    right: parseInt(style.getPropertyValue('--sar') || '0'),
  };
};
