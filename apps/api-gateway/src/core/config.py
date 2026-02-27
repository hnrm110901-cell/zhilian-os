"""
配置管理
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

    # 应用配置
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # 数据库配置
    DATABASE_URL: str
    REDIS_URL: str

    # Redis Sentinel 配置（生产 HA 模式，留空则使用 REDIS_URL 直连）
    REDIS_SENTINEL_HOSTS: str = ""   # 逗号分隔，如 "sentinel1:26379,sentinel2:26379"
    REDIS_SENTINEL_MASTER: str = "mymaster"
    REDIS_SENTINEL_PASSWORD: str = ""
    REDIS_SENTINEL_DB: int = 0

    # AI/LLM配置
    LLM_PROVIDER: str = "deepseek"  # openai, anthropic, azure_openai, deepseek
    LLM_MODEL: str = "deepseek-chat"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com"  # For Azure OpenAI, DeepSeek or custom endpoints
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 2000
    LLM_ENABLED: bool = True  # 是否启用LLM（默认启用DeepSeek）

    # Legacy OpenAI config (for backward compatibility)
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = "https://api.openai.com/v1"
    MODEL_NAME: str = "gpt-4-turbo-preview"

    # Anthropic config
    ANTHROPIC_API_KEY: str = ""

    # 向量数据库配置
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""

    # 神经系统配置
    EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_DIMENSION: int = 384
    NEURAL_SYSTEM_ENABLED: bool = True

    # 联邦学习配置
    FL_MIN_STORES: int = 3
    FL_AGGREGATION_THRESHOLD: float = 0.8
    FL_LEARNING_RATE: float = 0.01

    # 企业微信配置
    WECHAT_CORP_ID: str = ""
    WECHAT_CORP_SECRET: str = ""
    WECHAT_AGENT_ID: str = ""
    WECHAT_TOKEN: str = ""  # 企业微信回调Token
    WECHAT_ENCODING_AES_KEY: str = ""  # 企业微信回调EncodingAESKey

    # 飞书配置
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""

    # 钉钉配置
    DINGTALK_APP_KEY: str = ""
    DINGTALK_APP_SECRET: str = ""

    # OAuth配置
    OAUTH_REDIRECT_URI: str = "http://localhost:5173/login"

    # 短信服务配置
    # 阿里云短信
    ALIYUN_ACCESS_KEY_ID: str = ""
    ALIYUN_ACCESS_KEY_SECRET: str = ""
    ALIYUN_SMS_SIGN_NAME: str = ""
    ALIYUN_SMS_TEMPLATE_CODE: str = ""

    # 腾讯云短信
    TENCENT_SECRET_ID: str = ""
    TENCENT_SECRET_KEY: str = ""
    TENCENT_SMS_APP_ID: str = ""
    TENCENT_SMS_SIGN_NAME: str = ""
    TENCENT_SMS_TEMPLATE_ID: str = ""

    # 语音服务配置
    # 百度语音
    BAIDU_APP_ID: str = ""
    BAIDU_API_KEY: str = ""
    BAIDU_SECRET_KEY: str = ""

    # 讯飞语音
    XUNFEI_APP_ID: str = ""
    XUNFEI_API_KEY: str = ""
    XUNFEI_API_SECRET: str = ""

    # Azure 语音服务
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = "eastasia"

    # 美团等位配置
    MEITUAN_DEVELOPER_ID: str = ""  # 美团开发者ID
    MEITUAN_SIGN_KEY: str = ""  # 美团签名密钥
    MEITUAN_BUSINESS_ID: str = "49"  # 到店餐饮排队业务ID

    # 外部API配置 - 奥琦玮供应链
    AOQIWEI_APP_KEY: str = ""
    AOQIWEI_APP_SECRET: str = ""
    AOQIWEI_BASE_URL: str = "http://openapi.acescm.cn"
    AOQIWEI_TIMEOUT: int = 30
    AOQIWEI_RETRY_TIMES: int = 3

    # 外部API配置 - 品智
    PINZHI_TOKEN: str = ""
    PINZHI_BASE_URL: str = ""
    PINZHI_TIMEOUT: int = 30
    PINZHI_RETRY_TIMES: int = 3

    # Celery配置
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # 安全配置
    SECRET_KEY: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION: int = 3600

    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # CORS配置
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # 业财税资金一体化扩展（FCT）
    FCT_ENABLED: bool = False
    FCT_MODE: str = "embedded"  # embedded | remote
    FCT_BASE_URL: str = ""  # mode=remote 时填独立服务 base_url
    FCT_EVENT_TARGET: str = "internal"  # internal | http | queue
    FCT_EVENT_HTTP_URL: str = ""  # event_target=http 时填写
    FCT_API_KEY: str = ""  # 独立部署时 API Key 认证，请求头 X-API-Key；空则独立服务不校验（仅建议内网使用）


# 创建全局配置实例
settings = Settings()
