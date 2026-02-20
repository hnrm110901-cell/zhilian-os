import type { FeishuConfig, MessageTemplate, NotificationPayload } from '../types/enterprise';

class FeishuService {
  private config: FeishuConfig;
  private tenantAccessToken: string | null = null;
  private tokenExpireTime: number = 0;

  constructor(config: FeishuConfig) {
    this.config = config;
  }

  /**
   * Get tenant access token - handled by backend
   * Frontend doesn't need to manage tokens directly
   */
  private async getTenantAccessToken(): Promise<string> {
    // Token management is handled by backend
    return 'managed-by-backend';
  }

  /**
   * Send message to users via backend API
   */
  async sendMessage(payload: NotificationPayload): Promise<boolean> {
    if (!this.config.enabled) {
      console.log('Feishu is not enabled');
      return false;
    }

    try {
      const response = await fetch('/api/v1/enterprise/feishu/send-message', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
        body: JSON.stringify({
          content: payload.message.content,
          receive_id: payload.userIds?.[0] || '',
          receive_id_type: 'user_id',
          message_type: this.mapMessageType(payload.message.type),
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to send message');
      }

      const result = await response.json();
      return result.success;
    } catch (error) {
      console.error('Failed to send Feishu message:', error);
      return false;
    }
  }

  /**
   * Send webhook notification via backend API
   */
  async sendWebhook(message: MessageTemplate): Promise<boolean> {
    if (!this.config.webhookUrl) {
      console.log('Feishu webhook URL not configured');
      return false;
    }

    try {
      const response = await fetch('/api/v1/enterprise/feishu/send-message', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
        body: JSON.stringify({
          content: message.content,
          receive_id: '@all',
          receive_id_type: 'user_id',
          message_type: this.mapMessageType(message.type),
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to send webhook');
      }

      return true;
    } catch (error) {
      console.error('Failed to send Feishu webhook:', error);
      return false;
    }
  }

  /**
   * Get user list from backend API
   */
  async getUserList(): Promise<any[]> {
    try {
      const response = await fetch('/api/v1/enterprise/feishu/users?department_id=0', {
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
      console.error('Failed to get Feishu user list:', error);
      return [];
    }
  }

  /**
   * Send batch messages
   */
  async sendBatchMessage(payload: NotificationPayload): Promise<boolean> {
    if (!payload.userIds || payload.userIds.length === 0) {
      return false;
    }

    try {
      const results = await Promise.all(
        payload.userIds.map(userId =>
          this.sendMessage({
            ...payload,
            userIds: [userId],
          })
        )
      );

      return results.every(result => result);
    } catch (error) {
      console.error('Failed to send batch messages:', error);
      return false;
    }
  }

  /**
   * Map message type to Feishu format
   */
  private mapMessageType(type: string): string {
    const typeMap: Record<string, string> = {
      text: 'text',
      markdown: 'post',
      card: 'interactive',
    };
    return typeMap[type] || 'text';
  }

  /**
   * Format message based on type
   */
  private formatMessage(message: MessageTemplate): any {
    switch (message.type) {
      case 'text':
        return { text: message.content };
      case 'markdown':
        return {
          post: {
            zh_cn: {
              title: message.title,
              content: [[{ tag: 'text', text: message.content }]],
            },
          },
        };
      case 'card':
        return {
          config: { wide_screen_mode: true },
          header: {
            title: { tag: 'plain_text', content: message.title },
          },
          elements: [
            {
              tag: 'div',
              text: { tag: 'plain_text', content: message.content },
            },
          ],
        };
      default:
        return { text: message.content };
    }
  }

  /**
   * Update configuration
   */
  updateConfig(config: Partial<FeishuConfig>): void {
    this.config = { ...this.config, ...config };
    this.tenantAccessToken = null; // Reset token
  }

  /**
   * Check if service is enabled
   */
  isEnabled(): boolean {
    return this.config.enabled;
  }
}

export default FeishuService;
