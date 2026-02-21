"""
神经系统性能基准测试
Performance Benchmark for Neural System
"""
import time
import asyncio
import statistics
from typing import List, Dict, Any
import requests
from datetime import datetime

API_URL = "http://localhost:8000/api/v1/neural"

class PerformanceTester:
    """性能测试器"""

    def __init__(self):
        self.results = []

    def measure_time(self, func):
        """测量函数执行时间"""
        start = time.time()
        result = func()
        end = time.time()
        elapsed = (end - start) * 1000  # 转换为毫秒
        return elapsed, result

    def test_health_check(self, iterations: int = 100) -> Dict[str, Any]:
        """测试健康检查端点性能"""
        print(f"\n[1] 测试健康检查端点 ({iterations}次)")
        times = []

        for i in range(iterations):
            elapsed, response = self.measure_time(
                lambda: requests.get(f"{API_URL}/health")
            )
            times.append(elapsed)
            if (i + 1) % 10 == 0:
                print(f"  进度: {i + 1}/{iterations}")

        return self._calculate_stats("健康检查", times)

    def test_status_endpoint(self, iterations: int = 100) -> Dict[str, Any]:
        """测试系统状态端点性能"""
        print(f"\n[2] 测试系统状态端点 ({iterations}次)")
        times = []

        for i in range(iterations):
            elapsed, response = self.measure_time(
                lambda: requests.get(f"{API_URL}/status")
            )
            times.append(elapsed)
            if (i + 1) % 10 == 0:
                print(f"  进度: {i + 1}/{iterations}")

        return self._calculate_stats("系统状态", times)

    def test_event_emission(self, iterations: int = 100) -> Dict[str, Any]:
        """测试事件发射端点性能"""
        print(f"\n[3] 测试事件发射端点 ({iterations}次)")
        times = []

        test_event = {
            "event_type": "order",
            "store_id": "store_001",
            "data": {
                "order_id": f"ORD_PERF_TEST",
                "total_amount": 158.50,
                "status": "completed"
            }
        }

        for i in range(iterations):
            elapsed, response = self.measure_time(
                lambda: requests.post(f"{API_URL}/events/emit", json=test_event)
            )
            times.append(elapsed)
            if (i + 1) % 10 == 0:
                print(f"  进度: {i + 1}/{iterations}")

        return self._calculate_stats("事件发射", times)

    def test_search_endpoint(self, iterations: int = 100) -> Dict[str, Any]:
        """测试搜索端点性能"""
        print(f"\n[4] 测试搜索端点 ({iterations}次)")
        times = []

        search_query = {
            "query": "大额订单",
            "store_id": "store_001",
            "top_k": 10
        }

        for i in range(iterations):
            elapsed, response = self.measure_time(
                lambda: requests.post(f"{API_URL}/search/orders", json=search_query)
            )
            times.append(elapsed)
            if (i + 1) % 10 == 0:
                print(f"  进度: {i + 1}/{iterations}")

        return self._calculate_stats("语义搜索", times)

    def _calculate_stats(self, name: str, times: List[float]) -> Dict[str, Any]:
        """计算统计数据"""
        stats = {
            "name": name,
            "count": len(times),
            "min": min(times),
            "max": max(times),
            "mean": statistics.mean(times),
            "median": statistics.median(times),
            "stdev": statistics.stdev(times) if len(times) > 1 else 0,
            "p95": self._percentile(times, 95),
            "p99": self._percentile(times, 99)
        }

        self.results.append(stats)

        print(f"\n  结果:")
        print(f"    最小值: {stats['min']:.2f}ms")
        print(f"    最大值: {stats['max']:.2f}ms")
        print(f"    平均值: {stats['mean']:.2f}ms")
        print(f"    中位数: {stats['median']:.2f}ms")
        print(f"    标准差: {stats['stdev']:.2f}ms")
        print(f"    P95: {stats['p95']:.2f}ms")
        print(f"    P99: {stats['p99']:.2f}ms")

        return stats

    def _percentile(self, data: List[float], percentile: int) -> float:
        """计算百分位数"""
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]

    def generate_report(self):
        """生成性能报告"""
        print("\n" + "=" * 60)
        print("性能测试总结")
        print("=" * 60)

        print(f"\n{'端点':<15} {'平均值':<12} {'P95':<12} {'P99':<12} {'状态'}")
        print("-" * 60)

        for result in self.results:
            status = "✅ 优秀" if result['p95'] < 100 else "⚠️ 需优化" if result['p95'] < 500 else "❌ 慢"
            print(f"{result['name']:<15} {result['mean']:>8.2f}ms  {result['p95']:>8.2f}ms  {result['p99']:>8.2f}ms  {status}")

        print("\n性能等级:")
        print("  ✅ 优秀: P95 < 100ms")
        print("  ⚠️ 需优化: 100ms ≤ P95 < 500ms")
        print("  ❌ 慢: P95 ≥ 500ms")


def main():
    """主函数"""
    print("=" * 60)
    print("智链OS神经系统 - 性能基准测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API地址: {API_URL}")

    tester = PerformanceTester()

    try:
        # 运行各项测试
        tester.test_health_check(iterations=100)
        tester.test_status_endpoint(iterations=100)
        tester.test_event_emission(iterations=50)  # 事件发射测试次数少一些
        tester.test_search_endpoint(iterations=50)

        # 生成报告
        tester.generate_report()

        print("\n" + "=" * 60)
        print("✓ 性能测试完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
