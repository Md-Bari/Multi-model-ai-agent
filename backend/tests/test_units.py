from app.db import engine_args
from app.services.llm import pick_tier
from app.services.pricing import cost_usd


def test_neon_url_is_adapted_for_asyncpg():
    url, kwargs = engine_args(
        "postgresql://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/db?sslmode=require&channel_binding=require"
    )
    assert url == "postgresql+asyncpg://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/db"
    assert kwargs["connect_args"] == {"ssl": "require", "statement_cache_size": 0}


def test_render_style_url():
    url, kwargs = engine_args("postgres://u:p@host:5432/db")
    assert url.startswith("postgresql+asyncpg://")
    assert kwargs["connect_args"] == {}


def test_pick_tier():
    assert pick_tier([{"role": "user", "content": "Hi there"}]) == "cheap"
    assert pick_tier([{"role": "user", "content": "Write a SQL query for top users"}]) == "strong"
    assert pick_tier([{"role": "user", "content": "এই কোড ঠিক করো"}]) == "strong"
    assert pick_tier([{"role": "user", "content": "x" * 2000}]) == "strong"


def test_cost():
    assert cost_usd("llama-3.1-8b-instant", 1_000_000, 1_000_000) == 0.05 + 0.08
    assert cost_usd("unknown-model", 100, 100) == 0.0
