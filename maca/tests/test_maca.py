"""MACA 单元测试（无网络、无 PyNite 也能跑）。

运行：python tests/test_maca.py  或  python -m unittest discover -s tests
"""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import adapters  # noqa: F401  导入即注册引擎
from core import Agent
from core.models import DesignParams
from core.solver import get, all_names
from ai.decider import AIDecider
import examples_lib


class TestRegistry(unittest.TestCase):
    def test_registry(self):
        for n in ("FormulaEngine", "PyNite", "MIDAS(NX)"):
            self.assertIn(n, all_names())
        get("FormulaEngine")
        get("PyNite")
        get("MIDAS(NX)")


class TestFormulaSolver(unittest.TestCase):
    def test_small_section_overloads(self):
        f = get("FormulaEngine")
        p = DesignParams(span=6000, wll=20, section_b=200, section_h=300, as_area=1256)
        r = f.solve(p)
        self.assertEqual(r.engine, "FormulaEngine")
        self.assertGreater(r.deflection_mm, p.max_serviceability_span_mm)  # 挠度超限

    def test_big_section_ok(self):
        f = get("FormulaEngine")
        p = DesignParams(span=6000, wll=20, section_b=400, section_h=800, as_area=2000)
        r = f.solve(p)
        self.assertTrue(r.ok)


class TestAgent(unittest.TestCase):
    def test_agent_converges_via_rules(self):
        agent = Agent(AIDecider(), engine="FormulaEngine", max_iters=8)
        rep = agent.run(examples_lib.SAMPLE)
        self.assertGreaterEqual(len(rep.steps), 1)
        self.assertTrue(rep.converged, rep.reason)
        # 首步超限，末步满足
        self.assertFalse(rep.steps[0].ok)
        self.assertTrue(rep.final_result.ok)
        # 末步截面高度比初步大（规则会放大）
        first_h = int(rep.steps[0].section_label.split("x")[1])
        self.assertGreater(rep.design_params.section_h, first_h)


class TestMidasMock(unittest.TestCase):
    def test_degrades_gracefully(self):
        m = get("MIDAS(NX)")
        p = DesignParams()
        r = m.solve(p)
        self.assertTrue(math.isnan(r.stress_ratio))
        self.assertIn("未接入", r.log)


class TestRuleParser(unittest.TestCase):
    def test_parser(self):
        p = AIDecider().parse_design_book(examples_lib.SAMPLE)
        self.assertEqual(p.span, 6000.0)
        self.assertEqual(p.wll, 20.0)
        self.assertEqual(int(p.section_b), 200)
        self.assertEqual(int(p.section_h), 300)


if __name__ == "__main__":
    unittest.main(verbosity=2)
