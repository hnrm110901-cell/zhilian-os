"""z07 plugin marketplace

Revision ID: z07
Revises: z06_isv_lifecycle
Create Date: 2026-03-07
"""
from alembic import op

revision = 'z07'
down_revision = 'z06_isv_lifecycle'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE marketplace_plugins (
            id               VARCHAR(40)  PRIMARY KEY,
            developer_id     VARCHAR(40)  NOT NULL REFERENCES isv_developers(id),
            name             VARCHAR(100) NOT NULL,
            slug             VARCHAR(100) NOT NULL UNIQUE,
            description      TEXT,
            category         VARCHAR(50)  NOT NULL DEFAULT 'operations',
            icon_emoji       VARCHAR(10)  NOT NULL DEFAULT '🔌',
            version          VARCHAR(20)  NOT NULL DEFAULT '1.0.0',
            status           VARCHAR(30)  NOT NULL DEFAULT 'pending_review',
            tier_required    VARCHAR(20)  NOT NULL DEFAULT 'free',
            price_type       VARCHAR(20)  NOT NULL DEFAULT 'free',
            price_amount     FLOAT        NOT NULL DEFAULT 0,
            install_count    INTEGER      NOT NULL DEFAULT 0,
            rating_avg       FLOAT        NOT NULL DEFAULT 0,
            rating_count     INTEGER      NOT NULL DEFAULT 0,
            webhook_url      VARCHAR(500),
            tags             TEXT         NOT NULL DEFAULT '[]',
            review_note      VARCHAR(500),
            published_at     TIMESTAMPTZ,
            created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_mp_status   ON marketplace_plugins(status)")
    op.execute("CREATE INDEX ix_mp_category ON marketplace_plugins(category)")
    op.execute("CREATE INDEX ix_mp_developer ON marketplace_plugins(developer_id)")

    op.execute("""
        CREATE TABLE plugin_installations (
            id           VARCHAR(40)  PRIMARY KEY,
            plugin_id    VARCHAR(40)  NOT NULL REFERENCES marketplace_plugins(id),
            store_id     VARCHAR(100) NOT NULL,
            status       VARCHAR(20)  NOT NULL DEFAULT 'active',
            config       TEXT         NOT NULL DEFAULT '{}',
            installed_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            last_used_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE UNIQUE INDEX uq_plugin_store ON plugin_installations(plugin_id, store_id)")
    op.execute("CREATE INDEX ix_pi_store ON plugin_installations(store_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS plugin_installations")
    op.execute("DROP TABLE IF EXISTS marketplace_plugins")
