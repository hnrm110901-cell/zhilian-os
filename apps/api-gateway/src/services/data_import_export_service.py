"""
数据导入导出服务
"""

import csv
import io
from typing import Any, Dict, List, Optional, Tuple


class DataImportExportService:
    """CSV 数据导入/导出服务（无外部依赖）"""

    async def export_to_csv(
        self,
        data: List[Dict[str, Any]],
        columns: List[str],
        filename: Optional[str] = None,
    ) -> bytes:
        """将数据导出为 CSV 字节流（UTF-8-BOM，兼容 Excel）。

        Args:
            data:    数据行列表
            columns: 要导出的列名（按顺序）
            filename: 可选，文件名（当前不影响返回值）

        Returns:
            bytes: UTF-8-BOM 编码的 CSV 内容
        """
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=columns,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(data)
        return buf.getvalue().encode("utf-8-sig")

    async def import_from_csv(
        self,
        file_content: bytes,
        required_columns: List[str],
        optional_columns: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """从 CSV 字节流导入数据。

        Args:
            file_content:      文件内容（bytes）
            required_columns:  必需列名列表
            optional_columns:  可选列名列表

        Returns:
            (data, errors): 成功行列表 + 错误信息列表
        """
        errors: List[str] = []
        data: List[Dict[str, Any]] = []

        if not file_content:
            errors.append("文件内容为空")
            return data, errors

        # 剥离 BOM
        text = file_content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        # 检查必需列
        fieldnames = reader.fieldnames or []
        missing = [col for col in required_columns if col not in fieldnames]
        if missing:
            errors.append(f"缺少必需的列: {', '.join(missing)}")
            return data, errors

        for row_idx, row in enumerate(reader, start=2):
            row_errors = []
            for col in required_columns:
                if not row.get(col, "").strip():
                    row_errors.append(f"第 {row_idx} 行缺少必需字段 '{col}'")
            if row_errors:
                errors.extend(row_errors)
                continue
            data.append(dict(row))

        return data, errors
