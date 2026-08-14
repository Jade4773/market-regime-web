import unittest

from market_pulse.products import (
    ETF_BUY_ZONE_MAX_PCT,
    ETF_VOLUME_THRESHOLD,
    classify_etf_candidate,
)


def base_item(**overrides):
    item = {
        "last_price": 102.0,
        "pivot": 100.0,
        "pivot_distance_pct": 2.0,
        "ma50": 90.0,
        "ma50_slope": 2.0,
        "market_state": "CONFIRMED_UPTREND",
        "avg_volume50": 300_000,
        "avg_value50": 30_000_000,
        "min_avg_volume": 100_000,
        "min_avg_value": 5_000_000,
        "base_exists": True,
        "volume_ratio": ETF_VOLUME_THRESHOLD,
    }
    item.update(overrides)
    return item


class EtfClassificationTest(unittest.TestCase):
    def status_for(self, **overrides):
        return classify_etf_candidate(base_item(**overrides))["trading_status"]

    def test_buy_ready_requires_all_filters(self):
        result = classify_etf_candidate(base_item())
        self.assertTrue(result["eligible"])
        self.assertEqual(result["display_group"], "BUY_NOW")
        self.assertEqual(result["trading_status"], "BUY_READY")

    def test_breakout_without_volume_waits_for_confirmation(self):
        self.assertEqual(self.status_for(volume_ratio=0.94), "VOLUME_CONFIRM")

    def test_below_pivot_is_approach_not_buy_ready(self):
        self.assertEqual(
            self.status_for(last_price=99.0, pivot_distance_pct=-1.0, volume_ratio=2.0),
            "PIVOT_APPROACH",
        )

    def test_above_buy_zone_is_extended(self):
        self.assertEqual(
            self.status_for(
                last_price=106.0,
                pivot_distance_pct=ETF_BUY_ZONE_MAX_PCT + 1.0,
                volume_ratio=2.0,
            ),
            "EXTENDED",
        )

    def test_no_valid_base_blocks_buy_ready(self):
        result = classify_etf_candidate(base_item(base_exists=False, volume_ratio=2.0))
        self.assertFalse(result["eligible"])
        self.assertEqual(result["trading_status"], "NO_VALID_BASE")
        self.assertEqual(result["display_group"], "WATCHLIST")

    def test_below_50sma_is_excluded(self):
        result = classify_etf_candidate(
            base_item(last_price=88.0, ma50=90.0, ma50_slope=2.0, volume_ratio=2.0)
        )
        self.assertEqual(result["trading_status"], "BELOW_50SMA")
        self.assertEqual(result["display_group"], "EXCLUDED")

    def test_market_not_confirmed_blocks_buy_ready(self):
        result = classify_etf_candidate(base_item(market_state="UPTREND_UNDER_PRESSURE"))
        self.assertFalse(result["eligible"])
        self.assertEqual(result["trading_status"], "MARKET_NOT_CONFIRMED")

    def test_liquidity_fail_is_excluded(self):
        result = classify_etf_candidate(base_item(avg_value50=1_000_000))
        self.assertEqual(result["trading_status"], "LIQUIDITY_FAIL")
        self.assertEqual(result["display_group"], "EXCLUDED")

    def test_missing_pivot_data_never_buys(self):
        result = classify_etf_candidate(base_item(pivot=None, pivot_distance_pct=None))
        self.assertEqual(result["trading_status"], "DATA_INCOMPLETE")
        self.assertFalse(result["eligible"])


if __name__ == "__main__":
    unittest.main()
