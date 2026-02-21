"""
API端点测试脚本
测试所有新功能的API端点
"""
import requests
import json
from datetime import datetime, date, timedelta


class APITester:
    """API测试器"""

    def __init__(self, base_url="http://localhost:8000", token=None):
        self.base_url = base_url
        self.token = token
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

        self.passed = 0
        self.failed = 0
        self.errors = []

    def test(self, name: str, method: str, endpoint: str, data=None, expected_status=200):
        """测试单个API端点"""
        try:
            print(f"\n🧪 测试: {name}")
            url = f"{self.base_url}{endpoint}"

            if method == "GET":
                response = requests.get(url, headers=self.headers, params=data)
            elif method == "POST":
                response = requests.post(url, headers=self.headers, json=data)
            elif method == "PUT":
                response = requests.put(url, headers=self.headers, json=data)
            elif method == "DELETE":
                response = requests.delete(url, headers=self.headers)
            elif method == "PATCH":
                response = requests.patch(url, headers=self.headers, json=data)
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")

            print(f"   状态码: {response.status_code}")

            if response.status_code == expected_status:
                print(f"✅ 通过: {name}")
                self.passed += 1
                return response.json() if response.content else None
            else:
                print(f"❌ 失败: {name}")
                print(f"   期望状态码: {expected_status}, 实际: {response.status_code}")
                if response.content:
                    print(f"   响应: {response.text[:200]}")
                self.failed += 1
                self.errors.append(f"{name}: 状态码 {response.status_code}")
                return None

        except Exception as e:
            print(f"❌ 错误: {name}")
            print(f"   异常: {str(e)}")
            self.failed += 1
            self.errors.append(f"{name}: {str(e)}")
            return None

    def summary(self):
        """打印测试摘要"""
        total = self.passed + self.failed
        print("\n" + "=" * 60)
        print("📊 API测试摘要")
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
            print("\n🎉 所有API测试通过！")
        else:
            print(f"\n⚠️  有 {self.failed} 个测试失败")

        return self.failed == 0


def main():
    """主测试函数"""
    print("=" * 60)
    print("🚀 智链OS API端点测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n⚠️  注意: 此测试需要API服务器运行在 http://localhost:8000")
    print("⚠️  注意: 某些测试需要管理员权限，可能会失败（401/403）")

    tester = APITester()

    # 测试健康检查
    print("\n📦 第一部分: 基础API测试")
    tester.test("健康检查", "GET", "/api/v1/health")

    # 测试多门店管理API
    print("\n🏪 第二部分: 多门店管理API")
    tester.test("获取门店列表", "GET", "/api/v1/multi-store/stores")
    tester.test("获取门店统计", "GET", "/api/v1/multi-store/stores/STORE001/stats")

    # 测试对比（需要POST）
    compare_data = {
        "store_ids": ["STORE001", "STORE002"],
        "start_date": (date.today() - timedelta(days=7)).isoformat(),
        "end_date": date.today().isoformat(),
    }
    tester.test("门店对比", "POST", "/api/v1/multi-store/compare", compare_data)

    tester.test("区域汇总", "GET", "/api/v1/multi-store/regional-summary")
    tester.test("绩效排名", "GET", "/api/v1/multi-store/performance-ranking", {"metric": "revenue", "limit": 10})

    # 测试供应链管理API
    print("\n📦 第三部分: 供应链管理API")
    tester.test("获取供应商列表", "GET", "/api/v1/supply-chain/suppliers")
    tester.test("获取采购订单", "GET", "/api/v1/supply-chain/purchase-orders")
    tester.test("补货建议", "GET", "/api/v1/supply-chain/replenishment-suggestions")

    # 测试财务管理API
    print("\n💰 第四部分: 财务管理API")
    finance_params = {
        "store_id": "STORE001",
        "start_date": (date.today() - timedelta(days=30)).isoformat(),
        "end_date": date.today().isoformat(),
    }

    tester.test("获取交易记录", "GET", "/api/v1/finance/transactions", finance_params)
    tester.test("损益表", "GET", "/api/v1/finance/reports/income-statement", finance_params)
    tester.test("现金流量表", "GET", "/api/v1/finance/reports/cash-flow", finance_params)
    tester.test("财务指标", "GET", "/api/v1/finance/metrics", finance_params)

    # 测试预算分析
    budget_params = {
        "store_id": "STORE001",
        "year": datetime.now().year,
        "month": datetime.now().month,
    }
    tester.test("预算分析", "GET", "/api/v1/finance/budgets/analysis", budget_params)

    # 测试备份管理API
    print("\n💾 第五部分: 备份管理API")
    tester.test("获取备份列表", "GET", "/api/v1/backup/list")

    # 测试数据可视化API
    print("\n📊 第六部分: 数据可视化API")
    tester.test("概览数据", "GET", "/api/v1/dashboard/overview")
    tester.test("销售趋势", "GET", "/api/v1/dashboard/sales-trend", {"days": 7})
    tester.test("会员统计", "GET", "/api/v1/dashboard/member-stats")
    tester.test("实时指标", "GET", "/api/v1/dashboard/realtime-metrics")

    # 打印摘要
    success = tester.summary()

    # 生成测试报告
    print("\n📄 生成测试报告...")
    report = {
        "test_time": datetime.now().isoformat(),
        "total_tests": tester.passed + tester.failed,
        "passed": tester.passed,
        "failed": tester.failed,
        "success_rate": f"{(tester.passed / (tester.passed + tester.failed) * 100):.1f}%",
        "errors": tester.errors,
    }

    with open("api_test_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("✅ 测试报告已保存到: api_test_report.json")

    return 0 if success else 1


if __name__ == "__main__":
    import sys
    exit_code = main()
    sys.exit(exit_code)
