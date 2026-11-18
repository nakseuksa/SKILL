#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
value_trap_metrics.py: 个股价值陷阱诊断指标计算器(纯标准库,无第三方依赖)

用法:
    python value_trap_metrics.py <input.json>            # 输出 Markdown
    python value_trap_metrics.py <input.json> --json     # 输出 JSON

输入格式见 ../examples/sample_input.json 和 ../references/input_schema.md。

设计约束(来自《终版裁决报告》):
  * 除"生存硬约束"外,任何单一指标都不能一票否决。
  * 阈值均为启发式,未经样本外校准;证据等级见 ../references/thresholds.md。
  * 周期股、金融股、REIT 走独立路由,不适用的指标标记为 exempt(豁免)。
  * Sloan 应计比率只做单向使用:高正值是红旗,大负值只作提示。
  * 缺失数据一律标 n/a,不估算、不填充。
"""
from __future__ import annotations

import argparse
import json
import sys
from statistics import mean, median

GREEN, AMBER, RED, NA, EXEMPT, INFO = "green", "amber", "red", "n/a", "exempt", "info"
ICON = {GREEN: "🟢", AMBER: "🟠", RED: "🔴", NA: "⚪", EXEMPT: "⏭️", INFO: "ℹ️"}
ROUTES = ("general", "cyclical", "financial", "reit", "utility")
CATEGORIES = {
    "A": "估值成因",
    "B": "资本回报",
    "C": "盈余质量",
    "D": "边际动量",
    "E": "生存能力",
    "F": "股息可持续性",
    "G": "时机信号(仅参考,不参与聚合)",
}
AGGREGATED = ("A", "B", "C", "D", "E", "F")


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def num(d, key):
    """安全取数:缺失或无法转换时返回 None。"""
    if not d:
        return None
    v = d.get(key)
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def avg2(a, b):
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return (a + b) / 2.0


def all_present(*vals):
    return all(v is not None for v in vals)


def gross_margin(p):
    rev, cogs = num(p, "revenue"), num(p, "cogs")
    if rev is None or cogs is None or rev == 0:
        return None
    return (rev - cogs) / rev


def gt(a, b):
    """a > b → 1;否则 0;任一缺失 → None。"""
    if a is None or b is None:
        return None
    return int(a > b)


def lt(a, b):
    if a is None or b is None:
        return None
    return int(a < b)


def fcf_of(p):
    """传统口径 FCF = CFO − |CapEx|(不采用公司自定义的"调整后 FCF")。"""
    cfo, capex = num(p, "cfo"), num(p, "capex")
    if cfo is None or capex is None:
        return None
    return cfo - abs(capex)


class Result:
    def __init__(self):
        self.items = []
        self.warnings = []

    def add(self, cat, name, value, status, note="", evidence="E", fmt="num", hard=False):
        self.items.append({
            "category": cat, "name": name, "value": value, "status": status,
            "note": note, "evidence": evidence, "fmt": fmt, "hard": hard,
        })

    def warn(self, msg):
        self.warnings.append(msg)


# --------------------------------------------------------------------------- #
# 口径检查(来自终版报告中 Tata Steel / Intel / Walgreens 三类错误)
# --------------------------------------------------------------------------- #
def data_checks(data, res):
    meta = data.get("meta", {})
    if not meta.get("unit"):
        res.warn("未声明金额单位(meta.unit)。务必核对 crore/lakh/亿/百万 的换算,终版报告中 Tata Steel 一例就是 10 倍单位错误。")
    basis = (meta.get("period_basis") or "").lower()
    if basis not in ("annual", "ttm"):
        res.warn("期间口径不是 annual/ttm。单季度数据含营运资金季节性(如 Walgreens 节日季备货),不得据此判断现金流断裂。")
    eps_basis = (meta.get("eps_basis") or "").lower()
    if eps_basis and eps_basis != "gaap":
        res.warn(f"EPS 口径为 '{eps_basis}',不是 GAAP/IFRS。须同时报告法定口径盈亏(Walgreens、Intel 都存在调整后为正、法定口径为负的情况)。")
    if not meta.get("sources"):
        res.warn("未提供数据来源(meta.sources)。最终报告中每个数字都必须可追溯。")
    route = meta.get("route", "general")
    if route not in ROUTES:
        res.warn(f"未知路由 '{route}',已按 general 处理。")


# --------------------------------------------------------------------------- #
# A. 估值成因
# --------------------------------------------------------------------------- #
def valuation(data, route, res):
    meta, hist, assum = data.get("meta", {}), data.get("history", {}), data.get("assumptions", {})
    t = data["periods"]["t"]
    t1 = data["periods"].get("t1", {})
    price = num(meta, "price")
    shares = num(t, "shares_outstanding") or num(meta, "shares_outstanding")
    ni = num(t, "net_income")
    eps_ttm = num(meta, "eps_ttm")
    if eps_ttm is None:
        eps_ttm = div(ni, shares)

    # 当期 P/E
    if price is not None and eps_ttm is not None:
        if eps_ttm > 0:
            res.add("A", "当期 P/E", price / eps_ttm, INFO, "静态值,只作参照;不能单独作为低估证据。", "B", "x")
        else:
            res.add("A", "当期 P/E", None, INFO, "当期亏损,P/E 无意义。", "B")
    else:
        res.add("A", "当期 P/E", None, NA, "缺少价格或 EPS。")

    # 远期与当期盈利对比(周期顶点 / 盈利坍塌信号)
    fwd = num(meta, "forward_eps")
    if fwd is not None and eps_ttm is not None and eps_ttm > 0 and price is not None:
        ratio = fwd / eps_ttm
        if ratio < 0.5:
            st, note = RED, "一致预期远期 EPS 较当期下滑超过 50%(周期顶点或盈利坍塌特征)。"
        elif ratio < 0.8:
            st, note = AMBER, "一致预期远期 EPS 较当期下滑 20%–50%。"
        else:
            st, note = GREEN, "远期预期没有显著下滑。"
        fpe = f"远期 P/E = {price / fwd:.1f}x。" if fwd > 0 else "远期预期亏损。"
        res.add("A", "远期 EPS / 当期 EPS", ratio, st, note + fpe, "B", "x")
    else:
        res.add("A", "远期 EPS / 当期 EPS", None, NA, "缺少 forward_eps,或当期亏损。")

    # 正常化盈利 P/E
    eps_hist = [float(x) for x in hist.get("eps", []) if x is not None]
    if len(eps_hist) >= 5 and price is not None:
        norm, med = mean(eps_hist), median(eps_hist)
        if norm > 0:
            pe_norm = price / norm
            note = f"正常化 EPS = {len(eps_hist)} 年均值 {norm:.2f}(中位数 {med:.2f})。"
            st = INFO
            if route == "cyclical" and eps_ttm and eps_ttm > 0 and eps_ttm > 1.5 * norm:
                st = AMBER
                note += "当期 EPS 超过周期均值 1.5 倍,存在顶点风险,应以本行为估值主依据。"
            elif route != "cyclical" and eps_ttm is not None and eps_ttm < 0.7 * norm:
                note += ("当期 EPS 明显低于历史均值。非周期股如果处于结构性衰退,历史均值会高估正常盈利,"
                         "这一正常化 P/E 偏乐观,不能当作低估证据。")
            res.add("A", "正常化 P/E", pe_norm, st, note, "B", "x")
        else:
            res.add("A", "正常化 P/E", None, RED if route == "cyclical" else AMBER,
                    "多年平均 EPS ≤ 0:整个周期都没有创造利润。", "B")
    else:
        st = NA
        note = "历史 EPS 少于 5 年,无法正常化。"
        if route == "cyclical":
            note += "周期股必须提供 ≥5 年(最好覆盖一个完整周期)的 EPS。"
        res.add("A", "正常化 P/E", None, st, note)

    # 合理市净率区间,做敏感性网格
    r = num(assum, "cost_of_equity")
    g = num(assum, "growth")
    book_t, book_t1 = num(t, "book_equity"), num(t1, "book_equity")
    roe_hist = [float(x) for x in hist.get("roe", []) if x is not None]
    if len(roe_hist) >= 3:
        roe_norm, roe_src = mean(roe_hist), f"{len(roe_hist)} 年平均 ROE"
    else:
        roe_norm, roe_src = div(ni, avg2(book_t, book_t1)), "单期 ROE(未正常化)"
    if all_present(r, g, roe_norm):
        grid = []
        for dr in (-0.01, 0.0, 0.01):
            for dg in (-0.01, 0.0, 0.01):
                rr, gg = r + dr, g + dg
                if rr - gg >= 0.005:
                    grid.append((roe_norm - gg) / (rr - gg))
        lo, hi = min(grid), max(grid)
        base = (roe_norm - g) / (r - g) if r - g >= 0.005 else None
        # B 类:ROE 与 r 的关系
        if roe_norm < r:
            res.add("B", "ROE − r(权益成本)", roe_norm - r, AMBER if route != "cyclical" else INFO,
                    f"{roe_src} {roe_norm:.1%} < r {r:.1%}:合理 P/B < 1,破净是合理折价,不是安全边际。"
                    + ("周期股须用周期中枢 ROE 判断。" if route == "cyclical" else ""), "B", "pct")
        else:
            res.add("B", "ROE − r(权益成本)", roe_norm - r, GREEN,
                    f"{roe_src} {roe_norm:.1%} ≥ r {r:.1%}。", "B", "pct")
        # A 类:实际 P/B 与合理区间
        pb = div(price * shares if all_present(price, shares) else None, book_t)
        sens = f"基准 {base:.2f}x,r±1%、g±1% 敏感区间 [{lo:.2f}x, {hi:.2f}x];r 与 g 不可观测,区间宽度本身就是不确定性。" if base else ""
        if pb is None:
            res.add("A", "实际 P/B 与合理 P/B 区间", None, NA, "缺少价格、股本或净资产。" + sens, "B")
        elif pb < lo:
            roe_now = div(ni, avg2(book_t, book_t1))
            if len(roe_hist) >= 3 and roe_now is not None and roe_now < roe_norm - 0.03 and route != "cyclical":
                res.add("A", "实际 P/B 与合理 P/B 区间", pb, INFO,
                        f"实际 P/B 低于区间下沿,但当期 ROE {roe_now:.1%} 明显低于历史均值 {roe_norm:.1%}。"
                        "如果 ROE 下行是结构性的,用均值算出的合理 P/B 偏高,'低于下沿'不构成低估证据。" + sens, "B", "x")
            else:
                res.add("A", "实际 P/B 与合理 P/B 区间", pb, GREEN, "实际 P/B 低于敏感区间下沿(只在给定假设下成立)。" + sens, "B", "x")
        elif pb > hi:
            res.add("A", "实际 P/B 与合理 P/B 区间", pb, INFO, "实际 P/B 高于区间上沿,看不到折价。" + sens, "B", "x")
        else:
            res.add("A", "实际 P/B 与合理 P/B 区间", pb, INFO, "落在敏感区间内,无法据此判定低估。" + sens, "B", "x")
    else:
        res.add("A", "实际 P/B 与合理 P/B 区间", None, NA, "缺少 cost_of_equity、growth 或 ROE。")


# --------------------------------------------------------------------------- #
# B. 资本回报
# --------------------------------------------------------------------------- #
def returns(data, route, res):
    hist, assum = data.get("history", {}), data.get("assumptions", {})
    t = data["periods"]["t"]
    if route == "financial":
        res.add("B", "ROIC / CROIC", None, EXEMPT, "金融业不适用;请用 ROE − r 和合理 P/B 判断。")
    else:
        tax = num(assum, "tax_rate") if num(assum, "tax_rate") is not None else 0.25
        r = num(assum, "cost_of_equity")
        ebit, book, debt, cash = num(t, "ebit"), num(t, "book_equity"), num(t, "total_debt"), num(t, "cash")
        ic = book + debt - cash if all_present(book, debt, cash) else None
        roic = div(ebit * (1 - tax) if ebit is not None else None, ic)
        croic = div(fcf_of(t), ic)
        roic_hist = [float(x) for x in hist.get("roic", []) if x is not None]
        if len(roic_hist) >= 3:
            first, last = roic_hist[0], roic_hist[-1]
            declining = last < first
            if declining and r is not None and last < r:
                st, note = RED, f"ROIC 由 {first:.1%} 降至 {last:.1%},已低于资本成本代理值 r={r:.1%}。"
            elif min(roic_hist) > 0.15:
                st, note = GREEN, "历史 ROIC 均高于 15%(经验阈值,芒格出处缺失)。"
            elif declining:
                st, note = AMBER, f"ROIC 呈下行趋势({first:.1%} → {last:.1%})。"
            else:
                st, note = INFO, "ROIC 没有持续下行。"
            if route == "cyclical" and st == RED:
                st, note = AMBER, note + "周期股的 ROIC 随周期波动,降为提示,须结合周期位置判断。"
            res.add("B", "ROIC 趋势(历史序列)", last, st, note, "B", "pct")
        elif roic is not None:
            if r is not None and roic < r:
                st = AMBER if route != "cyclical" else INFO
                note = "单期 ROIC 低于资本成本代理值(单期数据不足以判断趋势)。"
            elif roic > 0.15:
                st, note = GREEN, "单期 ROIC > 15%(经验阈值)。"
            else:
                st, note = INFO, "单期 ROIC。"
            res.add("B", "ROIC(单期)", roic, st, note, "B", "pct")
        else:
            res.add("B", "ROIC", None, NA, "缺少 EBIT、净资产、债务或现金。")
        res.add("B", "CROIC = FCF / 投入资本", croic, INFO if croic is not None else NA,
                "交叉检验用;'前五分位跑赢 5–8%'出处缺失,不作阈值。", "B", "pct")

    rev_hist = [float(x) for x in hist.get("revenue", []) if x is not None]
    if len(rev_hist) >= 3:
        two_down = rev_hist[-1] < rev_hist[-2] < rev_hist[-3]
        if two_down:
            if route == "cyclical":
                res.add("B", "营收连续两年下滑", rev_hist[-1] / rev_hist[-3] - 1, INFO,
                        "周期股的名义营收下滑多为价格波动,豁免否决。", "B", "pct")
            else:
                res.add("B", "营收连续两年下滑", rev_hist[-1] / rev_hist[-3] - 1, AMBER,
                        "可能是份额流失或行业萎缩;须区分价格因素与量的因素。", "B", "pct")
        else:
            res.add("B", "营收连续两年下滑", None, GREEN, "否。", "B")
    else:
        res.add("B", "营收连续两年下滑", None, NA, "营收历史少于 3 期。")


# --------------------------------------------------------------------------- #
# C. 盈余质量
# --------------------------------------------------------------------------- #
def sloan(data, route, res):
    t, t1 = data["periods"]["t"], data["periods"].get("t1", {})
    if route == "financial":
        res.add("C", "Sloan 应计比率", None, EXEMPT, "金融业现金流科目不适用。")
        return
    ni, cfo, cfi = num(t, "net_income"), num(t, "cfo"), num(t, "cfi")
    ata = avg2(num(t, "total_assets"), num(t1, "total_assets"))
    if not all_present(ni, cfo, cfi, ata) or ata == 0:
        res.add("C", "Sloan 应计比率(现金流法)", None, NA, "缺少 NI、CFO、CFI 或总资产。")
        return
    s = (ni - cfo - cfi) / ata
    narrow = (ni - cfo) / ata
    if s > 0.25:
        st, note = RED, "高正应计:账面利润远超现金,盈利回归风险高(Sloan 异象方向)。"
    elif s > 0.10:
        st, note = AMBER, "应计偏高,须审视应收和存货变动。"
    elif s < -0.25:
        st, note = INFO, "大幅负值本身不是红旗(低应计在 Sloan 异象中是做多方向);须检查 CFI 是否含大额资产出售或并购回款。"
    else:
        st, note = GREEN, "处于 ±10% 区间。"
    if route == "reit" and st in (RED, AMBER):
        st, note = INFO, note + "REIT 的 CFI 受物业收购和处置主导,降为提示。"
    res.add("C", "Sloan 应计比率(现金流法)", s, st, note, "D", "pct")
    res.add("C", "狭义应计率 (NI−CFO)/平均总资产", narrow, INFO,
            "为负表示现金流超过利润。作为辅助信息,不重复计分。", "D", "pct")


def cscore(data, route, res):
    t, t1 = data["periods"]["t"], data["periods"].get("t1", {})
    if route == "financial":
        res.add("C", "Montier C-Score", None, EXEMPT, "金融业不适用。")
        return
    ni_t, cfo_t, ni_t1, cfo_t1 = num(t, "net_income"), num(t, "cfo"), num(t1, "net_income"), num(t1, "cfo")
    gap_t = ni_t - cfo_t if all_present(ni_t, cfo_t) else None
    gap_t1 = ni_t1 - cfo_t1 if all_present(ni_t1, cfo_t1) else None

    def ratio(p, a, b):
        return div(num(p, a), num(p, b))

    tests = {
        "C1 NI−CFO 差距扩大": gt(gap_t, gap_t1),
        "C2 DSO 上升": gt(ratio(t, "receivables", "revenue"), ratio(t1, "receivables", "revenue")),
        "C3 DSI 上升": gt(ratio(t, "inventory", "cogs"), ratio(t1, "inventory", "cogs")),
        "C4 其他流动资产/营收上升": gt(ratio(t, "other_current_assets", "revenue"),
                                  ratio(t1, "other_current_assets", "revenue")),
        "C5 折旧/固定资产原值下降": lt(ratio(t, "depreciation", "ppe_gross"), ratio(t1, "depreciation", "ppe_gross")),
        "C6 总资产增速 > 10%": None,
    }
    ta_t, ta_t1 = num(t, "total_assets"), num(t1, "total_assets")
    if all_present(ta_t, ta_t1) and ta_t1 != 0:
        tests["C6 总资产增速 > 10%"] = int((ta_t - ta_t1) / ta_t1 > 0.10)
    avail = [v for v in tests.values() if v is not None]
    missing = [k for k, v in tests.items() if v is None]
    if len(avail) < 5:
        res.add("C", "Montier C-Score", None, NA, f"可计算项不足(缺:{', '.join(missing)})。")
        return
    lo, hi = sum(avail), sum(avail) + len(missing)
    triggered = [k for k, v in tests.items() if v == 1]
    if lo >= 4:
        st = RED
    elif hi <= 1:
        st = GREEN
    else:
        st = AMBER
    rng = f"{lo}" if lo == hi else f"{lo}–{hi}(缺 {', '.join(missing)})"
    res.add("C", "Montier C-Score(0–6)", lo, st,
            f"得分 {rng};触发项:{', '.join(triggered) or '无'}。分档 0–1 / 2–3 / 4–6 为实务惯例,出处缺失。",
            "D", "score")


def mscore(data, route, res):
    t, t1 = data["periods"]["t"], data["periods"].get("t1", {})
    if route == "financial":
        res.add("C", "Beneish M-Score", None, EXEMPT, "金融业不适用。")
        return

    def g(p, k, default=None):
        v = num(p, k)
        return default if v is None else v

    rec_t, rec_t1 = g(t, "receivables"), g(t1, "receivables")
    rev_t, rev_t1 = g(t, "revenue"), g(t1, "revenue")
    ca_t, ca_t1 = g(t, "current_assets"), g(t1, "current_assets")
    ppe_t, ppe_t1 = g(t, "ppe_net"), g(t1, "ppe_net")
    sec_t, sec_t1 = g(t, "securities", 0.0), g(t1, "securities", 0.0)
    ta_t, ta_t1 = g(t, "total_assets"), g(t1, "total_assets")
    dep_t, dep_t1 = g(t, "depreciation"), g(t1, "depreciation")
    sga_t, sga_t1 = g(t, "sga"), g(t1, "sga")
    cl_t, cl_t1 = g(t, "current_liabilities"), g(t1, "current_liabilities")
    ltd_t, ltd_t1 = g(t, "long_term_debt"), g(t1, "long_term_debt")
    inc_t = g(t, "income_cont_ops", g(t, "net_income"))
    cfo_t = g(t, "cfo")
    gm_t, gm_t1 = gross_margin(t), gross_margin(t1)

    idx = {}
    idx["DSRI"] = div(div(rec_t, rev_t), div(rec_t1, rev_t1))
    idx["GMI"] = div(gm_t1, gm_t)
    if all_present(ca_t, ppe_t, ta_t, ca_t1, ppe_t1, ta_t1) and ta_t and ta_t1:
        idx["AQI"] = div(1 - (ca_t + ppe_t + sec_t) / ta_t, 1 - (ca_t1 + ppe_t1 + sec_t1) / ta_t1)
    else:
        idx["AQI"] = None
    idx["SGI"] = div(rev_t, rev_t1)
    if all_present(dep_t, ppe_t, dep_t1, ppe_t1):
        idx["DEPI"] = div(div(dep_t1, dep_t1 + ppe_t1), div(dep_t, dep_t + ppe_t))
    else:
        idx["DEPI"] = None
    idx["SGAI"] = div(div(sga_t, rev_t), div(sga_t1, rev_t1))
    if all_present(cl_t, ltd_t, ta_t, cl_t1, ltd_t1, ta_t1):
        idx["LVGI"] = div(div(cl_t + ltd_t, ta_t), div(cl_t1 + ltd_t1, ta_t1))
    else:
        idx["LVGI"] = None
    idx["TATA"] = div(inc_t - cfo_t, ta_t) if all_present(inc_t, cfo_t) else None

    missing = [k for k, v in idx.items() if v is None]
    if missing:
        res.add("C", "Beneish M-Score(8 变量)", None, NA, f"无法计算的分项:{', '.join(missing)}。")
        return
    m = (-4.84 + 0.920 * idx["DSRI"] + 0.528 * idx["GMI"] + 0.404 * idx["AQI"] + 0.892 * idx["SGI"]
         + 0.115 * idx["DEPI"] - 0.172 * idx["SGAI"] + 4.679 * idx["TATA"] - 0.327 * idx["LVGI"])
    if m > -1.78:
        st, band = RED, "高于 -1.78(Beneish 1999 原始分界)"
    elif m > -2.22:
        st, band = AMBER, "介于 -2.22 与 -1.78 之间(-2.22 为后续实务中的宽网阈值)"
    else:
        st, band = GREEN, "低于 -2.22"
    note = (f"{band}。基础概率提示:原论文约 76% 识别率、17.5% 误报率,真实操纵的先验概率很低,"
            "红旗公司中多数并未操纵,只触发人工复核,不单独否决。")
    res.add("C", "Beneish M-Score(8 变量)", m, st, note, "D", "num")


# --------------------------------------------------------------------------- #
# D. 边际动量
# --------------------------------------------------------------------------- #
def piotroski(data, route, res):
    p = data["periods"]
    t, t1, t2 = p["t"], p.get("t1", {}), p.get("t2", {})
    if route == "financial":
        res.add("D", "Piotroski F-Score", None, EXEMPT, "金融业不适用(杠杆、流动比率、毛利率没有可比含义)。")
        return
    notes = []
    ta_t, ta_t1, ta_t2 = num(t, "total_assets"), num(t1, "total_assets"), num(t2, "total_assets")
    if ta_t2 is None:
        ta_t2 = ta_t1
        notes.append("缺 t-2 总资产,t-1 期比率以期末资产近似")
    ni_t, ni_t1, cfo_t = num(t, "net_income"), num(t1, "net_income"), num(t, "cfo")
    roa_t, roa_t1 = div(ni_t, ta_t1), div(ni_t1, ta_t2)
    comps = {
        "F1 ROA>0": None if roa_t is None else int(roa_t > 0),
        "F2 CFO>0": None if cfo_t is None else int(cfo_t > 0),
        "F3 ΔROA>0": gt(roa_t, roa_t1),
        "F4 CFO>NI": gt(cfo_t, ni_t),
    }
    lev_t = div(num(t, "long_term_debt"), avg2(ta_t, ta_t1))
    lev_t1 = div(num(t1, "long_term_debt"), avg2(ta_t1, ta_t2))
    if lev_t is None or lev_t1 is None:
        comps["F5 Δ长期杠杆<0"] = None
    else:
        comps["F5 Δ长期杠杆<0"] = int(lev_t < lev_t1 or (lev_t == 0 and lev_t1 == 0))
    comps["F6 Δ流动比率>0"] = gt(div(num(t, "current_assets"), num(t, "current_liabilities")),
                             div(num(t1, "current_assets"), num(t1, "current_liabilities")))
    sh_t, sh_t1 = num(t, "shares_outstanding"), num(t1, "shares_outstanding")
    comps["F7 无股本增加"] = None if not all_present(sh_t, sh_t1) else int(sh_t <= sh_t1)
    comps["F8 Δ毛利率>0"] = gt(gross_margin(t), gross_margin(t1))
    comps["F9 Δ资产周转>0"] = gt(div(num(t, "revenue"), ta_t1), div(num(t1, "revenue"), ta_t2))

    avail = [v for v in comps.values() if v is not None]
    missing = [k for k, v in comps.items() if v is None]
    if len(avail) < 7:
        res.add("D", "Piotroski F-Score", None, NA, f"可计算项不足(缺:{', '.join(missing)})。")
        return
    lo, hi = sum(avail), sum(avail) + len(missing)
    failed = [k for k, v in comps.items() if v == 0]
    # 阈值统一采用 Piotroski (2000) 原文分组:高分 8–9、低分 0–1
    if lo >= 8:
        st = GREEN
    elif hi <= 1:
        st = RED
    else:
        st = AMBER
    rng = f"{lo}" if lo == hi else f"{lo}–{hi}(缺 {', '.join(missing)})"
    note = f"得分 {rng};未通过:{', '.join(failed) or '无'}。分组沿用 Piotroski 原文(8–9 高分,0–1 低分)。"
    if notes:
        note += ";".join(notes) + "。"
    if route == "cyclical":
        st = INFO
        note += "周期股路由:F-Score 顺周期(顶点高分、底部低分),不作否决依据。"
    res.add("D", "Piotroski F-Score(0–9)", lo, st, note, "D", "score")


# --------------------------------------------------------------------------- #
# E. 生存能力
# --------------------------------------------------------------------------- #
def altman(data, route, res):
    meta, t = data.get("meta", {}), data["periods"]["t"]
    if route in ("financial", "reit"):
        res.add("E", "Altman Z", None, EXEMPT, "金融业和 REIT 不适用。")
        return
    ca, cl, ta = num(t, "current_assets"), num(t, "current_liabilities"), num(t, "total_assets")
    re_, ebit, rev, tl = num(t, "retained_earnings"), num(t, "ebit"), num(t, "revenue"), num(t, "total_liabilities")
    x1 = div(ca - cl, ta) if all_present(ca, cl) else None
    x2, x3, x5 = div(re_, ta), div(ebit, ta), div(rev, ta)
    manufacturing = meta.get("manufacturing")
    if manufacturing is None:
        manufacturing = route in ("general", "cyclical")
    if manufacturing:
        price = num(meta, "price")
        shares = num(t, "shares_outstanding") or num(meta, "shares_outstanding")
        mcap = price * shares if all_present(price, shares) else None
        x4 = div(mcap, tl)
        if not all_present(x1, x2, x3, x4, x5):
            res.add("E", "Altman Z(原版,上市制造业)", None, NA, "缺少计算所需科目。")
            return
        z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
        st = RED if z < 1.81 else (AMBER if z <= 2.99 else GREEN)
        share = (0.6 * x4 / z) if z > 0 else None
        note = "阈值 1.81 / 2.99。X4 含市值,股价下跌会直接压低 Z,对低估值股存在循环惩罚"
        note += f"(X4 贡献约 {share:.0%})。" if share is not None else "。"
        res.add("E", "Altman Z(原版,上市制造业)", z, st, note, "D", "num")
    else:
        be = num(t, "book_equity")
        x4b = div(be, tl)
        if not all_present(x1, x2, x3, x4b):
            res.add("E", "Altman Z″(非制造业)", None, NA, "缺少计算所需科目。")
            return
        z2 = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4b
        st = RED if z2 < 1.1 else (AMBER if z2 <= 2.6 else GREEN)
        res.add("E", "Altman Z″(非制造业)", z2, st,
                "X4 用账面权益,阈值 1.1 / 2.6(不得沿用 1.81 / 2.99)。", "D", "num")


def leverage_and_survival(data, route, res):
    meta, t = data.get("meta", {}), data["periods"]["t"]
    if route == "financial":
        res.add("E", "杠杆与流动性", None, EXEMPT,
                "金融业请人工核查资本充足率(CET1)、不良率、拨备覆盖率、存款结构;本脚本不计算。")
        return
    ebit, dep, debt, cash = num(t, "ebit"), num(t, "depreciation"), num(t, "total_debt"), num(t, "cash")
    interest, ta = num(t, "interest_expense"), num(t, "total_assets")
    ebitda = ebit + dep if all_present(ebit, dep) else None

    if route == "reit":
        gearing = div(debt, ta)
        if gearing is None:
            res.add("E", "REIT 总杠杆率", None, NA, "缺少总债务或总资产。")
        else:
            st = RED if gearing > 0.50 else (AMBER if gearing > 0.45 else GREEN)
            res.add("E", "REIT 总杠杆率", gearing, st,
                    "S-REIT 规则(MAS 2024-11-28 起):统一 50% 上限。其他司法辖区规则不同,须替换。", "A", "pct")
        icr = div(ebitda, interest)
        if icr is None:
            res.add("E", "REIT 利息覆盖率 ICR", None, NA, "缺少 EBITDA 或利息支出。")
        else:
            st = RED if icr < 1.5 else (AMBER if icr < 1.8 else GREEN)
            res.add("E", "REIT 利息覆盖率 ICR", icr, st,
                    "S-REIT:ICR 下限 1.5×,低于 1.8× 须制定改善计划(MAS 2024)。", "A", "x")
    else:
        if not all_present(ebitda, debt, cash):
            res.add("E", "净债务 / EBITDA", None, NA, "缺少 EBIT、折旧、债务或现金。")
        elif ebitda <= 0:
            res.add("E", "净债务 / EBITDA", None, RED, "EBITDA ≤ 0。", "B")
        else:
            nde = (debt - cash) / ebitda
            if route == "utility":
                st = RED if nde > 6 else (AMBER if nde > 5 else GREEN)
                th = "公用事业 / 基建:5× / 6×(启发式,须与同业中位数对比)"
            else:
                st = RED if nde > 4 else (AMBER if nde > 3 else GREEN)
                th = "一般工业:3× / 4×(启发式)"
            res.add("E", "净债务 / EBITDA", nde, st, th + "。", "E", "x")
        if ebit is None or interest is None:
            res.add("E", "利息覆盖 EBIT / 利息", None, NA, "缺少 EBIT 或利息支出。")
        elif interest == 0:
            res.add("E", "利息覆盖 EBIT / 利息", None, GREEN, "无利息支出。", "B")
        else:
            cov = ebit / interest
            st = RED if cov < 1.5 else (AMBER if cov < 3 else GREEN)
            res.add("E", "利息覆盖 EBIT / 利息", cov, st, "阈值 1.5× / 3×(启发式)。", "E", "x")

    # 生存硬约束:全文唯一允许一票否决的项
    if meta.get("going_concern_doubt") is True:
        res.add("E", "持续经营疑虑(审计意见)", None, RED,
                "审计师出具持续经营重大不确定性。生存硬约束。", "A", hard=True)
    fcf = fcf_of(t)
    due = num(t, "debt_due_18m")
    undrawn = num(t, "undrawn_credit") or 0.0
    if fcf is None or cash is None:
        res.add("E", "现金跑道", None, NA, "缺少 CFO、CapEx 或现金。")
        return
    liquidity = cash + undrawn
    if fcf >= 0:
        res.add("E", "现金跑道", None, GREEN, f"FCF(CFO−CapEx)= {fcf:,.0f} ≥ 0,无需消耗现金。", "B")
    else:
        runway = liquidity / (-fcf) * 12
        hard = runway < 6 and due is not None and due > liquidity
        if runway < 6:
            st = RED
        elif runway < 24:
            st = AMBER
        else:
            st = GREEN
        note = f"(现金 + 未用授信)/ 年化 FCF 缺口 = {runway:.1f} 个月。"
        if due is not None:
            note += f" 18 个月内到期债务 {due:,.0f},可用流动性 {liquidity:,.0f}。"
        else:
            note += " 未提供 18 个月内到期债务(debt_due_18m),无法判定是否构成硬约束。"
        if hard:
            note += " 构成生存硬约束:跑道不足 6 个月且到期债务超过可用流动性,大概率被迫增发、重组或削减股息。"
        res.add("E", "现金跑道", runway, st, note, "B", "months", hard=hard)


# --------------------------------------------------------------------------- #
# F. 股息可持续性
# --------------------------------------------------------------------------- #
def dividends(data, route, res):
    meta, t = data.get("meta", {}), data["periods"]["t"]
    dp = num(t, "dividends_paid")
    dps, price, chg = num(meta, "dps"), num(meta, "price"), num(meta, "price_change_12m")
    if not dp and not dps:
        res.add("F", "股息", None, NA, "不分红或缺少数据,本类不参与聚合。")
        return
    dp = abs(dp) if dp else None
    ni = num(t, "net_income")

    if route == "reit":
        affo = num(t, "affo")
        payout = div(dp, affo)
        if payout is None:
            res.add("F", "AFFO 派息率", None, NA, "REIT 必须提供 AFFO(扣除维持性资本开支)。")
        else:
            st = RED if payout > 1.0 else (AMBER if payout > 0.9 else GREEN)
            res.add("F", "AFFO 派息率", payout, st,
                    "超过 100% 表示靠借债或卖资产分红;REIT 法定分配要求使派息率天然偏高。", "B", "pct")
    else:
        norm_eps = num(meta, "normalized_eps")
        if dps is not None and norm_eps:
            payout, basis = div(dps, norm_eps), "DPS / 正常化 EPS"
        else:
            payout, basis = div(dp, ni) if ni and ni > 0 else None, "股息 / 净利润"
        if ni is not None and ni <= 0 and not norm_eps:
            res.add("F", "盈利派息率", None, RED, "当期亏损仍在分红。", "B")
        elif payout is None:
            res.add("F", "盈利派息率", None, NA, "缺少数据。")
        else:
            st = RED if payout > 1.0 else (AMBER if payout > 0.7 else GREEN)
            res.add("F", f"盈利派息率({basis})", payout, st, "阈值 70% / 100%(启发式)。", "E", "pct")
        if route != "financial":
            fcf = fcf_of(t)
            cov = div(fcf, dp)
            if cov is None:
                res.add("F", "FCF 股息覆盖倍数", None, NA, "缺少 FCF 或已付股息。")
            else:
                st = RED if cov < 1.0 else (AMBER if cov < 1.5 else GREEN)
                res.add("F", "FCF 股息覆盖倍数", cov, st,
                        "FCF 按传统口径 CFO−CapEx;必须用年度或 TTM 数据,不得用单季度。", "B", "x")

    if dps is not None and price:
        y = dps / price
        if y > 0.08 and chg is not None and chg < -0.30:
            st, note = RED, f"股息率 {y:.1%} 由股价下跌 {abs(chg):.0%} 被动推升,市场在质疑分红的可持续性。"
        elif y > 0.08:
            st, note = AMBER, f"股息率 {y:.1%} 偏高,须核实覆盖率。"
        else:
            st, note = INFO, f"股息率 {y:.1%}。"
        res.add("F", "股息率与价格背离", y, st, note + "阈值 8% / 跌幅 30% 为启发式。", "E", "pct")


# --------------------------------------------------------------------------- #
# G. 时机信号(仅报告,不参与聚合)
# --------------------------------------------------------------------------- #
def timing(data, res):
    s = data.get("signals", {})
    if not s:
        return
    caveat = ("仅供参考,不参与结论聚合。Brandes 研究显示:跌幅 ≥60% 的股票作为一篮子平均跑赢(美国 1980–2003 年,"
              "3 年年化 11.2% 对 4.6%),但中位数落后 7.7%;等待右侧确认的成本没有被评估。")
    mapping = [
        ("estimates_trend", "盈利预测趋势"),
        ("above_200dma", "股价位于 200 日线上方"),
        ("insider_net_buy", "内部人净买入"),
        ("catalyst", "可验证催化剂"),
    ]
    for key, label in mapping:
        if key in s:
            v = s[key]
            shown = {True: "是", False: "否"}.get(v, v) if isinstance(v, bool) else v
            res.add("G", label, None, INFO, f"{shown}。{caveat if key == 'estimates_trend' else ''}", "E")


# --------------------------------------------------------------------------- #
# 聚合
# --------------------------------------------------------------------------- #
def aggregate(res):
    cats = {}
    for c in AGGREGATED:
        items = [i for i in res.items if i["category"] == c and i["status"] not in (INFO, EXEMPT)]
        scored = [i for i in items if i["status"] != NA]
        reds = sum(1 for i in scored if i["status"] == RED)
        ambers = sum(1 for i in scored if i["status"] == AMBER)
        greens = sum(1 for i in scored if i["status"] == GREEN)
        hard = any(i["hard"] for i in scored)
        if hard or reds >= 2:
            st = RED
        elif reds == 1 or ambers >= 1:
            st = AMBER
        elif greens >= 1:
            st = GREEN
        else:
            st = NA
        cats[c] = {"status": st, "reds": reds, "ambers": ambers, "greens": greens,
                   "na": len(items) - len(scored), "applicable": len(items), "hard": hard}

    applicable = sum(v["applicable"] for v in cats.values())
    na_total = sum(v["na"] for v in cats.values())
    na_share = na_total / applicable if applicable else 1.0
    red_cats = [c for c, v in cats.items() if v["status"] == RED]
    amber_cats = [c for c, v in cats.items() if v["status"] == AMBER]
    hard = any(v["hard"] for v in cats.values())

    if hard:
        verdict = "高陷阱风险(生存硬约束触发)"
    elif na_share > 0.40:
        verdict = "证据不足(缺失数据超过 40%,不下结论)"
    elif len(red_cats) >= 2:
        verdict = "高陷阱风险"
    elif len(red_cats) == 1 or len(amber_cats) >= 3:
        verdict = "需深挖"
    else:
        verdict = "低陷阱风险(只表示未见陷阱特征,不等于低估)"
    return {
        "verdict": verdict,
        "categories": cats,
        "na_share": na_share,
        "red_categories": [CATEGORIES[c] for c in red_cats],
        "amber_categories": [CATEGORIES[c] for c in amber_cats],
        "rule": ("类别:≥2 红或触发硬约束 → 红;1 红或 ≥1 橙 → 橙。总体:硬约束 → 高风险;"
                 "缺失 > 40% → 证据不足;≥2 红类 → 高风险;1 红类或 ≥3 橙类 → 需深挖;否则低风险。"
                 "聚合规则本身是启发式,未经校准。"),
    }


def run(data):
    route = data.get("meta", {}).get("route", "general")
    if route not in ROUTES:
        route = "general"
    res = Result()
    data_checks(data, res)
    valuation(data, route, res)
    returns(data, route, res)
    sloan(data, route, res)
    cscore(data, route, res)
    mscore(data, route, res)
    piotroski(data, route, res)
    altman(data, route, res)
    leverage_and_survival(data, route, res)
    dividends(data, route, res)
    timing(data, res)
    return {"route": route, "items": res.items, "warnings": res.warnings, "summary": aggregate(res)}


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #
def fmt_value(v, f):
    if v is None:
        return "—"
    if f == "pct":
        return f"{v:.1%}"
    if f == "x":
        return f"{v:.2f}x"
    if f == "score":
        return f"{v:.0f}"
    if f == "months":
        return f"{v:.1f} 个月"
    return f"{v:.2f}"


def to_markdown(data, out):
    meta = data.get("meta", {})
    s = out["summary"]
    lines = [
        f"# 价值陷阱诊断指标:{meta.get('name', '?')}({meta.get('ticker', '?')})",
        "",
        f"- 数据截至:{meta.get('as_of', '?')}|路由:`{out['route']}`|币种/单位:{meta.get('currency', '?')} / {meta.get('unit', '未声明')}",
        f"- **脚本初判:{s['verdict']}**",
        f"- 缺失率:{s['na_share']:.0%}|红色类别:{', '.join(s['red_categories']) or '无'}|橙色类别:{', '.join(s['amber_categories']) or '无'}",
        f"- 聚合规则:{s['rule']}",
        "",
    ]
    if out["warnings"]:
        lines += ["## 口径警告", ""] + [f"- ⚠️ {w}" for w in out["warnings"]] + [""]
    lines += ["## 分类汇总", "", "| 类别 | 信号 | 红 | 橙 | 绿 | 缺失 |", "|---|---|---|---|---|---|"]
    for c, v in s["categories"].items():
        lines.append(f"| {CATEGORIES[c]} | {ICON[v['status']]} {v['status']} | {v['reds']} | {v['ambers']} | {v['greens']} | {v['na']} |")
    lines += ["", "## 指标明细", "", "| 类别 | 指标 | 数值 | 信号 | 证据 | 说明 |", "|---|---|---|---|---|---|"]
    for i in out["items"]:
        flag = " **[硬约束]**" if i["hard"] else ""
        lines.append(
            f"| {CATEGORIES[i['category']]} | {i['name']} | {fmt_value(i['value'], i['fmt'])} | "
            f"{ICON[i['status']]} {i['status']}{flag} | {i['evidence']} | {i['note']} |"
        )
    lines += ["", "> 证据等级:A 监管或一手来源;B 可复算;D 学术模型(公式有出处,阈值多为实务惯例);E 启发式阈值。"
              "所有结论均未经样本外校准,也没有已知的事前命中率。", ""]
    return "\n".join(lines)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="个股价值陷阱诊断指标计算器")
    ap.add_argument("input", help="输入 JSON 文件路径")
    ap.add_argument("--json", action="store_true", help="输出 JSON 而不是 Markdown")
    args = ap.parse_args(argv)
    with open(args.input, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "periods" not in data or "t" not in data["periods"]:
        print("输入缺少 periods.t", file=sys.stderr)
        return 2
    out = run(data)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(to_markdown(data, out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
