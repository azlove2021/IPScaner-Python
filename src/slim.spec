# -*- mode: python ; coding: utf-8 -*-
"""
IPScaner Python 复刻版 —— 极限裁剪 spec

在标准 PyInstaller 分析流程之后，过滤掉 tcl/tk 运行时用不到的数据：
  · _tcl_data/tzdata    2.2 MB  时区数据库，只有 tcl 的 `clock` 命令按名字取时区才用
  · _tcl_data/msgs      0.39 MB Tcl 本地化错误消息，界面全在 Python/tk 层
  · _tcl_data/opt0.4    仅 tcl 交互式 shell 的选项解析
编码表全部保留（cp936 是中文 Windows 的关键，删了会乱码），只做这三项保守裁剪。
"""
import os

EXCLUDES = [
    "ssl", "_ssl", "pyexpat", "xml", "email", "http", "unittest", "pydoc", "doctest",
    "test", "distutils", "lib2to3", "multiprocessing", "hashlib", "_hashlib",
    "decimal", "_decimal", "bz2", "_bz2", "lzma", "_lzma", "numpy", "pandas",
    "matplotlib", "PIL", "setuptools", "pip", "asyncio", "curses", "sqlite3",
]

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
    print(f"[spec] 剔除 tcl 冗余数据 {len(dropped)} 项，省 {saved/1024/1024:.2f} MB")
    return kept


# 资源必须打包：菜单图标 / 按钮图标 / 关于页 logo / 窗口图标。
# 构建时 build.py 已把 src/assets 拷成工作区里的 assets/，这里的相对路径
# 是按 spec 所在目录（SPECPATH）解析的，所以直接写 "assets"。
a = Analysis(
    ["main_opt.py"],
    pathex=[],
    binaries=[],
    datas=[("assets", "assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,
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
)
