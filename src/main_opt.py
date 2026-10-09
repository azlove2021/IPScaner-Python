# -*- coding: utf-8 -*-
"""IPScaner Python 复刻版 —— 裁剪版入口（PyInstaller slim/opt 用）

只做一件事：调 gui.main()。

为什么这么薄：
  · 真正的初始化（DPI 感知、命令行参数、主窗体、mainloop）全在 gui.main() 里，
    入口只负责「被 PyInstaller 当脚本分析」。
  · multiprocessing 的 freeze_support 由 gui.freeze_support() **延迟导入**——
    它会连带拉进 ssl/libcrypto/libssl 约 7.4 MB，而 build/slim.spec 已经把
    multiprocessing 列入 --exclude-module；顶层 import 会让 exe 一启动就崩。
"""
from gui import main

if __name__ == "__main__":
    main()
