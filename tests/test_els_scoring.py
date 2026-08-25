import unittest
from unittest.mock import patch

from market_pulse.products import (
    infer_underlyings,
    kofia_row_to_product,
    score_els_coupon,
    score_els_product,
    score_els_protection,
)


class ElsScoringTest(unittest.TestCase):
    def test_knock_in_35_and_40_receive_same_score(self):
        score35, _ = score_els_protection(
            final_barrier=50,
            avg_barrier=75,
            knock_in=35,
            no_knock_in=False,
        )
        score40, _ = score_els_protection(
            final_barrier=50,
            avg_barrier=75,
            knock_in=40,
            no_knock_in=False,
        )
        score45, _ = score_els_protection(
            final_barrier=50,
            avg_barrier=75,
            knock_in=45,
            no_knock_in=False,
        )

        self.assertEqual(score35, score40)
        self.assertGreater(score40, score45)

    def test_coupon_score_rewards_higher_coupon_inside_normal_range(self):
        lower_score, _ = score_els_coupon(12.2)
        higher_score, _ = score_els_coupon(14.0)
        max_score, _ = score_els_coupon(18.0)

        self.assertGreater(higher_score, lower_score)
        self.assertEqual(max_score, 25)

    def test_els_detail_score_uses_updated_component_caps(self):
        scored = score_els_product(
            {
                "상품명": "테스트 ELS",
                "쿠폰": "연 14.0%",
                "기초자산": "KOSPI200 Index, S&P500 Index, Nikkei225 Index",
                "조기상환 조건": "StepDown형[90/90/85/85/80/75/35 KI]",
                "만기/상환주기": "3년/6개월",
                "신용등급": "AA",
            }
        )

        self.assertIn("방어", scored["상세 점수"])
        self.assertIn("/30", scored["상세 점수"])
        self.assertIn("/25", scored["상세 점수"])

    def test_infer_underlyings_preserves_kosdaq150_index_name(self):
        self.assertEqual(
            infer_underlyings("KOSPI200 </br> KOSDAQ150 </br>"),
            "KOSPI200 Index, KOSDAQ150 Index",
        )

    def test_kofia_row_enriches_incomplete_underlyings_from_detail_link(self):
        vals = {
            "val4": "NH투자증권",
            "val5": "AA+",
            "val6": "NH투자증권(ELS) 25105",
            "val7": "2",
            "val8": "KOSPI200 Index",
            "val9": "KOSPI200 Index",
            "val15": "17",
            "val16": "20260825",
            "val17": "20260903",
            "val18": "원금비보장, 85-85-80-80-75-70/35 KI",
            "val20": "https://example.test/nh-els-25105",
            "val21": "26-09-03(오후 4시) 청약종료",
            "val22": "KR6NH0006X95",
            "val23": "-100",
        }
        with patch(
            "market_pulse.products.fetch_detail_underlyings",
            return_value="KOSPI200 Index, KOSDAQ150 Index",
        ):
            product = kofia_row_to_product(vals)

        self.assertIsNotNone(product)
        self.assertEqual(product["기초자산"], "KOSPI200 Index, KOSDAQ150 Index")


if __name__ == "__main__":
    unittest.main()
