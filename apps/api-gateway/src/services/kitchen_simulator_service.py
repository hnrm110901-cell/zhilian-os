"""
高峰排队论模拟器（Kitchen Stress Simulator）
基于 M/G/s 排队论模型，模拟新品加入菜单后厨房高峰期的压力变化。

M/G/s 模型：
  M — 泊松到达过程（订单到达率 λ）
  G — 一般服务时间分布（每道菜制作时间 μ，有标准差）
  s — 多服务台（灶台、蒸柜、油炸等工位数）

输出：
  - 加入新品前后的平均等待时间变化 ΔW
  - 各工位利用率热力图
  - 瓶颈工位识别
  - 建议（限量/错峰/增员）
"""
import math
from dataclasses import dataclass
from typing import Dict, List

import structlog

logger = structlog.get_logger()


@dataclass
class WorkStation:
    """厨房工位"""
    station_id: str
    name: str           # 如 "灶台", "蒸柜", "油炸", "凉菜", "打荷"
    capacity: int       # 该工位并行处理数（如 6 个灶台）


@dataclass
class DishWorkload:
    """一道菜对厨房的负载"""
    dish_name: str
    station_id: str          # 主要占用工位
    avg_prep_seconds: float  # 平均制作时间（秒）
    std_prep_seconds: float  # 制作时间标准差（秒）
    daily_order_count: float # 日均点单量
    peak_ratio: float = 0.4  # 高峰时段订单占比（默认40%在午/晚高峰）


@dataclass
class StationResult:
    """单工位模拟结果"""
    station_id: str
    station_name: str
    capacity: int
    utilization_pct: float        # 利用率 ρ (0-100)
    avg_wait_seconds: float       # 平均等待时间
    is_bottleneck: bool           # 是否瓶颈
    status: str                   # "正常" / "繁忙" / "过载"


@dataclass
class SimulationResult:
    """模拟结果"""
    scenario: str                          # "当前菜单" / "加入新品后"
    peak_duration_hours: float             # 高峰时段时长
    total_avg_wait_seconds: float          # 全厨房平均等待时间
    station_results: List[StationResult]   # 各工位结果
    bottleneck_stations: List[str]         # 瓶颈工位名称
    recommendations: List[str]            # 建议


@dataclass
class ComparisonResult:
    """新品加入前后对比"""
    before: SimulationResult
    after: SimulationResult
    delta_wait_seconds: float              # 等待时间变化
    new_bottlenecks: List[str]             # 新增瓶颈
    risk_level: str                        # "低" / "中" / "高"
    summary: str                           # 一句话结论


# ── M/G/s 排队论纯函数 ────────────────────────────────────────────────────────

def erlang_c(s: int, rho_total: float) -> float:
    """
    Erlang C 公式近似：计算所有服务台忙碌的概率。
    s: 服务台数量
    rho_total: 总负载 = λ / (s × μ) × s = λ/μ
    返回: P(排队) 概率
    """
    if s <= 0 or rho_total <= 0:
        return 0.0
    rho_per_server = rho_total / s
    if rho_per_server >= 1.0:
        return 1.0  # 过载，必定排队

    # Erlang C: P(wait) = (A^s / s!) × (1 / (1-ρ)) / Σ(A^k/k!) + (A^s/s!)×(1/(1-ρ))
    # 其中 A = rho_total
    a = rho_total

    # 计算 A^s / s!
    a_s_over_s_fact = (a ** s) / math.factorial(s)
    inv_1_minus_rho = 1.0 / (1.0 - rho_per_server)

    # 计算 Σ(A^k / k!) for k=0..s-1
    sum_terms = sum((a ** k) / math.factorial(k) for k in range(s))

    denominator = sum_terms + a_s_over_s_fact * inv_1_minus_rho
    if denominator == 0:
        return 0.0

    return (a_s_over_s_fact * inv_1_minus_rho) / denominator


def mgs_avg_wait(
    arrival_rate: float,
    service_rate: float,
    service_cv: float,
    num_servers: int,
) -> float:
    """
    M/G/s 近似平均等待时间（Kingman/Allen-Cunneen 近似）。

    Args:
        arrival_rate: λ，每秒到达率
        service_rate: μ，每秒服务率（1/平均服务时间）
        service_cv: 服务时间的变异系数 σ/μ_time
        num_servers: s，服务台数量

    Returns:
        平均等待时间（秒），如果系统过载返回 float('inf')
    """
    if num_servers <= 0 or service_rate <= 0:
        return float('inf')

    rho_total = arrival_rate / service_rate  # A = λ/μ
    rho = rho_total / num_servers             # ρ = A/s

    if rho >= 1.0:
        return float('inf')  # 系统过载

    # M/M/s 等待时间
    p_wait = erlang_c(num_servers, rho_total)
    w_mms = p_wait / (num_servers * service_rate * (1 - rho))

    # Allen-Cunneen M/G/s 修正：乘以 (1 + cv²) / 2
    correction = (1 + service_cv ** 2) / 2
    return w_mms * correction


def calc_utilization(arrival_rate: float, service_rate: float, num_servers: int) -> float:
    """计算工位利用率 ρ"""
    if num_servers <= 0 or service_rate <= 0:
        return 100.0
    rho = arrival_rate / (service_rate * num_servers)
    return min(100.0, rho * 100)


def classify_utilization(util_pct: float) -> str:
    if util_pct >= 90:
        return "过载"
    elif util_pct >= 70:
        return "繁忙"
    return "正常"


# ── 服务类 ────────────────────────────────────────────────────────────────────

class KitchenSimulatorService:
    """
    厨房高峰压力模拟服务。

    使用方式：
    1. 定义工位配置和当前菜单的负载
    2. 调用 simulate() 获取当前状态
    3. 调用 compare() 对比加入新品前后的变化
    """

    def simulate(
        self,
        stations: List[WorkStation],
        workloads: List[DishWorkload],
        peak_hours: float = 2.5,
    ) -> SimulationResult:
        """
        模拟高峰时段厨房压力。

        Args:
            stations: 工位配置
            workloads: 各菜品负载
            peak_hours: 高峰时段时长（小时）

        Returns:
            SimulationResult
        """
        peak_seconds = peak_hours * 3600

        # 按工位聚合负载
        station_map = {s.station_id: s for s in stations}
        station_load: Dict[str, list] = {s.station_id: [] for s in stations}
        for w in workloads:
            if w.station_id in station_load:
                station_load[w.station_id].append(w)

        station_results = []
        total_wait = 0.0
        total_weight = 0.0

        for sid, ws_list in station_load.items():
            station = station_map[sid]
            if not ws_list:
                station_results.append(StationResult(
                    station_id=sid, station_name=station.name,
                    capacity=station.capacity,
                    utilization_pct=0, avg_wait_seconds=0,
                    is_bottleneck=False, status="正常",
                ))
                continue

            # 高峰时段到达率 λ = Σ(每道菜日均量 × 高峰占比) / 高峰秒数
            arrival_rate = sum(
                w.daily_order_count * w.peak_ratio / peak_seconds
                for w in ws_list
            )

            # 加权平均服务时间和标准差
            total_orders = sum(w.daily_order_count * w.peak_ratio for w in ws_list)
            if total_orders == 0:
                station_results.append(StationResult(
                    station_id=sid, station_name=station.name,
                    capacity=station.capacity,
                    utilization_pct=0, avg_wait_seconds=0,
                    is_bottleneck=False, status="正常",
                ))
                continue

            avg_service_time = sum(
                w.avg_prep_seconds * w.daily_order_count * w.peak_ratio
                for w in ws_list
            ) / total_orders

            avg_std = sum(
                w.std_prep_seconds * w.daily_order_count * w.peak_ratio
                for w in ws_list
            ) / total_orders

            service_rate = 1.0 / avg_service_time if avg_service_time > 0 else 1.0
            cv = avg_std / avg_service_time if avg_service_time > 0 else 0.5

            util = calc_utilization(arrival_rate, service_rate, station.capacity)
            wait = mgs_avg_wait(arrival_rate, service_rate, cv, station.capacity)
            if wait == float('inf'):
                wait = 9999.0  # 上限

            is_bottleneck = util >= 85
            station_results.append(StationResult(
                station_id=sid, station_name=station.name,
                capacity=station.capacity,
                utilization_pct=round(util, 1),
                avg_wait_seconds=round(wait, 1),
                is_bottleneck=is_bottleneck,
                status=classify_utilization(util),
            ))

            total_wait += wait * total_orders
            total_weight += total_orders

        avg_wait = total_wait / total_weight if total_weight > 0 else 0
        bottlenecks = [r.station_name for r in station_results if r.is_bottleneck]

        recs = []
        for r in station_results:
            if r.status == "过载":
                recs.append(f"{r.station_name}过载（利用率{r.utilization_pct:.0f}%），建议增加工位或减少该工位菜品")
            elif r.status == "繁忙":
                recs.append(f"{r.station_name}偏忙（利用率{r.utilization_pct:.0f}%），高峰期可能排队")

        return SimulationResult(
            scenario="模拟",
            peak_duration_hours=peak_hours,
            total_avg_wait_seconds=round(avg_wait, 1),
            station_results=station_results,
            bottleneck_stations=bottlenecks,
            recommendations=recs,
        )

    def compare(
        self,
        stations: List[WorkStation],
        current_workloads: List[DishWorkload],
        new_dish_workload: DishWorkload,
        peak_hours: float = 2.5,
    ) -> ComparisonResult:
        """
        对比加入新品前后的厨房压力变化。

        Args:
            stations: 工位配置
            current_workloads: 当前菜单负载
            new_dish_workload: 新品负载
            peak_hours: 高峰时段时长

        Returns:
            ComparisonResult
        """
        before = self.simulate(stations, current_workloads, peak_hours)
        before.scenario = "当前菜单"

        after_workloads = current_workloads + [new_dish_workload]
        after = self.simulate(stations, after_workloads, peak_hours)
        after.scenario = "加入新品后"

        delta = after.total_avg_wait_seconds - before.total_avg_wait_seconds
        new_bottlenecks = [
            name for name in after.bottleneck_stations
            if name not in before.bottleneck_stations
        ]

        if delta <= 30:
            risk = "低"
            summary = f"新品对出品效率影响很小（等待时间仅增加{delta:.0f}秒），可放心上线"
        elif delta <= 120:
            risk = "中"
            summary = f"新品导致等待时间增加{delta:.0f}秒，建议高峰期限量供应或错峰推荐"
        else:
            risk = "高"
            summary = f"新品严重影响出品效率（等待时间增加{delta:.0f}秒），建议优化工序或增加{', '.join(new_bottlenecks)}工位后再上线"

        logger.info(
            "厨房压力模拟完成",
            delta_wait=round(delta, 1),
            risk=risk,
            new_bottlenecks=new_bottlenecks,
        )

        return ComparisonResult(
            before=before,
            after=after,
            delta_wait_seconds=round(delta, 1),
            new_bottlenecks=new_bottlenecks,
            risk_level=risk,
            summary=summary,
        )
