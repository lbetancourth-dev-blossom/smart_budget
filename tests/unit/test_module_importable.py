"""TC-1.1 — smart_budget module is importable and has expected public API."""


def test_module_importable():
    from smart_budget import filters, aggregator

    assert hasattr(filters, "filter_transactions")
    assert hasattr(aggregator, "prepare_smart_budget_data")
