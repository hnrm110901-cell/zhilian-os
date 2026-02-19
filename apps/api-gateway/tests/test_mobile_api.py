"""
Mobile API Tests
测试移动端API接口
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from src.main import app
from src.models.user import User, UserRole
from src.core.dependencies import get_current_active_user


@pytest.fixture
def mock_user():
    """Mock authenticated user"""
    user = MagicMock(spec=User)
    user.id = "test-user-123"
    user.username = "testuser"
    user.full_name = "Test User"
    user.role = UserRole.STORE_MANAGER
    user.store_id = "store-123"
    return user


@pytest.fixture
def client(mock_user):
    """Test client fixture with auth override"""
    def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_active_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def client_no_auth():
    """Test client without authentication"""
    return TestClient(app)


class TestMobileDashboard:
    """测试移动端仪表盘接口"""

    @patch("src.api.mobile.store_service")
    @patch("src.api.mobile.notification_service")
    @patch("src.api.mobile.pos_service")
    def test_get_mobile_dashboard_success(
        self,
        mock_pos_service,
        mock_notification_service,
        mock_store_service,
        client,
        mock_user,
    ):
        """测试成功获取移动端仪表盘数据"""
        # Setup mocks
        mock_store = MagicMock()
        mock_store.name = "Test Store"
        mock_store_service.get_store = AsyncMock(return_value=mock_store)

        mock_notification_service.get_unread_count = AsyncMock(return_value=5)
        mock_notification_service.get_user_notifications = AsyncMock(return_value=[])

        mock_pos_service.query_orders = AsyncMock(return_value={
            "orders": [
                {"realPrice": 10000, "people": 2},
                {"realPrice": 15000, "people": 3},
            ]
        })

        # Make request
        response = client.get("/api/v1/mobile/dashboard")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert "notifications" in data
        assert "quick_actions" in data
        assert "today_stats" in data
        assert data["user"]["username"] == "testuser"
        assert data["notifications"]["unread_count"] == 5
        assert len(data["quick_actions"]) > 0
        assert data["today_stats"]["orders"] == 2
        assert data["today_stats"]["revenue"] == 25000
        assert data["today_stats"]["customers"] == 5

    def test_get_mobile_dashboard_unauthorized(self, client_no_auth):
        """测试未授权访问仪表盘"""
        response = client_no_auth.get("/api/v1/mobile/dashboard")
        assert response.status_code in [401, 403]


class TestMobileNotifications:
    """测试移动端通知接口"""

    @patch("src.api.mobile.notification_service")
    def test_get_notifications_summary(
        self,
        mock_notification_service,
        client,
        mock_user,
    ):
        """测试获取通知摘要"""
        mock_notification_service.get_unread_count = AsyncMock(return_value=3)

        mock_notification = MagicMock()
        mock_notification.id = "notif-1"
        mock_notification.title = "Test Notification"
        mock_notification.message = "This is a test message"
        mock_notification.type = "info"
        mock_notification.priority = "normal"
        mock_notification.created_at = datetime.now()

        mock_notification_service.get_user_notifications = AsyncMock(
            return_value=[mock_notification]
        )

        response = client.get("/api/v1/mobile/notifications/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["unread_count"] == 3
        assert len(data["notifications"]) == 1
        assert data["notifications"][0]["title"] == "Test Notification"

    @patch("src.api.mobile.notification_service")
    def test_batch_mark_notifications_read(
        self,
        mock_notification_service,
        client,
        mock_user,
    ):
        """测试批量标记通知为已读"""
        mock_notification_service.mark_as_read = AsyncMock(return_value=True)

        notification_ids = ["notif-1", "notif-2", "notif-3"]
        response = client.post(
            "/api/v1/mobile/batch/mark-read",
            json=notification_ids,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["marked_count"] == 3
        assert data["total"] == 3


class TestMobileOrders:
    """测试移动端订单接口"""

    
    @patch("src.api.mobile.pos_service")
    def test_get_today_orders_success(
        self,
        mock_pos_service,
        
        client,
        mock_user,
    ):
        """测试成功获取今日订单"""
        
        mock_pos_service.query_orders = AsyncMock(return_value={
            "orders": [
                {
                    "billId": "order-1",
                    "billNo": "20260219001",
                    "tableNo": "A01",
                    "people": 2,
                    "realPrice": 12800,
                    "billStatus": 1,
                    "payTime": "2026-02-19 12:30:00",
                },
                {
                    "billId": "order-2",
                    "billNo": "20260219002",
                    "tableNo": "B05",
                    "people": 4,
                    "realPrice": 25600,
                    "billStatus": 1,
                    "openTime": "2026-02-19 13:00:00",
                },
            ]
        })

        response = client.get("/api/v1/mobile/orders/today", )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["orders"]) == 2
        assert data["orders"][0]["order_no"] == "20260219001"
        assert data["orders"][0]["amount"] == 128.0
        assert data["orders"][1]["table_no"] == "B05"

    
    @patch("src.api.mobile.pos_service")
    def test_get_today_orders_error(
        self,
        mock_pos_service,
        
        client,
        mock_user,
    ):
        """测试获取今日订单失败"""
        
        mock_pos_service.query_orders = AsyncMock(side_effect=Exception("POS service error"))

        response = client.get("/api/v1/mobile/orders/today", )

        assert response.status_code == 500
        assert "获取今日订单失败" in response.json()["detail"]


class TestMobileMenu:
    """测试移动端菜单接口"""

    
    @patch("src.api.mobile.pos_service")
    def test_get_menu_categories(
        self,
        mock_pos_service,
        
        client,
        mock_user,
    ):
        """测试获取菜单类别"""
        
        mock_pos_service.get_dish_categories = AsyncMock(return_value=[
            {"rcId": 1, "rcNAME": "热菜", "fatherId": 0},
            {"rcId": 2, "rcNAME": "凉菜", "fatherId": 0},
        ])

        response = client.get("/api/v1/mobile/menu/categories", )

        assert response.status_code == 200
        data = response.json()
        assert len(data["categories"]) == 2
        assert data["categories"][0]["name"] == "热菜"

    
    @patch("src.api.mobile.pos_service")
    def test_get_menu_dishes(
        self,
        mock_pos_service,
        
        client,
        mock_user,
    ):
        """测试获取菜品列表"""
        
        mock_pos_service.get_dishes = AsyncMock(return_value=[
            {
                "dishesId": 1,
                "dishesName": "宫保鸡丁",
                "dishPrice": 3800,
                "rcId": 1,
                "unit": "份",
                "isRecommend": 1,
            },
            {
                "dishesId": 2,
                "dishesName": "麻婆豆腐",
                "dishPrice": 2800,
                "rcId": 1,
                "unit": "份",
                "isRecommend": 0,
            },
        ])

        response = client.get("/api/v1/mobile/menu/dishes", )

        assert response.status_code == 200
        data = response.json()
        assert len(data["dishes"]) == 2
        assert data["dishes"][0]["name"] == "宫保鸡丁"
        assert data["dishes"][0]["is_recommend"] is True

    
    @patch("src.api.mobile.pos_service")
    def test_get_menu_dishes_filtered(
        self,
        mock_pos_service,
        
        client,
        mock_user,
    ):
        """测试按类别过滤菜品"""
        
        mock_pos_service.get_dishes = AsyncMock(return_value=[
            {"dishesId": 1, "dishesName": "宫保鸡丁", "dishPrice": 3800, "rcId": 1, "unit": "份", "isRecommend": 1},
            {"dishesId": 2, "dishesName": "凉拌黄瓜", "dishPrice": 1800, "rcId": 2, "unit": "份", "isRecommend": 0},
        ])

        response = client.get("/api/v1/mobile/menu/dishes?category_id=1", )

        assert response.status_code == 200
        data = response.json()
        assert len(data["dishes"]) == 1
        assert data["dishes"][0]["name"] == "宫保鸡丁"


class TestMobileHealth:
    """测试移动端健康检查"""

    def test_mobile_health_check(self, client):
        """测试移动端健康检查接口"""
        response = client.get("/api/v1/mobile/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert data["version"] == "1.0.0"


class TestMobileFeedback:
    """测试移动端反馈接口"""

    
    def test_submit_feedback(
        self,
        
        client,
        mock_user,
    ):
        """测试提交反馈"""
        

        feedback = {
            "type": "bug",
            "content": "发现一个小问题",
        }

        response = client.post(
            "/api/v1/mobile/feedback",
            json=feedback,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "感谢" in data["message"]


class TestMobileQuickActions:
    """测试快捷操作功能"""

    def test_quick_actions_for_store_manager(self):
        """测试店长角色的快捷操作"""
        from src.api.mobile import _get_quick_actions_by_role

        actions = _get_quick_actions_by_role("store_manager")
        assert len(actions) == 4
        assert any(action["id"] == "dashboard" for action in actions)
        assert any(action["id"] == "staff" for action in actions)

    def test_quick_actions_for_waiter(self):
        """测试服务员角色的快捷操作"""
        from src.api.mobile import _get_quick_actions_by_role

        actions = _get_quick_actions_by_role("waiter")
        assert len(actions) == 3
        assert any(action["id"] == "new_order" for action in actions)

    def test_quick_actions_for_chef(self):
        """测试厨师角色的快捷操作"""
        from src.api.mobile import _get_quick_actions_by_role

        actions = _get_quick_actions_by_role("chef")
        assert len(actions) == 2
        assert any(action["id"] == "orders" for action in actions)

    def test_quick_actions_for_unknown_role(self):
        """测试未知角色的快捷操作"""
        from src.api.mobile import _get_quick_actions_by_role

        actions = _get_quick_actions_by_role("unknown_role")
        assert len(actions) == 2  # Default actions
        assert any(action["id"] == "home" for action in actions)


class TestMobileTables:
    """测试移动端桌台接口"""

    
    @patch("src.api.mobile.pos_service")
    def test_get_tables(
        self,
        mock_pos_service,
        
        client,
        mock_user,
    ):
        """测试获取桌台列表"""
        
        mock_pos_service.get_tables = AsyncMock(return_value=[
            {"tableId": 1, "tableName": "A01", "blName": "大厅"},
            {"tableId": 2, "tableName": "B05", "blName": "包间"},
        ])

        response = client.get("/api/v1/mobile/tables", )

        assert response.status_code == 200
        data = response.json()
        assert len(data["tables"]) == 2
        assert data["tables"][0]["name"] == "A01"
        assert data["tables"][1]["area"] == "包间"


class TestMobilePerformance:
    """测试移动端性能"""

    
    @patch("src.api.mobile.store_service")
    @patch("src.api.mobile.notification_service")
    @patch("src.api.mobile.pos_service")
    def test_dashboard_response_time(
        self,
        mock_pos_service,
        mock_notification_service,
        mock_store_service,
        
        client,
        mock_user,
    ):
        """测试仪表盘响应时间"""
        import time

        # Setup mocks
        
        mock_store_service.get_store = AsyncMock(return_value=MagicMock(name="Test Store"))
        mock_notification_service.get_unread_count = AsyncMock(return_value=0)
        mock_notification_service.get_user_notifications = AsyncMock(return_value=[])
        mock_pos_service.query_orders = AsyncMock(return_value={"orders": []})

        start_time = time.time()
        response = client.get("/api/v1/mobile/dashboard", )
        end_time = time.time()

        assert response.status_code == 200
        # Mobile API should respond quickly (< 1 second for mocked services)
        assert (end_time - start_time) < 1.0

