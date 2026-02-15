import type { FeishuConfig, MessageTemplate, NotificationPayload } from '../types/enterprise';

class FeishuService {
  private config: FeishuConfig;
  private tenantAccessToken: string | null = null;
  private tokenExpireTime: number = 0;

  constructor(config: FeishuConfig) {
    this.config = config;
  }

  /**
   * Get tenant access token from Feishu API
   */
  async getTenantAccessToken(): Promise<string> {
    if (this.tenantAccessToken && Date.now() < this.tokenExpireTime) {
      return this.tenantAccessToken;
    }

    try {
      // Mock implementation - replace with real API call
      // const response = await axios.post(
      //   'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
      //   {
      //     app_id: this.config.appId,
      //     app_secret: this.config.appSecret,
      //   }
      // );

      // Mock token for development
      this.tenantAccessToken = 'mock-feishu-tenant-token-' + Date.now();
      this.tokenExpireTime = Date.now() + 7200 * 1000; // 2 hours

      return this.tenantAccessToken;
    } catch (error) {
      console.error('Failed to get Feishu tenant access token:', error);
      throw error;
    }
  }

  /**
   * Send message to users
   */
  async sendMessage(payload: NotificationPayload): Promise<boolean> {
    if (!this.config.enabled) {
      console.log('Feishu is not enabled');
      return false;
    }

    try {
      await this.getTenantAccessToken();

      const messageData = {
        receive_id_type: 'user_id',
        user_id: payload.userIds?.[0] || '',
        msg_type: this.mapMessageType(payload.message.type),
        content: JSON.stringify(this.formatMessage(payload.message)),
      };

      // Mock implementation - replace with real API call
      // const response = await axios.post(
      //   'https://open.feishu.cn/open-apis/im/v1/messages',
      //   messageData,
      //   {
      //     headers: {
      //       Authorization: `Bearer ${token}`,
      //     },
      //     params: {
      //       receive_id_type: 'user_id',
      //     },
      //   }
      // );

      console.log('Feishu message sent (mock):', messageData);
      return true;
    } catch (error) {
      console.error('Failed to send Feishu message:', error);
      return false;
    }
  }

  /**
   * Send webhook notification
   */
  async sendWebhook(message: MessageTemplate): Promise<boolean> {
    if (!this.config.webhookUrl) {
      console.log('Feishu webhook URL not configured');
      return false;
    }

    try {
      const webhookData = {
        msg_type: this.mapMessageType(message.type),
        content: this.formatMessage(message),
      };

      // Mock implementation - replace with real API call
      // await axios.post(this.config.webhookUrl, webhookData);

      console.log('Feishu webhook sent (mock):', webhookData);
      return true;
    } catch (error) {
      console.error('Failed to send Feishu webhook:', error);
      return false;
    }
  }

  /**
   * Get user list from Feishu
   */
  async getUserList(): Promise<any[]> {
    try {
      await this.getTenantAccessToken();

      // Mock implementation - replace with real API call
      // const response = await axios.get(
      //   'https://open.feishu.cn/open-apis/contact/v3/users',
      //   {
      //     headers: {
      //       Authorization: `Bearer ${token}`,
      //     },
      //     params: {
      //       department_id: departmentId,
      //       page_size: 50,
      //     },
      //   }
      // );

      // Mock user list
      return [
        { user_id: 'user1', name: '张三', department_ids: ['dept1'] },
        { user_id: 'user2', name: '李四', department_ids: ['dept1'] },
      ];
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
