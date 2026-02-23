"""
PDF报表生成服务
使用ReportLab生成PDF格式的财务报表
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import os
import structlog

logger = structlog.get_logger()


def _register_chinese_font() -> Optional[str]:
    """尝试注册中文字体，返回字体名称或None"""
    candidates = [
        ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", "NotoSansCJK"),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "NotoSansCJK"),
        ("/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf", "NotoSansCJK"),
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "WQYMicroHei"),
        ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "WQYZenHei"),
        ("/System/Library/Fonts/PingFang.ttc", "PingFang"),
        ("/System/Library/Fonts/STHeiti Light.ttc", "STHeiti"),
    ]
    for path, name in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                logger.info("中文字体注册成功", font=name, path=path)
                return name
            except Exception as e:
                logger.warning("字体注册失败", font=name, error=str(e))
    logger.warning("未找到中文字体，PDF中文可能显示为乱码。建议运行: apt-get install fonts-noto-cjk")
    return None


class PDFReportService:
    """PDF报表生成服务"""

    def __init__(self):
        # 尝试注册中文字体
        self._chinese_font = _register_chinese_font()
        self.styles = getSampleStyleSheet()
        font_name = self._chinese_font or "Helvetica"

        # 创建自定义样式
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontName=font_name,
            fontSize=18,
            textColor=colors.HexColor('#1890ff'),
            spaceAfter=30,
            alignment=TA_CENTER,
        )

        self.heading_style = ParagraphStyle(
            'CustomHeading',
            parent=self.styles['Heading2'],
            fontName=font_name,
            fontSize=14,
            textColor=colors.HexColor('#262626'),
            spaceAfter=12,
        )

        self.normal_style = ParagraphStyle(
            'CustomNormal',
            parent=self.styles['Normal'],
            fontName=font_name,
            fontSize=10,
            textColor=colors.HexColor('#595959'),
        )

    def generate_income_statement_pdf(
        self,
        data: Dict[str, Any],
        start_date: datetime,
        end_date: datetime
    ) -> bytes:
        """
        生成损益表PDF

        Args:
            data: 损益表数据
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            PDF文件字节流
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        story = []

        # 标题
        title = Paragraph("Income Statement / 损益表", self.title_style)
        story.append(title)

        # 日期范围
        date_range = Paragraph(
            f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
            self.normal_style
        )
        story.append(date_range)
        story.append(Spacer(1, 20))

        # 收入部分
        story.append(Paragraph("Revenue", self.heading_style))
        revenue_data = [
            ['Item', 'Amount (CNY)'],
            ['Operating Revenue', f'¥{data.get("revenue", 0):,.2f}'],
            ['Other Income', f'¥{data.get("other_income", 0):,.2f}'],
            ['Total Revenue', f'¥{data.get("total_revenue", 0):,.2f}'],
        ]
        revenue_table = Table(revenue_data, colWidths=[3*inch, 2*inch])
        revenue_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1890ff')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(revenue_table)
        story.append(Spacer(1, 20))

        # 成本部分
        story.append(Paragraph("Cost of Goods Sold", self.heading_style))
        cogs_data = [
            ['Item', 'Amount (CNY)'],
            ['Cost of Goods Sold', f'¥{data.get("cost_of_goods_sold", 0):,.2f}'],
            ['Gross Profit', f'¥{data.get("gross_profit", 0):,.2f}'],
            ['Gross Profit Margin', f'{data.get("gross_profit_margin", 0):.2f}%'],
        ]
        cogs_table = Table(cogs_data, colWidths=[3*inch, 2*inch])
        cogs_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#52c41a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgreen),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(cogs_table)
        story.append(Spacer(1, 20))

        # 费用部分
        story.append(Paragraph("Operating Expenses", self.heading_style))
        expenses_data = [
            ['Item', 'Amount (CNY)'],
            ['Labor Cost', f'¥{data.get("labor_cost", 0):,.2f}'],
            ['Rent', f'¥{data.get("rent", 0):,.2f}'],
            ['Utilities', f'¥{data.get("utilities", 0):,.2f}'],
            ['Marketing', f'¥{data.get("marketing", 0):,.2f}'],
            ['Other Expenses', f'¥{data.get("other_expenses", 0):,.2f}'],
            ['Total Expenses', f'¥{data.get("total_expenses", 0):,.2f}'],
        ]
        expenses_table = Table(expenses_data, colWidths=[3*inch, 2*inch])
        expenses_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#faad14')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightyellow),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(expenses_table)
        story.append(Spacer(1, 20))

        # 利润部分
        story.append(Paragraph("Profit", self.heading_style))
        profit_data = [
            ['Item', 'Amount (CNY)'],
            ['Operating Profit', f'¥{data.get("operating_profit", 0):,.2f}'],
            ['Operating Profit Margin', f'{data.get("operating_profit_margin", 0):.2f}%'],
            ['Net Profit', f'¥{data.get("net_profit", 0):,.2f}'],
            ['Net Profit Margin', f'{data.get("net_profit_margin", 0):.2f}%'],
        ]
        profit_table = Table(profit_data, colWidths=[3*inch, 2*inch])

        # 根据利润正负设置颜色
        net_profit = data.get("net_profit", 0)
        profit_color = colors.HexColor('#52c41a') if net_profit >= 0 else colors.HexColor('#ff4d4f')

        profit_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), profit_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(profit_table)

        # 页脚
        story.append(Spacer(1, 40))
        footer = Paragraph(
            f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Zhilian OS",
            ParagraphStyle('Footer', parent=self.normal_style, fontSize=8, textColor=colors.grey, alignment=TA_CENTER)
        )
        story.append(footer)

        # 生成PDF
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        return pdf_bytes

    def generate_cash_flow_pdf(
        self,
        data: Dict[str, Any],
        start_date: datetime,
        end_date: datetime
    ) -> bytes:
        """
        生成现金流量表PDF

        Args:
            data: 现金流量表数据
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            PDF文件字节流
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        story = []

        # 标题
        title = Paragraph("Cash Flow Statement / 现金流量表", self.title_style)
        story.append(title)

        # 日期范围
        date_range = Paragraph(
            f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
            self.normal_style
        )
        story.append(date_range)
        story.append(Spacer(1, 20))

        # 经营活动现金流
        story.append(Paragraph("Operating Activities", self.heading_style))
        operating_data = [
            ['Item', 'Amount (CNY)'],
            ['Cash from Sales', f'¥{data.get("cash_from_sales", 0):,.2f}'],
            ['Cash for Purchases', f'¥{data.get("cash_for_purchases", 0):,.2f}'],
            ['Cash for Salaries', f'¥{data.get("cash_for_salaries", 0):,.2f}'],
            ['Cash for Operations', f'¥{data.get("cash_for_operations", 0):,.2f}'],
            ['Net Operating Cash Flow', f'¥{data.get("operating_cash_flow", 0):,.2f}'],
        ]
        operating_table = Table(operating_data, colWidths=[3*inch, 2*inch])
        operating_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1890ff')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(operating_table)
        story.append(Spacer(1, 20))

        # 投资活动现金流
        story.append(Paragraph("Investing Activities", self.heading_style))
        investing_data = [
            ['Item', 'Amount (CNY)'],
            ['Cash for Investments', f'¥{data.get("cash_for_investments", 0):,.2f}'],
            ['Net Investing Cash Flow', f'¥{data.get("investing_cash_flow", 0):,.2f}'],
        ]
        investing_table = Table(investing_data, colWidths=[3*inch, 2*inch])
        investing_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#52c41a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgreen),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(investing_table)
        story.append(Spacer(1, 20))

        # 筹资活动现金流
        story.append(Paragraph("Financing Activities", self.heading_style))
        financing_data = [
            ['Item', 'Amount (CNY)'],
            ['Cash from Financing', f'¥{data.get("cash_from_financing", 0):,.2f}'],
            ['Net Financing Cash Flow', f'¥{data.get("financing_cash_flow", 0):,.2f}'],
        ]
        financing_table = Table(financing_data, colWidths=[3*inch, 2*inch])
        financing_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#faad14')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightyellow),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(financing_table)
        story.append(Spacer(1, 20))

        # 现金净变动
        story.append(Paragraph("Net Change in Cash", self.heading_style))
        summary_data = [
            ['Item', 'Amount (CNY)'],
            ['Net Cash Flow', f'¥{data.get("net_cash_flow", 0):,.2f}'],
            ['Beginning Cash', f'¥{data.get("beginning_cash", 0):,.2f}'],
            ['Ending Cash', f'¥{data.get("ending_cash", 0):,.2f}'],
        ]
        summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#722ed1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lavender),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(summary_table)

        # 页脚
        story.append(Spacer(1, 40))
        footer = Paragraph(
            f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Zhilian OS",
            ParagraphStyle('Footer', parent=self.normal_style, fontSize=8, textColor=colors.grey, alignment=TA_CENTER)
        )
        story.append(footer)

        # 生成PDF
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        return pdf_bytes


# 全局实例
pdf_report_service = PDFReportService()
