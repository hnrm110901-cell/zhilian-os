"""
快速性能测试 - 使用curl进行基准测试
"""
import subprocess
import time
import statistics
from typing import List

def run_curl_test(url: str, iterations: int = 50) -> List[float]:
    """使用curl测试端点性能"""
    times = []
    for _ in range(iterations):
        start = time.time()
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{time_total}', url],
            capture_output=True,
            text=True
        )
        elapsed = float(result.stdout) * 1000  # 转换为毫秒
        times.append(elapsed)
    return times

def calculate_stats(name: str, times: List[float]):
    """计算并打印统计数据"""
    sorted_times = sorted(times)
    p95_index = int(len(sorted_times) * 0.95)
    p99_index = int(len(sorted_times) * 0.99)

    stats = {
        'min': min(times),
        'max': max(times),
        'mean': statistics.mean(times),
        'median': statistics.median(times),
        'p95': sorted_times[p95_index],
        'p99': sorted_times[p99_index]
    }

    status = "✅" if stats['p95'] < 100 else "⚠️" if stats['p95'] < 500 else "❌"

    print(f"\n{name}:")
    print(f"  平均: {stats['mean']:.2f}ms | P95: {stats['p95']:.2f}ms | P99: {stats['p99']:.2f}ms {status}")

    return stats

print("=" * 60)
print("快速性能测试")
print("=" * 60)

# 测试健康检查
print("\n[1] 健康检查端点")
times = run_curl_test("http://localhost:8000/api/v1/neural/health", 50)
health_stats = calculate_stats("健康检查", times)

# 测试系统状态
print("\n[2] 系统状态端点")
times = run_curl_test("http://localhost:8000/api/v1/neural/status", 50)
status_stats = calculate_stats("系统状态", times)

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
print("\n性能等级:")
print("  ✅ 优秀: P95 < 100ms")
print("  ⚠️ 需优化: 100ms ≤ P95 < 500ms")
print("  ❌ 慢: P95 ≥ 500ms")
