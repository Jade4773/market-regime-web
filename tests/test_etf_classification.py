import unittest

from market_pulse.products import (
    ETF_BUY_ZONE_MAX_PCT,
    ETF_STOP_LOSS_PCT,
    ETF_VOLUME_THRESHOLD,
    build_holding_review,
    classify_etf_candidate,
    infer_category_from_text,
    infer_etf_category,
    infer_investment_country,
    is_screenable_equity_etf,
    tracked_market_group,
    tracked_signal_key,
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


def holding_item(**overrides):
    item = {
        "ticker": "TEST",
        "name": "Test ETF",
        "listing": "미국상장 ETF",
        "country": "미국",
        "index": "Test Index",
        "market": "미국 시장",
        "data_source": "Test",
        "data_status": "마감 기준",
        "last_price": 110.0,
        "ma21": 105.0,
        "ma50": 100.0,
        "volume_ratio": 0.9,
        "market_state": "CONFIRMED_UPTREND",
        "market_state_label": "상승장 확인",
        "sell_signal": "특별한 매도 신호 없음",
        "can_slim_score": 80,
        "leader_rank": 1,
        "category": "sector",
        "rs_trend5_pct": 0.0,
        "rs_weakening_days": 0,
        "distribution_days": 0,
    }
    item.update(overrides)
    return item


def buy_ready_event(**overrides):
    event = {
        "date": "2026-07-01",
        "last_signal_date": "2026-07-01",
        "signal_count": 1,
        "sessions_ago": 20,
        "entry_price": 100.0,
        "pivot": 100.0,
        "stop_loss": 100.0 * (1 - ETF_STOP_LOSS_PCT / 100),
        "quick_20pct": False,
        "hold_until_date": "2026-08-26",
        "max_unrealized_gain_pct": 10.0,
        "gain_giveback_pct": 0.0,
        "largest_down_day": False,
        "close_location": 0.7,
        "new_high": False,
    }
    event.update(overrides)
    return event


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

    def test_holding_review_cuts_loss_at_six_percent(self):
        review = build_holding_review(
            holding_item(last_price=93.5),
            buy_ready_event(),
        )

        self.assertEqual(review["action_label"], "매도/손절")

    def test_holding_review_flags_profit_zone(self):
        review = build_holding_review(
            holding_item(last_price=121.0),
            buy_ready_event(),
        )

        self.assertEqual(review["action_label"], "이익실현 검토")

    def test_holding_review_applies_eight_week_exception(self):
        review = build_holding_review(
            holding_item(last_price=121.0),
            buy_ready_event(quick_20pct=True),
        )

        self.assertEqual(review["action_label"], "8주 보유 후보")

    def test_holding_review_flags_pyramid_ready_two(self):
        review = build_holding_review(
            holding_item(last_price=102.2, ma21=100.0, ma50=95.0),
            buy_ready_event(),
        )

        self.assertEqual(review["action_label"], "2차 추가매수 후보")

    def test_holding_review_failed_breakout_before_stop(self):
        review = build_holding_review(
            holding_item(last_price=99.0, ma21=101.0, volume_ratio=1.3),
            buy_ready_event(sessions_ago=3),
        )

        self.assertEqual(review["action_label"], "조기매도 검토")
        self.assertIn("FAILED_BREAKOUT", review["sell_reason_codes"])

    def test_broad_index_holds_instead_of_profit_zone(self):
        review = build_holding_review(
            holding_item(last_price=121.0, category="broad"),
            buy_ready_event(),
        )

        self.assertEqual(review["action_label"], "보유 유지")

    def test_korean_software_ai_etf_is_sector_category(self):
        self.assertEqual(infer_category_from_text("SOL 미국AI소프트웨어"), "sector")
        self.assertEqual(
            infer_etf_category({"index": "ETF", "note": "미국 AI 소프트웨어 테마", "ticker": "481180"}),
            "sector",
        )

    def test_country_etf_outside_tracked_markets_is_not_screenable(self):
        candidate = {
            "ticker": "COLO",
            "name": "GLOBAL X MSCI COLOMBIA ETF",
            "korean_name": "",
            "listing": "미국상장 ETF",
            "country": infer_investment_country("GLOBAL X MSCI COLOMBIA ETF"),
            "category": "country",
        }

        self.assertEqual(candidate["country"], "콜롬비아")
        self.assertFalse(is_screenable_equity_etf(candidate))

    def test_us_etf_from_global_x_brand_can_remain_screenable(self):
        candidate = {
            "ticker": "TEST",
            "name": "GLOBAL X NASDAQ 100 ETF",
            "korean_name": "",
            "listing": "미국상장 ETF",
            "country": infer_investment_country("GLOBAL X NASDAQ 100 ETF"),
            "category": "broad",
        }

        self.assertEqual(candidate["country"], "미국")
        self.assertTrue(is_screenable_equity_etf(candidate))

    def test_us_listed_korea_etf_uses_korea_market_gate(self):
        country = infer_investment_country("ISHARES MSCI SOUTH KOREA ETF")

        self.assertEqual(country, "대한민국")
        self.assertEqual(tracked_market_group(country), "korea")
        self.assertEqual(tracked_signal_key("ISHARES MSCI SOUTH KOREA ETF", country), "kospi")

    def test_domestic_listed_us_nasdaq_etf_uses_nasdaq_gate(self):
        country = infer_investment_country("TIGER 미국나스닥100")

        self.assertEqual(country, "미국")
        self.assertEqual(tracked_market_group(country), "us")
        self.assertEqual(tracked_signal_key("TIGER 미국나스닥100", country), "nasdaq_composite")


if __name__ == "__main__":
    unittest.main()
