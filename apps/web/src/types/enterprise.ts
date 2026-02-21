export interface EnterpriseConfig {
  appId: string;
  appSecret: string;
  corpId?: string;
  agentId?: string;
  webhookUrl?: string;
  enabled: boolean;
}

export interface WeChatWorkConfig extends EnterpriseConfig {
  corpId: string;
  agentId: string;
}

export interface FeishuConfig extends EnterpriseConfig {
  appId: string;
  appSecret: string;
}

export interface MessageTemplate {
  title: string;
  content: string;
  url?: string;
  type: 'text' | 'markdown' | 'card';
}

export interface NotificationPayload {
  userIds?: string[];
  departmentIds?: string[];
  message: MessageTemplate;
  platform: 'wechat' | 'feishu';
}

export interface WebhookEvent {
  eventType: string;
  timestamp: number;
  data: Record<string, any>;
}

export const defaultWeChatConfig: WeChatWorkConfig = {
  appId: '',
  appSecret: '',
  corpId: '',
  agentId: '',
  webhookUrl: '',
  enabled: false,
};

export const defaultFeishuConfig: FeishuConfig = {
  appId: '',
  appSecret: '',
  webhookUrl: '',
  enabled: false,
};
