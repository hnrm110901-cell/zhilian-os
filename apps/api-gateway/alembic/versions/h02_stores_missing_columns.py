"""
stores 테이블에 누락된 컬럼 추가

Model에 정의된 컬럼들이 실제 DB에 없어 SQLAlchemy SELECT 시 오류 발생.
기존 레코드와 호환되도록 모든 컬럼은 nullable로 추가.

Revision ID: h02_stores_missing_columns
Revises: h01_fix_dish_ingredients
Create Date: 2026-03-06
"""
from alembic import op, context
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'h02_stores_missing_columns'
down_revision = 'h01_fix_dish_ingredients'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = None if context.is_offline_mode() else op.get_bind()

    def col_exists(table, col):
        if conn is None:
            return False
        r = conn.execute(sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name=:t AND column_name=:c)"
        ), {"t": table, "c": col})
        return r.scalar()

    # 逐列按需添加，避免重复执行报错
    cols = [
        ("city",                    "VARCHAR(50)"),
        ("district",                "VARCHAR(50)"),
        ("email",                   "VARCHAR(100)"),
        ("manager_id",              "UUID"),
        ("region",                  "VARCHAR(50)"),
        ("is_active",               "BOOLEAN DEFAULT TRUE NOT NULL"),
        ("area",                    "DOUBLE PRECISION"),
        ("seats",                   "INTEGER"),
        ("floors",                  "INTEGER DEFAULT 1"),
        ("opening_date",            "VARCHAR(20)"),
        ("business_hours",          "JSON"),
        ("config",                  "JSON"),
        ("monthly_revenue_target",  "NUMERIC(12, 2)"),
        ("daily_customer_target",   "INTEGER"),
        ("cost_ratio_target",       "DOUBLE PRECISION"),
        ("labor_cost_ratio_target", "DOUBLE PRECISION"),
    ]
    for col_name, col_type in cols:
        if not col_exists("stores", col_name):
            op.execute(sa.text(
                f"ALTER TABLE stores ADD COLUMN {col_name} {col_type}"
            ))

    # 将现有记录的 is_active 默认设为 TRUE
    op.execute(sa.text(
        "UPDATE stores SET is_active = TRUE WHERE is_active IS NULL"
    ))


def downgrade() -> None:
    cols = [
        "city", "district", "email", "manager_id", "region", "is_active",
        "area", "seats", "floors", "opening_date", "business_hours", "config",
        "monthly_revenue_target", "daily_customer_target",
        "cost_ratio_target", "labor_cost_ratio_target",
    ]
    for col in cols:
        op.execute(sa.text(f"ALTER TABLE stores DROP COLUMN IF EXISTS {col}"))
