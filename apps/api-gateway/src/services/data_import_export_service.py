"""
数据导入导出服务
支持Excel和CSV格式的批量导入导出
"""
from typing import Dict, List, Optional, Any, BinaryIO
from datetime import datetime
import io
import csv
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

logger = structlog.get_logger()


class DataImportExportService:
    """数据导入导出服务"""

    def __init__(self):
        pass

    async def export_to_csv(
        self,
        data: List[Dict[str, Any]],
        columns: List[str],
        filename: str = "export.csv"
    ) -> bytes:
        """
        导出数据为CSV格式

        Args:
            data: 数据列表
            columns: 列名列表
            filename: 文件名

        Returns:
            CSV文件字节流
        """
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns)

        # 写入表头
        writer.writeheader()

        # 写入数据
        for row in data:
            # 只保留指定的列
            filtered_row = {col: row.get(col, '') for col in columns}
            writer.writerow(filtered_row)

        return output.getvalue().encode('utf-8-sig')

    async def import_from_csv(
        self,
        file_content: bytes,
        required_columns: List[str],
        optional_columns: Optional[List[str]] = None
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        """
        从CSV文件导入数据

        Args:
            file_content: CSV文件内容
            required_columns: 必需的列
            optional_columns: 可选的列

        Returns:
            (数据列表, 错误列表)
        """
        errors = []
        data = []

        try:
            # 解码文件内容
            content = file_content.decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))

            # 验证列名
            if not reader.fieldnames:
                errors.append("CSV文件为空或格式不正确")
                return data, errors

            missing_columns = set(required_columns) - set(reader.fieldnames)
            if missing_columns:
                errors.append(f"缺少必需的列: {', '.join(missing_columns)}")
                return data, errors

            # 读取数据
            for row_num, row in enumerate(reader, start=2):  # 从第2行开始（第1行是表头）
                try:
                    # 验证必需字段
                    for col in required_columns:
                        if not row.get(col):
                            errors.append(f"第{row_num}行: 缺少必需字段 '{col}'")
                            continue

                    # 清理数据
                    cleaned_row = {}
                    all_columns = required_columns + (optional_columns or [])
                    for col in all_columns:
                        if col in row:
                            cleaned_row[col] = row[col].strip() if row[col] else None

                    data.append(cleaned_row)

                except Exception as e:
                    errors.append(f"第{row_num}行: 处理错误 - {str(e)}")

        except Exception as e:
            errors.append(f"文件解析错误: {str(e)}")

        return data, errors

    async def validate_import_data(
        self,
        data: List[Dict[str, Any]],
        validation_rules: Dict[str, Any]
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        """
        验证导入数据

        Args:
            data: 待验证的数据
            validation_rules: 验证规则

        Returns:
            (有效数据, 错误列表)
        """
        valid_data = []
        errors = []

        for idx, row in enumerate(data, start=1):
            row_errors = []

            for field, rules in validation_rules.items():
                value = row.get(field)

                # 必需字段验证
                if rules.get('required') and not value:
                    row_errors.append(f"字段 '{field}' 是必需的")
                    continue

                if value:
                    # 类型验证
                    field_type = rules.get('type')
                    if field_type == 'int':
                        try:
                            row[field] = int(value)
                        except ValueError:
                            row_errors.append(f"字段 '{field}' 必须是整数")

                    elif field_type == 'float':
                        try:
                            row[field] = float(value)
                        except ValueError:
                            row_errors.append(f"字段 '{field}' 必须是数字")

                    elif field_type == 'date':
                        try:
                            datetime.strptime(value, '%Y-%m-%d')
                        except ValueError:
                            row_errors.append(f"字段 '{field}' 必须是日期格式 (YYYY-MM-DD)")

                    # 长度验证
                    max_length = rules.get('max_length')
                    if max_length and len(str(value)) > max_length:
                        row_errors.append(f"字段 '{field}' 长度不能超过 {max_length}")

                    # 枚举值验证
                    choices = rules.get('choices')
                    if choices and value not in choices:
                        row_errors.append(f"字段 '{field}' 必须是以下值之一: {', '.join(choices)}")

            if row_errors:
                errors.append(f"第{idx}行: {'; '.join(row_errors)}")
            else:
                valid_data.append(row)

        return valid_data, errors

    async def export_users_to_csv(self, db: AsyncSession) -> bytes:
        """导出用户数据为CSV"""
        from src.models.user import User

        stmt = select(User)
        result = await db.execute(stmt)
        users = result.scalars().all()

        data = [
            {
                'id': str(user.id),
                'username': user.username,
                'email': user.email,
                'role': user.role.value if hasattr(user.role, 'value') else str(user.role),
                'store_id': user.store_id,
                'is_active': str(user.is_active),
                'created_at': user.created_at.isoformat() if user.created_at else '',
            }
            for user in users
        ]

        columns = ['id', 'username', 'email', 'role', 'store_id', 'is_active', 'created_at']
        return await self.export_to_csv(data, columns)

    async def import_users_from_csv(
        self,
        file_content: bytes,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """从CSV导入用户数据"""
        from src.models.user import User, UserRole

        # 定义必需和可选列
        required_columns = ['username', 'email', 'role']
        optional_columns = ['store_id', 'is_active']

        # 导入数据
        data, import_errors = await self.import_from_csv(
            file_content,
            required_columns,
            optional_columns
        )

        if import_errors:
            return {
                'success': False,
                'errors': import_errors,
                'imported_count': 0,
            }

        # 验证数据
        validation_rules = {
            'username': {'required': True, 'max_length': 50},
            'email': {'required': True, 'max_length': 100},
            'role': {'required': True, 'choices': ['admin', 'manager', 'staff']},
            'store_id': {'max_length': 36},
        }

        valid_data, validation_errors = await self.validate_import_data(data, validation_rules)

        if validation_errors:
            return {
                'success': False,
                'errors': validation_errors,
                'imported_count': 0,
            }

        # 导入用户
        imported_count = 0
        errors = []

        for row in valid_data:
            try:
                # 检查用户是否已存在
                stmt = select(User).where(User.username == row['username'])
                result = await db.execute(stmt)
                existing_user = result.scalar_one_or_none()

                if existing_user:
                    errors.append(f"用户 '{row['username']}' 已存在")
                    continue

                # 创建用户
                user = User(
                    username=row['username'],
                    email=row['email'],
                    role=UserRole(row['role']),
                    store_id=row.get('store_id'),
                    is_active=row.get('is_active', 'true').lower() == 'true',
                )

                # 设置默认密码
                from src.core.security import get_password_hash
                user.hashed_password = get_password_hash('password123')

                db.add(user)
                imported_count += 1

            except Exception as e:
                errors.append(f"导入用户 '{row['username']}' 失败: {str(e)}")

        await db.commit()

        return {
            'success': len(errors) == 0,
            'imported_count': imported_count,
            'errors': errors,
        }

    async def export_inventory_to_csv(self, db: AsyncSession) -> bytes:
        """导出库存数据为CSV"""
        from src.models.inventory import InventoryItem

        stmt = select(InventoryItem)
        result = await db.execute(stmt)
        items = result.scalars().all()

        data = [
            {
                'id': str(item.id),
                'name': item.name,
                'category': item.category,
                'quantity': str(item.quantity),
                'unit': item.unit,
                'min_quantity': str(item.min_quantity),
                'max_quantity': str(item.max_quantity),
                'unit_price': str(item.unit_price),
                'supplier': item.supplier,
                'store_id': item.store_id,
            }
            for item in items
        ]

        columns = ['id', 'name', 'category', 'quantity', 'unit', 'min_quantity', 'max_quantity', 'unit_price', 'supplier', 'store_id']
        return await self.export_to_csv(data, columns)

    async def import_inventory_from_csv(
        self,
        file_content: bytes,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """从CSV导入库存数据"""
        from src.models.inventory import InventoryItem

        # 定义必需和可选列
        required_columns = ['name', 'category', 'quantity', 'unit']
        optional_columns = ['min_quantity', 'max_quantity', 'unit_price', 'supplier', 'store_id']

        # 导入数据
        data, import_errors = await self.import_from_csv(
            file_content,
            required_columns,
            optional_columns
        )

        if import_errors:
            return {
                'success': False,
                'errors': import_errors,
                'imported_count': 0,
            }

        # 验证数据
        validation_rules = {
            'name': {'required': True, 'max_length': 100},
            'category': {'required': True, 'max_length': 50},
            'quantity': {'required': True, 'type': 'int'},
            'unit': {'required': True, 'max_length': 20},
            'min_quantity': {'type': 'int'},
            'max_quantity': {'type': 'int'},
            'unit_price': {'type': 'float'},
        }

        valid_data, validation_errors = await self.validate_import_data(data, validation_rules)

        if validation_errors:
            return {
                'success': False,
                'errors': validation_errors,
                'imported_count': 0,
            }

        # 导入库存
        imported_count = 0
        errors = []

        for row in valid_data:
            try:
                item = InventoryItem(
                    name=row['name'],
                    category=row['category'],
                    quantity=row['quantity'],
                    unit=row['unit'],
                    min_quantity=row.get('min_quantity', 10),
                    max_quantity=row.get('max_quantity', 1000),
                    unit_price=row.get('unit_price', 0),
                    supplier=row.get('supplier'),
                    store_id=row.get('store_id', 'STORE001'),
                )

                db.add(item)
                imported_count += 1

            except Exception as e:
                errors.append(f"导入库存 '{row['name']}' 失败: {str(e)}")

        await db.commit()

        return {
            'success': len(errors) == 0,
            'imported_count': imported_count,
            'errors': errors,
        }


# 全局实例
data_import_export_service = DataImportExportService()
