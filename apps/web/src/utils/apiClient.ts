/**
 * API Client with automatic authentication and token refresh
 */

interface RequestOptions extends RequestInit {
  requiresAuth?: boolean;
  _retry?: boolean; // Internal flag to prevent infinite retry loops
}

class APIClient {
  private baseURL: string;
  private isRefreshing: boolean = false;
  private refreshPromise: Promise<boolean> | null = null;

  constructor(baseURL: string = '/api/v1') {
    this.baseURL = baseURL;
  }

  private getAuthToken(): string | null {
    return localStorage.getItem('token');
  }

  private getRefreshToken(): string | null {
    return localStorage.getItem('refresh_token');
  }

  private getHeaders(requiresAuth: boolean = true): HeadersInit {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    if (requiresAuth) {
      const token = this.getAuthToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    }

    return headers;
  }

  private async refreshAccessToken(): Promise<boolean> {
    // If already refreshing, wait for that promise
    if (this.isRefreshing && this.refreshPromise) {
      return this.refreshPromise;
    }

    this.isRefreshing = true;
    this.refreshPromise = (async () => {
      try {
        const refreshToken = this.getRefreshToken();
        if (!refreshToken) {
          return false;
        }

        const response = await fetch(`${this.baseURL}/auth/refresh`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });

        if (response.ok) {
          const data = await response.json();
          localStorage.setItem('token', data.access_token);
          return true;
        } else {
          // Refresh failed, clear tokens
          localStorage.removeItem('token');
          localStorage.removeItem('refresh_token');
          return false;
        }
      } catch (error) {
        console.error('Token refresh error:', error);
        return false;
      } finally {
        this.isRefreshing = false;
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  async request<T>(
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const { requiresAuth = true, _retry = false, ...fetchOptions } = options;

    const url = `${this.baseURL}${endpoint}`;
    const headers = {
      ...this.getHeaders(requiresAuth),
      ...fetchOptions.headers,
    };

    const response = await fetch(url, {
      ...fetchOptions,
      headers,
    });

    // Handle 401 Unauthorized - try to refresh token
    if (response.status === 401 && requiresAuth && !_retry) {
      const refreshed = await this.refreshAccessToken();

      if (refreshed) {
        // Retry the request with new token
        return this.request<T>(endpoint, {
          ...options,
          _retry: true, // Prevent infinite retry loop
        });
      } else {
        // Refresh failed, redirect to login
        window.location.href = '/login';
        throw new Error('认证失败，请重新登录');
      }
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        detail: 'An error occurred',
      }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async get<T>(endpoint: string, requiresAuth = true): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'GET',
      requiresAuth,
    });
  }

  async post<T>(
    endpoint: string,
    data?: any,
    requiresAuth = true
  ): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
      requiresAuth,
    });
  }

  async put<T>(
    endpoint: string,
    data?: any,
    requiresAuth = true
  ): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
      requiresAuth,
    });
  }

  async delete<T>(endpoint: string, requiresAuth = true): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'DELETE',
      requiresAuth,
    });
  }
}

export const apiClient = new APIClient();

// Agent API calls
export const agentAPI = {
  executeAgent: (agentType: string, inputData: any) =>
    apiClient.post(`/agents/${agentType}`, {
      agent_type: agentType,
      input_data: inputData,
    }),
};

// Auth API calls
export const authAPI = {
  login: (username: string, password: string) =>
    apiClient.post('/auth/login', { username, password }, false),

  refreshToken: (refreshToken: string) =>
    apiClient.post('/auth/refresh', { refresh_token: refreshToken }, false),

  getCurrentUser: () => apiClient.get('/auth/me'),

  updateProfile: (data: any) => apiClient.put('/auth/me', data),

  changePassword: (oldPassword: string, newPassword: string) =>
    apiClient.post('/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    }),
};
