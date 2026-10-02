from engine.r5_conditional_policy import decide


def test_low_confidence_is_half_rank1_half_cash():
    d = decide(
        rank1_symbol="AAA", rank1_score=0.1,
        rank2_symbol="BBB", rank2_score=0.09,
        gap_threshold=0.35, confidence_threshold=0.2,
        total_krw=20000,
    )
    assert d.regime == "LOW_CONFIDENCE"
    assert d.legs_krw == (("AAA", 10000),)
    assert d.cash_krw == 10000


def test_close_gap_is_10k_each():
    d = decide(
        rank1_symbol="AAA", rank1_score=1.0,
        rank2_symbol="BBB", rank2_score=0.8,
        gap_threshold=0.35, confidence_threshold=0.2,
        total_krw=20000,
    )
    assert d.regime == "CLOSE_GAP"
    assert d.legs_krw == (("AAA", 10000), ("BBB", 10000))
    assert d.cash_krw == 0


def test_wide_gap_is_rank1_20k():
    d = decide(
        rank1_symbol="AAA", rank1_score=1.0,
        rank2_symbol="BBB", rank2_score=0.5,
        gap_threshold=0.35, confidence_threshold=0.2,
        total_krw=20000,
    )
    assert d.regime == "TOP1_ONLY_WIDE_GAP"
    assert d.legs_krw == (("AAA", 20000),)


def test_missing_rank2_falls_back_rank1_20k():
    d = decide(
        rank1_symbol="AAA", rank1_score=1.0,
        rank2_symbol=None, rank2_score=None,
        gap_threshold=0.35, confidence_threshold=0.2,
        total_krw=20000,
    )
    assert d.regime == "TOP1_ONLY_NO_RANK2"
    assert d.legs_krw == (("AAA", 20000),)
