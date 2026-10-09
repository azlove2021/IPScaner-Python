# -*- mode: python ; coding: utf-8 -*-
"""IPScaner 绿色版 → 单文件 exe 打包 spec。

与 src/slim.spec 的差异：
  1. 入口 main_opt.py 与 7 个业务模块（core/dialogs/gui/mainform/menu_def/
     popup/theme）放在同目录，业务模块是 **sourceless .pyc**（绿色版 PYZ 里
     提取出来的权威字节码，Python 3.10）——PyInstaller 会按「无源码模块」收录。
  2. optimize=0：绿色版就是 optimize=0（保留了 docstring），保持一致。
  3. 沿用 slim.spec 的裁剪清单与 tcl 冗余数据剔除逻辑，控制体积。
"""
import os

# 裁剪清单：在 src/slim.spec 的基础上**回退了 decimal / _decimal**。
# 原因（实测踩坑）：mainform.scale_img 里有延迟 import fractions，
# 而 fractions → decimal → _decimal。一旦把 decimal 排掉，
# 冻结版一启动就 ModuleNotFoundError: No module named 'decimal'。
# 绿色版 PYZ 里确实带 decimal / _pydecimal / fractions / numbers / statistics，
# _internal 里也带 _decimal.pyd —— 说明绿色版用的清单没排 decimal。
# ⚠️ 2026-10-10 教训：**别把 xml / pyexpat 排掉**。
#    需求36 的「导入表格」用 xml.etree.ElementTree 读 .xlsx ——
#    源码态一切正常（标准库齐全），一进冻结包就
#    `ModuleNotFoundError: No module named 'xml'`，而这条异常被
#    `_import_table` 的 `except` 吞进 messagebox，光看日志只会以为"导入没生效"。
#    本质原因同上一条 decimal：**函数体内延迟 import 的标准库，静态分析扫不到**。
#    excludes 列表必须逐个对照修复层的实际 import 再定稿（已扫过：只剩 xml 中招）。
EXCLUDES = [
    "ssl", "_ssl", "email", "http", "unittest", "pydoc", "doctest",
    "test", "distutils", "lib2to3", "multiprocessing", "hashlib", "_hashlib",
    "bz2", "_bz2", "lzma", "_lzma", "numpy", "pandas",
    "matplotlib", "PIL", "setuptools", "pip", "asyncio", "curses", "sqlite3",
]

# fractions 是在函数体里延迟导入的，静态分析容易漏，显式声明兜底。
HIDDEN = ["decimal", "_pydecimal", "contextvars", "fractions", "numbers", "statistics"]

DROP_PREFIXES = ("_tcl_data/tzdata", "_tcl_data/msgs", "_tcl_data/opt0.4")


def drop_tcl_fat(datas):
    kept, dropped, saved = [], [], 0
    for entry in datas:
        dest = entry[0].replace("\\", "/")
        src = entry[1]
        if any(dest.startswith(p) for p in DROP_PREFIXES):
            try:
                saved += os.path.getsize(src)
            except OSError:
                pass
            dropped.append(dest)
        else:
            kept.append(entry)
    print("[spec] 剔除 tcl 冗余数据 %d 项，省 %.2f MB" % (len(dropped), saved / 1024 / 1024))
    return kept


a = Analysis(
    ["main_opt.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=[("assets", "assets")],
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    # 唯一钩子：rthook_ipscaner_uifix.py（由 gen_hook.py 从 ui_fix.py 生成，
    # SHALL 带源码指纹；跑 `gen_hook.py --check` 可验陈旧）。
    # 它包含：字体/缩放统一层 + 网卡名规范化/截断 + 系统命令启动器 + 端口扫描并发。
    #
    # ⚠️ 2026-10-08：端口扫描那条**不再是「路由到 scan_ports_fast」**。
    #   旧做法把调用方的 concurrency=1000 当成 fast 版的 batch，而 Windows 的
    #   select.select 最多监视 512 个 FD → 每批抛 ValueError 被吞 → 进度 100%
    #   但结果恒为空。现在改成只把 _scan_ports_thread 的 workers 提到 1200。
    #
    # ⚠️ 不要同时挂 rthook_ipscaner_fixes.py：那个旧钩子会**先**改写
    # dialogs.FORMS 的设计尺寸与 groupbox 高度，而新钩子是「按 FORMS 设计值
    # 统一乘 SCALE」，两者叠加会导致尺寸被放大两次。
    runtime_hooks=["rthook_ipscaner_uifix.py"],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
a.datas = drop_tcl_fat(a.datas)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="IPScaner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join("assets", "app_icon.ico"),
)
