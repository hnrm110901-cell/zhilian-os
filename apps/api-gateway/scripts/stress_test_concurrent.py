"""
并发压力测试 - 使用Python多线程
Concurrent Stress Testing using Python Threading
"""
import time
import threading
import requests
from collections import defaultdict
from datetime import datetime

API_URL = "http://localhost:8000/api/v1/neural"

class StressTester:
    """压力测试器"""

    def __init__(self):
        self.results = defaultdict(list)
        self.errors = []
        self.lock = threading.Lock()

    def make_request(self, endpoint: str, test_id: int):
        """发送单个请求"""
        try:
            start = time.time()
            response = requests.get(f"{API_URL}/{endpoint}", timeout=10)
            elapsed = (time.time() - start) * 1000  # 毫秒

            with self.lock:
                self.results[endpoint].append({
                    'time': elapsed,
                    'status': response.status_code,
                    'success': response.status_code == 200
                })
        except Exception as e:
            with self.lock:
                self.errors.append(str(e))

    def run_concurrent_test(self, endpoint: str, total_requests: int, concurrency: int):
        """运行并发测试"""
        print(f"\n测试: {endpoint}")
        print(f"  总请求数: {total_requests}")
        print(f"  并发数: {concurrency}")

        start_time = time.time()
        threads = []

        # 创建并启动线程
        for i in range(total_requests):
            thread = threading.Thread(target=self.make_request, args=(endpoint, i))
            threads.append(thread)
            thread.start()

            # 控制并发数
            if len(threads) >= concurrency:
                for t in threads:
                    t.join()
                threads = []

        # 等待剩余线程完成
        for thread in threads:
            thread.join()

        total_time = time.time() - start_time

        # 计算统计数据
        results = self.results[endpoint]
        if results:
            times = [r['time'] for r in results]
            success_count = sum(1 for r in results if r['success'])

            sorted_times = sorted(times)
            p50 = sorted_times[len(sorted_times) // 2]
            p95 = sorted_times[int(len(sorted_times) * 0.95)]
            p99 = sorted_times[int(len(sorted_times) * 0.99)]

            rps = len(results) / total_time

            print(f"\n  结果:")
            print(f"    总耗时: {total_time:.2f}秒")
            print(f"    成功请求: {success_count}/{len(results)}")
            print(f"    失败请求: {len(results) - success_count}")
            print(f"    RPS (每秒请求数): {rps:.2f}")
            print(f"    平均响应时间: {sum(times)/len(times):.2f}ms")
            print(f"    P50: {p50:.2f}ms")
            print(f"    P95: {p95:.2f}ms")
            print(f"    P99: {p99:.2f}ms")

            # 性能评级
            if p95 < 100:
                grade = "✅ 优秀"
            elif p95 < 500:
                grade = "⚠️ 良好"
            else:
                grade = "❌ 需优化"
            print(f"    性能评级: {grade}")

            return {
                'endpoint': endpoint,
                'total_time': total_time,
                'success_rate': success_count / len(results) * 100,
                'rps': rps,
                'p95': p95,
                'grade': grade
            }

def main():
    """主函数"""
    print("=" * 60)
    print("智链OS神经系统 - 并发压力测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    tester = StressTester()

    # 测试配置
    tests = [
        ("health", 100, 10),   # 100请求, 10并发
        ("health", 100, 50),   # 100请求, 50并发
        ("status", 100, 10),   # 100请求, 10并发
        ("status", 100, 50),   # 100请求, 50并发
    ]

    summary = []

    for endpoint, requests_count, concurrency in tests:
        result = tester.run_concurrent_test(endpoint, requests_count, concurrency)
        if result:
            summary.append(result)

    # 打印总结
    print("\n" + "=" * 60)
    print("压力测试总结")
    print("=" * 60)
    print(f"\n{'端点':<15} {'RPS':<12} {'P95':<12} {'成功率':<12} {'评级'}")
    print("-" * 60)

    for result in summary:
        print(f"{result['endpoint']:<15} {result['rps']:>8.2f}  {result['p95']:>8.2f}ms  {result['success_rate']:>8.1f}%  {result['grade']}")

    if tester.errors:
        print(f"\n错误数: {len(tester.errors)}")
        print("前5个错误:")
        for error in tester.errors[:5]:
            print(f"  - {error}")

    print("\n" + "=" * 60)
    print("✓ 压力测试完成")
    print("=" * 60)

if __name__ == "__main__":
    main()
