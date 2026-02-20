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

    # 飞书配置
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""

    # 外部API配置 - 奥琦韦
    AOQIWEI_API_KEY: str = ""
    AOQIWEI_BASE_URL: str = "https://api.aoqiwei.com"
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


# 创建全局配置实例
settings = Settings()
