import axios from 'axios';
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';
import { API_BASE_URL } from './config';

// Agent请求接口
export interface AgentRequest {
  agent_type: string;
  input_data: Record<string, any>;
}

// Agent响应接口
export interface AgentResponse {
  agent_type: string;
  output_data: Record<string, any>;
  execution_time: number;
}

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // 请求拦截器
    this.client.interceptors.request.use(
      (config) => {
        // 添加认证token
        const token = localStorage.getItem('token');
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => {
        return Promise.reject(error);
      }
    );

    // 响应拦截器
    this.client.interceptors.response.use(
      (response) => {
        return response;
      },
      (error) => {
        // 统一错误处理
        if (error.response?.status === 401) {
          // Token过期或无效，清除本地存储并跳转到登录页
          localStorage.removeItem('token');
          localStorage.removeItem('user');
          window.location.href = '/login';
        }
        console.error('API Error:', error);
        return Promise.reject(error);
      }
    );
  }

  // 通用请求方法
  async request<T = any>(config: AxiosRequestConfig): Promise<T> {
    const response: AxiosResponse<T> = await this.client.request(config);
    return response.data;
  }

  // GET请求
  async get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return this.request<T>({ ...config, method: 'GET', url });
  }

  // POST请求
  async post<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    return this.request<T>({ ...config, method: 'POST', url, data });
  }

  // PUT请求
  async put<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    return this.request<T>({ ...config, method: 'PUT', url, data });
  }

  // PATCH请求
  async patch<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    return this.request<T>({ ...config, method: 'PATCH', url, data });
  }

  // DELETE请求
  async delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return this.request<T>({ ...config, method: 'DELETE', url });
  }

  // 调用Agent
  async callAgent(agentType: string, inputData: Record<string, any>): Promise<AgentResponse> {
    const request: AgentRequest = {
      agent_type: agentType,
      input_data: inputData,
    };

    return this.post<AgentResponse>(`/api/v1/agents/${agentType}`, request);
  }

  // 健康检查
  async healthCheck(): Promise<any> {
    return this.get('/api/v1/health');
  }
}

export const apiClient = new ApiClient();
export default apiClient;
