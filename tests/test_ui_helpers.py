import unittest

from market_pulse.ui import prioritize_els_columns


class UiHelperTest(unittest.TestCase):
    def test_prioritize_els_columns_moves_core_columns_to_front(self):
        rows = [
            {
                "판정": "우선 검토",
                "핵심 근거": "만기상환 기준 35%",
                "ELS 점수": "87.3",
                "증권사": "메리츠증권",
                "상품명": "메리츠 ELS",
                "기초자산": "S&P 500 / KOSPI 200",
                "쿠폰": "연 14%",
            }
        ]

        reordered = prioritize_els_columns(rows)

        self.assertEqual(
            list(reordered[0])[:4],
            ["ELS 점수", "상품명", "쿠폰", "기초자산"],
        )
        self.assertIn("판정", reordered[0])


if __name__ == "__main__":
    unittest.main()
