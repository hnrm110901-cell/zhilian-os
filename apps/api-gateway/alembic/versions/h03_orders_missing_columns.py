"""
orders / order_items 테이블 누락 컬럼 일괄 추가

SQLAlchemy 모델에 정의된 컬럼이 프로덕션 DB에 없어 UndefinedColumnError 발생.

Revision ID: h03_orders_missing_columns
Revises: h02_stores_missing_columns
Create Date: 2026-03-06
"""
from alembic import op, context
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'h03_orders_missing_columns'
down_revision = 'h02_stores_missing_columns'
branch_labels = None
depends_on = None


def _col_exists(conn, table, col):
    if conn is None:
        return False
    r = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name=:t AND column_name=:c)"
    ), {"t": table, "c": col})
    return r.scalar()


def _add_col(conn, table, col, col_type):
    if not _col_exists(conn, table, col):
        op.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))


def upgrade() -> None:
    conn = None if context.is_offline_mode() else op.get_bind()

    # ── orders ──────────────────────────────────────────────────────────────
    _add_col(conn, "orders", "discount_amount",  "INTEGER DEFAULT 0")
    _add_col(conn, "orders", "final_amount",      "INTEGER")
    _add_col(conn, "orders", "confirmed_at",      "TIMESTAMP WITH TIME ZONE")
    _add_col(conn, "orders", "completed_at",      "TIMESTAMP WITH TIME ZONE")
    _add_col(conn, "orders", "order_metadata",    "JSON")

    # final_amount 기본값: total_amount (기존 레코드 보정)
    # total_amount 는 numeric(10,2) 이지만 Integer 모델과 매핑 시 반올림 필요.
    # demo 에서는 final_amount = total_amount * 100 (분→원) 대신
    # 그냥 total_amount 를 그대로 쓰면 됨(원 단위 저장이므로).
    op.execute(sa.text(
        "UPDATE orders SET final_amount = ROUND(total_amount)::INTEGER "
        "WHERE final_amount IS NULL AND total_amount IS NOT NULL"
    ))

    # ── order_items ──────────────────────────────────────────────────────────
    _add_col(conn, "order_items", "customizations", "JSON")
    _add_col(conn, "order_items", "updated_at",
             "TIMESTAMP WITH TIME ZONE DEFAULT NOW()")


def downgrade() -> None:
    for col in ["discount_amount", "final_amount", "confirmed_at",
                "completed_at", "order_metadata"]:
        op.execute(sa.text(f"ALTER TABLE orders DROP COLUMN IF EXISTS {col}"))
    for col in ["customizations", "updated_at"]:
        op.execute(sa.text(f"ALTER TABLE order_items DROP COLUMN IF EXISTS {col}"))
