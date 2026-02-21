"""
Integration Tests for API Endpoints
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime

from src.main import app
from src.models.user import User, UserRole
from src.core.security import create_access_token


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create authentication headers"""
    import uuid
    token = create_access_token(
        data={
            "sub": str(uuid.uuid4()),
            "username": "testuser",
            "role": "staff",
        }
    )
    return {"Authorization": f"Bearer {token}"}


class TestHealthEndpoints:
    """Test health check endpoints"""

    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["version"] == "0.1.0"

    def test_readiness_check(self, client):
        """Test readiness check endpoint"""
        response = client.get("/api/v1/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"

    def test_liveness_check(self, client):
        """Test liveness check endpoint"""
        response = client.get("/api/v1/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"


class TestAgentEndpoints:
    """Test agent API endpoints"""

    def test_schedule_agent_without_auth(self, client):
        """Test schedule agent endpoint without authentication"""
        response = client.post(
            "/api/v1/agents/schedule",
            json={
                "agent_type": "schedule",
                "input_data": {"action": "get_schedule", "params": {}},
            },
        )

        # Should return 403 Forbidden without authentication
        assert response.status_code == 403

    def test_schedule_agent_with_auth(self, client, auth_headers):
        """Test schedule agent endpoint with authentication"""
        response = client.post(
            "/api/v1/agents/schedule",
            json={
                "agent_type": "schedule",
                "input_data": {
                    "action": "get_schedule",
                    "params": {
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-07",
                    },
                },
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "agent_type" in data
        assert "output_data" in data
        assert "execution_time" in data

    def test_order_agent_with_auth(self, client, auth_headers):
        """Test order agent endpoint with authentication"""
        response = client.post(
            "/api/v1/agents/order",
            json={
                "agent_type": "order",
                "input_data": {
                    "action": "list_orders",
                    "params": {"limit": 10},
                },
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["agent_type"] == "order"

    def test_inventory_agent_with_auth(self, client, auth_headers):
        """Test inventory agent endpoint with authentication"""
        response = client.post(
            "/api/v1/agents/inventory",
            json={
                "agent_type": "inventory",
                "input_data": {
                    "action": "monitor_inventory",
                    "params": {},
                },
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["agent_type"] == "inventory"

    def test_invalid_agent_type(self, client, auth_headers):
        """Test with invalid agent type"""
        response = client.post(
            "/api/v1/agents/schedule",
            json={
                "agent_type": "invalid",
                "input_data": {"action": "test", "params": {}},
            },
            headers=auth_headers,
        )

        # Should still return 200 but with error in output_data
        assert response.status_code == 200
        data = response.json()
        assert "output_data" in data


class TestEndToEndWorkflows:
    """Test end-to-end workflows"""

    @pytest.mark.integration
    def test_complete_order_workflow(self, client, auth_headers):
        """Test complete order creation and retrieval workflow"""
        # Create an order
        create_response = client.post(
            "/api/v1/agents/order",
            json={
                "agent_type": "order",
                "input_data": {
                    "action": "create_order",
                    "params": {
                        "table_number": "A1",
                        "items": [
                            {"name": "宫保鸡丁", "quantity": 2, "price": 38.0},
                            {"name": "麻婆豆腐", "quantity": 1, "price": 28.0},
                        ],
                        "customer_name": "测试客户",
                    },
                },
            },
            headers=auth_headers,
        )

        assert create_response.status_code == 200
        create_data = create_response.json()
        assert create_data["output_data"]["success"] is True

        # List orders to verify creation
        list_response = client.post(
            "/api/v1/agents/order",
            json={
                "agent_type": "order",
                "input_data": {
                    "action": "list_orders",
                    "params": {"limit": 10},
                },
            },
            headers=auth_headers,
        )

        assert list_response.status_code == 200
        list_data = list_response.json()
        assert list_data["output_data"]["success"] is True

    @pytest.mark.integration
    def test_inventory_monitoring_workflow(self, client, auth_headers):
        """Test inventory monitoring workflow"""
        # Monitor inventory
        monitor_response = client.post(
            "/api/v1/agents/inventory",
            json={
                "agent_type": "inventory",
                "input_data": {
                    "action": "monitor_inventory",
                    "params": {},
                },
            },
            headers=auth_headers,
        )

        assert monitor_response.status_code == 200
        monitor_data = monitor_response.json()
        assert "output_data" in monitor_data

        # Generate restock alerts
        alerts_response = client.post(
            "/api/v1/agents/inventory",
            json={
                "agent_type": "inventory",
                "input_data": {
                    "action": "generate_restock_alerts",
                    "params": {},
                },
            },
            headers=auth_headers,
        )

        assert alerts_response.status_code == 200
        alerts_data = alerts_response.json()
        assert "output_data" in alerts_data
