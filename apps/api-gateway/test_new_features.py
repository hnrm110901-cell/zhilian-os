"""
新功能集成测试脚本
测试多门店管理、供应链管理、财务系统、数据备份等新功能
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, date, timedelta

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from src.core.database import get_db_session
from src.services.store_service import StoreService
from src.services.supply_chain_service import SupplyChainService
from src.services.finance_service import FinanceService
from src.services.backup_service import BackupService


class TestRunner:
    """测试运行器"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def test(self, name: str, func):
        """运行单个测试"""
        try:
            print(f"\n🧪 测试: {name}")
            result = func()
            if asyncio.iscoroutine(result):
                result = asyncio.run(result)

            if result:
                print(f"✅ 通过: {name}")
                self.passed += 1
            else:
                print(f"❌ 失败: {name}")
                self.failed += 1
                self.errors.append(name)
        except Exception as e:
            print(f"❌ 错误: {name}")
            print(f"   异常: {str(e)}")
            self.failed += 1
            self.errors.append(f"{name}: {str(e)}")

    def summary(self):
        """打印测试摘要"""
        total = self.passed + self.failed
        print("\n" + "=" * 60)
        print("📊 测试摘要")
        print("=" * 60)
        print(f"总计: {total} 个测试")
        print(f"✅ 通过: {self.passed} 个")
        print(f"❌ 失败: {self.failed} 个")

        if self.errors:
            print("\n失败的测试:")
            for error in self.errors:
                print(f"  - {error}")

        success_rate = (self.passed / total * 100) if total > 0 else 0
        print(f"\n成功率: {success_rate:.1f}%")

        if self.failed == 0:
            print("\n🎉 所有测试通过！")
        else:
            print(f"\n⚠️  有 {self.failed} 个测试失败")

        return self.failed == 0


# 测试函数
async def test_store_service():
    """测试门店服务"""
    async with get_db_session() as session:
        service = StoreService(session)

        # 测试获取门店统计
        stats = await service.get_store_stats("STORE001")
        assert stats is not None, "门店统计为空"
        assert "revenue" in stats, "缺少营收数据"
        assert "orders" in stats, "缺少订单数据"

        # 测试门店对比
        comparison = await service.compare_stores(
            ["STORE001", "STORE002"],
            date.today() - timedelta(days=7),
            date.today()
        )
        assert comparison is not None, "门店对比为空"
        assert "stores" in comparison, "缺少门店数据"

        # 测试区域汇总
        summary = await service.get_regional_summary()
        assert len(summary) > 0, "区域汇总为空"

        # 测试绩效排名
        ranking = await service.get_performance_ranking("revenue", 10)
        assert len(ranking) > 0, "绩效排名为空"

        return True


async def test_supply_chain_service():
    """测试供应链服务"""
    async with get_db_session() as session:
        service = SupplyChainService(session)

        # 测试获取供应商列表
        suppliers = await service.get_suppliers()
        assert suppliers is not None, "供应商列表为空"
        assert "suppliers" in suppliers, "缺少供应商数据"

        # 测试获取采购订单
        orders = await service.get_purchase_orders()
        assert orders is not None, "采购订单为空"
        assert "orders" in orders, "缺少订单数据"

        # 测试补货建议
        suggestions = await service.get_replenishment_suggestions()
        assert suggestions is not None, "补货建议为空"

        return True


async def test_finance_service():
    """测试财务服务"""
    async with get_db_session() as session:
        service = FinanceService(session)

        # 测试生成损益表
        start_date = date.today() - timedelta(days=30)
        end_date = date.today()

        income_statement = await service.generate_income_statement(
            "STORE001", start_date, end_date
        )
        assert income_statement is not None, "损益表为空"
        assert "revenue" in income_statement, "缺少营收数据"
        assert "expenses" in income_statement, "缺少支出数据"
        assert "profit" in income_statement, "缺少利润数据"

        # 测试生成现金流量表
        cash_flow = await service.generate_cash_flow(
            "STORE001", start_date, end_date
        )
        assert cash_flow is not None, "现金流量表为空"
        assert "cash_flow" in cash_flow, "缺少现金流数据"

        # 测试财务指标
        metrics = await service.get_financial_metrics(
            "STORE001", start_date, end_date
        )
        assert metrics is not None, "财务指标为空"
        assert "metrics" in metrics, "缺少指标数据"

        return True


async def test_backup_service():
    """测试备份服务"""
    service = BackupService()

    # 测试列出备份
    backups = await service.list_backups()
    assert backups is not None, "备份列表为空"
    print(f"   找到 {len(backups)} 个备份文件")

    # 测试创建备份（可选，因为会创建实际文件）
    # backup_result = await service.create_backup("test")
    # assert backup_result["success"], "创建备份失败"

    return True


def test_models_import():
    """测试模型导入"""
    from src.models import (
        Supplier, PurchaseOrder,
        FinancialTransaction, Budget, Invoice, FinancialReport
    )

    assert Supplier is not None, "Supplier模型导入失败"
    assert PurchaseOrder is not None, "PurchaseOrder模型导入失败"
    assert FinancialTransaction is not None, "FinancialTransaction模型导入失败"
    assert Budget is not None, "Budget模型导入失败"
    assert Invoice is not None, "Invoice模型导入失败"
    assert FinancialReport is not None, "FinancialReport模型导入失败"

    return True


def test_api_imports():
    """测试API导入"""
    from src.api import multi_store, supply_chain, finance, backup

    assert multi_store.router is not None, "多门店API导入失败"
    assert supply_chain.router is not None, "供应链API导入失败"
    assert finance.router is not None, "财务API导入失败"
    assert backup.router is not None, "备份API导入失败"

    return True


def test_service_imports():
    """测试服务导入"""
    from src.services.store_service import StoreService
    from src.services.supply_chain_service import SupplyChainService
    from src.services.finance_service import FinanceService
    from src.services.backup_service import BackupService
    from src.services.scheduler import TaskScheduler

    assert StoreService is not None, "StoreService导入失败"
    assert SupplyChainService is not None, "SupplyChainService导入失败"
    assert FinanceService is not None, "FinanceService导入失败"
    assert BackupService is not None, "BackupService导入失败"
    assert TaskScheduler is not None, "TaskScheduler导入失败"

    return True


async def main():
    """主测试函数"""
    print("=" * 60)
    print("🚀 智链OS新功能集成测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    runner = TestRunner()

    # 基础测试
    print("\n📦 第一部分: 基础导入测试")
    runner.test("模型导入测试", test_models_import)
    runner.test("API导入测试", test_api_imports)
    runner.test("服务导入测试", test_service_imports)

    # 服务测试
    print("\n🔧 第二部分: 服务功能测试")
    runner.test("门店服务测试", test_store_service)
    runner.test("供应链服务测试", test_supply_chain_service)
    runner.test("财务服务测试", test_finance_service)
    runner.test("备份服务测试", test_backup_service)

    # 打印摘要
    success = runner.summary()

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
