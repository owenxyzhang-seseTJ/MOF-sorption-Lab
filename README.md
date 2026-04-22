# MOF Sorption Lab

本地网页程序，包含：

- 吸附质信息检索
- 等温线拟合
- Qst 计算
- IAST 选择性
- BET / t-plot / 孔径分布

## 运行

最省事的方式：

在 Finder 中双击 `启动 MOF Sorption Lab.command`

它会自动：

- 启动本地服务
- 打开 `http://127.0.0.1:5055`

现在也可以直接双击 `MOF Sorption Lab.app`

这是一个 macOS 应用封装，放在项目根目录中即可使用。

Windows 下可以双击 `Start MOF Sorption Lab.bat`

它会自动：

- 调用 `launcher.py`
- 如有需要自动创建 `.venv`
- 安装 `requirements.txt` 中的依赖
- 启动本地服务并打开 `http://127.0.0.1:5055`

如果要为 Windows 用户制作真正的安装包：

- 桌面版入口：`desktop_app.py`
- 打包脚本：`windows/build_windows.ps1`
- 安装脚本：`windows/installer.iss`
- GitHub Actions：`.github/workflows/build-windows-installer.yml`

在 Windows 上执行后会产出：

- 便携版：`dist\MOF Sorption Lab\`
- 安装包：`dist-installer\MOF-Sorption-Lab-Setup-1.2.exe`

你也可以直接双击根目录下的 `index.html`，如果服务已经在运行，它会自动跳转到网页。

跨平台也可以直接运行：

```bash
python launcher.py
```

Windows 也可以：

```text
py -3 launcher.py
```

## 说明

- 当前 `NLDFT` 使用运行环境内置的 `DFT-N2-77K-carbon-slit` 内核。
- 其余经典方法使用 `pyGAPS` 的 `BET / t-plot / HK / SF / BJH / DH` 能力。
- 文件导入支持 `csv / dat / txt / xlsx / xls`。
- 新增 `logo / favicon / Windows .ico / macOS .icns` 资产。
- 当前仓库中的 `.vendor` 是本机运行缓存；跨平台正式使用时优先走 `launcher.py + requirements.txt + .venv` 方案。
- 对纯 Windows 用户，更推荐走 `desktop_app.py + PyInstaller + Inno Setup` 的桌面安装包链路。
