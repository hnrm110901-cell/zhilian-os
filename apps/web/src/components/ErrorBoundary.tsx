import React from 'react';
import { Button, Result } from 'antd';

interface Props {
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorPath: string;
}

class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorPath: '' };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error, errorPath: window.location.pathname };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info);
  }

  componentDidUpdate() {
    // 路由变化时自动重置错误状态
    if (this.state.hasError && window.location.pathname !== this.state.errorPath) {
      this.setState({ hasError: false, error: null, errorPath: '' });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <Result
          status="error"
          title="页面出错了"
          subTitle={this.state.error?.message || '未知错误'}
          extra={
            <Button type="primary" onClick={() => this.setState({ hasError: false, error: null, errorPath: '' })}>
              重试
            </Button>
          }
        />
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
