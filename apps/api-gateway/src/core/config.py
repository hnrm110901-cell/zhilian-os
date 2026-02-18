"""
配置管理
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """应用配置"""

    # 应用配置
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # 数据库配置
    DATABASE_URL: str
    REDIS_URL: str

    # AI/LLM配置
    LLM_PROVIDER: str = "openai"  # openai, anthropic, azure_openai
    LLM_MODEL: str = "gpt-4-turbo-preview"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""  # For Azure OpenAI or custom endpoints
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 2000
    LLM_ENABLED: bool = False  # 是否启用LLM（默认关闭，使用模拟数据）

    # Legacy OpenAI config (for backward compatibility)
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = "https://api.openai.com/v1"
    MODEL_NAME: str = "gpt-4-turbo-preview"

    # Anthropic config
    ANTHROPIC_API_KEY: str = ""

    # 向量数据库配置
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""

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

    class Config:
        env_file = ".env"
        case_sensitive = True


# 创建全局配置实例
settings = Settings()
