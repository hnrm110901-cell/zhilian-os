from src.core.database import _get_async_database_url


def test_keeps_asyncpg_url() -> None:
    url = "postgresql+asyncpg://user:pass@localhost:5432/zhilian"

    assert _get_async_database_url(url) == url


def test_converts_plain_postgres_url_to_asyncpg() -> None:
    url = "postgresql://user:pass@localhost:5432/zhilian"

    assert _get_async_database_url(url) == "postgresql+asyncpg://user:pass@localhost:5432/zhilian"


def test_converts_psycopg2_url_to_asyncpg() -> None:
    url = "postgresql+psycopg2://user:pass@localhost:5432/zhilian"

    assert _get_async_database_url(url) == "postgresql+asyncpg://user:pass@localhost:5432/zhilian"


def test_leaves_non_postgres_urls_unchanged() -> None:
    url = "sqlite+aiosqlite:///tmp/test.db"

    assert _get_async_database_url(url) == url
