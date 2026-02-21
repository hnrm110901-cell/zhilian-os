import { message } from 'antd';

/**
 * 统一的消息提示工具
 */

export const showSuccess = (content: string, duration: number = 3) => {
  message.success(content, duration);
};

export const showError = (content: string, duration: number = 3) => {
  message.error(content, duration);
};

export const showWarning = (content: string, duration: number = 3) => {
  message.warning(content, duration);
};

export const showInfo = (content: string, duration: number = 3) => {
  message.info(content, duration);
};

export const showLoading = (content: string = '加载中...', duration: number = 0) => {
  return message.loading(content, duration);
};

/**
 * 处理API错误并显示友好的错误消息
 */
export const handleApiError = (error: any, defaultMessage: string = '操作失败') => {
  console.error('API Error:', error);

  if (error.response) {
    // 服务器返回错误
    const status = error.response.status;
    const data = error.response.data;

    if (status === 401) {
      showError('登录已过期，请重新登录');
      setTimeout(() => {
        window.location.href = '/login';
      }, 1500);
      return;
    }

    if (status === 403) {
      showError('没有权限执行此操作');
      return;
    }

    if (status === 404) {
      showError('请求的资源不存在');
      return;
    }

    if (status === 422) {
      showError(data.detail || '请求参数错误');
      return;
    }

    if (status >= 500) {
      showError('服务器错误，请稍后重试');
      return;
    }

    // 显示服务器返回的错误消息
    showError(data.message || data.detail || defaultMessage);
  } else if (error.request) {
    // 请求已发送但没有收到响应
    showError('网络连接失败，请检查网络');
  } else {
    // 其他错误
    showError(error.message || defaultMessage);
  }
};
