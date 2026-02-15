import type { WeChatWorkConfig, MessageTemplate, NotificationPayload } from '../types/enterprise';

class WeChatWorkService {
  private config: WeChatWorkConfig;
  private accessToken: string | null = null;
  private tokenExpireTime: number = 0;

  constructor(config: WeChatWorkConfig) {
    this.config = config;
  }

  /**
   * Get access token from WeChat Work API
   */
  async getAccessToken(): Promise<string> {
    if (this.accessToken && Date.now() < this.tokenExpireTime) {
      return this.accessToken;
    }

    try {
      // Mock implementation - replace with real API call
      // const response = await axios.get(
      //   `https://qyapi.weixin.qq.com/cgi-bin/gettoken`,
      //   {
      //     params: {
      //       corpid: this.config.corpId,
      //       corpsecret: this.config.appSecret,
      //     },
      //   }
      // );

      // Mock token for development
      this.accessToken = 'mock-wechat-access-token-' + Date.now();
      this.tokenExpireTime = Date.now() + 7200 * 1000; // 2 hours

      return this.accessToken;
    } catch (error) {
      console.error('Failed to get WeChat Work access token:', error);
      throw error;
    }
  }

  /**
   * Send message to users
   */
  async sendMessage(payload: NotificationPayload): Promise<boolean> {
    if (!this.config.enabled) {
      console.log('WeChat Work is not enabled');
      return false;
    }

    try {
      await this.getAccessToken();

      const messageData = {
        touser: payload.userIds?.join('|') || '@all',
        msgtype: payload.message.type,
        agentid: this.config.agentId,
        [payload.message.type]: this.formatMessage(payload.message),
      };

      // Mock implementation - replace with real API call
      // const response = await axios.post(
      //   `https://qyapi.weixin.qq.com/cgi-bin/message/send`,
      //   messageData,
      //   {
      //     params: { access_token: token },
      //   }
      // );

      console.log('WeChat Work message sent (mock):', messageData);
      return true;
    } catch (error) {
      console.error('Failed to send WeChat Work message:', error);
      return false;
    }
  }

  /**
   * Send webhook notification
   */
  async sendWebhook(message: MessageTemplate): Promise<boolean> {
    if (!this.config.webhookUrl) {
      console.log('WeChat Work webhook URL not configured');
      return false;
    }

    try {
      const webhookData = {
        msgtype: message.type,
        [message.type]: this.formatMessage(message),
      };

      // Mock implementation - replace with real API call
      // await axios.post(this.config.webhookUrl, webhookData);

      console.log('WeChat Work webhook sent (mock):', webhookData);
      return true;
    } catch (error) {
      console.error('Failed to send WeChat Work webhook:', error);
      return false;
    }
  }

  /**
   * Get user list from WeChat Work
   */
  async getUserList(): Promise<any[]> {
    try {
      await this.getAccessToken();

      // Mock implementation - replace with real API call
      // const response = await axios.get(
      //   `https://qyapi.weixin.qq.com/cgi-bin/user/list`,
      //   {
      //     params: {
      //       access_token: token,
      //       department_id: departmentId || 1,
      //     },
      //   }
      // );

      // Mock user list
      return [
        { userid: 'user1', name: '张三', department: [1] },
        { userid: 'user2', name: '李四', department: [1] },
      ];
    } catch (error) {
      console.error('Failed to get WeChat Work user list:', error);
      return [];
    }
  }

  /**
   * Format message based on type
   */
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
    this.accessToken = null; // Reset token
  }

  /**
   * Check if service is enabled
   */
  isEnabled(): boolean {
    return this.config.enabled;
  }
}

export default WeChatWorkService;
