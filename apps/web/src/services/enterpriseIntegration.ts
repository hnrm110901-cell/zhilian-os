import WeChatWorkService from './wechatWork';
import FeishuService from './feishu';
import type {
  WeChatWorkConfig,
  FeishuConfig,
  NotificationPayload,
  MessageTemplate,
} from '../types/enterprise';
import { defaultWeChatConfig, defaultFeishuConfig } from '../types/enterprise';

class EnterpriseIntegrationService {
  private wechatService: WeChatWorkService;
  private feishuService: FeishuService;

  constructor() {
    this.wechatService = new WeChatWorkService(defaultWeChatConfig);
    this.feishuService = new FeishuService(defaultFeishuConfig);
  }

  /**
   * Send notification to specified platform
   */
  async sendNotification(payload: NotificationPayload): Promise<boolean> {
    try {
      if (payload.platform === 'wechat') {
        return await this.wechatService.sendMessage(payload);
      } else if (payload.platform === 'feishu') {
        return await this.feishuService.sendMessage(payload);
      }
      return false;
    } catch (error) {
      console.error('Failed to send notification:', error);
      return false;
    }
  }

  /**
   * Send notification to all enabled platforms
   */
  async broadcastNotification(
    message: MessageTemplate,
    userIds?: string[]
  ): Promise<{ wechat: boolean; feishu: boolean }> {
    const results = {
      wechat: false,
      feishu: false,
    };

    if (this.wechatService.isEnabled()) {
      results.wechat = await this.wechatService.sendMessage({
        userIds,
        message,
        platform: 'wechat',
      });
    }

    if (this.feishuService.isEnabled()) {
      results.feishu = await this.feishuService.sendMessage({
        userIds,
        message,
        platform: 'feishu',
      });
    }

    return results;
  }

  /**
   * Send webhook to specified platform
   */
  async sendWebhook(
    platform: 'wechat' | 'feishu',
    message: MessageTemplate
  ): Promise<boolean> {
    try {
      if (platform === 'wechat') {
        return await this.wechatService.sendWebhook(message);
      } else if (platform === 'feishu') {
        return await this.feishuService.sendWebhook(message);
      }
      return false;
    } catch (error) {
      console.error('Failed to send webhook:', error);
      return false;
    }
  }

  /**
   * Get user list from specified platform
   */
  async getUserList(
    platform: 'wechat' | 'feishu'
  ): Promise<any[]> {
    try {
      if (platform === 'wechat') {
        return await this.wechatService.getUserList();
      } else if (platform === 'feishu') {
        return await this.feishuService.getUserList();
      }
      return [];
    } catch (error) {
      console.error('Failed to get user list:', error);
      return [];
    }
  }

  /**
   * Update WeChat Work configuration
   */
  updateWeChatConfig(config: Partial<WeChatWorkConfig>): void {
    this.wechatService.updateConfig(config);
  }

  /**
   * Update Feishu configuration
   */
  updateFeishuConfig(config: Partial<FeishuConfig>): void {
    this.feishuService.updateConfig(config);
  }

  /**
   * Get service status
   */
  getStatus(): {
    wechat: { enabled: boolean };
    feishu: { enabled: boolean };
  } {
    return {
      wechat: { enabled: this.wechatService.isEnabled() },
      feishu: { enabled: this.feishuService.isEnabled() },
    };
  }

  /**
   * Send order notification
   */
  async sendOrderNotification(
    orderId: string,
    status: string,
    platform?: 'wechat' | 'feishu'
  ): Promise<boolean> {
    const message: MessageTemplate = {
      title: '订单状态更新',
      content: `订单 ${orderId} 状态已更新为: ${status}`,
      type: 'card',
    };

    if (platform) {
      return await this.sendNotification({ message, platform });
    } else {
      const results = await this.broadcastNotification(message);
      return results.wechat || results.feishu;
    }
  }

  /**
   * Send inventory alert
   */
  async sendInventoryAlert(
    itemName: string,
    currentStock: number,
    platform?: 'wechat' | 'feishu'
  ): Promise<boolean> {
    const message: MessageTemplate = {
      title: '库存预警',
      content: `${itemName} 库存不足，当前库存: ${currentStock}`,
      type: 'card',
    };

    if (platform) {
      return await this.sendNotification({ message, platform });
    } else {
      const results = await this.broadcastNotification(message);
      return results.wechat || results.feishu;
    }
  }

  /**
   * Send service quality alert
   */
  async sendServiceAlert(
    reviewId: string,
    rating: number,
    platform?: 'wechat' | 'feishu'
  ): Promise<boolean> {
    const message: MessageTemplate = {
      title: '服务质量预警',
      content: `收到差评 (${rating}星)，评价ID: ${reviewId}，请及时处理`,
      type: 'card',
    };

    if (platform) {
      return await this.sendNotification({ message, platform });
    } else {
      const results = await this.broadcastNotification(message);
      return results.wechat || results.feishu;
    }
  }
}

export const enterpriseService = new EnterpriseIntegrationService();
export default enterpriseService;
