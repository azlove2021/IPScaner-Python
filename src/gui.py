# -*- coding: utf-8 -*-
"""程序入口 —— 启动主窗体并完成原版的开机初始化。

原版行为（Program.cs + FormMain_Load）：
  1. 启动即以 runas 自提权（复刻版改为按需，避免每次弹 UAC）
  2. 读取 IPScaner.exe.config，没有就用默认值
  3. 枚举网卡，自动选中与「当前 IP」同网段的那块，并把 IP 段前三段填入输入框

界面细节见 mainform.py（单 Canvas 手绘，像素级对齐 FormMain）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class Config:
    """等价于原版 ConfigInfo（XML 序列化），字段名对齐源码。"""

    def __init__(self):
        self.version = "1.0"
        self.query_hostname = False        # QueryHostNameEnabled
        self.ping_timeout = 500            # PingTimeout
        self.ping_count = 4                # PingCount
        self.port_instead_ping = False     # PortInsteadPingEnabled
        self.pre_ports = "80,135,445,500"  # PrePortArray
        self.port_timeout = 50             # PortTimeout
        self.double_click_time = 200       # DoubleClickTime
        self.font_size = 9                 # BtnFontSize
        self.menu_auto_open = False        # MenuAutoOpen
        self.default_color = "#87CEEB"     # DefaultColorArgb
        self.ok_color = "#32CD32"          # NetworkOKColorArgb
        self.ng_color = "#CD5C5C"          # NetworkNGColorArgb
        self.memo_color = "#0000FF"        # MemoColorArgb


APP_VERSION = "1.25.0"


def init_state(app):
    """枚举网卡 + 填 IP 段，对应原版 FormMain_Load。

    环境变量 IPSCANER_IP / IPSCANER_ADAPTER 可强制覆盖。与原版截图做逐像素
    比对时必须让 IP 段与网卡名一致，否则标题、状态栏 statusIP、以及被高亮成
    橙色的那个色块，文字内容全都不同，差异率会虚高。
    """
    import core
    import theme as T

    app.version = APP_VERSION
    try:
        local = core.get_local_ip()
        adapters = core.get_adapters()
    except Exception:  # noqa: BLE001
        local, adapters = "", []

    forced_ip = os.environ.get("IPSCANER_IP", "").strip()
    if forced_ip:
        local = forced_ip
    forced_adapter = os.environ.get("IPSCANER_ADAPTER", "").strip()
    if forced_adapter:
        app.adapter_text = forced_adapter

    app.local_ip = local

    chosen = None
    for a in adapters:
        if a.ip == local:
            chosen = a
            break
    if chosen is None and adapters:
        chosen = next((a for a in adapters if a.ip), adapters[0])

    if chosen is not None and not forced_adapter:
        app.adapter_text = chosen.name
    if local and local.count(".") == 3:
        app.ip_part = local.rsplit(".", 1)[0]
        app.caret_pos = len(app.ip_part)

    # 重建 base 层：色块前景色依赖 local_ip（本机 IP 那格要变橙框）
    app.build_base()
    app.refresh_fx()

    # statusIP = "活动IP:" + 所有 Status==1 的网卡 IP（原版 262-263 行）
    forced_active = os.environ.get("IPSCANER_ACTIVE_IPS", "").strip()
    if forced_active:
        # 必须 strip 再拼：原版是 string.Join("; ", ips)，若这里保留分隔后的前导空格
        # 会变成 ";  " 双空格，statusIP 整串宽度凭空多 7px（踩过）。
        active = [s.strip() for s in forced_active.split(";") if s.strip()]
    else:
        active = [a.ip for a in adapters if a.ip]
    app.set_status("ip", "活动IP:" + "; ".join(active))
    app.set_status("host", "已启用主机名查询" if getattr(app.cfg, "query_hostname", False)
                   else "已禁用主机名查询")
    # 原版每 10 秒轮换一条 Tip，比对时必须钉死成截图那一帧的那条
    forced_tip = os.environ.get("IPSCANER_TIP", "").strip()
    idx = os.environ.get("IPSCANER_TIP_INDEX", "").strip()
    if not forced_tip and idx.isdigit():
        # 用序号而不是原文：命令行传中文在 PowerShell/ANSI 下容易被转码毁掉
        n = int(idx)
        if 0 <= n < len(T.TIP_LIST):
            forced_tip = T.TIP_LIST[n]
    if forced_tip:
        app.set_status("friendly", forced_tip)
    return app


def enable_dpi_awareness():
    """必须在创建任何窗口之前调用。

    否则 Windows 会把整个窗口位图放大（模糊、且拿不到真实 DPI），
    原版 WinForms 是 DPI 感知的，这里要对齐它的行为。
    """
    try:
        import ctypes

        try:                                     # Win8.1+ 推荐入口
            ctypes.windll.shcore.SetProcessDpiAwareness(1)   # SYSTEM_DPI_AWARE
        except Exception:  # noqa: BLE001
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass


def freeze_support():
    """PyInstaller onefile 下必须调用，否则打出的 exe 会无限重启自身。

    ⚠️ 不能在模块顶层 `import multiprocessing` —— 它会连带拉进
    ssl / libcrypto-3.dll / libssl-3.dll 约 7.4 MB，裁剪版（build/slim.spec）
    已经把 multiprocessing 列进 `--exclude-module`；顶层导入会让裁剪版
    **一启动就 ImportError**。所以这里必须延迟导入且容错。
    """
    try:
        import multiprocessing
    except Exception:  # noqa: BLE001
        return
    try:
        multiprocessing.freeze_support()
    except Exception:  # noqa: BLE001
        pass


def main():
    freeze_support()
    enable_dpi_awareness()

    # --scale N：强制缩放比（与原版截图做 1:1 比对时用；不传则走真实 DPI）
    for i, a in enumerate(sys.argv):
        if a == "--scale" and i + 1 < len(sys.argv):
            os.environ["IPSCANER_SCALE"] = sys.argv[i + 1]
        elif a.startswith("--scale="):
            os.environ["IPSCANER_SCALE"] = a.split("=", 1)[1]
        elif a == "--ip" and i + 1 < len(sys.argv):
            os.environ["IPSCANER_IP"] = sys.argv[i + 1]
        elif a.startswith("--ip="):
            os.environ["IPSCANER_IP"] = a.split("=", 1)[1]
        elif a == "--adapter" and i + 1 < len(sys.argv):
            os.environ["IPSCANER_ADAPTER"] = sys.argv[i + 1]
        elif a.startswith("--adapter="):
            os.environ["IPSCANER_ADAPTER"] = a.split("=", 1)[1]
        elif a == "--active-ips" and i + 1 < len(sys.argv):
            os.environ["IPSCANER_ACTIVE_IPS"] = sys.argv[i + 1]
        elif a.startswith("--active-ips="):
            os.environ["IPSCANER_ACTIVE_IPS"] = a.split("=", 1)[1]
        elif a == "--tip" and i + 1 < len(sys.argv):
            os.environ["IPSCANER_TIP"] = sys.argv[i + 1]
        elif a.startswith("--tip="):
            os.environ["IPSCANER_TIP"] = a.split("=", 1)[1]
        elif a == "--tip-index" and i + 1 < len(sys.argv):
            os.environ["IPSCANER_TIP_INDEX"] = sys.argv[i + 1]
        elif a.startswith("--tip-index="):
            os.environ["IPSCANER_TIP_INDEX"] = a.split("=", 1)[1]
        elif a in ("--freeze", "--freeze=1"):
            os.environ["IPSCANER_FREEZE"] = "1"

    import tkinter as tk

    import mainform

    root = tk.Tk()
    app = mainform.MainForm(root, Config())
    init_state(app)
    root.mainloop()


if __name__ == "__main__":
    main()
