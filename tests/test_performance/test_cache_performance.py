import pytest

pytestmark = pytest.mark.skip(
    reason="integration test — requires real ProductSearchService with Supabase"
)


def test_cache_performance_improvement():
    pass
