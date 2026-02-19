"""
数据导入导出API
"""
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_active_user, require_permission
from src.services.data_import_export_service import data_import_export_service
from src.models import User

router = APIRouter()


@router.get("/export/users")
async def export_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("data:export")),
):
    """
    导出用户数据为CSV

    需要data:export权限
    """
    try:
        content = await data_import_export_service.export_users_to_csv(db)

        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=users_export.csv"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.post("/import/users")
async def import_users(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("data:import")),
):
    """
    从CSV导入用户数据

    需要data:import权限

    CSV格式要求:
    - 必需列: username, email, role
    - 可选列: store_id, is_active
    - role可选值: admin, manager, staff
    """
    try:
        # 验证文件类型
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="只支持CSV文件")

        # 读取文件内容
        content = await file.read()

        # 导入数据
        result = await data_import_export_service.import_users_from_csv(content, db)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


@router.get("/export/inventory")
async def export_inventory(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("data:export")),
):
    """
    导出库存数据为CSV

    需要data:export权限
    """
    try:
        content = await data_import_export_service.export_inventory_to_csv(db)

        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=inventory_export.csv"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.post("/import/inventory")
async def import_inventory(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("data:import")),
):
    """
    从CSV导入库存数据

    需要data:import权限

    CSV格式要求:
    - 必需列: name, category, quantity, unit
    - 可选列: min_quantity, max_quantity, unit_price, supplier, store_id
    """
    try:
        # 验证文件类型
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="只支持CSV文件")

        # 读取文件内容
        content = await file.read()

        # 导入数据
        result = await data_import_export_service.import_inventory_from_csv(content, db)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


@router.get("/templates/users")
async def get_user_import_template(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取用户导入模板CSV

    返回一个包含示例数据的CSV模板
    """
    import io
    import csv

    output = io.StringIO()
    writer = csv.writer(output)

    # 写入表头
    writer.writerow(['username', 'email', 'role', 'store_id', 'is_active'])

    # 写入示例数据
    writer.writerow(['zhangsan', 'zhangsan@example.com', 'staff', 'STORE001', 'true'])
    writer.writerow(['lisi', 'lisi@example.com', 'manager', 'STORE001', 'true'])

    content = output.getvalue().encode('utf-8-sig')

    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=user_import_template.csv"
        }
    )


@router.get("/templates/inventory")
async def get_inventory_import_template(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取库存导入模板CSV

    返回一个包含示例数据的CSV模板
    """
    import io
    import csv

    output = io.StringIO()
    writer = csv.writer(output)

    # 写入表头
    writer.writerow(['name', 'category', 'quantity', 'unit', 'min_quantity', 'max_quantity', 'unit_price', 'supplier', 'store_id'])

    # 写入示例数据
    writer.writerow(['西红柿', '蔬菜', '100', '斤', '20', '500', '3.5', '新鲜蔬菜供应商', 'STORE001'])
    writer.writerow(['鸡蛋', '禽蛋', '200', '个', '50', '1000', '0.8', '农场直供', 'STORE001'])

    content = output.getvalue().encode('utf-8-sig')

    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=inventory_import_template.csv"
        }
    )
