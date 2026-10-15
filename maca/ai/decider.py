"""MACA AI 决策层。

两个职责：
    1. parse_design_book(text) -> DesignParams   需求解析层
    2. decide(params, result)  -> Suggestion      迭代反馈层

接入 Agnes（或其它 LLM）时设 MACA_LLM=agnes 并提供 AGNES_API_KEY / AGNES_BASE_URL。
没有网或没配 Key 时自动退化为"规则 fallback"（按经验放大截面直到理论解满足），
保证黑客松现场无论如何都能跑通完整闭环——这正是答辩话术里的"可复现性"卖点。
"""

import json
import os
import re

from core.models import DesignParams, SolverResult, Suggestion

# 默认参数（与示例计算书一致，作为解析失败兜底）
DEFAULT_PARAMS = DesignParams()


def llm_enabled() -> bool:
    return os.environ.get("MACA_LLM", "rule") == "agnes" and bool(os.environ.get("AGNES_API_KEY"))


class AIDecider:
    name = "Agnes" if llm_enabled() else "RuleEngine(fallback)"

    def parse_design_book(self, text: str) -> DesignParams:
        """把计算书自然语言文本解析成结构化 DesignParams。

        有 Agnes 时用大模型做泛化理解；否则用正则/关键词规则提取。
        """
        if llm_enabled():
            p = self._parse_via_agnes(text)
            if p:
                return p
        return self._parse_via_rules(text)

    def decide(self, params: DesignParams, result: SolverResult) -> Suggestion:
        """看求解结果，给出下一条调整建议。"""
        if result.ok:
            return Suggestion(kind="accept", reason=f"当前截面 {params.section_label()} 满足承载力与服务性要求，无需调整。")
        if llm_enabled():
            s = self._decide_via_agnes(params, result)
            if s:
                return s
        return self._decide_via_rules(params, result)

    # ---------- LLM 通道 ----------

    def _agnes_request(self, prompt: str) -> str | None:
        import requests

        base = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1").rstrip("/")
        model = os.environ.get("AGNES_MODEL", "agnes-2.5-flash")
        key = os.environ["AGNES_API_KEY"]
        try:
            r = requests.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.0},
                timeout=30,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception:
            return None

    def _parse_via_agnes(self, text: str) -> DesignParams | None:
        prompt = (
            "你是结构工程师。从下面计算书中提取参数，仅输出 JSON，键：\n"
            '{material, fc, fy, span(mm), wll(kN/m), self_weight(bool), section_b(mm), section_h(mm), as_area(mm2), notes}。\n'
            "计算书：\n" + text
        )
        raw = self._agnes_request(prompt)
        if not raw:
            return None
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
            p = DesignParams.from_json(d)
            # 单位规整：LLM 可能给 m
            if p.span < 100:  # 判定为米
                p.span *= 1000
            if p.section_b < 100:
                p.section_b *= 1000
            if p.section_h < 100:
                p.section_h *= 1000
            return p
        except Exception:
            return None

    def _decide_via_agnes(self, params: DesignParams, result: SolverResult) -> Suggestion | None:
        prompt = (
            "你是结构工程师。当前截面 "
            f"{params.section_label()}，应力比={result.stress_ratio}，挠度={result.deflection_mm}mm"
            f"（限值{params.max_serviceability_span_mm}mm）。若超限，请给出放大后的截面建议，"
            "仅输出 JSON：{kind, target_b, target_h, target_as_area, reason}。"
            "若满足则 kind=accept。"
        )
        raw = self._agnes_request(prompt)
        if not raw:
            return None
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
            return Suggestion(
                kind=d.get("kind", "section"),
                target_b=d.get("target_b"),
                target_h=d.get("target_h"),
                target_as_area=d.get("target_as_area"),
                reason=d.get("reason", ""),
            )
        except Exception:
            return None

    # ---------- 规则 fallback 通道（离线也能跑通） ----------

    def _parse_via_rules(self, text: str) -> DesignParams:
        p = DesignParams()

        def grab(pattern, group=1):
            m = re.search(pattern, text, re.I)
            return m.group(group) if m else None

        # 材料
        mm = re.search(r"C\s?(\d{2})", text)
        if mm:
            grade = int(mm.group(1))
            p.material = f"C{grade}"
            p.fc = min(14.3 + (grade - 30) * 1.0, 35.9)  # 粗略

        # 跨度（优先 mm，其次 m，其次数字<100 默认 m）
        m_span = re.search(r"跨度\s*[：:]?\s*(\d+(?:\.\d+)?)\s*(mm|m)", text, re.I)
        if m_span:
            val = float(m_span.group(1))
            unit = m_span.group(2).lower()
            p.span = val if unit == "mm" else val * 1000.0
        else:
            bare = re.search(r"跨度\s*[：:]?\s*(\d+(?:\.\d+)?)", text, re.I)
            if bare:
                v = float(bare.group(1))
                p.span = v * 1000.0 if v < 100 else v

        # 均布荷载
        w = grab(r"荷载[^\d]{0,6}(\d+(?:\.\d+)?)\s*kN/m")
        if w:
            p.wll = float(w)

        # 截面（支持全/半角冒号）
        sec = re.search(r"截面[\s：:]*(\d+)\s*[x×]\s*(\d+)", text)
        if sec:
            p.section_b = float(sec.group(1))
            p.section_h = float(sec.group(2))

        # 配筋
        a = re.search(r"as[_ ]?area\s*[=:：]?\s*(\d+(?:\.\d+)?)\s*mm", text, re.I)
        if a:
            p.as_area = float(a.group(1))

        p.notes = f"rule-parse of: {text[:80]}"
        return p

    def _decide_via_rules(self, params: DesignParams, result: SolverResult) -> Suggestion:
        """经验放大：应力比超限时按 1/ratio 放大截面；挠度超限则优先加大高度。"""
        ratio = result.stress_ratio
        if not result.ok and (result.stress_ratio == float("nan") or ratio == 0):
            ratio = 1.0

        new_b = params.section_b
        new_h = params.section_h

        if result.deflection_mm > params.max_serviceability_span_mm and result.deflection_mm > 0:
            # 挠度主控制：加高
            scale = 1.15
            new_h = min(round(params.section_h * scale, -1), 1200)
            reason = f"挠度{result.deflection_mm:.1f}mm超限({params.max_serviceability_span_mm}mm)，加高截面→{new_h}mm"
        elif ratio > 1.0:
            # 承载力主控制：按 1/ratio 放大（留 10% 余量）
            f = ratio * 1.05
            new_b = round(params.section_b * f, -1)
            new_h = round(params.section_h * min(f, 1.3), -1)
            reason = f"应力比{ratio:.2f}超限，按余量放大→b={new_b},h={new_h}"
        else:
            return Suggestion(kind="accept", reason="各项指标已满足。")

        return Suggestion(kind="section", target_b=new_b, target_h=new_h, reason=reason)
