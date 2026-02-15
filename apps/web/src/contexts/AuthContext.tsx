import React, { createContext, useContext, useState, useEffect } from 'react';
import { message } from 'antd';

interface User {
  id: string;
  username: string;
  email: string;
  role: 'admin' | 'manager' | 'staff';
  avatar?: string;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => void;
  updateUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const storedUser = localStorage.getItem('user');
    const token = localStorage.getItem('token');

    if (storedUser && token) {
      try {
        setUser(JSON.parse(storedUser));
      } catch (error) {
        console.error('Failed to parse stored user:', error);
        localStorage.removeItem('user');
        localStorage.removeItem('token');
      }
    }

    setIsLoading(false);
  }, []);

  const login = async (username: string, password: string): Promise<boolean> => {
    try {
      // Mock authentication - replace with real API call
      if (username === 'admin' && password === 'admin123') {
        const mockUser: User = {
          id: '1',
          username: 'admin',
          email: 'admin@zhilian.com',
          role: 'admin',
          avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=admin'
        };

        const mockToken = 'mock-jwt-token-' + Date.now();

        setUser(mockUser);
        localStorage.setItem('user', JSON.stringify(mockUser));
        localStorage.setItem('token', mockToken);

        message.success('登录成功');
        return true;
      } else if (username === 'manager' && password === 'manager123') {
        const mockUser: User = {
          id: '2',
          username: 'manager',
          email: 'manager@zhilian.com',
          role: 'manager',
          avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=manager'
        };

        const mockToken = 'mock-jwt-token-' + Date.now();

        setUser(mockUser);
        localStorage.setItem('user', JSON.stringify(mockUser));
        localStorage.setItem('token', mockToken);

        message.success('登录成功');
        return true;
      } else if (username === 'staff' && password === 'staff123') {
        const mockUser: User = {
          id: '3',
          username: 'staff',
          email: 'staff@zhilian.com',
          role: 'staff',
          avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=staff'
        };

        const mockToken = 'mock-jwt-token-' + Date.now();

        setUser(mockUser);
        localStorage.setItem('user', JSON.stringify(mockUser));
        localStorage.setItem('token', mockToken);

        message.success('登录成功');
        return true;
      } else {
        message.error('用户名或密码错误');
        return false;
      }
    } catch (error) {
      console.error('Login error:', error);
      message.error('登录失败，请稍后重试');
      return false;
    }
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('user');
    localStorage.removeItem('token');
    message.success('已退出登录');
  };

  const updateUser = (updatedUser: User) => {
    setUser(updatedUser);
    localStorage.setItem('user', JSON.stringify(updatedUser));
  };

  const value: AuthContextType = {
    user,
    isAuthenticated: !!user,
    isLoading,
    login,
    logout,
    updateUser
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export type { User };
