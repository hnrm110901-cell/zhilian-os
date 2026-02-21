import type { WeChatWorkConfig, MessageTemplate, NotificationPayload } from '../types/enterprise';

class WeChatWorkService {
  private config: WeChatWorkConfig;

  constructor(config: WeChatWorkConfig) {
    this.config = config;
  }

  /**
   * Send message to users via backend API
   */
  async sendMessage(payload: NotificationPayload): Promise<boolean> {
    if (!this.config.enabled) {
      console.log('WeChat Work is not enabled');
      return false;
    }

    try {
      const response = await fetch('/api/v1/enterprise/wechat/send-message', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
        body: JSON.stringify({
          content: payload.message.content,
          touser: payload.userIds?.join('|'),
          message_type: payload.message.type,
          title: payload.message.title,
          url: payload.message.url,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to send message');
      }

      const result = await response.json();
      return result.success;
    } catch (error) {
      console.error('Failed to send WeChat Work message:', error);
      return false;
    }
  }

  /**
   * Send webhook notification via backend API
   */
  async sendWebhook(message: MessageTemplate): Promise<boolean> {
    if (!this.config.webhookUrl) {
      console.log('WeChat Work webhook URL not configured');
      return false;
    }

    try {
      const response = await fetch('/api/v1/enterprise/wechat/send-message', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
        body: JSON.stringify({
          content: message.content,
          message_type: message.type,
          title: message.title,
          url: message.url,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to send webhook');
      }

      return true;
    } catch (error) {
      console.error('Failed to send WeChat Work webhook:', error);
      return false;
    }
  }

  /**
   * Get user list from backend API
   */
  async getUserList(): Promise<any[]> {
    try {
      const response = await fetch('/api/v1/enterprise/wechat/users?department_id=1', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to get user list');
      }

      const result = await response.json();
      return result.data || [];
    } catch (error) {
      console.error('Failed to get WeChat Work user list:', error);
      return [];
    }
  }

  /**
   * Format message based on type
   * @private
   */
  // @ts-ignore - Reserved for future use
  private formatMessage(message: MessageTemplate): any {
    switch (message.type) {
      case 'text':
        return { content: message.content };
      case 'markdown':
        return { content: `# ${message.title}\n\n${message.content}` };
      case 'card':
        return {
          title: message.title,
          description: message.content,
          url: message.url,
        };
      default:
        return { content: message.content };
    }
  }

  /**
   * Update configuration
   */
  updateConfig(config: Partial<WeChatWorkConfig>): void {
    this.config = { ...this.config, ...config };
  }

  /**
   * Check if service is enabled
   */
  isEnabled(): boolean {
    return this.config.enabled;
  }
}

export default WeChatWorkService;
