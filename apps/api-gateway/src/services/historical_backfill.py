"""
历史数据回填服务 — 三通道批量回填（API / 文件 / DB镜像）
支持断点续传、错误隔离、进度回调

核心能力：
  1. API 通道：通过已有适配器的历史数据查询接口按日期分页拉取
  2. 文件通道：解析 CSV/Excel 文件批量导入
  3. DB镜像通道：直接对接原SaaS的只读数据库副本
  4. 断点续传：记录 last_cursor，失败后从断点恢复
  5. 进度回调：实时向 DataFusionEngine 报告进度

使用方式：
  backfill = HistoricalBackfill(engine, resolver)
  result = await backfill.execute_task(task)
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import structlog

from .entity_resolver import EntityResolver, ResolveResult

logger = structlog.get_logger()


# ── 回填结果 ──────────────────────────────────────────────────────────────────

@dataclass
class BackfillResult:
    """回填结果"""
    task_id: str
    status: str              # completed / failed / paused
    processed_count: int
    success_count: int
    error_count: int
    duplicate_count: int
    last_cursor: Optional[str]
    errors: List[Dict] = field(default_factory=list)
    resolved_entities: List[Dict] = field(default_factory=list)
    provenances: List[Dict] = field(default_factory=list)


# ── 历史回填服务 ──────────────────────────────────────────────────────────────

class HistoricalBackfill:
    """
    历史数据回填服务

    执行流程：
    1. 根据 task.channel 选择采集通道
    2. 按批次拉取数据
    3. 每条数据经过 EntityResolver 解析
    4. 生成 provenance 血缘记录
    5. 回调 DataFusionEngine 更新进度
    6. 支持断点续传（从 last_cursor 恢复）
    """

    def __init__(
        self,
        entity_resolver: Optional[EntityResolver] = None,
        progress_callback: Optional[Callable] = None,
    ):
        """
        Args:
            entity_resolver: 实体解析器
            progress_callback: 进度回调函数 (task_id, progress_dict) -> None
        """
        self.resolver = entity_resolver or EntityResolver()
        self._progress_callback = progress_callback

    def backfill_from_records(
        self,
        task_id: str,
        entity_type: str,
        source_system: str,
        records: List[Dict],
        id_field: str = "id",
        name_field: str = "name",
        resume_from: Optional[str] = None,
    ) -> BackfillResult:
        """
        从内存记录列表回填（通用入口，API/文件/DB数据最终都转成records）

        Args:
            task_id: 融合任务ID
            entity_type: 实体类型
            source_system: 来源系统
            records: 数据记录列表
            id_field: 记录中的ID字段名
            name_field: 记录中的名称字段名
            resume_from: 断点续传起始位置（跳过此ID之前的记录）

        Returns:
            BackfillResult
        """
        success_count = 0
        error_count = 0
        duplicate_count = 0
        errors = []
        resolved_entities = []
        provenances = []

        # 断点续传：跳过已处理的记录
        skip = bool(resume_from)
        processed = 0

        for record in records:
            external_id = str(record.get(id_field, ""))
            if not external_id:
                error_count += 1
                errors.append({"record": record, "error": f"缺少 {id_field} 字段"})
                processed += 1
                continue

            # 断点续传逻辑
            if skip:
                if external_id == resume_from:
                    skip = False  # 找到断点，从下一条开始
                processed += 1
                continue

            try:
                # 实体解析
                name = record.get(name_field, "")
                phone = record.get("phone", record.get("customer_phone"))
                result = self.resolver.resolve(
                    entity_type=entity_type,
                    source_system=source_system,
                    external_id=external_id,
                    name=name,
                    phone=phone,
                    metadata=record,
                )

                if not result.is_new and result.match_method == "exact_id":
                    duplicate_count += 1
                else:
                    success_count += 1

                resolved_entities.append({
                    "canonical_id": result.canonical_id,
                    "canonical_name": result.canonical_name,
                    "external_id": external_id,
                    "confidence": result.confidence,
                    "match_method": result.match_method,
                    "is_new": result.is_new,
                })

                # 生成数据血缘
                provenances.append({
                    "id": str(uuid.uuid4()),
                    "target_table": f"{entity_type}s",
                    "target_id": result.canonical_id,
                    "source_system": source_system,
                    "source_id": external_id,
                    "fusion_task_id": task_id,
                    "original_value": json.dumps(record, ensure_ascii=False, default=str),
                })

            except Exception as exc:
                error_count += 1
                errors.append({
                    "external_id": external_id,
                    "error": str(exc),
                })
                logger.warning(
                    "backfill.record_error",
                    task_id=task_id,
                    external_id=external_id,
                    error=str(exc),
                )

            processed += 1

            # 每100条报告一次进度
            if processed % 100 == 0 and self._progress_callback:
                self._progress_callback(task_id, {
                    "processed_count": processed,
                    "success_count": success_count,
                    "error_count": error_count,
                    "duplicate_count": duplicate_count,
                    "last_cursor": external_id,
                })

        status = "completed"
        if error_count > 0 and success_count == 0:
            status = "failed"

        return BackfillResult(
            task_id=task_id,
            status=status,
            processed_count=processed,
            success_count=success_count,
            error_count=error_count,
            duplicate_count=duplicate_count,
            last_cursor=external_id if records else resume_from,
            errors=errors[:50],  # 最多保留50条错误
            resolved_entities=resolved_entities,
            provenances=provenances,
        )

    def backfill_from_csv(
        self,
        task_id: str,
        entity_type: str,
        source_system: str,
        csv_content: str,
        id_field: str = "id",
        name_field: str = "name",
        encoding: str = "utf-8-sig",
    ) -> BackfillResult:
        """
        从CSV内容回填

        Args:
            task_id: 融合任务ID
            entity_type: 实体类型
            source_system: 来源系统
            csv_content: CSV文本内容
            id_field: CSV中的ID列名
            name_field: CSV中的名称列名
            encoding: 编码（默认 UTF-8-BOM）
        """
        records = []
        reader = csv.DictReader(io.StringIO(csv_content))
        for row in reader:
            records.append(dict(row))

        logger.info(
            "backfill.csv_parsed",
            task_id=task_id,
            record_count=len(records),
            entity_type=entity_type,
        )

        return self.backfill_from_records(
            task_id=task_id,
            entity_type=entity_type,
            source_system=source_system,
            records=records,
            id_field=id_field,
            name_field=name_field,
        )

    def generate_date_ranges(
        self,
        start_date: date,
        end_date: date,
        interval_days: int = 1,
    ) -> List[Dict[str, date]]:
        """
        生成日期范围列表（用于按天/按周拉取API历史数据）

        Args:
            start_date: 起始日期
            end_date: 截止日期
            interval_days: 每批的天数间隔

        Returns:
            [{"start": date, "end": date}, ...]
        """
        ranges = []
        current = start_date
        while current <= end_date:
            range_end = min(current + timedelta(days=interval_days - 1), end_date)
            ranges.append({"start": current, "end": range_end})
            current = range_end + timedelta(days=1)
        return ranges

    def estimate_total_records(
        self,
        entity_type: str,
        source_system: str,
        date_range_days: int,
    ) -> int:
        """
        估算历史数据总量（用于进度条显示）
        基于行业经验值的粗略估算

        Args:
            entity_type: 实体类型
            source_system: 来源系统
            date_range_days: 数据范围天数
        """
        # 行业经验值：单店日均数据量
        daily_estimates = {
            "order": 150,       # 日均150笔订单
            "dish": 0.5,        # 菜品变化很少，总量约200
            "customer": 30,     # 日均30个新/回头客记录
            "ingredient": 0.3,  # 食材品类变化少，总量约100
            "supplier": 0.05,   # 供应商很少变化
            "employee": 0.1,    # 员工变动少
        }
        daily = daily_estimates.get(entity_type, 10)
        return max(1, int(daily * date_range_days))
