from __future__ import annotations

import io
import json
import math
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VENDOR_DIR = BASE_DIR / ".vendor"
if os.environ.get("MOF_SORPTION_USE_VENDOR", "").strip().lower() in {"1", "true", "yes", "on"} and str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

import numpy as np
import pandas as pd
from CoolProp.CoolProp import PropsSI
from flask import Flask, jsonify, render_template, request, send_file
from pyiast import InterpolatorIsotherm, ModelIsotherm as PyIASTModelIsotherm, iast as pyiast_iast
from pygaps import ModelIsotherm, PointIsotherm
from pygaps.characterisation import area_BET_raw, t_plot
from pygaps.characterisation.psd_kernel import psd_dft
from pygaps.characterisation.psd_meso import psd_mesoporous
from pygaps.characterisation.psd_micro import psd_microporous
from pygaps.data import KERNELS
from scipy.interpolate import PchipInterpolator
from scipy import stats

app = Flask(__name__)

PRESSURE_FACTORS_BAR = {
    "bar": 1.0,
    "kpa": 0.01,
    "pa": 1e-5,
    "mpa": 10.0,
    "atm": 1.01325,
    "torr": 1.33322e-3,
    "mmhg": 1.33322e-3,
}

RELATIVE_UNITS = {"p/p0", "p/p₀", "relative", "relative pressure"}

LOADING_FACTORS_MMOL_G = {
    "mmol/g": 1.0,
    "mol/kg": 1.0,
    "mol/g": 1000.0,
    "cm3(stp)/g": 1 / 22.414,
    "cc(stp)/g": 1 / 22.414,
    "cm3/g": 1 / 22.414,
    "cc/g": 1 / 22.414,
    "ml/g": 1 / 22.414,
}

FIT_MODEL_MAP = {
    "Henry": "Henry",
    "Langmuir": "Langmuir",
    "Freundlich": "Freundlich",
    "BET": "BET",
    "Quadratic": "Quadratic",
    "Temkin (Approx)": "TemkinApprox",
    "Toth": "Toth",
    "Unit-site Langmuir": "Langmuir",
    "Dual-site Langmuir": "DSLangmuir",
    "PCHIP interpolation": "__pchip__",
}

IAST_MODEL_MAP = {
    "Henry": "Henry",
    "Langmuir": "Langmuir",
    "BET": "BET",
    "Quadratic": "Quadratic",
    "Temkin (Approx)": "TemkinApprox",
    "Toth": "Toth",
    "Dual-site Langmuir": "DSLangmuir",
    "Interpolation (Linear)": "__interp__",
}

BET_ALLOWED = {
    ("nitrogen", 77),
    ("argon", 87),
    ("carbon dioxide", 273),
}

PLOT_EXPORT_HEADERS = {
    "isotherm_data": ["pressure", "loading"],
    "isotherm_fit": ["pressure", "loading_fit"],
    "qst_table": ["loading_mmol_g", "qst_kj_mol", "linearity_r2"],
    "iast_results": [],
    "psd_distribution": ["pore_width_nm", "distribution"],
}

METHOD_EXPLANATIONS = {
    "Langmuir": {
        "title": "Langmuir 单层吸附模型",
        "summary": "适合有限等价位点、近似单层吸附的体系，常用于微孔材料的基础拟合。",
        "equations": [
            {
                "label": "Model equation",
                "latex": r"q(P)=\frac{q_m K P}{1+K P}",
            },
        ],
        "notes": [
            "q_m 是饱和吸附量，K 是吸附亲和常数。",
            "假设位点等价、单层吸附、吸附分子间相互作用可忽略。",
            "如果低压到中压段拟合较好而高压偏离，常提示需要更复杂模型。",
        ],
    },
    "Freundlich": {
        "title": "Freundlich 非均匀表面经验模型",
        "summary": "适合表面能量分布不均匀、经验拟合优先的情况，常用于非理想表面。",
        "equations": [
            {
                "label": "Model equation",
                "latex": r"q(P)=K_F P^{1/n}",
            },
        ],
        "notes": [
            "K_F 反映吸附能力，n 反映非线性程度。",
            "模型没有严格饱和上限，因此高压区外推要谨慎。",
            "更适合经验描述，不适合解释明确的单层饱和行为。",
        ],
    },
    "BET": {
        "title": "BET 多层吸附模型",
        "summary": "主要用于比表面积计算，也可用于特定相对压力区间的多层吸附描述。",
        "equations": [
            {
                "label": "Loading form",
                "latex": r"q(P)=q_m\frac{C(P/P_0)}{(1-P/P_0)\left[1+(C-1)(P/P_0)\right]}",
            },
            {
                "label": "Linearized form",
                "latex": r"\frac{P/P_0}{q\left(1-P/P_0\right)}=\frac{1}{q_m C}+\frac{C-1}{q_m C}\frac{P}{P_0}",
            },
        ],
        "notes": [
            "q_m 是单层吸附量，C 是 BET 常数。",
            "实际分析时应结合 Rouquerol 判据选点，不建议机械全区间拟合。",
            "BET 更偏表面积分析，不是所有等温线的最佳全程拟合模型。",
        ],
    },
    "Henry": {
        "title": "Henry 低压线性模型",
        "summary": "用于极低压区的初始斜率分析，适合近似线性吸附段。",
        "equations": [
            {
                "label": "Model equation",
                "latex": r"q(P)=K_H P",
            },
        ],
        "notes": [
            "只适合低覆盖度区域。",
            "K_H 常用于比较初始亲和性或作为更复杂模型的低压参考。",
        ],
    },
    "Quadratic": {
        "title": "Quadratic 双位相互作用模型",
        "summary": "适合考虑更复杂表面相互作用的情形，比 Langmuir 更灵活。",
        "equations": [
            {
                "label": "Model equation",
                "latex": r"q(P)=q_m\frac{P(K_a+2K_bP)}{1+K_aP+K_bP^2}",
            },
        ],
        "notes": [
            "在一些协同吸附或曲率较复杂的体系中表现更好。",
            "参数较多，拟合成功时要同步检查物理意义和稳定性。",
        ],
    },
    "Temkin (Approx)": {
        "title": "Temkin 近似模型",
        "summary": "考虑吸附热随覆盖度变化的近似行为，适合中等复杂度拟合。",
        "equations": [
            {
                "label": "Coverage surrogate",
                "latex": r"\theta_L=\frac{K P}{1+K P}",
            },
            {
                "label": "Temkin approximation used by pyGAPS",
                "latex": r"q(P)=q_m\left[\theta_L+\Theta\theta_L^2(\theta_L-1)\right]",
            },
        ],
        "notes": [
            "这里的 Θ 表示 Temkin 相互作用项；在程序底层 pyGAPS 参数中对应 tht。",
            "常用于热力学趋势的半经验描述。",
            "解释能力有限，通常作为补充模型而非唯一结论来源。",
        ],
    },
    "Toth": {
        "title": "Toth 非理想单层模型",
        "summary": "适用于偏离理想 Langmuir 的非均匀表面，常见于真实多孔材料。",
        "equations": [
            {
                "label": "Model equation",
                "latex": r"q(P)=q_m\frac{K P}{\left[1+(K P)^t\right]^{1/t}}",
            },
        ],
        "notes": [
            "t 描述表面非均匀程度，t = 1 时退化为 Langmuir。",
            "通常比 Langmuir 更稳健地描述宽压力范围数据。",
        ],
    },
    "Dual-site Langmuir": {
        "title": "双位点 Langmuir 模型",
        "summary": "适合存在两类吸附位点的体系，是 MOF 吸附中很常见的解析模型。",
        "equations": [
            {
                "label": "Model equation",
                "latex": r"q(P)=q_{m,1}\frac{K_1P}{1+K_1P}+q_{m,2}\frac{K_2P}{1+K_2P}",
            },
        ],
        "notes": [
            "可分别反映强位点与弱位点的贡献。",
            "当单一 Langmuir 拟合系统性偏离时，DSL 往往更合适。",
        ],
    },
    "PCHIP interpolation": {
        "title": "PCHIP 保形插值通用拟合",
        "summary": "适合 S 型或非典型曲线，不强行假设具体物理模型，而是用保形分段三次插值平滑连接实验点。",
        "equations": [
            {
                "label": "Interpolation operator",
                "latex": r"q(P)=\operatorname{PCHIP}\!\left(P;\{(P_i,q_i)\}_{i=1}^{N}\right)",
            },
        ],
        "notes": [
            "优点是保留原始趋势、不过度振荡，特别适合不规则等温线。",
            "它更适合作为通用表达或后续插值，不应直接代替物理机制解释。",
            "如果要写论文机理讨论，仍建议结合解析模型或实验背景解释。",
        ],
    },
    "Interpolation (Linear)": {
        "title": "线性插值型纯组分输入",
        "summary": "在 IAST 中作为通用近似输入，直接基于原始纯组分数据插值，而不强行套解析模型。",
        "equations": [
            {
                "label": "Interpolation operator",
                "latex": r"q(P)=\operatorname{Interp}_{\mathrm{linear}}\!\left(P;\{(P_i,q_i)\}_{i=1}^{N}\right)",
            },
        ],
        "notes": [
            "适用于解析模型难以稳定描述的非典型纯组分曲线。",
            "优点是保留实验点趋势，缺点是外推能力有限。",
        ],
    },
    "Clausius-Clapeyron": {
        "title": "Clausius-Clapeyron 等量吸附热",
        "summary": "在恒定吸附量下，利用不同温度对应平衡压力的关系求 Qst。",
        "equations": [
            {
                "label": "Definition at constant loading",
                "latex": r"Q_{st}(q)=-R\left(\frac{\partial \ln P}{\partial(1/T)}\right)_{q}",
            },
            {
                "label": "Linear form used in the fit",
                "latex": r"\ln P=-\frac{Q_{st}}{R}\frac{1}{T}+C_q",
            },
        ],
        "notes": [
            "每个 loading 点都来自多温等温线之间的插值对应。",
            "线性越好，说明该 loading 点的等量吸附热估计越稳定。",
            "温区越合理、数据越平滑，结果越可信。",
        ],
    },
    "Virial": {
        "title": "Virial 方程法 Qst",
        "summary": "把多温数据统一写入 Virial 方程，通过系数随覆盖度变化估算 Qst。",
        "equations": [
            {
                "label": "Truncated virial form used here",
                "latex": r"\ln\!\left(\frac{P}{n}\right)=\frac{a_0+a_1n+a_2n^2}{T}+b_0+b_1n+b_2n^2",
            },
            {
                "label": "Resulting isosteric heat expression",
                "latex": r"Q_{st}(n)=-R\left(a_0+a_1n+a_2n^2\right)",
            },
        ],
        "notes": [
            "优点是可以统一处理多温数据，减少逐点取值误差。",
            "系数对数据质量和覆盖区间较敏感，建议与 CC 法交叉验证。",
        ],
    },
    "IAST": {
        "title": "IAST 多组分竞争吸附",
        "summary": "先拟合纯组分等温线，再通过扩展压力平衡计算混合气选择性与吸附量。",
        "equations": [
            {
                "label": "Spreading pressure",
                "latex": r"\pi_i(P_i^*)=\int_{0}^{P_i^*}\frac{q_i^{0}(P)}{P}\,dP",
            },
            {
                "label": "IAST equilibrium condition",
                "latex": r"\pi_1(P_1^*)=\pi_2(P_2^*)=\cdots=\pi_N(P_N^*)",
            },
            {
                "label": "Binary selectivity",
                "latex": r"S_{1/2}=\frac{x_1/x_2}{y_1/y_2}",
            },
        ],
        "notes": [
            "x 是吸附相摩尔分数，y 是气相摩尔分数。",
            "纯组分拟合质量会直接影响 IAST 结果。",
            "若纯组分曲线非常非典型，可考虑插值型输入作为通用近似。",
        ],
    },
    "BET-PSD": {
        "title": "BET / t-plot / PSD 结构分析",
        "summary": "BET 给出比表面积，t-plot 估算微孔体积与平均孔径，PSD 则输出孔径分布峰位与分布曲线。",
        "equations": [
            {
                "label": "BET linearization",
                "latex": r"\frac{P/P_0}{q\left(1-P/P_0\right)}=\frac{1}{q_m C}+\frac{C-1}{q_m C}\frac{P}{P_0}",
            },
            {
                "label": "t-plot workflow",
                "latex": r"q \text{ vs. } t(P/P_0)",
            },
            {
                "label": "PSD ordinates",
                "latex": r"\mathrm{PSD}\propto \frac{dV}{dW}\ \text{or}\ \frac{dq}{dW}",
            },
        ],
        "notes": [
            "经典模型与 NLDFT 应分开理解和使用，不建议混合成一个结果判断。",
            "HK / SF 适合微孔，BJH / DH 更偏介孔，大孔分析要谨慎解释。",
            "NLDFT 必须匹配正确的探针分子、温度和 kernel。",
        ],
    },
}


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

ADSORBATE_BLUEPRINTS = [
    {
        "key": "carbon dioxide",
        "lookup": ["carbon dioxide", "co2"],
        "zh": "二氧化碳",
        "en": "Carbon dioxide",
        "formula": "CO2",
        "melting_point_c": -56.6,
        "boiling_point_c": -78.5,
        "note": "1 atm 下表现为升华温度。",
    },
    {
        "key": "nitrogen",
        "lookup": ["nitrogen", "n2"],
        "zh": "氮气",
        "en": "Nitrogen",
        "formula": "N2",
        "melting_point_c": -210.0,
        "boiling_point_c": -195.8,
    },
    {
        "key": "carbon monoxide",
        "lookup": ["carbon monoxide", "co"],
        "zh": "一氧化碳",
        "en": "Carbon monoxide",
        "formula": "CO",
        "melting_point_c": -205.0,
        "boiling_point_c": -191.5,
    },
    {
        "key": "methane",
        "lookup": ["methane", "ch4"],
        "zh": "甲烷",
        "en": "Methane",
        "formula": "CH4",
        "melting_point_c": -182.5,
        "boiling_point_c": -161.5,
    },
    {
        "key": "ethane",
        "lookup": ["ethane", "c2h6"],
        "zh": "乙烷",
        "en": "Ethane",
        "formula": "C2H6",
        "melting_point_c": -182.8,
        "boiling_point_c": -88.6,
    },
    {
        "key": "ethene",
        "lookup": ["ethene", "ethylene", "c2h4"],
        "zh": "乙烯",
        "en": "Ethylene",
        "formula": "C2H4",
        "melting_point_c": -169.2,
        "boiling_point_c": -103.7,
    },
    {
        "key": "acetylene",
        "lookup": ["acetylene", "c2h2"],
        "zh": "乙炔",
        "en": "Acetylene",
        "formula": "C2H2",
        "melting_point_c": -80.8,
        "boiling_point_c": -84.0,
        "note": "常压附近常以升华/分解边界参考。",
    },
    {
        "key": "propane",
        "lookup": ["propane", "c3h8"],
        "zh": "丙烷",
        "en": "Propane",
        "formula": "C3H8",
        "melting_point_c": -187.7,
        "boiling_point_c": -42.1,
    },
    {
        "key": "propene",
        "lookup": ["propene", "propylene", "c3h6"],
        "zh": "丙烯",
        "en": "Propylene",
        "formula": "C3H6",
        "melting_point_c": -185.2,
        "boiling_point_c": -47.6,
    },
    {
        "key": "propyne",
        "lookup": ["propyne", "methylacetylene", "c3h4"],
        "zh": "丙炔",
        "en": "Propyne",
        "formula": "C3H4",
        "melting_point_c": -102.7,
        "boiling_point_c": -23.2,
    },
    {
        "key": "allene",
        "lookup": ["allene", "propadiene"],
        "zh": "丙二烯",
        "en": "Allene",
        "formula": "C3H4",
        "melting_point_c": -136.0,
        "boiling_point_c": -34.4,
        "manual": {
            "molecular_size_a": 5.8,
            "kinetic_diameter_a": 4.0,
            "dipole_moment_d": 0.0,
            "quadrupole_moment": 0.6,
        },
    },
    {
        "key": "n-butane",
        "lookup": ["n-butane", "butane", "c4h10"],
        "zh": "正丁烷",
        "en": "n-Butane",
        "formula": "n-C4H10",
        "melting_point_c": -138.3,
        "boiling_point_c": -0.5,
    },
    {
        "key": "isobutane",
        "lookup": ["isobutane", "i-c4h10"],
        "zh": "异丁烷",
        "en": "Isobutane",
        "formula": "i-C4H10",
        "melting_point_c": -159.6,
        "boiling_point_c": -11.7,
        "manual": {
            "molecular_size_a": 7.1,
            "kinetic_diameter_a": 5.0,
            "dipole_moment_d": 0.1,
            "quadrupole_moment": 0.0,
        },
    },
    {
        "key": "1-butene",
        "lookup": ["1-butene", "butene", "c4h8"],
        "zh": "丁烯",
        "en": "1-Butene",
        "formula": "C4H8",
        "melting_point_c": -185.3,
        "boiling_point_c": -6.3,
        "manual": {
            "molecular_size_a": 6.9,
            "kinetic_diameter_a": 4.9,
            "dipole_moment_d": 0.34,
            "quadrupole_moment": 0.0,
        },
    },
    {
        "key": "1,3-butadiene",
        "lookup": ["1,3-butadiene", "butadiene", "c4h6"],
        "zh": "丁二烯",
        "en": "1,3-Butadiene",
        "formula": "C4H6",
        "melting_point_c": -108.9,
        "boiling_point_c": -4.4,
        "manual": {
            "molecular_size_a": 6.5,
            "kinetic_diameter_a": 4.7,
            "dipole_moment_d": 0.0,
            "quadrupole_moment": 1.1,
        },
    },
    {
        "key": "ammonia",
        "lookup": ["ammonia", "nh3"],
        "zh": "氨气",
        "en": "Ammonia",
        "formula": "NH3",
        "melting_point_c": -77.7,
        "boiling_point_c": -33.3,
        "manual": {
            "kinetic_diameter_a": 2.6,
        },
    },
    {
        "key": "sulphur dioxide",
        "lookup": ["sulphur dioxide", "sulfur dioxide", "so2"],
        "zh": "二氧化硫",
        "en": "Sulfur dioxide",
        "formula": "SO2",
        "melting_point_c": -72.7,
        "boiling_point_c": -10.0,
        "manual": {
            "molecular_size_a": 4.7,
            "kinetic_diameter_a": 4.1,
            "dipole_moment_d": 1.63,
            "quadrupole_moment": 3.1,
        },
    },
    {
        "key": "sulfur hexafluoride",
        "lookup": ["sulfur hexafluoride", "sf6"],
        "zh": "六氟化硫",
        "en": "Sulfur hexafluoride",
        "formula": "SF6",
        "melting_point_c": -50.8,
        "boiling_point_c": -63.8,
        "note": "1 atm 下常以升华温度为参考。",
        "manual": {
            "molecular_size_a": 5.5,
            "kinetic_diameter_a": 5.5,
            "dipole_moment_d": 0.0,
            "quadrupole_moment": 0.0,
        },
    },
    {
        "key": "tetrafluoromethane",
        "lookup": ["tetrafluoromethane", "cf4"],
        "zh": "四氟化碳",
        "en": "Tetrafluoromethane",
        "formula": "CF4",
        "melting_point_c": -183.6,
        "boiling_point_c": -128.0,
        "manual": {
            "molecular_size_a": 4.9,
            "kinetic_diameter_a": 4.7,
            "dipole_moment_d": 0.0,
            "quadrupole_moment": 0.0,
        },
    },
    {
        "key": "xenon",
        "lookup": ["xenon", "xe"],
        "zh": "氙",
        "en": "Xenon",
        "formula": "Xe",
        "melting_point_c": -111.8,
        "boiling_point_c": -108.1,
    },
    {
        "key": "krypton",
        "lookup": ["krypton", "kr"],
        "zh": "氪",
        "en": "Krypton",
        "formula": "Kr",
        "melting_point_c": -157.4,
        "boiling_point_c": -153.4,
    },
    {
        "key": "argon",
        "lookup": ["argon", "ar"],
        "zh": "氩气",
        "en": "Argon",
        "formula": "Ar",
        "melting_point_c": -189.3,
        "boiling_point_c": -185.8,
    },
    {
        "key": "helium",
        "lookup": ["helium", "he"],
        "zh": "氦气",
        "en": "Helium",
        "formula": "He",
        "melting_point_c": -272.2,
        "boiling_point_c": -268.9,
    },
    {
        "key": "neon",
        "lookup": ["neon", "ne"],
        "zh": "氖气",
        "en": "Neon",
        "formula": "Ne",
        "melting_point_c": -248.6,
        "boiling_point_c": -246.0,
    },
    {
        "key": "oxygen",
        "lookup": ["oxygen", "o2"],
        "zh": "氧气",
        "en": "Oxygen",
        "formula": "O2",
        "melting_point_c": -218.8,
        "boiling_point_c": -183.0,
    },
    {
        "key": "water",
        "lookup": ["water", "h2o"],
        "zh": "水",
        "en": "Water",
        "formula": "H2O",
        "melting_point_c": 0.0,
        "boiling_point_c": 100.0,
    },
]


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"[\s_\-]+", "", str(value).strip().lower())


def latex_formula_to_plain(formula: str | None) -> str | None:
    if not formula:
        return formula
    plain = re.sub(r"_\{([^}]+)\}", r"\1", formula)
    return plain.replace("{", "").replace("}", "")


def safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return numeric


def load_pygaps_adsorbates() -> tuple[list[dict], dict[str, dict]]:
    adsorbate_path = VENDOR_DIR / "pygaps" / "data" / "adsorbates.json"
    items = json.loads(adsorbate_path.read_text(encoding="utf-8"))
    alias_lookup: dict[str, dict] = {}
    for item in items:
        names = [item.get("name", "")]
        names.extend(item.get("alias", []))
        formula_plain = latex_formula_to_plain(item.get("formula"))
        if formula_plain:
            names.append(formula_plain)
        for name in names:
            alias_lookup[normalize_text(name)] = item
    return items, alias_lookup


_PYGAPS_ITEMS, _PYGAPS_LOOKUP = load_pygaps_adsorbates()


def build_adsorbate_library() -> list[dict]:
    library = []
    for blueprint in ADSORBATE_BLUEPRINTS:
        raw = None
        for token in blueprint["lookup"]:
            raw = _PYGAPS_LOOKUP.get(normalize_text(token))
            if raw:
                break
        area = safe_float(raw.get("cross_sectional_area")) if raw else None
        size_a = round(math.sqrt(4 * area / math.pi) * 10, 2) if area else None
        kinetic = round(safe_float(raw.get("kinetic_diameter")) * 10, 2) if raw and raw.get("kinetic_diameter") else None
        entry = {
            "key": blueprint["key"],
            "zh": blueprint["zh"],
            "en": blueprint["en"],
            "formula": latex_formula_to_plain(raw.get("formula")) if raw and raw.get("formula") else blueprint["formula"],
            "formula_display": blueprint["formula"],
            "molecular_size_a": size_a,
            "kinetic_diameter_a": kinetic,
            "melting_point_c": blueprint["melting_point_c"],
            "boiling_point_c": blueprint["boiling_point_c"],
            "dipole_moment_d": safe_float(raw.get("dipole_moment")) if raw else None,
            "quadrupole_moment": safe_float(raw.get("quadrupole_moment")) if raw else None,
            "cross_section_nm2": area,
            "backend_name": raw.get("backend_name") if raw else None,
            "aliases": sorted(set(blueprint["lookup"] + [blueprint["zh"], blueprint["en"], blueprint["formula"]])),
            "note": blueprint.get("note", ""),
        }
        manual = blueprint.get("manual", {})
        entry.update({key: manual.get(key, entry.get(key)) for key in manual})
        library.append(entry)
    return library


ADSORBATE_LIBRARY = build_adsorbate_library()
ADSORBATE_LOOKUP = {normalize_text(item["key"]): item for item in ADSORBATE_LIBRARY}
for item in ADSORBATE_LIBRARY:
    for alias in item["aliases"]:
        ADSORBATE_LOOKUP[normalize_text(alias)] = item
    ADSORBATE_LOOKUP[normalize_text(item["formula"])] = item


def find_adsorbate(token: str | None) -> dict | None:
    if not token:
        return None
    return ADSORBATE_LOOKUP.get(normalize_text(token))


def saturation_pressure_bar(adsorbate_name: str, temperature_k: float) -> float:
    adsorbate = find_adsorbate(adsorbate_name)
    if not adsorbate or not adsorbate.get("backend_name"):
        raise ValueError("所选吸附质没有可用的饱和蒸气压后端。")
    pressure_pa = PropsSI("P", "T", float(temperature_k), "Q", 0, adsorbate["backend_name"])
    return pressure_pa / 1e5


def convert_pressure(values, unit: str, target: str, adsorbate: str | None = None, temperature: float | None = None):
    unit_key = normalize_text(unit)
    arr = np.asarray(values, dtype=float)
    if unit_key in {normalize_text(value) for value in RELATIVE_UNITS}:
        mode = "relative"
        converted = arr
    else:
        canonical = None
        for pressure_unit in PRESSURE_FACTORS_BAR:
            if unit_key == normalize_text(pressure_unit):
                canonical = pressure_unit
                break
        if not canonical:
            raise ValueError(f"暂不支持压力单位：{unit}")
        mode = "absolute"
        converted = arr * PRESSURE_FACTORS_BAR[canonical]
    if target == mode:
        return converted
    if adsorbate is None or temperature is None:
        raise ValueError("使用 p/p0 与绝对压力互转时，需要提供吸附质和温度。")
    p0 = saturation_pressure_bar(adsorbate, temperature)
    if target == "absolute":
        return converted * p0
    return converted / p0


def convert_loading(values, unit: str):
    unit_key = normalize_text(unit)
    canonical = None
    for loading_unit in LOADING_FACTORS_MMOL_G:
        if unit_key == normalize_text(loading_unit):
            canonical = loading_unit
            break
    if not canonical:
        raise ValueError(f"暂不支持吸附量单位：{unit}")
    return np.asarray(values, dtype=float) * LOADING_FACTORS_MMOL_G[canonical]


def clean_xy(pressure, loading):
    frame = pd.DataFrame({"pressure": pressure, "loading": loading})
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    frame = frame[frame["pressure"] >= 0]
    frame = frame.sort_values("pressure")
    if len(frame) < 3:
        raise ValueError("至少需要 3 个有效数据点。")
    return frame["pressure"].to_numpy(dtype=float), frame["loading"].to_numpy(dtype=float)


def build_model_isotherm(
    pressure,
    loading_mmol_g,
    adsorbate: str,
    temperature: float,
    model_name: str,
    pressure_mode: str,
):
    kwargs = {
        "pressure": pressure,
        "loading": loading_mmol_g,
        "model": model_name,
        "material": "sample",
        "adsorbate": adsorbate,
        "temperature": float(temperature),
        "temperature_unit": "K",
        "loading_basis": "molar",
        "loading_unit": "mmol",
        "material_basis": "mass",
        "material_unit": "g",
        "pressure_mode": pressure_mode,
    }
    if pressure_mode == "absolute":
        kwargs["pressure_unit"] = "bar"
    return ModelIsotherm(**kwargs)


def predict_curve_pressures(pressure_values: np.ndarray, pressure_mode: str) -> np.ndarray:
    p_min = float(np.min(pressure_values))
    p_max = float(np.max(pressure_values))
    if p_max <= 0:
        raise ValueError("压力数据必须包含正值。")
    if pressure_mode == "relative" or p_min <= 0:
        return np.linspace(max(p_min, 0.0), p_max, 220)
    return np.geomspace(max(p_min, 1e-6), p_max, 220)


def r_squared(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    residual = np.sum((y_true - y_pred) ** 2)
    total = np.sum((y_true - np.mean(y_true)) ** 2)
    if total == 0:
        return 1.0
    return 1 - residual / total


def infer_units_from_headers(columns) -> dict:
    joined = " ".join(str(col).lower() for col in columns)
    pressure_unit = infer_pressure_unit(joined)
    loading_unit = infer_loading_unit(joined)
    return {"pressure_unit": pressure_unit, "loading_unit": loading_unit}


def infer_pressure_unit(label: str) -> str:
    text = normalize_text(label)
    if "p/p0" in text or "p/p₀" in label.lower() or "relative" in text:
        return "p/p0"
    if "kpa" in text:
        return "kPa"
    if "mpa" in text:
        return "MPa"
    if "atm" in text:
        return "atm"
    if "torr" in text or "mmhg" in text:
        return "torr"
    if "pa" in text:
        return "Pa"
    return "bar"


def infer_loading_unit(label: str) -> str:
    text = normalize_text(label)
    if "cm3(stp)/g" in text or ("cm3" in text and "stp" in text and "/g" in text):
        return "cm3(STP)/g"
    if "cc(stp)/g" in text or ("cc" in text and "stp" in text and "/g" in text):
        return "cc(STP)/g"
    if "cm3/g" in text:
        return "cm3(STP)/g"
    if "cc/g" in text or "ml/g" in text:
        return "cc(STP)/g"
    if "mol/kg" in text:
        return "mol/kg"
    if "mol/g" in text:
        return "mol/g"
    return "mmol/g"


def read_text_dataframe(file_bytes: bytes) -> pd.DataFrame:
    text = file_bytes.decode("utf-8-sig", errors="ignore")
    try:
        return pd.read_csv(io.StringIO(text), sep=None, engine="python", header=None, dtype=str)
    except Exception:
        pass
    try:
        return pd.read_csv(io.StringIO(text), sep=r"\s+", engine="python", header=None, dtype=str)
    except Exception:
        pass
    rows = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in re.split(r"\t+|,+|;+|\s{2,}", line) if part.strip()]
        if parts:
            rows.append(parts)
    if not rows:
        return pd.DataFrame()
    width = max(len(row) for row in rows)
    padded = [row + [None] * (width - len(row)) for row in rows]
    return pd.DataFrame(padded)


def clean_numeric_token(value) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("−", "-").replace("×10^", "e").replace("×10", "e").replace(",", "")
    return text


def numeric_series_from_values(values) -> pd.Series:
    cleaned = [clean_numeric_token(value) for value in values]
    return pd.to_numeric(pd.Series(cleaned, dtype="object"), errors="coerce")


def detect_numeric_block(raw_frame: pd.DataFrame) -> tuple[pd.DataFrame, int, int, int | None]:
    frame = raw_frame.dropna(axis=1, how="all").dropna(axis=0, how="all").reset_index(drop=True)
    if frame.empty:
        raise ValueError("未能从文件中识别到有效数据。")
    numeric_mask = frame.apply(lambda column: numeric_series_from_values(column).notna())
    row_numeric_counts = numeric_mask.sum(axis=1).tolist()
    best = None
    start = None
    for idx, count in enumerate(row_numeric_counts + [0]):
        if count >= 2 and start is None:
            start = idx
        elif count < 2 and start is not None:
            end = idx - 1
            length = end - start + 1
            if length >= 3:
                score = (sum(row_numeric_counts[start:end + 1]), length)
                if best is None or score > best["score"]:
                    best = {"start": start, "end": end, "score": score}
            start = None
    if best is None:
        candidate_rows = [idx for idx, count in enumerate(row_numeric_counts) if count >= 2]
        if len(candidate_rows) < 3:
            raise ValueError("文件中没有识别到足够长的二维数值数据区。")
        best = {"start": candidate_rows[0], "end": candidate_rows[-1]}
    header_row = None
    if best["start"] > 0 and row_numeric_counts[best["start"] - 1] < 2:
        header_row = best["start"] - 1
    return frame, best["start"], best["end"], header_row


def label_for_column(frame: pd.DataFrame, header_row: int | None, column) -> str:
    default_label = f"Column {int(column) + 1}" if isinstance(column, int) else str(column)
    if header_row is None:
        return default_label
    header_value = frame.at[header_row, column]
    text = str(header_value).strip() if header_value is not None else ""
    return text or default_label


def branch_guess_from_label(label: str) -> str:
    label_lower = str(label or "").lower()
    if re.search(r"\bdes(?:orption|orb)?\b", label_lower):
        return "desorption"
    if re.search(r"\bads(?:orption|orb)?\b", label_lower):
        return "adsorption"
    text = normalize_text(label)
    if any(token in text for token in ["desorption", "desorb"]):
        return "desorption"
    if any(token in text for token in ["adsorption", "adsorb"]):
        return "adsorption"
    return "unknown"


def pressure_score(label: str, series: pd.Series) -> float:
    text = normalize_text(label)
    values = series.dropna().to_numpy(dtype=float)
    score = 0.0
    if any(token in text for token in ["pressure", "press", "equilibrium pressure", "p/p0", "p/p"]):
        score += 8.0
    if "relative" in text:
        score += 4.0
    if any(token in text for token in ["bar", "kpa", "mpa", "atm", "torr", "pa"]):
        score += 3.0
    if len(values) >= 3:
        diffs = np.diff(values)
        monotonic_fraction = float(np.mean(diffs >= 0))
        score += monotonic_fraction * 3.0
        if np.nanmin(values) >= 0:
            score += 1.0
        if np.nanmax(values) <= 1.05 and np.nanmin(values) >= 0:
            score += 1.5
    return score


def loading_score(label: str, series: pd.Series, pressure_series: pd.Series | None = None) -> float:
    text = normalize_text(label)
    values = series.dropna().to_numpy(dtype=float)
    score = 0.0
    if any(token in text for token in ["loading", "uptake", "adsorbed", "amount", "quantity", "q", "n"]):
        score += 7.0
    if any(token in text for token in ["mmol/g", "mol/kg", "mol/g", "cm3", "cc", "ml/g"]):
        score += 3.5
    if "desorption" in text or "adsorption" in text:
        score += 2.0
    if len(values) >= 3 and np.nanmin(values) >= 0:
        score += 1.5
    if pressure_series is not None:
        joined = pd.concat([pressure_series, series], axis=1).dropna()
        if len(joined) >= 3:
            corr = joined.corr().iloc[0, 1]
            if pd.notna(corr):
                score += max(float(corr), 0.0) * 2.0
    return score


def is_auxiliary_numeric_column(label: str, series: pd.Series) -> bool:
    text = normalize_text(label)
    if any(token in text for token in ["temperature", "temp", "time", "minute", "second", "cycle", "index", "point"]):
        return True
    valid = series.dropna().to_numpy(dtype=float)
    if len(valid) >= 3 and np.unique(valid).size <= 2 and not any(token in text for token in ["pressure", "press", "p/p0"]):
        return True
    return False


def build_selected_dataset(candidate_map: dict[str, dict], pressure_id: str, loading_id: str) -> dict:
    pressure_candidate = candidate_map.get(pressure_id)
    loading_candidate = candidate_map.get(loading_id)
    if not pressure_candidate or not loading_candidate:
        raise ValueError("未找到所选列。")
    pressure = numeric_series_from_values(pressure_candidate["values"])
    loading = numeric_series_from_values(loading_candidate["values"])
    paired = pd.DataFrame({"pressure": pressure, "loading": loading}).dropna()
    if len(paired) < 3:
        raise ValueError("所选压力列与吸附量列的有效重叠数据不足。")
    return {
        "pressure": paired["pressure"].round(8).tolist(),
        "loading": paired["loading"].round(8).tolist(),
        "preview": paired.head(12).round(8).values.tolist(),
        "detected_units": {
            "pressure_unit": pressure_candidate["unit_guess"],
            "loading_unit": loading_candidate["unit_guess"],
        },
        "selected_columns": {
            "pressure": pressure_id,
            "loading": loading_id,
            "loading_branch": loading_candidate["branch_guess"],
        },
    }


def inspect_numeric_table(raw_frame: pd.DataFrame, selected_sheet: str) -> dict:
    frame, block_start, block_end, header_row = detect_numeric_block(raw_frame)
    data_region = frame.iloc[block_start:block_end + 1].reset_index(drop=True)
    candidates = []
    candidate_map = {}
    threshold = max(3, math.ceil(len(data_region) * 0.55))
    for column in data_region.columns:
        series = numeric_series_from_values(data_region[column])
        numeric_count = int(series.notna().sum())
        if numeric_count < threshold:
            continue
        label = label_for_column(frame, header_row, column)
        if is_auxiliary_numeric_column(label, series):
            continue
        candidate = {
            "id": f"col_{column}",
            "label": label,
            "column_index": int(column) if isinstance(column, int) else str(column),
            "numeric_count": numeric_count,
            "values": [safe_float(value) if pd.notna(value) else None for value in series.tolist()],
            "unit_guess": "mmol/g",
            "role_guess": "loading",
            "branch_guess": branch_guess_from_label(label),
        }
        candidates.append(candidate)
        candidate_map[candidate["id"]] = candidate
    if len(candidates) < 2:
        raise ValueError("文件中至少需要两列可用的数值列。")
    pressure_candidates = sorted(
        candidates,
        key=lambda item: pressure_score(item["label"], numeric_series_from_values(item["values"])),
        reverse=True,
    )
    selected_pressure = pressure_candidates[0]
    selected_pressure["role_guess"] = "pressure"
    selected_pressure["unit_guess"] = infer_pressure_unit(selected_pressure["label"])
    pressure_series = numeric_series_from_values(selected_pressure["values"])
    for candidate in candidates:
        if candidate["id"] == selected_pressure["id"]:
            continue
        candidate["role_guess"] = "loading"
        candidate["unit_guess"] = infer_loading_unit(candidate["label"])
    loading_candidates = sorted(
        [item for item in candidates if item["id"] != selected_pressure["id"]],
        key=lambda item: (
            "adsorption" in item["branch_guess"],
            loading_score(item["label"], numeric_series_from_values(item["values"]), pressure_series),
        ),
        reverse=True,
    )
    selected_loading = loading_candidates[0]
    selected = build_selected_dataset(candidate_map, selected_pressure["id"], selected_loading["id"])
    warnings = []
    if any(item["branch_guess"] == "desorption" for item in loading_candidates):
        warnings.append("检测到可能的脱附支路列；导入前请在确认窗口中明确选择吸附或脱附列。")
    if len(loading_candidates) > 1:
        warnings.append("检测到多个候选吸附量列；程序已给出默认选择，但建议你手动确认。")
    return {
        **selected,
        "sheet_names": [selected_sheet],
        "selected_sheet": selected_sheet,
        "candidate_columns": [
            {
                "id": item["id"],
                "label": item["label"],
                "column_index": item["column_index"],
                "numeric_count": item["numeric_count"],
                "role_guess": item["role_guess"],
                "branch_guess": item["branch_guess"],
                "unit_guess": item["unit_guess"],
                "preview": [value for value in item["values"][:12] if value is not None],
                "values": item["values"],
            }
            for item in candidates
        ],
        "detected_window": {
            "header_row_1based": header_row + 1 if header_row is not None else None,
            "data_start_row_1based": block_start + 1,
            "data_end_row_1based": block_end + 1,
        },
        "warnings": warnings,
    }


def parse_uploaded_table(file_storage, requested_sheet: str | None = None) -> dict:
    filename = file_storage.filename or "data.txt"
    suffix = Path(filename).suffix.lower()
    file_bytes = file_storage.read()
    if suffix in {".xlsx", ".xls"}:
        workbook = pd.ExcelFile(io.BytesIO(file_bytes))
        sheet_names = workbook.sheet_names
        sheet_name = requested_sheet if requested_sheet in sheet_names else sheet_names[0]
        raw_frame = pd.read_excel(workbook, sheet_name=sheet_name, header=None, dtype=object)
        result = inspect_numeric_table(raw_frame, sheet_name)
        result["sheet_names"] = sheet_names
        result["selected_sheet"] = sheet_name
        return result
    else:
        raw_frame = read_text_dataframe(file_bytes)
        return inspect_numeric_table(raw_frame, "Data")


def serialize_trace(x_values, y_values):
    return {
        "x": [safe_float(value) for value in np.asarray(x_values, dtype=float)],
        "y": [safe_float(value) for value in np.asarray(y_values, dtype=float)],
    }


def explanation_for(method_key: str) -> dict:
    return METHOD_EXPLANATIONS.get(method_key, {
        "title": method_key,
        "summary": "该方法暂无预置说明。",
        "equations": [],
        "notes": [],
    })


def dataframe_records(frame: pd.DataFrame) -> list[dict]:
    safe_frame = frame.replace([np.inf, -np.inf], np.nan)
    records = []
    for row in safe_frame.to_dict(orient="records"):
        records.append({key: safe_float(value) for key, value in row.items()})
    return records


def pchip_fit_result(pressure, loading, pressure_mode: str, model_label: str) -> dict:
    pressure, loading = clean_xy(pressure, loading)
    if len(np.unique(pressure)) < 3:
        raise ValueError("PCHIP 插值至少需要 3 个不同压力点。")
    interpolator = PchipInterpolator(pressure, loading)
    curve_pressure = predict_curve_pressures(pressure, pressure_mode)
    curve_loading = interpolator(curve_pressure)
    observed = interpolator(pressure)
    parameter_summary = {
        "data_points": int(len(pressure)),
        "pressure_min": safe_float(np.min(pressure)),
        "pressure_max": safe_float(np.max(pressure)),
        "interpolation": "PCHIP",
    }
    return {
        "model": model_label,
        "pressure_mode": pressure_mode,
        "pressure_unit": "p/p0" if pressure_mode == "relative" else "bar",
        "loading_unit": "mmol/g",
        "r2": safe_float(r_squared(loading, observed)),
        "rmse": safe_float(np.sqrt(np.mean((loading - observed) ** 2))),
        "parameters": parameter_summary,
        "data": serialize_trace(pressure, loading),
        "fit": serialize_trace(curve_pressure, curve_loading),
        "table_data": dataframe_records(pd.DataFrame({"pressure": pressure, "loading": loading})),
        "table_fit": dataframe_records(pd.DataFrame({"pressure": curve_pressure, "loading_fit": curve_loading})),
        "explanation": explanation_for(model_label),
    }


def fit_isotherm(payload: dict) -> dict:
    model_label = payload["model"]
    model_name = FIT_MODEL_MAP.get(model_label)
    if not model_name:
        raise ValueError("不支持所选拟合模型。")
    adsorbate = payload.get("adsorbate") or "nitrogen"
    temperature = float(payload.get("temperature") or 298.15)
    pressure_unit = payload["pressureUnit"]
    loading_unit = payload["loadingUnit"]
    pressure = np.asarray(payload["pressure"], dtype=float)
    loading = convert_loading(payload["loading"], loading_unit)
    pressure_mode = "absolute"
    target_mode = "relative" if model_name == "BET" else "absolute"
    if normalize_text(pressure_unit) in {normalize_text(value) for value in RELATIVE_UNITS}:
        pressure_mode = "relative"
    pressure = convert_pressure(pressure, pressure_unit, target_mode, adsorbate, temperature)
    pressure_mode = target_mode
    if model_name == "__pchip__":
        return pchip_fit_result(pressure, loading, pressure_mode, model_label)
    pressure, loading = clean_xy(pressure, loading)
    model_iso = build_model_isotherm(
        pressure=pressure,
        loading_mmol_g=loading,
        adsorbate=adsorbate,
        temperature=temperature,
        model_name=model_name,
        pressure_mode=pressure_mode,
    )
    observed = model_iso.model.loading(np.asarray(pressure, dtype=float))
    curve_pressure = predict_curve_pressures(pressure, pressure_mode)
    curve_loading = model_iso.model.loading(curve_pressure)
    return {
        "model": model_label,
        "pressure_mode": pressure_mode,
        "pressure_unit": "p/p0" if pressure_mode == "relative" else "bar",
        "loading_unit": "mmol/g",
        "r2": safe_float(r_squared(loading, observed)),
        "rmse": safe_float(np.sqrt(np.mean((loading - observed) ** 2))),
        "parameters": {
            key: safe_float(value) for key, value in model_iso.model.params.items()
        },
        "data": serialize_trace(pressure, loading),
        "fit": serialize_trace(curve_pressure, curve_loading),
        "table_data": dataframe_records(pd.DataFrame({"pressure": pressure, "loading": loading})),
        "table_fit": dataframe_records(pd.DataFrame({"pressure": curve_pressure, "loading_fit": curve_loading})),
        "explanation": explanation_for(model_label),
    }


def qst_clausius_clapeyron(datasets: list[dict]) -> dict:
    converted = []
    temperatures = []
    for dataset in datasets:
        temperature = float(dataset["temperature"])
        pressure = convert_pressure(
            dataset["pressure"],
            dataset["pressureUnit"],
            "absolute",
            dataset.get("adsorbate"),
            temperature,
        )
        loading = convert_loading(dataset["loading"], dataset["loadingUnit"])
        pressure, loading = clean_xy(pressure, loading)
        sorter = np.argsort(loading)
        loading_sorted = loading[sorter]
        pressure_sorted = pressure[sorter]
        unique_loading, unique_idx = np.unique(loading_sorted, return_index=True)
        unique_pressure = pressure_sorted[unique_idx]
        if len(unique_loading) < 3:
            raise ValueError("每条等温线在去重后至少需要 3 个装载点。")
        converted.append({"loading": unique_loading, "pressure": unique_pressure, "temperature": temperature})
        temperatures.append(temperature)
    overlap_min = max(float(dataset["loading"][0]) for dataset in converted)
    overlap_max = min(float(dataset["loading"][-1]) for dataset in converted)
    if overlap_max <= overlap_min:
        raise ValueError("不同温度数据的装载区间没有重叠，无法计算 Qst。")
    loading_grid = np.linspace(overlap_min, overlap_max, 30)
    qst_values = []
    linearities = []
    for loading_point in loading_grid:
        ln_pressures = []
        inverse_temperatures = []
        for dataset in converted:
            pressure_value = np.interp(loading_point, dataset["loading"], dataset["pressure"])
            if pressure_value <= 0:
                continue
            ln_pressures.append(np.log(pressure_value))
            inverse_temperatures.append(1.0 / dataset["temperature"])
        slope, intercept, r_value, _, _ = stats.linregress(inverse_temperatures, ln_pressures)
        qst_values.append(-8.314462618 * slope / 1000.0)
        linearities.append(r_value**2)
    return {
        "method": "Clausius-Clapeyron",
        "loading_unit": "mmol/g",
        "qst_unit": "kJ/mol",
        "curve": serialize_trace(loading_grid, qst_values),
        "table": [
            {
                "loading_mmol_g": safe_float(load),
                "qst_kj_mol": safe_float(qst),
                "linearity_r2": safe_float(r2_value),
            }
            for load, qst, r2_value in zip(loading_grid, qst_values, linearities)
        ],
        "explanation": explanation_for("Clausius-Clapeyron"),
    }


def qst_virial(datasets: list[dict]) -> dict:
    rows = []
    traces = []
    for dataset in datasets:
        temperature = float(dataset["temperature"])
        pressure = convert_pressure(
            dataset["pressure"],
            dataset["pressureUnit"],
            "absolute",
            dataset.get("adsorbate"),
            temperature,
        )
        loading = convert_loading(dataset["loading"], dataset["loadingUnit"])
        pressure, loading = clean_xy(pressure, loading)
        valid = (pressure > 0) & (loading > 0)
        pressure = pressure[valid]
        loading = loading[valid]
        for p_value, n_value in zip(pressure, loading):
            rows.append(
                [
                    1 / temperature,
                    n_value / temperature,
                    (n_value**2) / temperature,
                    1,
                    n_value,
                    n_value**2,
                ]
            )
        traces.append({"temperature": temperature, "pressure": pressure, "loading": loading})
    if len(rows) < 6:
        raise ValueError("Virial 拟合点数不足。")
    x_matrix = np.asarray(rows, dtype=float)
    y_vector = []
    for dataset in traces:
        y_vector.extend(np.log(dataset["pressure"]) - np.log(dataset["loading"]))
    coefficients, *_ = np.linalg.lstsq(x_matrix, np.asarray(y_vector, dtype=float), rcond=None)
    a0, a1, a2, b0, b1, b2 = coefficients.tolist()
    loading_min = max(float(np.min(item["loading"])) for item in traces)
    loading_max = min(float(np.max(item["loading"])) for item in traces)
    loading_grid = np.linspace(loading_min, loading_max, 30)
    qst_values = -8.314462618 * (a0 + a1 * loading_grid + a2 * loading_grid**2) / 1000.0
    fitted_traces = []
    for dataset in traces:
        n = dataset["loading"]
        predicted_ln_p = np.log(n) + (a0 + a1 * n + a2 * n**2) / dataset["temperature"] + (b0 + b1 * n + b2 * n**2)
        fitted_traces.append(
            {
                "temperature": dataset["temperature"],
                "data": serialize_trace(n, dataset["pressure"]),
                "fit": serialize_trace(n, np.exp(predicted_ln_p)),
            }
        )
    return {
        "method": "Virial",
        "loading_unit": "mmol/g",
        "qst_unit": "kJ/mol",
        "curve": serialize_trace(loading_grid, qst_values),
        "coefficients": {
            "a0": safe_float(a0),
            "a1": safe_float(a1),
            "a2": safe_float(a2),
            "b0": safe_float(b0),
            "b1": safe_float(b1),
            "b2": safe_float(b2),
        },
        "fit_traces": fitted_traces,
        "table": [
            {
                "loading_mmol_g": safe_float(load),
                "qst_kj_mol": safe_float(qst),
            }
            for load, qst in zip(loading_grid, qst_values)
        ],
        "explanation": explanation_for("Virial"),
    }


def iast_calculation(payload: dict) -> dict:
    components = payload["components"]
    if len(components) < 2:
        raise ValueError("IAST 至少需要两个组分。")
    total_pressure_unit = payload.get("totalPressureUnit", "bar")
    total_pressures = convert_pressure(
        payload["totalPressures"],
        total_pressure_unit,
        "absolute",
        components[0].get("adsorbate"),
        components[0].get("temperature"),
    )
    gas_fractions = np.asarray(payload["gasFractions"], dtype=float)
    if not np.isclose(gas_fractions.sum(), 1.0, atol=1e-6):
        raise ValueError("气相组成需要归一化到 1。")
    if len(gas_fractions) != len(components):
        raise ValueError("气相组成数量与组分数量不一致。")
    model_isotherms = []
    pure_component_fits = []
    for component in components:
        model_label = component["model"]
        model_name = IAST_MODEL_MAP.get(model_label)
        if not model_name:
            raise ValueError(f"{model_label} 当前不支持 IAST。")
        temperature = float(component["temperature"])
        pressure = convert_pressure(
            component["pressure"],
            component["pressureUnit"],
            "absolute",
            component.get("adsorbate"),
            temperature,
        )
        loading = convert_loading(component["loading"], component["loadingUnit"])
        pressure, loading = clean_xy(pressure, loading)
        frame = pd.DataFrame({"pressure": pressure, "loading": loading})
        if model_name == "__interp__":
            iast_iso = InterpolatorIsotherm(frame, pressure_key="pressure", loading_key="loading", fill_value=float(np.max(loading)))
            curve_pressure = predict_curve_pressures(pressure, "absolute")
            curve_loading = np.interp(curve_pressure, pressure, loading)
            parameter_block = {"interpolation": "linear", "data_points": int(len(pressure))}
        else:
            iast_iso = PyIASTModelIsotherm(frame, pressure_key="pressure", loading_key="loading", model=model_name)
            curve_pressure = predict_curve_pressures(pressure, "absolute")
            curve_loading = iast_iso.loading(curve_pressure)
            parameter_block = {key: safe_float(value) for key, value in iast_iso.params.items()}
        model_isotherms.append(iast_iso)
        pure_component_fits.append(
            {
                "label": component["label"],
                "model": model_label,
                "parameters": parameter_block,
                "data": serialize_trace(pressure, loading),
                "fit": serialize_trace(curve_pressure, curve_loading),
                "explanation": explanation_for(model_label),
            }
        )
    result_rows = []
    component_traces = [[] for _ in components]
    selectivity = []
    for pressure_total in total_pressures:
        partial_pressures = (gas_fractions * pressure_total).tolist()
        loadings = np.asarray(pyiast_iast(partial_pressures, model_isotherms), dtype=float)
        total_loading = float(np.sum(loadings))
        adsorbed_fractions = loadings / total_loading if total_loading > 0 else np.zeros_like(loadings)
        row = {
            "total_pressure_bar": safe_float(pressure_total),
            "total_loading_mmol_g": safe_float(total_loading),
        }
        for idx, component in enumerate(components):
            row[f"{component['label']}_loading"] = safe_float(loadings[idx])
            row[f"{component['label']}_x"] = safe_float(adsorbed_fractions[idx])
            component_traces[idx].append(safe_float(loadings[idx]))
        if len(components) == 2 and gas_fractions[1] > 0 and adsorbed_fractions[1] > 0:
            s_value = (adsorbed_fractions[0] / adsorbed_fractions[1]) / (gas_fractions[0] / gas_fractions[1])
            row["selectivity"] = safe_float(s_value)
            selectivity.append(safe_float(s_value))
        result_rows.append(row)
    return {
        "pressure_unit": "bar",
        "loading_unit": "mmol/g",
        "components": pure_component_fits,
        "results": result_rows,
        "explanation": explanation_for("IAST"),
        "selectivity_curve": {
            "x": [safe_float(value) for value in total_pressures],
            "y": selectivity if selectivity else [],
        },
        "uptake_curves": [
            {
                "label": components[idx]["label"],
                "x": [safe_float(value) for value in total_pressures],
                "y": series,
            }
            for idx, series in enumerate(component_traces)
        ],
    }


def monotonic_rouquerol(pressure_rel, loading_mol_g, start, end) -> bool:
    subset = loading_mol_g[start:end] * (1 - pressure_rel[start:end])
    return bool(np.all(np.diff(subset) >= -1e-12))


def optimize_bet(relative_pressure, loading_mmol_g, cross_section):
    pressure = np.asarray(relative_pressure, dtype=float)
    loading_mol = np.asarray(loading_mmol_g, dtype=float) / 1000.0
    best = None
    fallback = None
    for start in range(0, len(pressure) - 4):
        for end in range(start + 5, len(pressure) + 1):
            p_limits = (pressure[start], pressure[end - 1])
            if not monotonic_rouquerol(pressure, loading_mol, start, end):
                continue
            try:
                area, c_const, n_monolayer, p_monolayer, slope, intercept, p_min, p_max, corr = area_BET_raw(
                    pressure.tolist(),
                    loading_mol.tolist(),
                    cross_section,
                    p_limits=p_limits,
                )
            except Exception:
                continue
            candidate = {
                "area_m2_g": safe_float(area),
                "c_const": safe_float(c_const),
                "n_monolayer_mol_g": safe_float(n_monolayer),
                "n_monolayer_mmol_g": safe_float(n_monolayer * 1000.0),
                "p_monolayer": safe_float(p_monolayer),
                "bet_slope": safe_float(slope),
                "bet_intercept": safe_float(intercept),
                "p_limits": [safe_float(pressure[start]), safe_float(pressure[end - 1])],
                "corr_coef": safe_float(corr),
                "r2": safe_float(corr**2),
                "points": end - start,
            }
            if candidate["c_const"] and candidate["c_const"] > 0:
                if fallback is None or candidate["r2"] > fallback["r2"]:
                    fallback = candidate
                if candidate["r2"] >= 0.999:
                    if best is None or (candidate["r2"], candidate["points"]) > (best["r2"], best["points"]):
                        best = candidate
    if best:
        best["auto_window_ok"] = True
        return best
    if fallback:
        fallback["auto_window_ok"] = False
        return fallback
    raise ValueError("未找到满足 BET 线性区域的有效取点范围。")


def peak_from_distribution(widths, distribution):
    widths_arr = np.asarray(widths, dtype=float)
    dist_arr = np.asarray(distribution, dtype=float)
    valid = np.isfinite(widths_arr) & np.isfinite(dist_arr)
    widths_arr = widths_arr[valid]
    dist_arr = dist_arr[valid]
    if len(widths_arr) == 0:
        return None
    index = int(np.argmax(dist_arr))
    return safe_float(widths_arr[index])


def bet_psd_calculation(payload: dict) -> dict:
    adsorbate = payload["adsorbate"]
    temperature = float(payload["temperature"])
    allowed_key = (normalize_text(adsorbate).replace(" ", ""), int(round(temperature)))
    normalized_allowed = {(normalize_text(name).replace(" ", ""), temp) for name, temp in BET_ALLOWED}
    if allowed_key not in normalized_allowed:
        raise ValueError("BET/孔径分布模块当前仅接受 77 K N2、87 K Ar、273 K CO2。")
    pressure_rel = convert_pressure(
        payload["pressure"],
        payload["pressureUnit"],
        "relative",
        adsorbate,
        temperature,
    )
    loading_mmol_g = convert_loading(payload["loading"], payload["loadingUnit"])
    pressure_rel, loading_mmol_g = clean_xy(pressure_rel, loading_mmol_g)
    adsorbate_props = find_adsorbate(adsorbate)
    cross_section = adsorbate_props.get("cross_section_nm2") if adsorbate_props else None
    if not cross_section:
        raise ValueError("无法获取 BET 所需的分子横截面积。")
    iso = PointIsotherm(
        pressure=pressure_rel,
        loading=loading_mmol_g,
        material="sample",
        adsorbate=adsorbate,
        temperature=temperature,
        temperature_unit="K",
        pressure_mode="relative",
        loading_basis="molar",
        loading_unit="mmol",
        material_basis="mass",
        material_unit="g",
        branch=payload.get("branch", "ads"),
    )
    bet_result = optimize_bet(pressure_rel, loading_mmol_g, cross_section)
    bet_y = pressure_rel / (loading_mmol_g / 1000.0 * (1 - pressure_rel))
    tplot_raw = t_plot(
        iso,
        thickness_model=payload.get("thicknessModel", "Harkins/Jura"),
        branch=payload.get("branch", "ads"),
    )
    tplot_sections = tplot_raw.get("results", [])
    positive_sections = [section for section in tplot_sections if safe_float(section.get("adsorbed_volume")) and safe_float(section.get("adsorbed_volume")) > 0]
    candidate_sections = positive_sections or tplot_sections
    best_section = max(candidate_sections, key=lambda section: abs(section.get("corr_coef", 0))) if candidate_sections else None
    average_pore_diameter_nm = None
    if best_section and best_section.get("area") and best_section.get("adsorbed_volume"):
        average_pore_diameter_nm = 4000 * best_section["adsorbed_volume"] / best_section["area"]
        if average_pore_diameter_nm <= 0:
            average_pore_diameter_nm = None
    warnings = []
    pore_family = payload.get("poreFamily", "micro")
    psd_mode = payload.get("psdMode", "classical")
    classical_model = payload.get("classicalModel", "HK")
    classical = None
    dft_result = None
    kernel_name = (payload.get("customKernelPath") or payload.get("dftKernel") or "DFT-N2-77K-carbon-slit").strip()
    if psd_mode == "classical":
        if pore_family == "micro":
            pore_geometry = payload.get("microGeometry", "slit")
            micro_model = classical_model
            if classical_model == "SF":
                pore_geometry = "cylinder"
                micro_model = "HK"
            classical = psd_microporous(
                iso,
                psd_model=micro_model,
                pore_geometry=pore_geometry,
                branch=payload.get("branch", "ads"),
                p_limits=(0.000001, 0.2),
            )
        else:
            classical = psd_mesoporous(
                iso,
                psd_model=classical_model,
                pore_geometry=payload.get("mesoGeometry", "cylinder"),
                meniscus_geometry=payload.get("meniscusGeometry") or None,
                branch=payload.get("mesoBranch", "des"),
            )
    else:
        if normalize_text(adsorbate) != normalize_text("nitrogen") or int(round(temperature)) != 77:
            raise ValueError("当前内置 NLDFT 仅支持 77 K N2。Ar 87 K 与 CO2 273 K 请使用经典模型或提供自定义 kernel 文件路径。")
        if kernel_name in KERNELS or Path(kernel_name).exists():
            try:
                dft_result = psd_dft(
                    iso,
                    kernel=kernel_name,
                    branch=payload.get("branch", "ads"),
                )
            except Exception as exc:
                warnings.append(f"NLDFT 计算失败：{exc}")
        else:
            warnings.append("当前运行环境中没有所选 NLDFT 内核；可填写自定义 kernel 文件路径。")
    if not bet_result["auto_window_ok"]:
        warnings.append("自动取点没有达到 R² ≥ 0.999 与正 C 常数的理想区间，已返回最优可用窗口，请手动复核。")
    response = {
        "warnings": warnings,
        "psd_mode": psd_mode,
        "bet": {
            **bet_result,
            "pressure_unit": "p/p0",
            "loading_unit": "mmol/g",
            "plot": serialize_trace(pressure_rel, bet_y),
        },
        "tplot": {
            "thickness_curve": [safe_float(value) for value in tplot_raw.get("t_curve", [])],
            "sections": [
                {
                    "area_m2_g": safe_float(section.get("area")),
                    "adsorbed_volume_cm3_g": safe_float(section.get("adsorbed_volume")),
                    "corr_coef": safe_float(section.get("corr_coef")),
                    "slope": safe_float(section.get("slope")),
                    "intercept": safe_float(section.get("intercept")),
                }
                for section in tplot_sections
            ],
            "selected_average_pore_diameter_nm": safe_float(average_pore_diameter_nm),
        },
        "explanation": explanation_for("BET-PSD"),
    }
    if classical:
        response["classical_psd"] = {
            "model": classical_model,
            "pore_widths_nm": [safe_float(value) for value in classical.get("pore_widths", [])],
            "distribution": [safe_float(value) for value in classical.get("pore_distribution", [])],
            "peak_pore_width_nm": peak_from_distribution(classical.get("pore_widths", []), classical.get("pore_distribution", [])),
        }
        if "pore_volumes" in classical:
            response["classical_psd"]["pore_volumes_cm3_g"] = [safe_float(value) for value in classical.get("pore_volumes", [])]
    if dft_result:
        response["dft_psd"] = {
            "kernel": kernel_name,
            "pore_widths_nm": [safe_float(value) for value in dft_result.get("pore_widths", [])],
            "distribution": [safe_float(value) for value in dft_result.get("pore_distribution", [])],
            "peak_pore_width_nm": peak_from_distribution(dft_result.get("pore_widths", []), dft_result.get("pore_distribution", [])),
        }
    return response


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/MANUAL.md")
def manual_markdown():
    return send_file(BASE_DIR / "MANUAL.md", mimetype="text/markdown; charset=utf-8")


@app.get("/api/adsorbates")
def api_adsorbates():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"items": ADSORBATE_LIBRARY})
    normalized = normalize_text(query)
    items = []
    for item in ADSORBATE_LIBRARY:
        haystack = [item["zh"], item["en"], item["formula"], item["key"]]
        haystack.extend(item["aliases"])
        if any(normalized in normalize_text(token) for token in haystack if token):
            items.append(item)
    return jsonify({"items": items})


@app.post("/api/parse-file")
def api_parse_file():
    if "file" not in request.files:
        return jsonify({"error": "请先选择文件。"}), 400
    try:
        sheet_name = request.form.get("sheet") or None
        return jsonify(parse_uploaded_table(request.files["file"], requested_sheet=sheet_name))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/isotherm-fit")
def api_isotherm_fit():
    try:
        return jsonify(fit_isotherm(request.get_json(force=True)))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/qst")
def api_qst():
    payload = request.get_json(force=True)
    try:
        method = payload.get("method", "Clausius-Clapeyron")
        datasets = payload["datasets"]
        if len(datasets) < 2:
            raise ValueError("Qst 至少需要两组不同温度的等温线。")
        if method == "Virial":
            return jsonify(qst_virial(datasets))
        return jsonify(qst_clausius_clapeyron(datasets))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/iast")
def api_iast():
    try:
        return jsonify(iast_calculation(request.get_json(force=True)))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/bet-psd")
def api_bet_psd():
    try:
        return jsonify(bet_psd_calculation(request.get_json(force=True)))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


if __name__ == "__main__":
    host = os.environ.get("MOF_SORPTION_HOST", "127.0.0.1")
    port = int(os.environ.get("MOF_SORPTION_PORT", "5055"))
    debug = os.environ.get("MOF_SORPTION_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    app.run(debug=debug, host=host, port=port)
