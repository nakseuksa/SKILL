# -*- coding: utf-8 -*-
"""value_trap_metrics.py 的单元测试(期望值均为手工复算)。

运行:python -m unittest discover -s <skill>/scripts -p "test_*.py" -v
"""
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import value_trap_metrics as vtm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "..", "examples", "sample_input.json")

BASE_PERIOD = {
    "revenue": 1000, "cogs": 600, "sga": 200, "net_income": 100, "income_cont_ops": 100,
    "cfo": 100, "cfi": -50, "capex": 50, "depreciation": 40, "ebit": 150, "interest_expense": 10,
    "total_assets": 1000, "current_assets": 400, "current_liabilities": 200, "cash": 100,
    "receivables": 100, "inventory": 100, "other_current_assets": 20, "ppe_net": 400,
    "ppe_gross": 800, "securities": 0, "long_term_debt": 200, "total_debt": 250,
    "total_liabilities": 500, "retained_earnings": 300, "book_equity": 500,
    "shares_outstanding": 100, "dividends_paid": 0,
}


def make(route="general", t=None, t1=None, t2=None, **meta):
    m = {"name": "T", "ticker": "T", "route": route, "unit": "百万", "period_basis": "annual",
         "eps_basis": "gaap", "price": 10.0, "sources": ["test"]}
    m.update(meta)
    d = {"meta": m, "assumptions": {"cost_of_equity": 0.10, "growth": 0.0, "tax_rate": 0.25},
         "periods": {"t": dict(BASE_PERIOD), "t1": dict(BASE_PERIOD), "t2": dict(BASE_PERIOD)},
         "history": {}}
    for key, upd in (("t", t), ("t1", t1), ("t2", t2)):
        if upd:
            d["periods"][key].update(upd)
    return d


def item(out, name_prefix):
    for i in out["items"]:
        if i["name"].startswith(name_prefix):
            return i
    raise AssertionError(f"未找到指标 {name_prefix}")


class TestFormulas(unittest.TestCase):
    def test_mscore_neutral_company(self):
        # 两期完全相同 → 七个指数均为 1,TATA = 0
        # M = -4.84 + .920 + .528 + .404 + .892 + .115 - .172 - .327 = -2.48
        out = vtm.run(make())
        m = item(out, "Beneish")
        self.assertAlmostEqual(m["value"], -2.48, places=6)
        self.assertEqual(m["status"], vtm.GREEN)

    def test_sloan_cashflow_version(self):
        # (100 - 50 - (-30)) / 1000 = 0.08 → green
        out = vtm.run(make(t={"cfo": 50, "cfi": -30}))
        s = item(out, "Sloan")
        self.assertAlmostEqual(s["value"], 0.08, places=9)
        self.assertEqual(s["status"], vtm.GREEN)

    def test_sloan_large_negative_is_not_red_flag(self):
        # (100 - 100 - 400)/1000 = -0.40 → 只作提示,不是红旗
        out = vtm.run(make(t={"cfi": 400}))
        self.assertEqual(item(out, "Sloan")["status"], vtm.INFO)

    def test_sloan_high_positive_is_red(self):
        # (400 - 100 - (-50)) / 1000 = 0.35 → red
        out = vtm.run(make(t={"net_income": 400, "income_cont_ops": 400}))
        self.assertEqual(item(out, "Sloan")["status"], vtm.RED)

    def test_justified_pb_roe_below_r(self):
        d = make()
        d["history"]["roe"] = [0.08, 0.08, 0.08]
        out = vtm.run(d)
        x = item(out, "ROE − r")
        self.assertAlmostEqual(x["value"], -0.02, places=9)
        self.assertEqual(x["status"], vtm.AMBER)
        pb = item(out, "实际 P/B")
        # 价格 10 × 100 股 / 净资产 500 = 2.0x;基准合理 P/B = 0.08/0.10 = 0.80x
        self.assertAlmostEqual(pb["value"], 2.0, places=9)
        self.assertIn("基准 0.80x", pb["note"])

    def test_altman_original_formula(self):
        out = vtm.run(make())
        # X1=.2 X2=.3 X3=.15 X4=1000/500=2 X5=1
        # Z = .24 + .42 + .495 + 1.2 + 1.0 = 3.355
        z = item(out, "Altman Z(原版")
        self.assertAlmostEqual(z["value"], 3.355, places=9)
        self.assertEqual(z["status"], vtm.GREEN)

    def test_altman_z_double_prime_for_non_manufacturing(self):
        out = vtm.run(make(manufacturing=False))
        # Z'' = 6.56*.2 + 3.26*.3 + 6.72*.15 + 1.05*(500/500) = 1.312+.978+1.008+1.05 = 4.348
        z = item(out, "Altman Z″")
        self.assertAlmostEqual(z["value"], 4.348, places=9)


class TestPiotroski(unittest.TestCase):
    IMPROVING_T = {"net_income": 120, "income_cont_ops": 120, "cfo": 150, "long_term_debt": 150,
                   "current_assets": 450, "cogs": 580, "revenue": 1100}

    def test_all_improving_scores_9(self):
        out = vtm.run(make(t=self.IMPROVING_T))
        f = item(out, "Piotroski")
        self.assertEqual(f["value"], 9)
        self.assertEqual(f["status"], vtm.GREEN)

    def test_cyclical_route_downgrades_to_info(self):
        out = vtm.run(make(route="cyclical", t=self.IMPROVING_T))
        self.assertEqual(item(out, "Piotroski")["status"], vtm.INFO)

    def test_financial_route_exempt(self):
        out = vtm.run(make(route="financial"))
        for prefix in ("Piotroski", "Sloan", "Montier", "Beneish", "Altman", "杠杆与流动性"):
            self.assertEqual(item(out, prefix)["status"], vtm.EXEMPT, prefix)


class TestSurvivalAndAggregation(unittest.TestCase):
    def test_hard_stop_triggers_high_risk(self):
        # FCF = 10 - 110 = -100;流动性 30 → 跑道 3.6 个月;18 个月到期 200 > 30 → 硬约束
        out = vtm.run(make(t={"cfo": 10, "capex": 110, "cash": 30, "debt_due_18m": 200}))
        r = item(out, "现金跑道")
        self.assertAlmostEqual(r["value"], 3.6, places=9)
        self.assertTrue(r["hard"])
        self.assertTrue(out["summary"]["verdict"].startswith("高陷阱风险(生存硬约束"))

    def test_short_runway_without_maturity_data_is_not_hard(self):
        out = vtm.run(make(t={"cfo": 10, "capex": 110, "cash": 30}))
        r = item(out, "现金跑道")
        self.assertEqual(r["status"], vtm.RED)
        self.assertFalse(r["hard"])

    def test_single_red_indicator_does_not_veto(self):
        # 只有 M-Score 一项红旗时,类别为橙,总体不应是"高陷阱风险"
        out = vtm.run(make(t={"receivables": 300}))
        self.assertEqual(item(out, "Beneish")["status"], vtm.RED)
        self.assertNotEqual(out["summary"]["categories"]["C"]["status"], vtm.RED)
        self.assertFalse(out["summary"]["verdict"].startswith("高陷阱风险"))

    def test_missing_data_gives_insufficient_evidence(self):
        d = make()
        d["periods"] = {"t": {"net_income": 10}}
        out = vtm.run(d)
        self.assertTrue(out["summary"]["verdict"].startswith("证据不足"))

    def test_unit_warning(self):
        out = vtm.run(make(unit=""))
        self.assertTrue(any("crore" in w for w in out["warnings"]))


class TestSample(unittest.TestCase):
    def test_sample_runs_and_flags_dividend_trap(self):
        with open(SAMPLE, encoding="utf-8") as fh:
            data = json.load(fh)
        out = vtm.run(data)
        # 派息率 300/210 = 142.9%;FCF 覆盖 (420-400)/300 = 0.067;股息率 12.5% 且跌 45%
        self.assertAlmostEqual(item(out, "盈利派息率")["value"], 300 / 210, places=9)
        self.assertAlmostEqual(item(out, "FCF 股息覆盖")["value"], 20 / 300, places=9)
        self.assertEqual(out["summary"]["categories"]["F"]["status"], vtm.RED)
        # Altman Z ≈ 1.936(灰色区)
        z = item(out, "Altman Z(原版")["value"]
        expected = 1.2 * 300 / 8200 + 1.4 * 1800 / 8200 + 3.3 * 420 / 8200 + 0.6 * 2400 / 5600 + 9500 / 8200
        self.assertAlmostEqual(z, expected, places=9)
        # 当期 ROE(约 8%)远低于 5 年均值 12.2%:"低于合理 P/B 下沿"不得判为绿色低估信号
        self.assertEqual(item(out, "实际 P/B")["status"], vtm.INFO)
        md = vtm.to_markdown(data, out)
        self.assertIn("脚本初判", md)

    def test_input_not_mutated(self):
        with open(SAMPLE, encoding="utf-8") as fh:
            data = json.load(fh)
        snapshot = copy.deepcopy(data)
        vtm.run(data)
        self.assertEqual(data, snapshot)


if __name__ == "__main__":
    unittest.main()
