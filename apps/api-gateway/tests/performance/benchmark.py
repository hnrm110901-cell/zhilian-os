"""
性能基准测试
测试关键API端点的响应时间和吞吐量
"""
import asyncio
import time
import statistics
from typing import List, Dict
import httpx


class PerformanceBenchmark:
    """性能基准测试类"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results = {}
    
    async def benchmark_endpoint(
        self,
        name: str,
        method: str,
        path: str,
        iterations: int = 100,
        **kwargs
    ) -> Dict:
        """测试单个端点的性能"""
        print(f"\n测试 {name}...")
        print(f"  方法: {method}")
        print(f"  路径: {path}")
        print(f"  迭代次数: {iterations}")
        
        response_times = []
        errors = 0
        
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            for i in range(iterations):
                start_time = time.time()
                
                try:
                    if method.upper() == "GET":
                        response = await client.get(path, **kwargs)
                    elif method.upper() == "POST":
                        response = await client.post(path, **kwargs)
                    elif method.upper() == "PUT":
                        response = await client.put(path, **kwargs)
                    elif method.upper() == "DELETE":
                        response = await client.delete(path, **kwargs)
                    
                    elapsed = (time.time() - start_time) * 1000  # 转换为毫秒
                    
                    if response.status_code < 400:
                        response_times.append(elapsed)
                    else:
                        errors += 1
                        
                except Exception as e:
                    errors += 1
                    print(f"  错误: {e}")
        
        # 计算统计数据
        if response_times:
            result = {
                "name": name,
                "iterations": iterations,
                "errors": errors,
                "success_rate": (iterations - errors) / iterations * 100,
                "min_time": min(response_times),
                "max_time": max(response_times),
                "avg_time": statistics.mean(response_times),
                "median_time": statistics.median(response_times),
                "p95_time": self._percentile(response_times, 95),
                "p99_time": self._percentile(response_times, 99),
            }
        else:
            result = {
                "name": name,
                "iterations": iterations,
                "errors": errors,
                "success_rate": 0,
            }
        
        self.results[name] = result
        self._print_result(result)
        
        return result
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """计算百分位数"""
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    def _print_result(self, result: Dict):
        """打印测试结果"""
        print(f"\n  结果:")
        print(f"    成功率: {result.get('success_rate', 0):.2f}%")
        
        if 'avg_time' in result:
            print(f"    最小响应时间: {result['min_time']:.2f}ms")
            print(f"    最大响应时间: {result['max_time']:.2f}ms")
            print(f"    平均响应时间: {result['avg_time']:.2f}ms")
            print(f"    中位数响应时间: {result['median_time']:.2f}ms")
            print(f"    P95响应时间: {result['p95_time']:.2f}ms")
            print(f"    P99响应时间: {result['p99_time']:.2f}ms")
    
    def print_summary(self):
        """打印测试总结"""
        print("\n" + "=" * 60)
        print("性能基准测试总结")
        print("=" * 60)
        
        for name, result in self.results.items():
            print(f"\n{name}:")
            print(f"  成功率: {result.get('success_rate', 0):.2f}%")
            if 'avg_time' in result:
                print(f"  平均响应时间: {result['avg_time']:.2f}ms")
                print(f"  P95响应时间: {result['p95_time']:.2f}ms")


async def run_benchmarks():
    """运行所有基准测试"""
    benchmark = PerformanceBenchmark()
    
    # 测试健康检查
    await benchmark.benchmark_endpoint(
        name="健康检查",
        method="GET",
        path="/health",
        iterations=1000
    )
    
    # 测试获取任务列表
    await benchmark.benchmark_endpoint(
        name="获取任务列表",
        method="GET",
        path="/api/v1/tasks",
        params={"limit": 20},
        iterations=100
    )
    
    # 测试获取对账记录
    await benchmark.benchmark_endpoint(
        name="获取对账记录",
        method="GET",
        path="/api/v1/reconciliation/records",
        params={"limit": 20},
        iterations=100
    )
    
    # 测试Prometheus指标
    await benchmark.benchmark_endpoint(
        name="Prometheus指标",
        method="GET",
        path="/metrics",
        iterations=500
    )
    
    # 打印总结
    benchmark.print_summary()


if __name__ == "__main__":
    print("开始性能基准测试...")
    asyncio.run(run_benchmarks())
