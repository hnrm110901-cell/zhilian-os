// API服务配置
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const API_ENDPOINTS = {
  // 健康检查
  health: '/api/v1/health',

  // Agent端点
  agents: {
    schedule: '/api/v1/agents/schedule',
    order: '/api/v1/agents/order',
    inventory: '/api/v1/agents/inventory',
    service: '/api/v1/agents/service',
    training: '/api/v1/agents/training',
    decision: '/api/v1/agents/decision',
    reservation: '/api/v1/agents/reservation',
  },
};
