from mcp_ads_arxiv import cache, tokens


def test_count_nonempty():
    assert tokens.count("hello world this is a test") > 0
    assert tokens.count("") == 0


def test_measure_records_cumulative():
    tokens.measure("one two three four five")
    tokens.measure("six seven eight")
    usage = cache.token_usage()
    assert usage["response_count"] == 2
    assert usage["tokens_served"] > 0


def test_measure_computes_savings_when_sectioned():
    full = "word " * 1000
    served = "word " * 100
    result = tokens.measure(served, full_text=full)
    assert result["tokens_saved"] > 0
    assert result["tokens_served"] < tokens.count(full)


def test_ads_call_counter_persists():
    cache.record_ads_call(limit=5000, remaining=4998, reset=1.0)
    cache.record_ads_call(limit=5000, remaining=4997, reset=1.0)
    au = cache.ads_usage()
    assert au["call_count"] == 2
    assert au["last_remaining"] == 4997
    assert au["last_limit"] == 5000
