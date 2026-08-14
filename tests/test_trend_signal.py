import unittest

import pandas as pd

from market_pulse.rules import analyze_trend_signal, prepare


def make_trending_history(final_close: float = 144.8, final_volume: int = 2_000_000):
    dates = pd.date_range("2025-01-01", periods=280, freq="B")
    closes = []
    for i in range(255):
        closes.append(80 + i * 0.23)
    for i in range(24):
        closes.append(137.5 + (i % 6) * 0.75)
    closes.append(final_close)
    volumes = [800_000] * 279 + [final_volume]
    return pd.DataFrame(
        {
            "Open": [close * 0.995 for close in closes],
            "High": [close * 1.01 for close in closes],
            "Low": [close * 0.99 for close in closes],
            "Close": closes,
            "Volume": volumes,
        },
        index=dates,
    )


class TrendSignalTest(unittest.TestCase):
    def signal_for(self, **overrides):
        history = make_trending_history(**overrides)
        return analyze_trend_signal(prepare(history))

    def test_oneil_trend_signal_uses_pivot_volume_and_21ema(self):
        signal = self.signal_for()
        metrics = signal["metrics"]

        self.assertEqual(signal["trading_status"], "BUY")
        self.assertEqual(signal["action_label"], "매수 가능")
        self.assertIn("21EMA", metrics)
        self.assertIn("Pivot", metrics)
        self.assertIn("Buy Zone 상단", metrics)
        self.assertIn("Volume Ratio", metrics)
        self.assertNotIn("150일선", metrics)

    def test_returns_are_percent_values_not_double_scaled(self):
        metrics = self.signal_for()["metrics"]

        self.assertLess(abs(metrics["120일 수익률"]), 100)

    def test_below_50sma_prioritizes_risk_warning(self):
        signal = self.signal_for(final_close=110.0, final_volume=2_000_000)

        self.assertEqual(signal["trading_status"], "RISK_WARNING")
        self.assertIn(signal["action_label"], {"회복 대기", "단기 방어"})


if __name__ == "__main__":
    unittest.main()
