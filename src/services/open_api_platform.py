"""
Open API Platform Service
开放API平台服务

Phase 5: 生态扩展期 (Ecosystem Expansion Period)
Enables third-party developers to build on top of Zhilian OS
"""

from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
from sqlalchemy.orm import Session
import secrets
import hashlib
import hmac


class DeveloperTier(Enum):
    """Developer tier enum"""
    FREE = "free"  # 免费版
    BASIC = "basic"  # 基础版
    PRO = "pro"  # 专业版
    ENTERPRISE = "enterprise"  # 企业版


class PluginCategory(Enum):
    """Plugin category enum"""
    ANALYTICS = "analytics"  # 数据分析
    MARKETING = "marketing"  # 营销工具
    OPERATIONS = "operations"  # 运营管理
    FINANCE = "finance"  # 财务管理
    INTEGRATION = "integration"  # 系统集成
    AI = "ai"  # AI增强


class PluginStatus(Enum):
    """Plugin status enum"""
    DRAFT = "draft"  # 草稿
    PENDING_REVIEW = "pending_review"  # 待审核
    APPROVED = "approved"  # 已批准
    REJECTED = "rejected"  # 已拒绝
    PUBLISHED = "published"  # 已发布
    SUSPENDED = "suspended"  # 已暂停


@dataclass
class Developer:
    """Third-party developer"""
    developer_id: str
    name: str
    email: str
    company: Optional[str]
    tier: DeveloperTier
    api_key: str
    api_secret: str
    rate_limit: int  # requests per minute
    created_at: datetime
    verified: bool


@dataclass
class Plugin:
    """Third-party plugin"""
    plugin_id: str
    developer_id: str
    name: str
    description: str
    category: PluginCategory
    version: str
    status: PluginStatus
    price: float  # Monthly subscription price
    revenue_share: float  # Platform revenue share (0-1)
    installs: int
    rating: float  # 0-5
    webhook_url: Optional[str]
    created_at: datetime
    updated_at: datetime


@dataclass
class APIUsage:
    """API usage record"""
    developer_id: str
    endpoint: str
    method: str
    timestamp: datetime
    response_time_ms: int
    status_code: int
    error: Optional[str]


class OpenAPIPlatform:
    """
    Open API Platform Service
    开放API平台服务

    Provides platform capabilities for third-party developers:
    1. Developer registration and API key management
    2. Plugin marketplace
    3. Revenue sharing
    4. Rate limiting and usage tracking
    5. Webhook integration

    Key features:
    - Secure API authentication
    - Tiered access control
    - Plugin lifecycle management
    - Revenue distribution
    - Usage analytics
    """

    def __init__(self, db: Session):
        self.db = db
        # Store developers
        self.developers: Dict[str, Developer] = {}
        # Store plugins
        self.plugins: Dict[str, Plugin] = {}
        # Store API usage
        self.api_usage: List[APIUsage] = []
        # Rate limit tracking
        self.rate_limit_tracker: Dict[str, List[datetime]] = {}

    def register_developer(
        self,
        name: str,
        email: str,
        company: Optional[str] = None,
        tier: DeveloperTier = DeveloperTier.FREE
    ) -> Developer:
        """
        Register a new developer
        注册新开发者

        Args:
            name: Developer name
            email: Developer email
            company: Company name (optional)
            tier: Developer tier (default: FREE)

        Returns:
            Developer with API credentials
        """
        developer_id = f"dev_{secrets.token_urlsafe(16)}"
        api_key = f"zlos_{secrets.token_urlsafe(32)}"
        api_secret = secrets.token_urlsafe(64)

        # Set rate limit based on tier
        rate_limits = {
            DeveloperTier.FREE: 60,  # 60 req/min
            DeveloperTier.BASIC: 300,  # 300 req/min
            DeveloperTier.PRO: 1000,  # 1000 req/min
            DeveloperTier.ENTERPRISE: 5000  # 5000 req/min
        }

        developer = Developer(
            developer_id=developer_id,
            name=name,
            email=email,
            company=company,
            tier=tier,
            api_key=api_key,
            api_secret=api_secret,
            rate_limit=rate_limits[tier],
            created_at=datetime.utcnow(),
            verified=False
        )

        self.developers[developer_id] = developer

        return developer

    def authenticate_request(
        self,
        api_key: str,
        signature: str,
        timestamp: str,
        request_body: str
    ) -> Optional[Developer]:
        """
        Authenticate API request
        验证API请求

        Uses HMAC-SHA256 signature verification.

        Args:
            api_key: Developer API key
            signature: Request signature
            timestamp: Request timestamp
            request_body: Request body

        Returns:
            Developer if authenticated, None otherwise
        """
        # Find developer by API key
        developer = None
        for dev in self.developers.values():
            if dev.api_key == api_key:
                developer = dev
                break

        if not developer:
            return None

        # Verify timestamp (prevent replay attacks)
        try:
            request_time = datetime.fromisoformat(timestamp)
            if abs((datetime.utcnow() - request_time).total_seconds()) > 300:
                # Request older than 5 minutes
                return None
        except ValueError:
            return None

        # Verify signature
        message = f"{timestamp}:{request_body}"
        expected_signature = hmac.new(
            developer.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_signature):
            return None

        return developer

    def check_rate_limit(
        self,
        developer_id: str
    ) -> bool:
        """
        Check if developer has exceeded rate limit
        检查开发者是否超过速率限制

        Args:
            developer_id: Developer identifier

        Returns:
            True if within limit, False if exceeded
        """
        developer = self.developers.get(developer_id)
        if not developer:
            return False

        now = datetime.utcnow()
        one_minute_ago = now - timedelta(minutes=1)

        # Get recent requests
        if developer_id not in self.rate_limit_tracker:
            self.rate_limit_tracker[developer_id] = []

        recent_requests = [
            ts for ts in self.rate_limit_tracker[developer_id]
            if ts > one_minute_ago
        ]

        # Update tracker
        self.rate_limit_tracker[developer_id] = recent_requests

        # Check limit
        if len(recent_requests) >= developer.rate_limit:
            return False

        # Add current request
        self.rate_limit_tracker[developer_id].append(now)
        return True

    def submit_plugin(
        self,
        developer_id: str,
        name: str,
        description: str,
        category: PluginCategory,
        version: str,
        price: float,
        webhook_url: Optional[str] = None
    ) -> Plugin:
        """
        Submit plugin for review
        提交插件审核

        Args:
            developer_id: Developer identifier
            name: Plugin name
            description: Plugin description
            category: Plugin category
            version: Plugin version
            price: Monthly subscription price
            webhook_url: Webhook URL for callbacks

        Returns:
            Plugin with pending review status
        """
        plugin_id = f"plugin_{secrets.token_urlsafe(16)}"

        # Calculate revenue share based on developer tier
        developer = self.developers.get(developer_id)
        if not developer:
            raise ValueError("Developer not found")

        revenue_shares = {
            DeveloperTier.FREE: 0.7,  # 70% to developer
            DeveloperTier.BASIC: 0.75,  # 75% to developer
            DeveloperTier.PRO: 0.80,  # 80% to developer
            DeveloperTier.ENTERPRISE: 0.85  # 85% to developer
        }

        plugin = Plugin(
            plugin_id=plugin_id,
            developer_id=developer_id,
            name=name,
            description=description,
            category=category,
            version=version,
            status=PluginStatus.PENDING_REVIEW,
            price=price,
            revenue_share=revenue_shares[developer.tier],
            installs=0,
            rating=0.0,
            webhook_url=webhook_url,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.plugins[plugin_id] = plugin

        return plugin

    def review_plugin(
        self,
        plugin_id: str,
        approved: bool,
        reason: Optional[str] = None
    ) -> Plugin:
        """
        Review plugin submission
        审核插件提交

        Args:
            plugin_id: Plugin identifier
            approved: Whether to approve the plugin
            reason: Reason for rejection (if not approved)

        Returns:
            Updated plugin
        """
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            raise ValueError("Plugin not found")

        if approved:
            plugin.status = PluginStatus.APPROVED
        else:
            plugin.status = PluginStatus.REJECTED

        plugin.updated_at = datetime.utcnow()

        return plugin

    def publish_plugin(
        self,
        plugin_id: str
    ) -> Plugin:
        """
        Publish approved plugin to marketplace
        发布已批准的插件到市场

        Args:
            plugin_id: Plugin identifier

        Returns:
            Published plugin
        """
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            raise ValueError("Plugin not found")

        if plugin.status != PluginStatus.APPROVED:
            raise ValueError("Plugin must be approved before publishing")

        plugin.status = PluginStatus.PUBLISHED
        plugin.updated_at = datetime.utcnow()

        return plugin

    def install_plugin(
        self,
        plugin_id: str,
        store_id: str
    ) -> Dict[str, Any]:
        """
        Install plugin for a store
        为门店安装插件

        Args:
            plugin_id: Plugin identifier
            store_id: Store identifier

        Returns:
            Installation details
        """
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            raise ValueError("Plugin not found")

        if plugin.status != PluginStatus.PUBLISHED:
            raise ValueError("Plugin is not published")

        # Increment install count
        plugin.installs += 1

        # Trigger webhook if configured
        if plugin.webhook_url:
            self._trigger_webhook(
                plugin.webhook_url,
                {
                    "event": "plugin_installed",
                    "plugin_id": plugin_id,
                    "store_id": store_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        return {
            "plugin_id": plugin_id,
            "store_id": store_id,
            "installed_at": datetime.utcnow().isoformat(),
            "monthly_price": plugin.price
        }

    def rate_plugin(
        self,
        plugin_id: str,
        rating: float
    ) -> Plugin:
        """
        Rate a plugin
        为插件评分

        Args:
            plugin_id: Plugin identifier
            rating: Rating (0-5)

        Returns:
            Updated plugin
        """
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            raise ValueError("Plugin not found")

        if not 0 <= rating <= 5:
            raise ValueError("Rating must be between 0 and 5")

        # Simple average (should use weighted average in production)
        if plugin.rating == 0:
            plugin.rating = rating
        else:
            plugin.rating = (plugin.rating + rating) / 2

        plugin.updated_at = datetime.utcnow()

        return plugin

    def get_marketplace_plugins(
        self,
        category: Optional[PluginCategory] = None,
        sort_by: str = "installs"
    ) -> List[Plugin]:
        """
        Get plugins from marketplace
        获取市场插件

        Args:
            category: Filter by category (optional)
            sort_by: Sort by field (installs, rating, price)

        Returns:
            List of published plugins
        """
        # Filter published plugins
        published_plugins = [
            p for p in self.plugins.values()
            if p.status == PluginStatus.PUBLISHED
        ]

        # Filter by category if specified
        if category:
            published_plugins = [
                p for p in published_plugins
                if p.category == category
            ]

        # Sort
        if sort_by == "installs":
            published_plugins.sort(key=lambda p: p.installs, reverse=True)
        elif sort_by == "rating":
            published_plugins.sort(key=lambda p: p.rating, reverse=True)
        elif sort_by == "price":
            published_plugins.sort(key=lambda p: p.price)

        return published_plugins

    def calculate_revenue(
        self,
        plugin_id: str,
        period_start: datetime,
        period_end: datetime
    ) -> Dict[str, float]:
        """
        Calculate revenue for plugin
        计算插件收入

        Args:
            plugin_id: Plugin identifier
            period_start: Period start date
            period_end: Period end date

        Returns:
            Revenue breakdown
        """
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            raise ValueError("Plugin not found")

        # Calculate days in period
        days = (period_end - period_start).days

        # Calculate revenue (simplified)
        total_revenue = plugin.price * plugin.installs * (days / 30)
        developer_revenue = total_revenue * plugin.revenue_share
        platform_revenue = total_revenue * (1 - plugin.revenue_share)

        return {
            "total_revenue": total_revenue,
            "developer_revenue": developer_revenue,
            "platform_revenue": platform_revenue,
            "installs": plugin.installs,
            "price": plugin.price,
            "revenue_share": plugin.revenue_share
        }

    def get_developer_analytics(
        self,
        developer_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        Get analytics for developer
        获取开发者分析数据

        Args:
            developer_id: Developer identifier
            start_date: Start date
            end_date: End date

        Returns:
            Analytics data
        """
        developer = self.developers.get(developer_id)
        if not developer:
            raise ValueError("Developer not found")

        # Get developer's plugins
        developer_plugins = [
            p for p in self.plugins.values()
            if p.developer_id == developer_id
        ]

        # Calculate metrics
        total_installs = sum(p.installs for p in developer_plugins)
        avg_rating = sum(p.rating for p in developer_plugins) / len(developer_plugins) if developer_plugins else 0

        # Calculate total revenue
        total_revenue = sum(
            self.calculate_revenue(p.plugin_id, start_date, end_date)["developer_revenue"]
            for p in developer_plugins
        )

        # Get API usage
        api_calls = [
            usage for usage in self.api_usage
            if usage.developer_id == developer_id
            and start_date <= usage.timestamp <= end_date
        ]

        return {
            "developer_id": developer_id,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "plugins": {
                "total": len(developer_plugins),
                "published": len([p for p in developer_plugins if p.status == PluginStatus.PUBLISHED]),
                "total_installs": total_installs,
                "avg_rating": avg_rating
            },
            "revenue": {
                "total": total_revenue,
                "currency": "CNY"
            },
            "api_usage": {
                "total_calls": len(api_calls),
                "avg_response_time_ms": sum(u.response_time_ms for u in api_calls) / len(api_calls) if api_calls else 0,
                "error_rate": len([u for u in api_calls if u.status_code >= 400]) / len(api_calls) if api_calls else 0
            }
        }

    def _trigger_webhook(
        self,
        webhook_url: str,
        payload: Dict[str, Any]
    ):
        """Trigger webhook (simplified)"""
        # In production, use async HTTP client
        pass

    def log_api_usage(
        self,
        developer_id: str,
        endpoint: str,
        method: str,
        response_time_ms: int,
        status_code: int,
        error: Optional[str] = None
    ):
        """Log API usage"""
        usage = APIUsage(
            developer_id=developer_id,
            endpoint=endpoint,
            method=method,
            timestamp=datetime.utcnow(),
            response_time_ms=response_time_ms,
            status_code=status_code,
            error=error
        )
        self.api_usage.append(usage)
