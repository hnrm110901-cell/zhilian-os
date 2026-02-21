"""
Neural System Test Script
Tests basic functionality of the neural system
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.neural_system import NeuralSystemOrchestrator
from src.schemas.restaurant_standard_schema import (
    NeuralEventSchema,
    OrderSchema,
    DishSchema
)
import structlog

logger = structlog.get_logger()


async def test_event_emission():
    """Test event emission"""
    logger.info("Testing event emission...")

    neural_system = NeuralSystemOrchestrator()

    # Create test event
    event = NeuralEventSchema(
        event_id="test_order_001",
        event_type="order",
        store_id="test_store",
        timestamp=datetime.now(),
        data={
            "order_id": "ORD_TEST_001",
            "total_amount": 158.50,
            "status": "completed"
        },
        metadata={"test": True}
    )

    try:
        await neural_system.emit_event(event)
        logger.info("✓ Event emission successful")
        return True
    except Exception as e:
        logger.error("✗ Event emission failed", error=str(e))
        return False


async def test_semantic_search():
    """Test semantic search"""
    logger.info("Testing semantic search...")

    neural_system = NeuralSystemOrchestrator()

    try:
        # Search for orders
        results = await neural_system.semantic_search_orders(
            query="大额订单",
            store_id="test_store",
            top_k=5
        )
        logger.info(f"✓ Semantic search successful, found {len(results)} results")
        return True
    except Exception as e:
        logger.error("✗ Semantic search failed", error=str(e))
        return False


async def test_vector_indexing():
    """Test vector indexing"""
    logger.info("Testing vector indexing...")

    neural_system = NeuralSystemOrchestrator()

    try:
        # Index test order
        test_order = OrderSchema(
            order_id="ORD_TEST_002",
            order_type="dine_in",
            status="completed",
            items=[
                {
                    "dish_id": "DISH_001",
                    "dish_name": "宫保鸡丁",
                    "quantity": 1,
                    "unit_price": 48.00,
                    "subtotal": 48.00
                }
            ],
            subtotal=48.00,
            discount=0.00,
            tax=4.80,
            total_amount=52.80,
            created_at=datetime.now(),
            confirmed_at=datetime.now(),
            completed_at=datetime.now(),
            server_id="SERVER_001",
            cashier_id="CASHIER_001"
        )

        await neural_system.vector_db.index_order(test_order, "test_store")
        logger.info("✓ Vector indexing successful")
        return True
    except Exception as e:
        logger.error("✗ Vector indexing failed", error=str(e))
        return False


async def test_federated_learning():
    """Test federated learning"""
    logger.info("Testing federated learning...")

    neural_system = NeuralSystemOrchestrator()

    try:
        # Register test store
        neural_system.fl_service.register_store("test_store")

        # Participate in federated learning
        test_model = {"weights": [0.1, 0.2, 0.3], "bias": [0.01]}
        success = await neural_system.participate_in_federated_learning(
            store_id="test_store",
            local_model=test_model,
            training_samples=100
        )

        if success:
            logger.info("✓ Federated learning successful")
            return True
        else:
            logger.error("✗ Federated learning failed")
            return False
    except Exception as e:
        logger.error("✗ Federated learning failed", error=str(e))
        return False


async def main():
    """Run all tests"""
    logger.info("=" * 60)
    logger.info("Neural System Test Suite")
    logger.info("=" * 60)

    tests = [
        ("Event Emission", test_event_emission),
        ("Vector Indexing", test_vector_indexing),
        ("Semantic Search", test_semantic_search),
        ("Federated Learning", test_federated_learning),
    ]

    results = []
    for test_name, test_func in tests:
        logger.info(f"\n[{test_name}]")
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"Test crashed: {test_name}", error=str(e))
            results.append((test_name, False))

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {test_name}")

    logger.info(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        logger.info("\n🎉 All tests passed!")
        return 0
    else:
        logger.error(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
