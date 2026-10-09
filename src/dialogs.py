# -*- coding: utf-8 -*-
"""子窗体 —— 按反编译源码的 InitializeComponent 还原布局、标题、尺寸、文案。

窗体清单（标题 / ClientSize 均取自源码）：
  关于            关于               514x396   FixedDialog
  选项配置         选项配置            268x352   FixedSingle
  一键设置IP       一键设置IP          576x631   FixedSingle
  自定义IP扫描地址 自定义IP扫描地址     713x547   Sizable
  IP地址计算器     IP地址计算器         452x331   FixedSingle
  端口扫描         端口扫描            670x606   Sizable
  系统端口查看工具 系统端口查看工具     1358x807  Sizable
  WiFi密码查看器   WiFi密码查看器       545x422   Sizable
  备注信息管理     备注信息管理         592x395   Sizable
  IP段扫描结果     IP段扫描结果         720x420   FixedSingle

主窗体是 Canvas 手绘的像素级复刻；子窗体用原生 tk 控件 + 源码里的绝对坐标，
保证标题、尺寸、控件位置、文案、配色一致。
"""
import os
import re
import subprocess
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

import core
import theme as T

A = T.assets_dir()
# 子窗体清单（供外部查询/测试）
FORMS = {
    "about": ("关于", 514, 396, False),
    "config": ("选项配置", 268, 352, False),
    "localip": ("一键设置IP", 576, 631, False),
    "ipsegment": ("自定义IP扫描地址", 713, 547, True),
    "addresscalc": ("IP地址计算器", 452, 331, False),
    "portscan": ("端口扫描", 670, 606, True),
    "processport": ("系统端口查看工具", 1358, 807, True),
    "wifi": ("WiFi密码查看器", 545, 422, True),
    "memomanager": ("备注信息管理", 592, 395, True),
    "ipdetail": ("IP段扫描结果", 720, 420, False),
}

_OPEN = {}


# --------------------------------------------------------------------- 基础件
def _font(size=-12, bold=False, family="宋体"):
    return (family, size, "bold") if bold else (family, size)


def mkform(main, key, resizable=None, geometry=None):
    """创建一个子窗体，若已存在则前置。geometry 可覆盖默认尺寸（用于按需放大）。"""
    title, w, h, res = FORMS[key]
    if key in _OPEN and _OPEN[key].winfo_exists():
        t = _OPEN[key]
        t.deiconify()
        t.lift()
        t.focus_force()
        return t
    top = tk.Toplevel(main.root)
    top.title(title)
    if geometry:
        top.geometry(geometry)
    else:
        top.geometry(f"{w}x{h}")
    top.configure(bg=T.C_FACE)
    top.resizable(True if (res if resizable is None else resizable) else False,
                  True if (res if resizable is None else resizable) else False)
    _OPEN[key] = top
    return top


def lbl(top, x, y, text, w=None, h=14, anchor="w", font=None, fg=T.C_BLACK):
    kw = {"text": text, "bg": T.C_FACE, "fg": fg, "anchor": anchor,
          "font": font or _font(), "justify": "left"}
    if w:
        kw.update(width=w, height=h)
    else:
        kw["height"] = h
    L = tk.Label(top, **kw)
    if w:
        L.place(x=x, y=y, width=w, height=h)
    else:
        L.place(x=x, y=y)
    return L


def entry(top, x, y, w, h, value="", readonly=False, multiline=False, font=None):
    if multiline:
        e = tk.Text(top, bg=T.C_WHITE, relief="solid", bd=1, font=font or _font(),
                    wrap="word", undo=True)
        e.place(x=x, y=y, width=w, height=h)
        e.insert("1.0", value)
        if readonly:
            e.configure(state="disabled")
        return e
    e = tk.Entry(top, bg=T.C_WHITE, relief="solid", bd=1, font=font or _font(),
                 insertbackground=T.C_BLACK)
    e.place(x=x, y=y, width=w, height=h)
    if value:
        e.insert(0, value)
    if readonly:
        e.configure(state="readonly", readonlybackground=T.C_WHITE)
    return e


def btn(top, x, y, w, h, text, cmd=None, font=None, default=False):
    b = tk.Button(top, text=text, font=font or _font(), bg="#E1E1E1", fg=T.C_BLACK,
                  activebackground="#D2D2D2", relief="raised", bd=1,
                  highlightbackground="#0078D4" if default else "#E1E1E1",
                  highlightthickness=1 if default else 0,
                  command=cmd or (lambda: None))
    b.place(x=x, y=y, width=w, height=h)
    return b


def combo(top, x, y, w, h, values, current=0, readonly=True):
    c = ttk.Combobox(top, values=values, state="readonly" if readonly else "normal",
                     font=_font())
    c.place(x=x, y=y, width=w, height=h)
    if values:
        c.current(min(current, len(values) - 1))
    return c


def grid(top, x, y, w, h, columns, widths=None):
    """DataGridView 的等价物（ttk.Treeview），带 WinForms 风格表头。"""
    style = ttk.Style(top)
    try:
        style.theme_use("clam")
    except Exception:  # noqa: BLE001
        pass
    style.configure("Wb.Treeview", background=T.C_WHITE, fieldbackground=T.C_WHITE,
                    foreground=T.C_BLACK, rowheight=20, font=_font(), borderwidth=1)
    style.configure("Wb.Treeview.Heading", background="#F0F0F0", foreground=T.C_BLACK,
                    font=_font(), relief="raised")
    style.map("Wb.Treeview", background=[("selected", T.C_MENU_HILIGHT)],
              foreground=[("selected", T.C_WHITE)])
    tv = ttk.Treeview(top, columns=columns, show="headings", style="Wb.Treeview")
    for i, c in enumerate(columns):
        tv.heading(c, text=c)
        tv.column(c, width=(widths[i] if widths else max(60, w // max(1, len(columns)))),
                  anchor="w", stretch=False)
    tv.place(x=x, y=y, width=w, height=h)
    return tv


def groupbox(top, x, y, w, h, caption):
    """GroupBox 等价物：1px 蚀刻框 + 左上角标题（标题处框线断开）。"""
    cv = tk.Canvas(top, width=w, height=h, bg=T.C_FACE, highlightthickness=0, bd=0)
    cv.place(x=x, y=y)
    top_y = 7
    f = tkfont.Font(family="宋体", size=-12)
    tw = f.measure(caption) if caption else 0
    cv.create_line(0, top_y, 3, top_y, fill=T.C_GROUP_FRAME)
    if caption:
        cv.create_line(3 + tw + 2, top_y, w - 1, top_y, fill=T.C_GROUP_FRAME)
        cv.create_text(3, top_y, text=caption, font=f, fill=T.C_BLACK, anchor="w")
    else:
        cv.create_line(3, top_y, w - 1, top_y, fill=T.C_GROUP_FRAME)
    cv.create_line(0, top_y, 0, h - 1, fill=T.C_GROUP_FRAME)
    cv.create_line(w - 1, top_y, w - 1, h - 1, fill=T.C_GROUP_FRAME)
    cv.create_line(0, h - 1, w - 1, h - 1, fill=T.C_GROUP_FRAME)
    return cv


ASSEMBLY = {
    "title": "IPScaner",
    "product": "局域网IP扫描工具",
    "company": "3672801@qq.com",
    "copyright": "Copyright © chenhuxiang 2019-2025",
    "version": "1.25.0.0",
    "description": "局域网IP扫描工具",
}


# --------------------------------------------------------------------- 关于
def f_about(main):
    top = mkform(main, "about")
    img = None
    p = os.path.join(A, "logoPictureBox.png")
    if os.path.exists(p):
        img = tk.PhotoImage(file=p)
        top._logo = img
    if img is not None:
        c = tk.Canvas(top, width=157, height=372, bg=T.C_FACE, highlightthickness=0)
        c.place(x=12, y=12)
        c.create_image(78, 8, image=img, anchor="n")

    x0 = 180
    lbl(top, x0, 14, "产品名称", 324, 15)
    lbl(top, x0, 14, ASSEMBLY["product"], 324, 15, anchor="e")
    lbl(top, x0, 34, "版本", 324, 15)
    lbl(top, x0, 34, ASSEMBLY["version"], 324, 15, anchor="e")
    lbl(top, x0, 54, "版权", 324, 15)
    lbl(top, x0, 54, ASSEMBLY["copyright"], 324, 15, anchor="e")
    lbl(top, x0, 74, "公司名称", 324, 15)
    lbl(top, x0, 74, ASSEMBLY["company"], 324, 15, anchor="e")
    txt = entry(top, x0, 96, 324, 254, "", readonly=True, multiline=True)
    txt.configure(state="normal")
    txt.insert("1.0", _about_text(main))
    txt.configure(state="disabled")
    btn(top, 430, 360, 75, 24, "确定(&O)", top.destroy, default=True)
    return top


def _about_text(main):
    """说明区文本 = 程序集信息 + 内置 readme 摘要。"""
    ver = getattr(main, "version", "1.25.0")
    return (
        f"{ASSEMBLY['product']}  Ver {ver}\r\n"
        f"{ASSEMBLY['copyright']}\r\n"
        f"联系方式：{ASSEMBLY['company']}\r\n"
        "\r\n"
        "局域网内快速搜索IP是否在线的绿色小工具，集成多个网络调试工具：\r\n"
        "IP段扫描、端口扫描、windows命令、IP地址计算器、系统端口占用查看等。\r\n"
        "\r\n"
        "主要功能：\r\n"
        "1. 主菜单IP段扫描：Ping检查通讯状态，Ping失败时可TCP端口侦测，\r\n"
        "   支持自定义状态外观、查询主机名与MAC，并发送常用网络调试命令。\r\n"
        "2. 修改本地IP：支持单网卡多IP、多网卡，保留历史记录，支持改DNS。\r\n"
        "3. IP批量扫描：单网段/连续IP范围/掩码位三种方式，支持定时自动扫描。\r\n"
        "4. IP地址计算器：可用数量、首个/末个可用IP、网络地址、广播地址、掩码。\r\n"
        "5. 目标端口扫描：IP网段扫若干端口、单IP扫全部端口。\r\n"
        "6. 系统端口占用查看：查看TCP/UDP占用，定位进程目录，杀死PID进程。\r\n"
        "7. WiFi密码查看：查看所有连过的WiFi名称与密码，支持导出，支持Win11 24H2。\r\n"
        "8. Windows命令：18个常用系统命令快速打开，并支持DIY自定义。\r\n"
        "9. 备注管理：自定义IP备注，支持从剪贴板导入。\r\n"
        "\r\n"
        "本版本为 Python 复刻版，界面与功能对齐原版 IPScaner V1.25。\r\n"
    )


# --------------------------------------------------------------------- 选项配置
def f_config(main):
    top = mkform(main, "config")
    cfg = main.cfg

    lbl(top, 14, 20, "启用主机名查询", 105, 14)
    combo(top, 175, 17, 75, 20, ["是", "否"], 0 if getattr(cfg, "query_hostname", False) else 1)

    lbl(top, 14, 50, "Ping超时毫秒", 91, 14)
    e1 = entry(top, 175, 47, 75, 21, str(getattr(cfg, "ping_timeout", 500)))

    lbl(top, 14, 80, "双击间隔毫秒", 91, 14)
    e2 = entry(top, 175, 77, 75, 21, str(getattr(cfg, "double_click_time", 200)))

    lbl(top, 14, 110, "Ping请求次数", 91, 14)
    e3 = entry(top, 175, 107, 75, 21, str(getattr(cfg, "ping_count", 4)))

    lbl(top, 14, 140, "小色块字号", 77, 14)
    combo(top, 175, 137, 75, 20, ["6", "7", "8", "9", "10", "11", "12"], 3)

    lbl(top, 14, 170, "注：变更小色块字号需要重启", 161, 12)

    lbl(top, 14, 188, "TCP超时毫秒", 84, 14)
    entry(top, 175, 185, 75, 21, str(getattr(cfg, "port_timeout", 50)))

    lbl(top, 14, 218, "TCP侦测端口", 84, 14)
    entry(top, 175, 215, 75, 21, "80,135,445,500")

    ck = tk.Checkbutton(top, text="启用Ping失败时侦测端口", bg=T.C_FACE, font=_font(),
                        anchor="w", variable=tk.IntVar(value=0))
    ck.place(x=14, y=245, width=180, height=18)

    lbl(top, 14, 273, "小色块双击事件", 105, 14)
    combo(top, 175, 270, 75, 20, ["Ping", "浏览网页", "Tracert", "Telnet",
                                  "Netstat", "ARP", "访问共享"], 0)

    lbl(top, 14, 303, "自动弹出菜单", 91, 14)
    combo(top, 175, 300, 75, 20, ["是", "否"], 1)

    lbl(top, 14, 333, "备注色块颜色", 91, 14)
    for i, (xx, col) in enumerate(((175, T.C_MEMO_BLUE), (205, T.C_LIMEGREEN), (235, T.C_INDIANRED))):
        c = tk.Canvas(top, width=18, height=19, bg=col, highlightthickness=1,
                      highlightbackground="#808080")
        c.place(x=xx, y=331)

    def save():
        try:
            cfg.ping_timeout = int(e1.get())
            cfg.double_click_time = int(e2.get())
            cfg.ping_count = int(e3.get())
        except ValueError:
            messagebox.showwarning("选项配置", "请输入数字")
            return
        messagebox.showinfo("选项配置", "保存成功")

    btn(top, 87, 318, 75, 23, "保存", save)
    btn(top, 175, 318, 75, 23, "关闭", top.destroy)
    return top


# --------------------------------------------------------------- 一键设置IP
def f_localip(main):
    top = mkform(main, "localip")
    adpts = [a.name for a in core.get_adapters()] or [""]

    lbl(top, 24, 22, "当前IP：", 116, 26)
    entry(top, 150, 18, 272, 37, main.local_ip, readonly=True)

    lbl(top, 24, 64, "适配器：", 116, 26)
    combo(top, 150, 62, 328, 29, adpts, 0)

    gb1 = groupbox(top, 18, 104, 540, 203, "")
    lbl(top, 24, 118, "IP地址：", 116, 26)
    entry(top, 150, 114, 272, 37, main.ip_part + ".100")
    lbl(top, 24, 160, "子网掩码：", 142, 26)
    entry(top, 150, 156, 272, 37, "255.255.255.0")
    lbl(top, 24, 202, "网关：", 90, 26)
    entry(top, 150, 198, 274, 37, "")

    v1 = tk.IntVar(value=0)
    tk.Radiobutton(top, text="自动获取 IP地址", variable=v1, value=0, bg=T.C_FACE,
                   font=_font()).place(x=40, y=248, width=215, height=28)
    tk.Radiobutton(top, text="使用下面的 IP地址", variable=v1, value=1, bg=T.C_FACE,
                   font=_font()).place(x=270, y=248, width=239, height=28)

    gb2 = groupbox(top, 18, 318, 540, 93, "")
    v2 = tk.IntVar(value=0)
    tk.Radiobutton(top, text="自动获取 DNS服务器地址", variable=v2, value=0, bg=T.C_FACE,
                   font=_font()).place(x=40, y=330, width=299, height=28)
    tk.Radiobutton(top, text="使用下面的 DNS服务器地址", variable=v2, value=1, bg=T.C_FACE,
                   font=_font()).place(x=40, y=362, width=323, height=28)
    lbl(top, 24, 396, "DNS 服务器：", 168, 26)
    entry(top, 196, 392, 242, 37, "")

    btn(top, 100, 520, 138, 40, "保存设置",
        lambda: messagebox.showinfo("一键设置IP", "复刻版未实现改IP（需管理员权限且可能断网）"))
    btn(top, 250, 520, 138, 40, "关闭", top.destroy)
    combo(top, 400, 526, 52, 29, ["", "1", "2", "3"], 0)
    combo(top, 460, 526, 84, 29, ["", "1", "2"], 0)
    return top


# ----------------------------------------------------------- 自定义IP扫描地址
def f_ipsegment(main):
    top = mkform(main, "ipsegment")
    lbl(top, 12, 12, "输入IP扫描段：", 105, 14)
    seg = entry(top, 12, 32, 134, 312, "192.168.1.1-254", multiline=True)
    btn(top, 12, 352, 83, 27, "开始扫描", lambda: messagebox.showinfo("提示", "请在主界面使用【开始】"))
    btn(top, 12, 386, 83, 27, "清空日志", lambda: seg.delete("1.0", "end"))
    btn(top, 12, 420, 83, 27, "导出结果",
        lambda: messagebox.showinfo("提示", "复刻版导出请在主界面点【导出】"))

    groupbox(top, 8, 4, 703, 117, "设置IP扫描范围")
    lbl(top, 160, 24, "开始：", 49, 14)
    entry(top, 210, 20, 42, 23, "1")
    lbl(top, 258, 24, "结束：", 49, 14)
    entry(top, 308, 20, 42, 23, "254")
    entry(top, 360, 20, 101, 23, main.ip_part)
    btn(top, 470, 19, 74, 26, "生成", lambda: None)

    groupbox(top, 160, 128, 549, 338, "网络扫描结果")
    cols = ("IP地址", "状态", "主机名", "MAC", "备注")
    tv = grid(top, 165, 148, 539, 312, cols, (120, 60, 130, 140, 89))
    for i in range(1, 21):
        tv.insert("", "end", values=(f"{main.ip_part}.{i}", "", "", "", ""))

    groupbox(top, 160, 470, 144, 338, "IP扫描范围 (0)")
    groupbox(top, 12, 470, 703, 42, "")
    lbl(top, 20, 482, "分", 17, 12)
    entry(top, 44, 478, 33, 21, "5")
    tk.Checkbutton(top, text="定时扫描", bg=T.C_FACE, font=_font()).place(
        x=84, y=480, width=72, height=16)
    btn(top, 620, 484, 74, 26, "生成")
    return top


# ----------------------------------------------------------- IP地址计算器
def f_addresscalc(main):
    top = mkform(main, "addresscalc")
    lbl(top, 12, 14, "网络和IP地址计算器", 408, 19, anchor="center", fg="#1F1F1F")
    lbl(top, 12, 40, "显示网络，广播，第一个和最后一个给定的网络地址", 408, 24,
        anchor="center")

    lbl(top, 12, 78, "IP/掩码位:", 65, 12)
    parts = (main.ip_part + ".1").split(".")
    e_ips = []
    for i, xx in enumerate((80, 128, 176, 224)):
        e_ips.append(entry(top, xx, 72, 45, 26, parts[i] if i < len(parts) else "0"))
    lbl(top, 272, 78, "/", 11, 12)
    e_plen = entry(top, 288, 72, 45, 26, "24")

    # 输出字段（键名对齐 core.subnet_calc 的返回值）
    OUT_FIELDS = [
        ("可用地址:", "usable", 186, 108, 59),
        ("掩码:", "netmask", 12, 164, 45),
        ("网络:", "network", 12, 210, 45),
    ]
    out_w = {}
    for cap, key, x, y, w in OUT_FIELDS:
        lbl(top, 12 if x != 186 else 12, y - 34 if x == 186 else y - 14, cap, 75, 12)
        out_w[key] = entry(top, x, y, w, 23, "", readonly=True)
    # 网络/掩码两个字段的标题位置按源码 layout（label 在输入框上方）
    y = 250
    for cap, key in (("广播地址:", "broadcast"), ("首个可用:", "first"),
                     ("末个可用:", "last"), ("可用地址数:", "total")):
        lbl(top, 12, y, cap, 74, 12)
        out_w[key] = entry(top, 96, y - 4, 150, 21, "", readonly=True)
        y += 22

    def calc():
        try:
            ip = ".".join(str(int(e.get())) for e in e_ips)
            plen = int(e_plen.get())
            info = core.subnet_calc(ip, plen)
        except Exception as exc:  # noqa: BLE001
            messagebox.showwarning("IP地址计算器", f"输入有误：{exc}")
            return
        for k, wgt in out_w.items():
            v = info.get(k, "")
            wgt.configure(state="normal")
            wgt.delete(0, "end")
            wgt.insert(0, str(v))

    btn(top, 350, 72, 46, 31, "计算", calc)
    # 掩码/网络两行的标题（源码里 label 在输入框左侧）
    lbl(top, 12, 150, "掩码:", 35, 12)
    lbl(top, 12, 196, "网络:", 35, 12)
    return top


# --------------------------------------------------------------- 端口扫描
def f_portscan(main):
    top = mkform(main, "portscan")
    lbl(top, 12, 14, "IP地址：", 63, 14)
    e_ip = entry(top, 80, 10, 109, 23, main.ip_part + ".1")
    lbl(top, 200, 14, "端口：", 49, 14)
    e_p1 = entry(top, 250, 10, 52, 21, "1")
    lbl(top, 306, 14, "-", 14, 14)
    e_p2 = entry(top, 322, 10, 52, 21, "65535")
    btn(top, 382, 10, 61, 20, "扫描", lambda: scan_one())
    btn(top, 449, 10, 61, 20, "停止", lambda: top.destroy())

    groupbox(top, 8, 42, 654, 47, "单个IP批量端口扫描")
    lbl(top, 16, 60, "端口：", 49, 14)
    entry(top, 66, 56, 92, 21, "25,80,443")

    groupbox(top, 8, 96, 654, 51, "IP段多个端口扫描 (结束值可为空)")
    lbl(top, 16, 116, "IP段：", 49, 14)
    entry(top, 66, 112, 109, 23, main.ip_part + ".")
    lbl(top, 186, 116, "开始：", 49, 14)
    entry(top, 236, 112, 42, 21, "1")
    lbl(top, 284, 116, "结束：", 49, 14)
    entry(top, 334, 112, 42, 21, "254")
    lbl(top, 384, 116, "端口：", 49, 14)
    entry(top, 434, 112, 92, 21, "25,80,443")
    btn(top, 536, 112, 61, 20, "扫描")
    btn(top, 601, 112, 61, 20, "停止")

    groupbox(top, 8, 154, 654, 490, "端口扫描结果")
    lb = tk.Listbox(top, bg=T.C_WHITE, font=_font(), relief="solid", bd=1)
    lb.place(x=16, y=172, width=638, height=458)
    status = lbl(top, 8, 652, "程序已就绪", 300, 21)

    def scan_one():
        lb.delete(0, "end")
        ip = e_ip.get()
        try:
            p1, p2 = int(e_p1.get()), int(e_p2.get())
        except ValueError:
            p1, p2 = 1, 1024
        p2 = min(p2, p1 + 2000)
        status.configure(text="扫描中…")

        def work():
            for p in range(p1, p2 + 1):
                ok, _ = core.tcp_probe(ip, p, 60)
                if ok:
                    top.after(0, lambda pp=p: lb.insert("end", f"端口 {pp}  开放"))
            top.after(0, lambda: status.configure(text="扫描完毕"))

        import threading
        threading.Thread(target=work, daemon=True).start()

    return top


# ------------------------------------------------------- 系统端口查看工具
def f_processport(main):
    top = mkform(main, "processport")
    cols = ("协议", "本地地址", "端口", "状态", "PID", "进程名", "路径")
    groupbox(top, 8, 8, 1328, 100, "查询（筛选条件：端口，PID，进程名，路径）")
    lbl(top, 20, 32, "筛选条件:", 118, 24)
    e_f = entry(top, 150, 26, 305, 34)
    lbl(top, 470, 32, "反向筛选:", 118, 24)
    e_r = entry(top, 600, 26, 305, 34)
    btn(top, 920, 22, 136, 46, "筛选", lambda: reload_())
    btn(top, 1070, 22, 174, 46, "刷新端口列表", lambda: reload_())

    groupbox(top, 8, 116, 1328, 634, "系统端口列表")
    tv = grid(top, 12, 136, 1320, 602, cols, (60, 170, 170, 100, 70, 160, 590))
    status = lbl(top, 8, 764, "程序已就绪", 400, 32)

    def reload_():
        tv.delete(*tv.get_children())
        rows = core.netstat_ports()
        names = core.process_names([r.pid for r in rows])
        kw = e_f.get().strip().lower()
        rkw = e_r.get().strip().lower()
        n = 0
        for r in rows:
            pname = names.get(r.pid, "")
            line = f"{r.proto} {r.local} {r.port} {r.pid} {pname}"
            if kw and kw not in line.lower():
                continue
            if rkw and rkw in line.lower():
                continue
            tv.insert("", "end", values=(r.proto, r.local, r.port, r.name, r.pid, pname, ""))
            n += 1
        status.configure(text=f"程序已就绪，共 {n} 条记录")

    def on_double(_e):
        sel = tv.selection()
        if not sel:
            return
        pid = tv.item(sel[0], "values")[4]
        if messagebox.askyesno("系统端口查看工具", f"是否结束 PID {pid} 的进程？"):
            core.kill_pid(pid)
            reload_()

    tv.bind("<Double-Button-1>", on_double)
    top.after(80, reload_)
    return top


# --------------------------------------------------------- WiFi密码查看器
_WIFI_KEYS = {
    "password": ("关键内容", "Key Content"),
    "auth": ("身份验证", "Authentication"),
    "cipher": ("密码", "Cipher"),
}


def _wifi_grab(text, keys):
    """双语抓取 netsh 输出里的某个字段（原版只写了中文正则，在英文系统上会失效）。"""
    for k in keys:
        m = re.search(r"^\s*" + re.escape(k) + r"\s*:\s*(.+)$", text, re.M)
        if m:
            return m.group(1).strip()
    return ""


def _wifi_rows():
    """返回 [(SSID, 密码, 身份验证, 加密方式)]。"""
    out = []
    for ssid in core.wifi_profiles():
        text = core.run_cmd(["netsh", "wlan", "show", "profile",
                             f"name={ssid}", "key=clear"])
        out.append((ssid,
                    _wifi_grab(text, _WIFI_KEYS["password"]),
                    _wifi_grab(text, _WIFI_KEYS["auth"]),
                    _wifi_grab(text, _WIFI_KEYS["cipher"])))
    return out


def f_wifi(main):
    top = mkform(main, "wifi")
    groupbox(top, 0, 0, 545, 396, "WiFi列表")
    cols = ("WiFi名称", "密码", "身份验证", "加密方式")
    tv = grid(top, 4, 20, 541, 378, cols, (200, 150, 100, 91))
    status = lbl(top, 0, 398, "程序已就绪", 300, 21)

    def load():
        tv.delete(*tv.get_children())
        rows = _wifi_rows()
        for r in rows:
            tv.insert("", "end", values=r)
        status.configure(text=f"程序已就绪，共 {len(rows)} 个配置文件")

    def export():
        import csv
        from tkinter import filedialog
        p = filedialog.asksaveasfilename(defaultextension=".csv",
                                        filetypes=[("Excel 逗号分隔", "*.csv")],
                                        initialfile="WiFi密码.csv")
        if not p:
            return
        with open(p, "w", newline="", encoding="utf-8-sig") as fh:
            wtr = csv.writer(fh)
            wtr.writerow(["WiFi名称", "密码", "身份验证", "加密方式"])
            for iid in tv.get_children():
                wtr.writerow(tv.item(iid, "values"))
        messagebox.showinfo("WiFi密码查看器", "导出成功")

    btn(top, 8, 424, 96, 21, "导出保存的密码", export)
    top.after(80, load)
    return top


# --------------------------------------------------------- 备注信息管理
def f_memomanager(main):
    top = mkform(main, "memomanager")
    groupbox(top, 8, 4, 572, 45, "查询条件")
    lbl(top, 16, 22, "备注内容：", 70, 14)
    e_f = entry(top, 90, 18, 108, 21)
    btn(top, 206, 16, 75, 23, "查询", lambda: reload_())

    groupbox(top, 8, 56, 572, 330, "数据列表")
    cols = ("IP地址", "备注内容", "MAC地址", "主机名")
    tv = grid(top, 12, 76, 566, 306, cols, (140, 220, 120, 86))

    def reload_():
        tv.delete(*tv.get_children())
        kw = e_f.get().strip()
        for ip, memo in sorted(main.memos.items()):
            if kw and kw not in str(memo):
                continue
            n = int(ip.rsplit(".", 1)[-1]) if ip.rsplit(".", 1)[-1].isdigit() else 0
            tv.insert("", "end", values=(ip, memo, main.macs.get(n, ""),
                                         main.host_names.get(n, "")))

    btn(top, 8, 360, 75, 23, "新增", lambda: _memo_edit(main, None, reload_))
    btn(top, 90, 360, 75, 23, "修改", lambda: _memo_edit_sel(main, tv, reload_))
    btn(top, 172, 360, 75, 23, "删除", lambda: _memo_del(main, tv, reload_))
    btn(top, 260, 360, 122, 23, "导入剪贴板数据", lambda: _memo_import(main, reload_))
    top.after(60, reload_)
    return top


def _memo_edit(main, ip, cb):
    top = mkform(main, "memomanager", geometry="317x186+300+300")
    top.title("备注 ")
    lbl(top, 14, 18, "IP地址：", 63, 14)
    e_ip = entry(top, 80, 14, 187, 21, ip or "")
    lbl(top, 14, 46, "备注内容：", 77, 14)
    e_memo = entry(top, 14, 62, 189, 88, "", multiline=True)
    if ip and ip in main.memos:
        e_memo.insert("1.0", str(main.memos[ip]))

    def save():
        v = e_ip.get().strip()
        memo = e_memo.get("1.0", "end").strip()
        if not v:
            return
        if memo:
            main.memos[v] = memo
        else:
            main.memos.pop(v, None)
        n = int(v.rsplit(".", 1)[-1]) if v.rsplit(".", 1)[-1].isdigit() else 0
        if n and memo:
            main.set_block(n, 3)
        top.destroy()
        cb()

    btn(top, 210, 14, 70, 24, "保存", save, default=True)
    btn(top, 210, 44, 70, 24, "关闭", top.destroy)
    return top


def _memo_edit_sel(main, tv, cb):
    sel = tv.selection()
    if not sel:
        return
    _memo_edit(main, tv.item(sel[0], "values")[0], cb)


def _memo_del(main, tv, cb):
    sel = tv.selection()
    if not sel:
        return
    ip = tv.item(sel[0], "values")[0]
    if messagebox.askyesno("备注信息管理", f"删除 {ip} 的备注？"):
        main.memos.pop(ip, None)
        cb()


def _memo_import(main, cb):
    """导入剪贴板数据 —— 严格对齐 FormMemoManager.btnImport_Click（136-171 行）。

    原版细节：
      · 按 "\\r" / "\\n" 切行、丢弃空白行
      · 每行按 "=" 切，**至少两段**才算有效；备注里若再出现 "=" 要拼回去
        （string.Join("=", array3.Skip(1))）—— 不能用逗号切
      · 已存在的 IP 不覆盖（MemoList.All(r => r.IP != ip)）
      · 剪贴板为空直接 return，**不弹框**；一条都没识别到才提示格式
    """
    try:
        data = main.root.clipboard_get()
    except Exception:  # noqa: BLE001
        return
    if not data:
        return
    added = 0
    for line in data.replace("\r", "\n").split("\n"):
        if not line.strip():
            continue
        parts = [p for p in line.split("=") if p]
        if len(parts) < 2:
            continue
        ip = parts[0].strip()
        memo = "=".join(parts[1:]).strip()
        if ip not in main.memos:            # 原版不校验 IP 合法性，这里也别自作主张
            main.memos[ip] = memo
            added += 1
    cb()
    if added:
        messagebox.showinfo("备注信息管理", f"成功导入{added}条备注信息")
    else:
        messagebox.showinfo("备注信息管理",
                            "未识别到有效的IP备注信息。格式参照如下：\r\n"
                            "IP在前，备注信息在后，例如：\r\n192.168.0.1 = 监控服务器")


# --------------------------------------------------------- IP段扫描结果（列表展示）
def show_list(main):
    top = mkform(main, "ipdetail")
    groupbox(top, 8, 8, 700, 400, "列表展示")
    cols = ("IP地址", "状态", "主机名", "MAC地址", "备注")
    tv = grid(top, 12, 28, 694, 380, cols, (130, 70, 150, 160, 184))
    for i in range(1, 255):
        st = main.block_state.get(i, 0)
        if st == 0:
            continue
        tv.insert("", "end", values=(f"{main.ip_part}.{i}",
                                     "正常" if st == 1 else "不通",
                                     main.host_names.get(i, ""),
                                     main.macs.get(i, ""),
                                     main.memos.get(f"{main.ip_part}.{i}", "")))
    return top


# --------------------------------------------------------------------- 命令
def run_ip_command(main, ip, cmd):
    """原版双击色块 / 右键菜单调用的命令（与 FormMain.Btn_DoubleClick 一致）。"""
    cmds = {
        "ping": f'ping {ip} -n 4 &pause',
        "tracert": f'tracert {ip} &pause',
        "telnet": f'telnet {ip} 23 &pause',
        "netstat": f'netstat -ano | findstr {ip} &pause',
        "arp": f'arp -a {ip} &pause',
    }
    if cmd in cmds:
        subprocess.Popen(["cmd", "/c", "start", "", "cmd", "/k", cmds[cmd]],
                         creationflags=0x08000000)
        return
    if cmd == "web":
        import webbrowser
        webbrowser.open("http://" + ip)
        return
    if cmd == "share":
        subprocess.Popen(["explorer.exe", "\\\\" + ip], creationflags=0x08000000)
        return
    if cmd == "portscan":
        f_portscan(main)
        return
    if cmd in ("memo", "cmemo"):
        _memo_edit(main, ip, lambda: None)
        return
    if cmd in ("copyip", "copyname", "copymac"):
        return


# --------------------------------------------------------------------- 路由
def open_dialog(main, act):
    mapping = {
        "about": f_about,
        "config": f_config,
        "localip": f_localip,
        "ipsegment": f_ipsegment,
        "addresscalc": f_addresscalc,
        "portscan": f_portscan,
        "processport": f_processport,
        "wifi": f_wifi,
        "memomanager": f_memomanager,
    }
    fn = mapping.get(act)
    if fn:
        return fn(main)
    if act == "diyhelp":
        return _diy_help(main)
    return None


def _diy_help(main):
    top = mkform(main, "about", geometry="480x300")
    top.title("功能说明")
    t = entry(top, 12, 12, 456, 258, "", readonly=True, multiline=True)
    t.configure(state="normal")
    t.insert("1.0",
             "我的命令（DIY）\r\n\r\n"
             "在这里自定义常用程序、文档、命令，一键打开。\r\n"
             "原版通过配置文件 IPScaner.exe.config 的 MnuDIY 节点存储，\r\n"
             "每行一条，格式为「显示名称|命令路径|参数」。\r\n\r\n"
             "Python 复刻版的配置保存在 %APPDATA%\\IPScaner-Py\\config.json。\r\n")
    t.configure(state="disabled")
    btn(top, 393, 276, 75, 24, "确定(&O)", top.destroy, default=True)
    return top
