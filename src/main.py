# -*- coding: utf-8 -*-
"""IPScaner Python 复刻版 —— 基准版入口（PyInstaller base 用）

与 main_opt.py 的唯一差别：这里**故意**在顶层 import multiprocessing，
用来复现「一句话多带 7.4 MB」的体积对比（ssl / libcrypto-3.dll / libssl-3.dll）。
build.py 构建 base 档时不会把 multiprocessing 列进 --exclude-module。

要出正式产物请用 main_opt.py。
"""
import multiprocessing

from gui import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
