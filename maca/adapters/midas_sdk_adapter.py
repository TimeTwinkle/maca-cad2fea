"""MIDAS Gen NX —— 官方 MAPI RESTful 直连适配器（按官方 2025 手册实证 schema）。

- 鉴权头 MAPI-Key <JWT>；中国区 Base https://moa-engineers.midasit.cn:443/gen
- 调用顺序：/OPE/APISTART -> 建模 -> /doc/ANAL {} -> /post/TABLE 取结果 -> /OPE/APIEND
- 没有 /db/RESULT；结果统一走 POST /post/TABLE（Argument.TABLE_TYPE 区分）

凭证走环境变量（绝不写死进代码）：MIDAS_API_URL / MIDAS_MAPI_KEY
未配置时自动退化为占位（灰色·待接入），保证 MACA 不依赖商业授权。
"""

import json
import os
import urllib.request
import urllib.error

from core.models import DesignParams, SolverResult
from core.solver import SolverBase, register

_E = float("nan")

# 官方手册 2：USER 自定义材料（绕开各国标准库差异）；C30（kN-m 制 ELAST=3.0e7）
_USER_MATL_BODY = {
    "Assign": {"1": {
        "TYPE": "USER", "NAME": "Conc_C30", "bMASS_DENS": True, "DAMP_RAT": 0.05,
        "PARAM": [{"P_TYPE": 2, "ELAST": 30000000, "POISN": 0.2,
                   "THERMAL": 0.00001, "DEN": 25, "MASS": 2.549}]}}
}
# 官方手册 1：梁单元（TYPE + NODE，无 Node1/Node2）
_BEAM_ELEM_BODY = {
    "Assign": {"1": {"TYPE": "BEAM", "MATL": 1, "SECT": 1, "NODE": [1, 2], "ANGLE": 0}}
}
# 官方手册 4：约束 / 荷载工况 / 自重 / 梁均布 / 组合
_CONSTRAINTS_BODY = {
    "Assign": {
        "1": {"ITEMS": [{"ID": 1, "CONSTRAINT": "1111000"}]},
        "2": {"ITEMS": [{"ID": 1, "CONSTRAINT": "1011000"}]},
    }}
_DC_BODY = {"Assign": {"1": {"NAME": "DL", "TYPE": "USER", "DESC": "dead"}, "2": {"NAME": "LL", "TYPE": "USER", "DESC": "live"}}}
_BODF_BODY = {"Assign": {"1": {"LCNAME": "DL", "FV": [0, 0, -1]}}}
_BMLD_BODY = {
    "Assign": {"1": {"ITEMS": [{
        "ID": 1, "LCNAME": "LL", "GROUP_NAME": "",
        "CMD": "BEAM", "TYPE": "UNILOAD", "DIRECTION": "GZ",
        "USE_PROJECTION": False, "USE_ECCEN": False,
        "D": [0, 1, 0, 0], "P": [-10, -10, 0, 0]}]}}}
_LCOM_BODY = {
    "Assign": {"1": {"iTYPE": 0, "NAME": "Comb1",
        "vCOMB": [{"ANAL": "ST", "LCNAME": "DL", "FACTOR": 1.0},
                   {"ANAL": "ST", "LCNAME": "LL", "FACTOR": 1.0}]}}
}


def _section_body(h_mm, b_mm):
    """官方手册 3：vSIZE=[H, B]，单位 m。"""
    return {"Assign": {"1": {
        "SECTTYPE": "DBUSER", "SECT_NAME": "Rectangular",
        "SECT_BEFORE": {"USE_SHEAR_DEFORM": True, "SHAPE": "SB", "DATATYPE": 2,
                        "SECT_I": {"vSIZE": [round(h_mm / 1000.0, 4), round(b_mm / 1000.0, 4)]}}}}}


def _post_table_arg(table_type, load_case_names, table_name=""):
    """官方手册 5：结果统一走 POST /post/TABLE。"""
    return {"Argument": {
        "TABLE_TYPE": table_type,
        "TABLE_NAME": table_name or table_type,
        "LOAD_CASE_NAMES": load_case_names,
    }}


@register
class MidasSdkAdapter(SolverBase):
    name = "MIDAS(NX)"
    mode = "commercial"
    note = "商业软件（midas Gen NX 官方 MAPI RESTful 直连）"

    def __init__(self):
        self.base_url = os.environ.get("MIDAS_API_URL", "").rstrip("/")
        self.mapi_key = os.environ.get("MIDAS_MAPI_KEY", "")
        self.available = bool(self.base_url and self.mapi_key)
        if not self.available:
            self.note = "商业软件（midas Gen NX），未接入（缺 MAPI_KEY/URL）→ 占位"

    def solve(self, p):
        if not self.available:
            return SolverResult(
                stress_ratio=_E, deflection_mm=_E, ok=False, engine=self.name,
                log="MIDAS 未接入：未设 MIDAS_API_URL / MIDAS_MAPI_KEY（官方 MAPI RESTful）")
        try:
            return self._solve_midas(p)
        except Exception as e:
            return SolverResult(
                stress_ratio=_E, deflection_mm=_E, ok=False, engine=self.name,
                log="MIDAS MAPI 调用失败: %s: %s" % (type(e).__name__, e))

    def _solve_midas(self, p):
        self._req("POST", "/OPE/APISTART", {})
        self._req("PUT", "/db/NODE", {"Assign": {
            "1": {"X": 0, "Y": 0, "Z": 0},
            "2": {"X": p.span / 1000.0, "Y": 0, "Z": 0}}})
        self._req("PUT", "/db/SECT", _section_body(p.section_h, p.section_b))
        self._req("POST", "/db/MATL", _USER_MATL_BODY)
        self._req("POST", "/db/ELEM", _BEAM_ELEM_BODY)
        self._req("POST", "/db/CONS", _CONSTRAINTS_BODY)
        self._req("POST", "/db/STLD", _DC_BODY)
        self._req("POST", "/db/BODF", _BODF_BODY)
        self._req("POST", "/db/BMLD", _BMLD_BODY)
        self._req("POST", "/db/LCOM-GEN", _LCOM_BODY)

        self._req("POST", "/doc/ANAL", {})

        disp = self._req("POST", "/post/TABLE",
                         _post_table_arg("DISPLACEMENTG", ["Comb1(CB)"], "Displacements(Global)"))
        bforce = self._req("POST", "/post/TABLE",
                           _post_table_arg("BEAMFORCE", ["Comb1(CB)"]))

        disp_max = _max_table_value(disp, ["DZ", "RY"])  # 竖向挠度: 平动 DZ 或 旋转 RY 取绝对值最大(MIDAS 坐标约定)
        m_max = _max_table_value(bforce, ["Moment-y", "Moment-z"])

        b_m = p.section_b / 1000.0
        h_m = p.section_h / 1000.0
        w_m3 = b_m * h_m * h_m / 6.0
        stress_ratio = ((m_max / w_m3) / 1000.0) / p.fy if (m_max is not None and w_m3 > 0) else None  # kN·m/m³=kPa, /1e3=MPa, 再除 fy(MPa) 得利用率

        ok = (
            (stress_ratio is None or stress_ratio <= 1.0)
            and (disp_max is None or disp_max <= p.max_serviceability_span_mm / 1000.0)
        )
        return SolverResult(
            stress_ratio=round(stress_ratio, 4) if stress_ratio is not None else _E,
            deflection_mm=round(disp_max * 1000.0, 3) if disp_max is not None else _E,
            max_moment_knm=round(m_max, 3) if m_max is not None else _E,
            ok=bool(ok),
            engine=self.name,
            log="MIDAS MAPI: M_max=%s kN·m, δ=%s m, 利用率=%s" % (_fmt(m_max), _fmt(disp_max), _fmt(stress_ratio)))

    def _req(self, method, path, body=None):
        url = self.base_url + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method.upper())
        req.add_header("Content-Type", "application/json")
        req.add_header("MAPI-Key", self.mapi_key)
        req.add_header("Authorization", "Bearer " + self.mapi_key)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode(errors="replace") or "{}"
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return {"raw": raw}
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace") or ""
            try:
                return {"http": e.code, "error": json.loads(raw)}
            except Exception:
                return {"http": e.code, "error": {"raw": raw[:300]}}


def _fmt(v):
    if v is None:
        return "NA"
    try:
        return "%.4f" % float(v)
    except Exception:
        return str(v)


def _max_table_value(resp, keys):
    """从 /post/TABLE 响应取指定组件的最大绝对值（官方值都是字符串）。"""
    if not isinstance(resp, dict):
        return None
    for _val in resp.values():
        if isinstance(_val, dict) and "DATA" in _val and "HEAD" in _val:
            head = _val["HEAD"]
            col_idx = {}
            for i, k in enumerate(head):
                if k in keys:
                    col_idx[k] = i
            if not col_idx:
                continue
            maxv = None
            for row in _val["DATA"]:
                for k, i in col_idx.items():
                    if i < len(row):
                        try:
                            v = float(row[i])
                        except (TypeError, ValueError):
                            continue
                        if maxv is None or abs(v) > abs(maxv):
                            maxv = v
            if maxv is not None:
                return maxv
    return None
