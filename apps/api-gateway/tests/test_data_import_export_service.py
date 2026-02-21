"""
数据导入导出服务测试
Tests for Data Import Export Service
"""
import pytest
import csv
import io
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.data_import_export_service import DataImportExportService


class TestDataImportExportService:
    """DataImportExportService测试类"""

    def test_init(self):
        """测试初始化"""
        service = DataImportExportService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_export_to_csv_basic(self):
        """测试基本CSV导出"""
        service = DataImportExportService()

        data = [
            {"name": "张三", "age": 30, "city": "北京"},
            {"name": "李四", "age": 25, "city": "上海"},
        ]
        columns = ["name", "age", "city"]

        result = await service.export_to_csv(data, columns)

        assert isinstance(result, bytes)
        # Decode and verify content
        content = result.decode('utf-8-sig')
        assert "name" in content
        assert "张三" in content
        assert "李四" in content

    @pytest.mark.asyncio
    async def test_export_to_csv_empty_data(self):
        """测试导出空数据"""
        service = DataImportExportService()

        data = []
        columns = ["name", "age"]

        result = await service.export_to_csv(data, columns)

        assert isinstance(result, bytes)
        content = result.decode('utf-8-sig')
        # Should have header only
        assert "name" in content
        assert "age" in content

    @pytest.mark.asyncio
    async def test_export_to_csv_partial_columns(self):
        """测试导出部分列"""
        service = DataImportExportService()

        data = [
            {"name": "张三", "age": 30, "city": "北京", "extra": "data"},
        ]
        columns = ["name", "age"]  # Only export name and age

        result = await service.export_to_csv(data, columns)

        content = result.decode('utf-8-sig')
        assert "name" in content
        assert "age" in content
        assert "extra" not in content

    @pytest.mark.asyncio
    async def test_import_from_csv_valid(self):
        """测试导入有效CSV"""
        service = DataImportExportService()

        # Create CSV content
        csv_content = "name,age,city\n张三,30,北京\n李四,25,上海"
        file_content = csv_content.encode('utf-8-sig')

        required_columns = ["name", "age"]
        optional_columns = ["city"]

        data, errors = await service.import_from_csv(
            file_content, required_columns, optional_columns
        )

        assert len(errors) == 0
        assert len(data) == 2
        assert data[0]["name"] == "张三"
        assert data[1]["name"] == "李四"

    @pytest.mark.asyncio
    async def test_import_from_csv_missing_required_column(self):
        """测试导入缺少必需列的CSV"""
        service = DataImportExportService()

        # CSV missing 'age' column
        csv_content = "name,city\n张三,北京"
        file_content = csv_content.encode('utf-8-sig')

        required_columns = ["name", "age"]

        data, errors = await service.import_from_csv(file_content, required_columns)

        assert len(errors) > 0
        assert "缺少必需的列" in errors[0]
        assert "age" in errors[0]

    @pytest.mark.asyncio
    async def test_import_from_csv_empty_file(self):
        """测试导入空CSV文件"""
        service = DataImportExportService()

        file_content = b""
        required_columns = ["name"]

        data, errors = await service.import_from_csv(file_content, required_columns)

        assert len(errors) > 0
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_import_from_csv_missing_required_value(self):
        """测试导入缺少必需值的CSV"""
        service = DataImportExportService()

        # Second row missing 'name' value
        csv_content = "name,age\n张三,30\n,25"
        file_content = csv_content.encode('utf-8-sig')

        required_columns = ["name", "age"]

        data, errors = await service.import_from_csv(file_content, required_columns)

        # Should have error for missing name in row 3
        assert len(errors) > 0

    @pytest.mark.asyncio
    async def test_export_to_csv_with_filename(self):
        """测试指定文件名导出"""
        service = DataImportExportService()

        data = [{"name": "张三"}]
        columns = ["name"]
        filename = "test_export.csv"

        result = await service.export_to_csv(data, columns, filename)

        assert isinstance(result, bytes)

    @pytest.mark.asyncio
    async def test_import_from_csv_only_required_columns(self):
        """测试仅使用必需列导入"""
        service = DataImportExportService()

        csv_content = "name,age\n张三,30"
        file_content = csv_content.encode('utf-8-sig')

        required_columns = ["name", "age"]

        data, errors = await service.import_from_csv(file_content, required_columns)

        assert len(errors) == 0
        assert len(data) == 1

    @pytest.mark.asyncio
    async def test_export_to_csv_special_characters(self):
        """测试导出包含特殊字符的数据"""
        service = DataImportExportService()

        data = [
            {"name": "张三,李四", "note": "包含\"引号\""},
        ]
        columns = ["name", "note"]

        result = await service.export_to_csv(data, columns)

        assert isinstance(result, bytes)
        content = result.decode('utf-8-sig')
        # CSV should handle special characters properly
        assert "张三" in content
