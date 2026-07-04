# 🧪 MOF Sorption Lab

<p align="center">
  <img src="static/mof-sorption-lab-icon-256.png" alt="MOF Sorption Lab" width="100" style="border-radius:20px">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/platform-macOS%20|%20Windows-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/rdkit--free-functional-green.svg" alt="RDKit-free">
  <img src="https://img.shields.io/badge/flask-backend-orange.svg" alt="Flask">
</p>

<p align="center">
  <b>面向多孔材料（MOFs / COFs / 沸石 / 多孔碳）的本地吸附数据处理与热力学分析工作台</b>
</p>

<p align="center">
  <i>A local web-based toolkit for sorption data analysis — isotherm fitting, Qst, IAST selectivity, and pore structure characterization.</i>
</p>

---

## ✨ 核心功能

| 模块 | 说明 |
|------|------|
| 🧬 **吸附质检索** | 内置 CoolProp 数据库，快速查询吸附质物性参数 |
| 📈 **等温线拟合** | 8 种模型：Langmuir、Freundlich、Henry、Toth、Dual-site Langmuir、Quadratic/Temkin、BET、PCHIP 插值 |
| 🔥 **Qst 等量吸附热** | Clausius-Clapeyron 法与 Virial 法双算法 |
| 🎯 **IAST 选择性** | 混合气竞争吸附预测，支持任意气相组成和总压组合 |
| 📐 **BET 比表面积** | 自动 R² 优化选点，C 常数检验 |
| 📏 **t-plot 分析** | 微孔体积与外表面贡献区分 |
| 🕳️ **孔径分布** | 微孔（HK / SF / RY / RY-CY / HK-CY）、介孔（BJH / DH）、NLDFT（77 K N₂ kernel） |

### 数据导入亮点

- 支持 **CSV / DAT / TXT / XLSX / XLS** 多种格式
- 自动识别复杂实验文件中的压力列、吸附列、脱附列
- 智能列名匹配与单位推测
- 导入前可交互确认和调整

---

## 🚀 快速开始

### macOS

双击 `启动 MOF Sorption Lab.command` 或：

```bash
python launcher.py
```

### Windows

双击 `Start MOF Sorption Lab.bat` 或：

```cmd
py -3 launcher.py
```

> 启动后自动打开 `http://127.0.0.1:5055`，也支持直接在 Finder 中双击 `MOF Sorption Lab.app`（macOS）

---

## 📦 支持的模型与方法

### 等温线拟合

| 模型 | 适用场景 |
|------|----------|
| **Langmuir** | 单位点单层吸附，微孔基线拟合 |
| **Freundlich** | 非均匀表面的经验描述 |
| **Henry** | 极低压线性区，亲和性比较 |
| **Toth** | 非均匀表面修正，宽压区覆盖 |
| **Dual-site Langmuir** | 强弱两类位点共存 |
| **Quadratic / Temkin** | 中等复杂度的半机理拟合 |
| **BET** | 比表面积和单层容量 |
| **PCHIP** | 插值型通用拟合，适合 S 型/台阶型曲线 |

### 孔径分析

| 孔区 | 方法 |
|------|------|
| 微孔 | HK、SF、RY、RY-CY、HK-CY |
| 介孔/大孔 | BJH、DH |
| 全范围 | NLDFT（内置 77 K N₂ carbon-slit kernel） |

### 当前支持的探针-温度组合

- 77 K N₂
- 87 K Ar
- 273 K CO₂

---

## 📁 项目结构

```
MOF-sorption-Lab/
├── app.py                          # Flask 后端主程序
├── launcher.py                     # 环境自举 + 启动入口
├── desktop_app.py                  # 桌面封装入口
├── index.html                      # 浏览器自动跳转页
├── requirements.txt                # 核心依赖
├── requirements-desktop.txt        # 桌面版额外依赖
├── 启动 MOF Sorption Lab.command    # macOS 一键启动
├── Start MOF Sorption Lab.bat      # Windows 一键启动
├── MANUAL.md                       # 📖 完整使用说明书
├── static/                         # 前端静态资源
│   ├── app.js                      # 前端逻辑
│   ├── styles.css                  # 样式
│   └── *.png / *.ico / *.svg       # 图标资源
├── templates/
│   └── index.html                  # Web 界面模板
├── windows/                        # Windows 打包
│   ├── build_windows.ps1           # PyInstaller 构建
│   ├── installer.iss               # Inno Setup 安装脚本
│   └── MOFSorptionLab.spec         # PyInstaller spec
└── .github/workflows/              # CI/CD
    └── Build Windows Installer.yml # 自动构建 Windows 安装包
```

---

## 🛠 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.9+ / Flask |
| 吸附分析 | [pyGAPS](https://github.com/pauliacomi/pyGAPS)（BET / t-plot / PSD） |
| IAST | [pyIAST](https://github.com/CorySimon/pyIAST) |
| 数值计算 | SciPy / NumPy / pandas |
| 物性查询 | [CoolProp](http://www.coolprop.org/) |
| 前端 | HTML5 / CSS3 / Chart.js |
| 桌面封装 | PyInstaller + pywebview / Inno Setup |

---

## 📖 详细文档

完整的使用说明书、模型选择指南和结果解读请见 **[MANUAL.md](./MANUAL.md)**，涵盖：

- 每个模型的公式、物理图像和适用场景
- Qst 两种算法的原理与差异
- IAST 的铺展压力推导过程
- BET 自动选点逻辑
- 孔径分布模型选择策略
- 常见导入错误与解决

---

## 👨‍🔬 作者

Designed by **Xiaoyu Zhang** at Tongji University, shaped together with Codex.

📧 owenxyzhang@gmail.com
