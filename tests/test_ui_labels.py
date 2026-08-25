import unittest

from market_pulse.ui import holding_sell_guide_markdown, signal_jump_display_value


class UiLabelTest(unittest.TestCase):
    def test_trend_jump_button_uses_action_label(self):
        label = signal_jump_display_value(
            "trend",
            {"opinion": "매도/방어", "action_label": "회복 대기"},
        )

        self.assertEqual(label, "회복 대기")

    def test_non_trend_jump_button_uses_opinion(self):
        label = signal_jump_display_value(
            "risk",
            {"opinion": "중립/관망", "action_label": "다른 상태"},
        )

        self.assertEqual(label, "중립/관망")

    def test_holding_sell_guide_explains_low_volume_high_label(self):
        guide = holding_sell_guide_markdown()

        self.assertIn("판정 라벨 해석", guide)
        self.assertIn("신고가 거래량 부족", guide)
        self.assertIn("기관성 수요가 강하게 확인되지 않았다는 뜻", guide)


if __name__ == "__main__":
    unittest.main()
