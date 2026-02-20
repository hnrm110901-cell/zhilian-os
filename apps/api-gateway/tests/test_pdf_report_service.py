"""
PDF报表服务测试
Tests for PDF Report Service
"""
import pytest
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch, Mock
from io import BytesIO

# Mock reportlab before importing the service
sys.modules['reportlab'] = MagicMock()
sys.modules['reportlab.lib'] = MagicMock()
sys.modules['reportlab.lib.colors'] = MagicMock()
sys.modules['reportlab.lib.pagesizes'] = MagicMock()
sys.modules['reportlab.lib.styles'] = MagicMock()
sys.modules['reportlab.lib.units'] = MagicMock()
sys.modules['reportlab.lib.enums'] = MagicMock()
sys.modules['reportlab.platypus'] = MagicMock()
sys.modules['reportlab.pdfbase'] = MagicMock()
sys.modules['reportlab.pdfbase.pdfmetrics'] = MagicMock()
sys.modules['reportlab.pdfbase.ttfonts'] = MagicMock()

from src.services.pdf_report_service import PDFReportService


class TestPDFReportService:
    """PDFReportService测试类"""

    def test_init(self):
        """测试初始化"""
        service = PDFReportService()
        assert service.styles is not None
        assert service.title_style is not None
        assert service.heading_style is not None
        assert service.normal_style is not None

    @patch('src.services.pdf_report_service.SimpleDocTemplate')
    def test_generate_income_statement_pdf(self, mock_doc_cls):
        """测试生成损益表PDF"""
        service = PDFReportService()

        # Mock document
        mock_doc = MagicMock()
        mock_doc_cls.return_value = mock_doc

        data = {
            "revenue": 100000.0,
            "other_income": 5000.0,
            "total_revenue": 105000.0,
            "cost_of_goods": 60000.0,
            "gross_profit": 45000.0,
            "operating_expenses": 20000.0,
            "net_profit": 25000.0,
        }

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)

        result = service.generate_income_statement_pdf(data, start_date, end_date)

        # Verify document was built
        mock_doc.build.assert_called_once()
        assert isinstance(result, bytes)

    def test_generate_income_statement_with_empty_data(self):
        """测试使用空数据生成损益表"""
        service = PDFReportService()

        data = {}
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)

        # Should not raise exception
        result = service.generate_income_statement_pdf(data, start_date, end_date)
        assert isinstance(result, bytes)
