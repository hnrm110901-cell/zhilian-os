/**
 * API Client with automatic authentication
 */

interface RequestOptions extends RequestInit {
  requiresAuth?: boolean;
}

class APIClient {
  private baseURL: string;

  constructor(baseURL: string = '/api/v1') {
    this.baseURL = baseURL;
  }

  private getAuthToken(): string | null {
    return localStorage.getItem('token');
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

  async request<T>(
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const { requiresAuth = true, ...fetchOptions } = options;

    const url = `${this.baseURL}${endpoint}`;
    const headers = {
      ...this.getHeaders(requiresAuth),
      ...fetchOptions.headers,
    };

    const response = await fetch(url, {
      ...fetchOptions,
      headers,
    });

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

  getCurrentUser: () => apiClient.get('/auth/me'),

  updateProfile: (data: any) => apiClient.put('/auth/me', data),

  changePassword: (oldPassword: string, newPassword: string) =>
    apiClient.post('/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    }),
};
