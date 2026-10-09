# -*- coding: utf-8 -*-
"""主窗体 —— 像素级复刻 IPScaner V1.25 的 FormMain。

实现方式：整个客户区是一块 tk.Canvas，所有控件（菜单栏、工具栏、分组框、
色块矩阵、状态栏）都用 Canvas 图元手绘。这样才能精确控制 WinForms
FlatStyle.Flat 的双层描边、GroupBox 的蚀刻框、下拉菜单的渐变等细节，
而不受 ttk 主题干扰。

分两层：
  base 层 —— 只构建一次（静态外观 + 254 个色块）
  fx   层 —— 需要时重建（悬停高亮、展开的下拉菜单、右键菜单、输入光标）
"""
import ctypes
import os
import queue
import sys
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from tkinter import messagebox

import core
import menu_def as M
import theme as T

A = T.assets_dir()


def _img(name):
    """加载 assets 下的 PNG，返回 PhotoImage（失败返回 None）。"""
    p = os.path.join(A, name + ".png")
    if not os.path.exists(p):
        return None
    try:
        return tk.PhotoImage(file=p)
    except Exception:  # noqa: BLE001
        return None


def scale_img(im, s):
    """按缩放比放大 PhotoImage。

    tk 的 zoom/subsample 只吃整数倍，所以把 s 化成最简分数 p/q，
    先 zoom(p) 再 subsample(q) —— 1.5x 走 3/2，1.25x 走 5/4，2x 直接 zoom(2)。
    """
    if s == 1.0:
        return im
    from fractions import Fraction

    fr = Fraction(s).limit_denominator(64)
    out = im
    if fr.numerator > 1:
        out = out.zoom(fr.numerator)
    if fr.denominator > 1:
        out = out.subsample(fr.denominator)
    return out


class ScaledCanvas(tk.Canvas):
    """自动按 DPI 缩放坐标的 Canvas。

    theme 里所有坐标都是 96 DPI 设计单位；高 DPI 显示器上这里统一乘以 SCALE，
    于是原版 WinForms 的 AutoScaleMode=Font 行为被复现。
    """

    def __init__(self, master, scale=1.0, **kw):
        super().__init__(master, **kw)
        self.s = scale

    def _t(self, coords):
        if self.s == 1.0:
            return coords
        return tuple(c * self.s for c in coords)

    def create_rectangle(self, *a, **kw):
        return super().create_rectangle(*self._t(a), **kw)

    def create_line(self, *a, **kw):
        return super().create_line(*self._t(a), **kw)

    def create_text(self, *a, **kw):
        return super().create_text(*self._t(a), **kw)

    def create_image(self, *a, **kw):
        return super().create_image(*self._t(a), **kw)

    def create_oval(self, *a, **kw):
        return super().create_oval(*self._t(a), **kw)

    def cbbox(self, item):
        """按设计单位返回 bbox。"""
        b = super().bbox(item)
        if b is None or self.s == 1.0:
            return b
        return tuple(v / self.s for v in b)


# 色块状态 → 填充色
STATE_FILL = {
    0: T.C_SKYBLUE,     # 未扫描
    1: T.C_LIMEGREEN,   # 通讯正常
    2: T.C_INDIANRED,   # 通讯不通
    3: T.C_MEMO_BLUE,   # 有备注（原版用蓝色区分）
}


class MainForm:
    def __init__(self, root, cfg=None):
        self.root = root
        self.cfg = cfg
        T.set_scale_from(root)
        self.S = T.SCALE
        root.title(T.TITLE_TEXT + T.TITLE_VER)
        root.geometry(f"{T.u(T.CLIENT_W)}x{T.u(T.CLIENT_H)}")
        root.resizable(False, False)
        root.configure(bg=T.C_FACE)
        ico = os.path.join(A, "app_icon.ico")
        if os.path.exists(ico):
            try:
                root.iconbitmap(ico)
            except Exception:  # noqa: BLE001
                pass

        self.cv = ScaledCanvas(root, scale=self.S,
                               width=T.u(T.CLIENT_W), height=T.u(T.CLIENT_H),
                               bg=T.C_FACE, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        self._force_client_size()

        # 字体
        self.f_default = T.resolve_font(T.F_DEFAULT)
        self.f_10 = T.resolve_font(T.F_10PT)
        self.f_10a = T.resolve_font(T.F_10PT_ASCII)
        self.f_block = T.resolve_font(T.F_BLOCK)
        self.f_title = T.resolve_font(T.F_TITLE)
        self.f_dd = T.resolve_font(T.F_DD)
        self.f_menu = T.resolve_font(T.F_MENU)
        self.f_status = T.resolve_font(T.F_STATUS)
        self._mk_fonts()

        # 图标缓存（必须保引用，否则被 GC 后不显示）
        self.icons = {}
        self._raw_icons = {}
        for n in ("工具ToolStripMenuItem", "mnuMemoManage", "mnuOptionSet",
                  "toolStripMenuItem2", "mnuAbout", "mnuLocalIP", "mnuIPSegment",
                  "mnuAddressCalc", "mnuPortScan", "mnuProcessPort", "mnuWiFiView",
                  "mnuDIY", "mnuDIYHelp", "控制面板ToolStripMenuItem",
                  "卸载程序ToolStripMenuItem", "区域语言ToolStripMenuItem",
                  "日期和时间ToolStripMenuItem", "网络连接ToolStripMenuItem",
                  "windows防火墙ToolStripMenuItem", "internet属性ToolStripMenuItem",
                  "计算机管理ToolStripMenuItem", "组策略ToolStripMenuItem",
                  "注册表ToolStripMenuItem", "服务ToolStripMenuItem",
                  "系统属性ToolStripMenuItem", "环境变量ToolStripMenuItem",
                  "用户账户ToolStripMenuItem", "设备管理ToolStripMenuItem",
                  "电源选项ToolStripMenuItem", "设备和打印机ToolStripMenuItem",
                  "磁盘管理ToolStripMenuItem", "btnDetail", "btnExport"):
            im = _img(n)
            if im is not None:
                self._raw_icons[n] = im            # 保住原图引用，避免被 GC
                self.icons[n] = scale_img(im, self.S)

        # ---- 运行状态
        self.adapter_text = ""
        self.ip_part = "192.168.100"
        self.focus_field = None          # "ip" | None
        self.caret_pos = len(self.ip_part)
        self.caret_on = True
        self.hover = None                # (kind, key)
        self.show_cues = T.MENU_KEYBOARD_CUES   # Alt 按下后置 True，才画 &X 下划线
        self.open_menu = None            # 展开的下拉菜单 id
        self.open_submenu = None         # 展开的子菜单
        self.open_at = (0, 0)
        self.open_sub_at = None
        # 弹出层（真·Toplevel，见 popup.MenuPopup）。旧实现在主 Canvas 上画菜单，
        # 会被客户区裁剪 → 「windows命令」那条 23 项菜单底边撞状态栏、最后几项
        # 看不到文字。迁到 Toplevel 后不再受主窗口边界限制，并能自动上/下翻转。
        self.menu_pop = None             # 顶级下拉的 MenuPopup
        self.ctx_pop = None              # 右键菜单的 MenuPopup
        self.combo_open = False
        self.ctx_open = False
        self.ctx_anchor = None           # 右键菜单选中的色块序号
        self.ctx_xy = (0, 0)
        self.regions = []                # 命中的区域列表
        self.blocks = {}                 # 序号 -> {rect, text}
        self.block_state = {}            # 序号 -> 0/1/2/3
        self.host_names = {}
        self.macs = {}
        self.memos = {}
        self.scanning = False
        self.cancel_ev = None
        self.local_ip = ""
        self.ok_count = 0
        self.ng_count = 0
        self.stat_text = "---"
        self.ui_q = queue.Queue()
        # 状态栏 7 面板的运行时文本（键名对齐原版 ToolStripStatusLabel 字段名）
        self.status = {
            "tip": T.STATUS_READY,          # statusTip
            "fetch": "",                    # statusFecthName
            "host": T.STATUS_HOSTNAME_OFF,  # statusHostName
            "friendly": "",                 # statusFriendlyTip2（Tip 轮播）
            "ip": "",                       # statusIP
            "time": "",                     # statusTime
        }
        import random
        self.tip_list = list(T.TIP_LIST)
        self.tip_queue = list(T.TIP_LIST)
        random.shuffle(self.tip_queue)
        self.status["friendly"] = random.choice(self.tip_list)
        self._clock = ""
        self._tick_s = None

        self.build_base()
        self.refresh_fx()
        self._bind()
        self.root.after(60, self._pump)

    # ------------------------------------------------------------------ 字体
    def _client_size(self):
        """真实客户区尺寸（设备像素）。GetClientRect 才是权威，winfo_width 会被 Tk 骗。"""
        from ctypes import wintypes

        u = ctypes.windll.user32
        hwnd = u.GetAncestor(self.root.winfo_id(), 2) or self.root.winfo_id()
        rc = wintypes.RECT()
        u.GetClientRect(hwnd, ctypes.byref(rc))
        return (rc.right, rc.bottom)

    def _force_client_size(self):
        """把客户区钉死成设计尺寸。

        Tk 9 在「系统 DPI ≠ 所在显示器 DPI」时会把 wm geometry 的像素值再乘一个
        缩放因子（实测 144/192 = 0.75 → 835x486 变成 626x364，右侧/下方内容被裁掉）。
        这里量到偏差就按比例反算再设一次，几轮即收敛。
        """
        w, h = T.u(T.CLIENT_W), T.u(T.CLIENT_H)
        gw, gh = w, h
        for _ in range(6):
            self.root.update_idletasks()
            cw, ch = self._client_size()
            if (cw, ch) == (w, h):
                break
            if cw:
                gw = int(round(gw * w / cw))
            if ch:
                gh = int(round(gh * h / ch))
            self.root.geometry(f"{gw}x{gh}")
            self.root.update()
        self.client_size = self._client_size()
        return self.client_size

    def _mk_fonts(self):
        """字体按 DPI 缩放。

        tkinter 的「负数字号」= 像素高度，正好与 WinForms 的 pt × 96 / 72 对齐，
        因此直接乘 SCALE 即可复现 AutoScaleMode=Font 的放大行为。
        """
        s = self.S

        def mk(spec, underline=False):
            fam, size = spec
            return tkfont.Font(family=fam, size=int(round(size * s)), underline=underline)

        self.tk_f_default = mk(self.f_default)
        self.tk_f_10 = mk(self.f_10)
        self.tk_f_10a = mk(self.f_10a)      # 宋体 10pt 的「纯 ASCII」档（13px 点阵）
        self.tk_f_block = mk(self.f_block)
        self.tk_f_title = mk(self.f_title)
        self.tk_f_dd = mk(self.f_dd)
        self.tk_f_menu = mk(self.f_menu)
        self.tk_f_status = mk(self.f_status)
        # 状态栏的链接面板（statusFecthName / statusHostName 的 IsLink=true）
        self.tk_f_status_link = mk(self.f_status, underline=True)

    # 文字测量：metric 返回的是「实际像素」，需换算回设计单位才能与画布坐标相加
    def _mw(self, font, text):
        return font.measure(text) / self.S

    def _f10_for(self, text):
        """宋体 10pt 的字体选择。

        GDI 对 Font("宋体", 10f) 在纯 ASCII 上走 13px 点阵、在 CJK 上走 14px 点阵
        （实测：IP 文本框 "172.19.80" 原版 60x9/125px 只对得上 Tk 宋体 -13；
        按钮「开始」27x14/110px、「图例：」32x14/148px 只对得上 -14）。
        Tk 一个字号只能给一档点阵，所以按内容挑。
        """
        ascii_only = all(ord(c) < 128 for c in text)
        return self.tk_f_10a if ascii_only else self.tk_f_10

    def _masc(self, font):
        return font.metrics("ascent") / self.S

    # ---------------------------------------------------------- 像素精确绘制
    @property
    def _px(self):
        """1 个设备像素 = 多少设计单位。"""
        return 1.0 / self.S

    def _rect(self, x, y, w, h):
        """逻辑矩形 (x, y, w, h) → Tk 矩形坐标。

        Tk 的 create_rectangle 用 XFillRectangle 填充 [x1, x2) 半开区间，
        与 WinForms 把 w 逻辑 px 画成 [x*S, (x+w)*S) 完全一致 ——
        所以这里不能再减 1 个设备像素（那会双重扣减，整体小 1px）。
        返回的右下角就是「右边界外一格」。
        """
        return (x, y, x + w, y + h)

    def _line1(self, x0, y0, x1, y1, color, tag, outer=False):
        """逻辑 1px 线。

        Tk 线段以路径为中线铺开，直接给 width=T.lw() 会在起点侧溢出半个像素，
        因此改成逐条画 lw() 条 1 设备像素的线。outer=True 时向 +x/+y 侧生长。
        """
        n = T.lw()
        cv, p = self.cv, self._px
        if x0 == x1:
            for k in range(n):
                cv.create_line(x0 + k * p, y0, x0 + k * p, y1,
                               fill=color, width=1, tags=tag)
        else:
            for k in range(n):
                cv.create_line(x0, y0 + k * p, x1, y0 + k * p,
                               fill=color, width=1, tags=tag)

    def _border_rect(self, x, y, w, h, border, fill, tag):
        """带 lw() 设备像素边框的实心矩形（边框厚度精确，不受 Tk 中线规则影响）。"""
        n = T.lw() * self._px
        cv = self.cv
        cv.create_rectangle(*self._rect(x, y, w, h), fill=border, outline="", tags=tag)
        if w - 2 * n > 0 and h - 2 * n > 0:
            cv.create_rectangle(*self._rect(x + n, y + n, w - 2 * n, h - 2 * n),
                                fill=fill, outline="", tags=tag)

    # ------------------------------------------------------------------ base 层
    def build_base(self):
        cv = self.cv
        cv.delete("base")
        self.regions = []

        self._draw_menubar_base()
        self._draw_groupbox(T.GB1, "")
        self._draw_toolbar_base()
        self._draw_groupbox(T.GB2, T.GB2_CAPTION)
        self._draw_title()
        self._draw_blocks()
        # 状态栏面板宽度随文字变化，放进动态层重绘
        self.regions_base = list(self.regions)

    # ---- 菜单栏（背景 + 5 个顶级项）
    def _draw_menubar_base(self):
        cv = self.cv
        # MenuStrip 底色 = GDI GradientFill 的分带渐变（实测边界表，见 theme.MENU_GRAD）
        bands = T.MENU_GRAD
        for i, (bx0, col) in enumerate(bands):
            bx1 = bands[i + 1][0] if i + 1 < len(bands) else T.CLIENT_W
            cv.create_rectangle(*self._rect(bx0, 0, bx1 - bx0, T.MENU_H),
                                fill=col, outline="", tags="base")

        x = T.MENU_PAD_L
        for i, item in enumerate(M.MENU_BAR):
            # 宽度用「运行时实测值」而不是设计器值（见 theme.MENU_ITEM_W 注释）
            w = T.MENU_ITEM_W[i] if i < len(T.MENU_ITEM_W) else item["w"]
            h = T.MENU_ITEM_H
            y = T.MENU_PAD_T
            self._draw_menu_item(x, y, w, h, item["text"], item["icon"])
            self.regions.append({"kind": "menubar", "box": (x, y, x + w, y + h), "key": item["id"]})
            x += w

    # ---- 单个顶级菜单项（图标 + 文字，&X 渲染为下划线）
    def _draw_menu_item(self, x, y, w, h, text, icon):
        cv = self.cv
        cy = y + h / 2 + T.MENU_TEXT_DY
        ic = self.icons.get(icon) if icon else None
        if ic is not None:
            cv.create_image(x + T.MENU_ICON_LEFT, y + h / 2, image=ic,
                            anchor="w", tags="base")
        plain, ul = M.strip_amp(text)
        tx = x + T.MENU_TEXT_LEFT
        cv.create_text(tx, cy, text=plain, font=self.tk_f_menu,
                       fill=T.C_BLACK, anchor="w", tags="base")
        # WinForms 默认不显示快捷键下划线，只有按下 Alt（ShowKeyboardCues）才画
        if ul is not None and self.show_cues:
            self._underline(tx, cy, plain, ul, self.tk_f_menu, "base")

    def _underline(self, tx, cy, plain, ul, font, tag):
        """给 plain 的第 ul 个字符画 WinForms 快捷键下划线。"""
        ly = cy + self._masc(font) - 2
        pre = self._mw(font, plain[:ul])
        wch = self._mw(font, plain[ul])
        self._line1(tx + pre, ly, tx + pre + wch, ly, T.C_BLACK, tag)

    # ---- 工具栏背景
    def _draw_groupbox(self, box, caption):
        cv = self.cv
        x, y, w, h = box
        top = y + T.GB1_FRAME_INSET
        # 底边在 y+h-2（实测：GB1 高 48 → 底边 70；GB2 高 388 → 底边 458）
        left, right, bottom = x, x + w - self._px, y + h - 2
        g = T.C_GROUP_FRAME
        # 左右下三边
        self._line1(left, top, left, bottom, g, "base")
        self._line1(right, top, right, bottom, g, "base")
        self._line1(left, bottom, right, bottom, g, "base")
        # 上边（有标题则在标题处断开）
        if caption:
            tw = self._mw(self.tk_f_default, caption)
            # [MEAS] 上边线在 x 0..6 有线、x=7 断开、x=57 接回（原版 y=79 行实测）。
            #        文字另起 1px 之所以要分开写：Tk 的 create_line 末点不包含，
            #        而 create_text 的调用点在字形左侧还留 1px 空白 —— 两个基准不同。
            gap = left + 7
            self._line1(left, top, gap, top, g, "base")
            self._line1(gap + tw + 2, top, right, top, g, "base")
            cv.create_text(left + T.GB_CAP_PAD_X, top + T.GB_CAP_DY, text=caption,
                           font=self.tk_f_default, fill=T.C_BLACK, anchor="w", tags="base")
        else:
            self._line1(left, top, right, top, g, "base")

    def _draw_toolbar_base(self):
        cv = self.cv
        px = self._px

        # 网卡下拉框
        x, y, w, h = T.CMB_ADAPTER
        cv.create_rectangle(*self._rect(x, y, w, h), fill=T.C_BTN_FACE,
                            outline="", tags="base")
        self._line1(x, y, x + w - px, y, T.C_COMBO_BORDER_T, "base")
        self._line1(x, y, x, y + h - px, T.C_COMBO_BORDER_T, "base")
        self._line1(x, y + h - px, x + w - px, y + h - px, T.C_COMBO_BORDER_B, "base")
        self._line1(x + w - px, y, x + w - px, y + h - px, T.C_COMBO_BORDER_B, "base")
        self.regions.append({"kind": "combo", "box": (x, y, x + w, y + h), "key": "adapter"})
        # 下拉箭头（⌄）：实测中心线 (67.5,51)->(71.75,55.5)->(76,51)，2px 粗
        self._draw_combo_arrow("base")

        # IP 文本框
        self._draw_textbox("base", record=True)

        # 四个带背景色的按钮
        self._draw_button(T.BTN_START, "开始", T.C_SKYBLUE, focus=True)
        self._draw_button(T.BTN_STOP, "停止", T.C_INDIANRED)
        # label1「图例：」（[SRC] Font("宋体",10f) → 32x14 点阵，控件 x=319 墨迹 x=323）
        lx, ly = T.LBL_LEGEND
        cv.create_text(lx + T.LBL_LEGEND_PAD, ly + 7, text=T.LBL_LEGEND_TEXT,
                       font=self.tk_f_10, fill=T.C_BLACK, anchor="w", tags="base")
        self.regions.append({"kind": "label",
                             "box": (lx, ly, lx + 49, ly + 14), "key": "legend"})
        # lblStat「---」（源码未设字体 → 窗体默认 宋体 9pt，控件 x=623 墨迹 x=625）
        sx, sy = T.LBL_STAT
        cv.create_text(sx + T.LBL_STAT_PAD, sy + T.LBL_STAT_DY, text=T.LBL_STAT_TEXT,
                       font=self.tk_f_default, fill=T.C_BLACK, anchor="w", tags="base")
        self.regions.append({"kind": "label",
                             "box": (sx, sy, sx + 23, sy + 12), "key": "stat"})
        self._draw_button(T.BTN_NG, "不通", T.C_INDIANRED)
        self._draw_button(T.BTN_OK, "正常", T.C_LIMEGREEN)
        # 带图标的两个工具按钮：源码没设 Font → 窗体默认 宋体 9pt
        self._draw_button(T.BTN_DETAIL, "列表展示", T.C_BTN_FACE, icon="btnDetail",
                          font=self.tk_f_default)
        self._draw_button(T.BTN_EXPORT, "导出", T.C_BTN_FACE, icon="btnExport",
                          font=self.tk_f_default)

    def _draw_textbox(self, tag, record=False):
        """IP 文本框：白底 + 四边深浅不同的固定 3D 边。

        单独抽成方法，是因为网卡下拉框的文字要在控件右边界裁掉，溢出到控件外
        的那截尾巴得先用窗体底色盖住、再把文本框整块重画在上面（见 refresh_fx）。
        """
        cv = self.cv
        px = self._px
        x, y, w, h = T.TXT_IPPART
        cv.create_rectangle(*self._rect(x, y, w, h), fill=T.C_WHITE, outline="", tags=tag)
        self._line1(x, y, x + w - px, y, T.C_EDIT_BORDER, tag)
        self._line1(x, y, x, y + h - px, T.C_EDIT_BORDER, tag)
        self._line1(x + w - px, y, x + w - px, y + h - px, T.C_EDIT_BORDER_R, tag)
        self._line1(x, y + h - px, x + w - px, y + h - px, T.C_EDIT_BORDER_B, tag)
        if record:
            self.regions.append({"kind": "edit", "box": (x, y, x + w, y + h), "key": "ip"})

    def _draw_combo_arrow(self, tag):
        """ComboBox 的下拉箭头：1px 粗 V 形（两条独立 45° 线段，见 theme.CMB_ARROW）。"""
        w = max(1, int(round(T.lw())))
        for x0, y0, x1, y1 in T.CMB_ARROW:
            self.cv.create_line(x0, y0, x1, y1, fill=T.C_ARROW, width=w,
                                capstyle="butt", joinstyle="miter", tags=tag)

    def _draw_button(self, box, text, face, icon=None, focus=False, font=None):
        """FlatStyle 按钮：[外框][2px #FDFDFD 高光][面]…[2px 高光][外框下沿]。

        font 默认走 宋体 10pt（btnStart/btnStop/btnNG/btnOK 源码里显式设了）；
        btnDetail/btnExport 源码没设字体 → 继承窗体默认 宋体 9pt，所以传 tk_f_default。
        """
        cv = self.cv
        x, y, w, h = box
        # 分层几何见 theme.BTN_FRAME_D / BTN_FACE_D（逐像素实测值）
        fl, ft, fdw, fdh = T.BTN_FRAME_D
        bx, by, bw, bh = x + fl, y + ft, w - fdw, h - fdh
        n = T.lw() * self._px            # 1 逻辑像素
        bc = T.C_ACCENT if focus else T.C_BTN_BORDER
        bc_b = T.C_ACCENT_DARK if focus else T.C_BTN_BORDER_B

        # 三层：外框 bc → 一圈高光 FDFDFD → 面 face
        self._border_rect(bx, by, bw, bh, bc, T.C_BTN_FACE, "base")
        fi, fdd = T.BTN_FACE_D[0], T.BTN_FACE_D[2]
        cv.create_rectangle(*self._rect(x + fi * n, y + fi * n,
                                        w - fdd * n, h - fdd * n),
                            fill=face, outline="", tags="base")
        # 下沿外框略深一档
        self._line1(bx, by + bh - n, bx + bw - n, by + bh - n, bc_b, "base")

        fnt = font or self._f10_for(text)
        ic = self.icons.get(icon) if icon else None
        if ic is not None:
            # 图标保持控件垂直正中（实测原版图标墨迹 y46..59 == Tk 直画结果）
            cv.create_image(bx + T.BTN_ICON_PAD, y + h / 2, image=ic, anchor="w", tags="base")
            tx, anchor = x + w - T.BTN_TEXT_RIGHT, "e"
            cy = y + h / 2 + T.BTN_TEXT_DY
        else:
            tx, anchor = bx + bw / 2 + T.BTN_TEXT_DX, "center"
            cy = y + h / 2 + T.BTN_TEXT_DY_C
        cv.create_text(tx, cy, text=text, font=fnt, fill=T.C_BLACK,
                       anchor=anchor, tags="base")
        self.regions.append({"kind": "button",
                             "box": (x, y, x + w - self._px, y + h - self._px), "key": text})

    # ---- 蓝色标题
    def _draw_title(self):
        self.cv.create_text(T.TITLE_CENTER[0], T.TITLE_CENTER[1],
                            text=self.ip_part + "网段IP使用情况",
                            font=self.tk_f_title, fill=T.C_ACCENT,
                            anchor="center", tags=("base", "title"))

    # ---- 色块矩阵
    def _draw_blocks(self):
        cv = self.cv
        for i in range(1, T.BLOCK_COUNT + 1):
            col = (i - 1) % T.BLOCK_COLS
            row = (i - 1) // T.BLOCK_COLS
            x = T.BLOCK_X0 + col * T.BLOCK_PITCH_X
            y = T.BLOCK_Y0 + row * T.BLOCK_PITCH_Y
            fg = T.C_ORANGERED if (self.ip_part + "." + str(i)) == self.local_ip else T.C_BLACK
            self._border_rect(x, y, T.BLOCK_W, T.BLOCK_H, fg, T.C_SKYBLUE,
                              ("base", "block"))
            # 垂直：墨迹中线 = 格中线 +1（实测 block1 墨迹 y 121..129，格 112..135）
            # 水平：Tk 的 measure 比 GDI 宽 4px，居中后会整体右移 2px，故 -2 修正
            txt = cv.create_text(x + T.BLOCK_W / 2 + T.BLOCK_DIGIT_DX,
                                 y + T.BLOCK_H / 2 + 1, text=str(i),
                                 font=self.tk_f_block, fill=fg, anchor="center",
                                 tags=("base", "blocktext"))
            self.blocks[i] = {"text": txt, "fg": fg}
            self.block_state[i] = 0
            self.regions.append({"kind": "block",
                                 "box": (x, y, x + T.BLOCK_W - self._px,
                                         y + T.BLOCK_H - self._px), "key": i})

    # ---- 状态栏：7 个面板（对齐 statusStrip1.Items）
    def _status_spec(self):
        """按原版 Items 顺序返回面板定义。

        (id, 文本, 字体, 颜色, 左侧是否有 BorderSides.Left, Margin.Left)
        7 项 = statusTip / toolStripStatusLabel1(空) / statusFecthName /
               statusHostName / statusFriendlyTip2 / statusIP / statusTime

        [SRC] 各面板原始属性（FormMain.cs 1411-1447 行）：
          statusTip             : 无边框, TextAlign=MiddleLeft
          toolStripStatusLabel1 : 空
          statusFecthName       : IsLink=true, Size.Width=0（无文字）
          statusHostName        : BorderSides.Left, IsLink, LinkColor=Red
          statusFriendlyTip2    : BorderSides.Left, ForeColor=MenuHighlight
          statusIP              : BorderSides.Left, Margin(10,3,0,2)
          statusTime            : BorderSides.Left, Margin(10,3,0,2), TextAlign=MiddleRight
        """
        s = self.status
        return [
            ("tip", s["tip"], self.tk_f_status, T.C_BLACK, False, 0),
            ("fetch", s["fetch"], self.tk_f_status_link, T.C_MENU_HILIGHT, False, 0),
            ("host", s["host"], self.tk_f_status_link, T.C_RED, True, 0),
            ("friendly", s["friendly"], self.tk_f_status, T.C_MENU_HILIGHT, True, 0),
            ("ip", s["ip"], self.tk_f_status, T.C_BLACK, True, 10),
            ("time", s["time"], self.tk_f_status, T.C_BLACK, True, 10),
        ]

    def _draw_status(self):
        """状态栏整体重绘。面板宽度按文字自适应（ToolStripStatusLabel.AutoSize）。

        宽度/文字偏移规则由设计器序列化的 Size 反解、并用截图像素验证，
        见 theme 里 STATUS_PAD_BASE / STATUS_BORDER_W / STATUS_TEXT_PAD* 的注释。
        无文字的面板宽度为 0 且不画左边框 —— 原版截图里 statusTime 未出字时
        分隔线确实不存在（x 786..835 全为 #F0F0F0）。
        """
        cv = self.cv
        y, h = T.STATUS_Y, T.STATUS_H
        cv.create_rectangle(*self._rect(0, y, T.CLIENT_W, h), fill=T.C_FACE,
                            outline="", tags="fx")
        self._line1(0, y, T.CLIENT_W, y, T.STATUS_TOP_LINE, "fx")

        x = T.STATUS_PAD_L
        tw_max = T.CLIENT_W - T.STATUS_PAD_R          # 可排布区域右界（825）
        for pid, text, font, color, border, margin in self._status_spec():
            x += margin
            if not text:
                w = 0
            else:
                adv = self._mw(font, text)
                w = adv + T.STATUS_PAD_BASE + (T.STATUS_BORDER_W if border else 0)
                pad = T.STATUS_TEXT_PAD + (T.STATUS_TEXT_PAD_B if border else 0)
                if border:
                    self._line1(x, y + T.STATUS_SEP_INSET,
                                x, y + h - T.STATUS_SEP_INSET,
                                T.C_STATUS_SEP, "fx")
                if pid == "time":      # [SRC] TextAlign = MiddleRight
                    cv.create_text(x + w - pad - adv, y + h / 2, text=text, font=font,
                                   fill=color, anchor="w", tags="fx")
                else:
                    cv.create_text(x + pad, y + h / 2, text=text, font=font,
                                   fill=color, anchor="w", tags="fx")
            self.regions.append({"kind": "status",
                                 "box": (x, y, x + max(w, 2), y + h), "key": pid})
            x += w
            if x > tw_max:                 # 超出可排布区 → 与原版一样被裁掉
                break

        # 右下角尺寸手柄（StatusStrip.SizingGrip）
        # 实测：2x2 逻辑像素方块、步距 4，右上角方块在 (830, 473)，向左下铺成三角
        for r in range(3):
            for j in range(r + 1):
                dx = T.CLIENT_W - 5 - 4 * j          # 830
                dy = y + h - 13 + 4 * r              # 473
                cv.create_rectangle(*self._rect(dx, dy, 2, 2),
                                    fill="#A0A0A0", outline="", tags="fx")

    # ------------------------------------------------------------------ fx 层
    def refresh_fx(self):
        """重建动态层：输入框文字/光标、悬停高亮、下拉菜单、右键菜单。"""
        cv = self.cv
        cv.delete("fx")
        self.regions = list(getattr(self, "regions_base", self.regions))

        # --- 状态栏（面板宽度随文字变化，必须每次重排）
        self._draw_status()

        # --- 网卡下拉框文字（必须先于 IP 文本框画，原因见下面「溢出尾巴」那段）
        #     源码未给 cmbAdapter 设 Font → 窗体默认 宋体 9pt
        #     WinForms 把子控件的渲染裁剪在自身边界内：网卡名超宽时在箭头左侧被切断，
        #     半个字形都不露出（原版 "vEthernet (WSL)" 只显示到 x=60）。Tk 画布没有
        #     裁剪区域，只能先整串画出来、再用底色把多出来的部分盖掉。
        cx0, cy0, cw, ch = T.CMB_ADAPTER
        face = T.C_BTN_FACE
        cv.create_rectangle(*self._rect(cx0 + 1, cy0 + 1, cw - 2, ch - 2),
                            fill=face, outline="", tags="fx")
        ctext_x = cx0 + T.CMB_TEXT_PAD
        cv.create_text(ctext_x, cy0 + ch / 2, text=self.adapter_text,
                       font=self.tk_f_default, fill=T.C_BLACK, anchor="w", tags="fx")
        clip_x = cx0 + cw - T.CMB_TEXT_CLIP_R          # 文字裁剪线（下拉按钮左沿）
        cv.create_rectangle(*self._rect(clip_x, cy0 + 1, (cx0 + cw - 1) - clip_x, ch - 2),
                            fill=face, outline="", tags="fx")
        # 溢出到控件之外的尾巴：先用窗体底色盖住，再把 IP 文本框整块重画在上面，
        # 否则「(WSL)」后半截会直接糊到右边的 IP 输入框上。
        over = ctext_x + self._mw(self.tk_f_default, self.adapter_text) + 2
        edge = cx0 + cw                                # 控件右沿外一格
        if over > edge:
            cv.create_rectangle(*self._rect(edge, cy0 + 1, over - edge, ch - 2),
                                fill=T.C_FACE, outline="", tags="fx")
            self._draw_textbox("fx")

        # --- IP 文本框内容（文字垂直居中 = y + h/2，不是 (y+h)/2）
        x, y, w, h = T.TXT_IPPART
        padx, pady = T.TXT_IP_PAD
        ty = y + h / 2 + T.TXT_IP_DY
        f_ip = self._f10_for(self.ip_part)
        cv.create_text(x + padx, ty, text=self.ip_part, font=f_ip,
                       fill=T.C_BLACK, anchor="w", tags="fx")
        if self.focus_field == "ip" and self.caret_on:
            cx = x + padx + self._mw(f_ip, self.ip_part[:self.caret_pos])
            cv.create_line(cx, y + 4, cx, y + h - 4, fill=T.C_BLACK,
                           width=T.lw(), tags="fx")

        self._draw_combo_arrow("fx")

        # --- 按钮 / 图例 悬停高亮
        if self.hover and self.hover[0] == "button":
            b = self._box_of("button", self.hover[1])
            if b:
                self._hover_rect(b)
        elif self.hover and self.hover[0] == "menubar":
            b = self._box_of("menubar", self.hover[1])
            if b:
                self._hover_rect(b)

        # --- 展开的网卡下拉列表（仍在 Canvas 上：它最多 8 行、高度可控，不会越界）
        if self.combo_open:
            self._draw_combo_list()
        # 菜单/右键菜单已迁到 popup.MenuPopup（真·Toplevel），
        # 不再在这里画 —— 原因见 popup.py 文件头注释。

    def _hover_rect(self, box):
        """悬停高亮：ToolStripProfessionalRenderer 的菜单选中底色。"""
        x, y, x1, y1 = box
        self.cv.create_rectangle(x, y, x1, y1, fill=T.C_MENU_SELECT, outline="", tags="fx")

    def _box_of(self, kind, key):
        for r in self.regions:
            if r["kind"] == kind and r["key"] == key:
                return r["box"]
        return None

    # ---- 下拉菜单绘制（含子菜单）
    def _draw_dropdown(self, menu_id=None, x=None, y=None, sub=False, submenu=None):
        if not sub:
            menu_id = self.open_menu
            x, y = self.open_at
            dd = M.DROPDOWNS.get(menu_id)
            if not dd:
                return
            items, w = dd["items"], dd["w"]
        else:
            items, w = submenu["items"], submenu["w"]

        item_h, sep_h, margin_w = 22, 6, 24
        total = sum(sep_h if it is M.SEP else item_h for it in items) + 4
        items_box = []
        cy = y
        for it in items:
            if it is M.SEP:
                items_box.append((it, cy, sep_h))
                cy += sep_h
            else:
                items_box.append((it, cy, item_h))
                cy += item_h
        h = cy - y + 3

        cv = self.cv
        self._border_rect(x, y, w, h, T.C_DD_BORDER, T.C_DD_BG, "fx")
        # 左侧图标栏分隔线
        self._line1(x + margin_w, y + self._px, x + margin_w, y + h - self._px,
                    T.C_DD_MARGIN_LINE, "fx")

        for it, iy, ih in items_box:
            if it is M.SEP:
                cv.create_line(x + margin_w + 2, iy + sep_h // 2, x + w - 4, iy + sep_h // 2,
                               fill=T.C_DD_SEP, tags="fx")
                continue
            text, icon, _act, sub_items = it
            box = (x, iy, x + w, iy + ih)
            hl = (self.hover == ("dd", (id(items), iy)))
            if hl:
                cv.create_rectangle(x + 1, iy, x + w - 1, iy + ih, fill=T.C_DD_HILIGHT,
                                    outline="", tags="fx")
            plain, ul = M.strip_amp(text)
            ic = self.icons.get(icon) if icon else None
            if ic is not None:
                cv.create_image(x + margin_w // 2, iy + ih // 2, image=ic, anchor="center",
                                tags="fx")
            tx = x + margin_w + 6
            cv.create_text(tx, iy + ih // 2, text=plain, font=self.tk_f_dd, fill=T.C_BLACK,
                           anchor="w", tags="fx")
            if ul is not None:
                self._underline(tx, iy + ih // 2, plain, ul, self.tk_f_dd, "fx")
            if sub_items:
                ax = x + w - 12
                cv.create_line(ax, iy + ih // 2 - 2, ax + 4, iy + ih // 2 + 2,
                               ax, iy + ih // 2 + 6, fill=T.C_BLACK, tags="fx")
            self.regions.append({"kind": "dd", "box": box, "key": (id(items), iy),
                                 "data": it, "menu": menu_id, "depth": 1 if sub else 0,
                                 "menu_x": x, "menu_w": w})

        # 子菜单
        if sub and self.open_submenu:
            pass

    def _draw_combo_list(self):
        """ComboBox(DropDownList) 的下拉列表 —— 宽度与下拉框相同，最多 8 行（超出滚动）。"""
        x, y, w, h = T.CMB_ADAPTER
        items = self.adapters if hasattr(self, "adapters") else []
        ih = 16
        max_rows = 8
        show = items[:max_rows]
        hh = max(1, len(show)) * ih + 2
        by = y + h
        cv = self.cv
        self._border_rect(x, by, w, hh, T.C_COMBO_BORDER_B, T.C_WHITE, "fx")
        for k, it in enumerate(show):
            iy = by + 1 + k * ih
            if self.hover == ("combo", k):
                cv.create_rectangle(x + 1, iy, x + w - 1, iy + ih, fill=T.C_ACCENT,
                                    outline="", tags="fx")
                fg = T.C_WHITE
            else:
                fg = T.C_BLACK
            txt = it if self._mw(self.tk_f_10, it) <= w - 6 else it[:6] + "…"
            cv.create_text(x + 3, iy + ih / 2, text=txt, font=self.tk_f_10, fill=fg,
                           anchor="w", tags="fx")
            self.regions.append({"kind": "combo_item", "box": (x, iy, x + w, iy + ih),
                                 "key": k, "data": it})

    def _draw_context_menu(self):
        d = M.CONTEXT_MENU
        n = self.ctx_anchor
        ip = f"{self.ip_part}.{n}" if n else ""
        labels = [
            ("复制IP       " + ip, "copyip"),
            ("复制主机名   " + self.host_names.get(n, ""), "copyname"),
            ("复制MAC地址  " + self.macs.get(n, ""), "copymac"),
            M.SEP,
            ("端口扫描(&S)", "cportscan"), ("访问共享目录", "cshare"),
            ("浏览网页(&V)", "cweb"), ("调用Ping命令", "cping"),
            ("调用Tracert(&R)", "ctracert"), ("调用Telnet(&T)", "ctelnet"),
            ("调用netstat(&N)", "cnetstat"), ("调用ARP(&A)", "carp"),
            M.SEP, ("备注信息(&M)", "cmemo"),
        ]
        items = [M.SEP if it is M.SEP else (it[0], None, it[1], None) for it in labels]
        self._draw_dropdown(sub=True, x=self.ctx_xy[0], y=self.ctx_xy[1],
                            submenu={"items": items, "w": 200})
        self._ctx_items = items

    # ------------------------------------------------------------------ 工具
    @staticmethod
    def _lerp(c1, c2, t):
        a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
        return "#%02X%02X%02X" % tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))

    # ------------------------------------------------------------------ 事件
    def _bind(self):
        cv = self.cv
        cv.bind("<Motion>", self.on_motion)
        cv.bind("<Button-1>", self.on_click)
        cv.bind("<Double-Button-1>", self.on_double)
        cv.bind("<Button-3>", self.on_right)
        self.root.bind("<Key>", self.on_key)
        self.root.bind("<FocusIn>", lambda e: None)

    def _hit(self, x, y):
        for r in reversed(self.regions):
            x0, y0, x1, y1 = r["box"]
            if x0 <= x <= x1 and y0 <= y <= y1:
                return r
        return None

    def on_motion(self, e):
        r = self._hit(e.x / self.S, e.y / self.S)
        new = None
        if r:
            if r["kind"] == "dd":
                new = ("dd", r["key"])
            elif r["kind"] == "combo_item":
                new = ("combo", r["key"])
            elif r["kind"] in ("button", "menubar"):
                new = (r["kind"], r["key"])
        if new != self.hover:
            self.hover = new
            self.refresh_fx()
        # WinForms MenuStrip 行为：菜单已展开时，鼠标划过其它顶级项直接切换菜单
        if self.open_menu and r and r["kind"] == "menubar" and r["key"] != self.open_menu:
            self.open_menu_popup(r["key"], r["box"])

    def _on_leave_item(self):
        """水平方向移出顶层菜单 → 收起下拉。垂直方向留给 MenuPopup 处理。"""
        return

    def _over_open_menu(self, x, y):
        return False

    # ------------------------------------------------------------------ 弹出层
    def _popup_geometry(self):
        """主窗口客户区左上角的屏幕坐标（物理像素）。"""
        from ctypes import wintypes

        u = ctypes.windll.user32
        hwnd = u.GetAncestor(self.root.winfo_id(), 2) or self.root.winfo_id()
        pt = wintypes.POINT(0, 0)
        u.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(pt))
        return pt.x, pt.y

    def _menu_fire(self, act):
        """菜单项被选中：先收全部弹层，再执行动作。"""
        self.close_menus()
        self.fire(act)

    def open_menu_popup(self, menu_id, box):
        """在顶级菜单项 box 下方弹出一个 MenuPopup（越界时自动上翻）。"""
        import popup as P

        dd = M.DROPDOWNS.get(menu_id)
        if not dd:
            return
        self.close_menus()
        self.open_menu = menu_id
        pop = P.MenuPopup(self, dd["items"], width=dd["w"],
                          on_fire=self._menu_fire,
                          on_hover_item=self._menu_hover_sub,
                          on_leave_item=self._menu_leave_sub)
        self.menu_pop = pop
        ox, oy = self._popup_geometry()
        # box[3] 是菜单项底边（设计像素）→ 换成物理像素
        x = ox + int(box[0] * self.S)
        y = oy + int((box[3] + 1) * self.S)
        pop.place(x, y, prefer_up=True)
        self._start_menu_watch()

    def _menu_hover_sub(self, parent, sub_items, ax, ay, ih, width=None):
        """悬停在含子菜单的父项上 → 展开子菜单（延迟一点，避免抖动）。"""
        import popup as P

        if parent._sub is not None and parent._sub_src is sub_items:
            return
        if parent._sub is not None:
            parent._sub.close()
            parent._sub = None
            parent._sub_src = None

        def spawn():
            if parent._closed or parent._sub is not None:
                return
            sub = P.MenuPopup(self, sub_items, width=width, level=1,
                              on_fire=self._menu_fire,
                              on_hover_item=self._menu_hover_sub,
                              on_leave_item=None)
            parent._sub = sub
            parent._sub_src = sub_items
            # 子菜单左沿 = 父面板右沿，顶边对齐父项
            sub.place(ax, ay, prefer_up=True)

        parent._cancel_timer()
        parent._sub_timer = parent.win.after(110, spawn)

    def _menu_leave_sub(self, parent):
        """移出父项 → 延迟收起子菜单（给鼠标跨过间隙留时间）。"""
        if parent._sub is None:
            return

        def drop():
            if parent._closed:
                return
            sub = parent._sub
            if sub is None:
                return
            # 鼠标还在子菜单上则不收
            try:
                px, py = self.root.winfo_pointerxy()
                if sub.contains_screen_point(px, py):
                    return
            except Exception:  # noqa: BLE001
                pass
            sub.close()
            parent._sub = None
            parent._sub_src = None

        parent._cancel_timer()
        parent._sub_timer = parent.win.after(200, drop)

    def close_menus(self):
        """收起全部菜单弹层（含右键菜单与子菜单）。"""
        self.open_menu = None
        self.open_submenu = None
        if self.menu_pop is not None:
            try:
                self.menu_pop.close()
            except Exception:  # noqa: BLE001
                pass
            self.menu_pop = None
        if self.ctx_pop is not None:
            try:
                self.ctx_pop.close()
            except Exception:  # noqa: BLE001
                pass
            self.ctx_pop = None
        self.ctx_open = False

    def dismiss_menus(self):
        """用户主动关掉菜单（点外部 / Esc）：收弹层 + 重绘主界面。"""
        if not (self.open_menu or self.ctx_open):
            return
        self.close_menus()
        self.refresh_fx()

    # ---- 点菜单外部就关掉（弹窗是独立 Toplevel，主 Canvas 收不到那些点击，
    #      所以用一个轻量轮询兜底；只在有菜单打开时运行，开销可忽略）
    def _menu_pops(self):
        out, p = [], self.menu_pop or self.ctx_pop
        while p is not None:
            out.append(p)
            p = p.sub
        return out

    def _start_menu_watch(self):
        self._menu_btn_seen_up = False
        if getattr(self, "_menu_watch_on", False):
            return
        self._menu_watch_on = True
        self.root.after(120, self._tick_menu_watch)

    def _tick_menu_watch(self):
        if not (self.open_menu or self.ctx_open):
            self._menu_watch_on = False
            return
        import ctypes

        u = ctypes.windll.user32
        down = bool(u.GetAsyncKeyState(0x01) & 0x8000)     # VK_LBUTTON
        if not down:
            self._menu_btn_seen_up = True
        elif self._menu_btn_seen_up:
            pt = ctypes.wintypes.POINT()
            u.GetCursorPos(ctypes.byref(pt))
            inside = any(p.contains_screen_point(pt.x, pt.y)
                         for p in self._menu_pops())
            if not inside:
                # 是否落在主窗口客户区内？是的话交给 Canvas 自己处理
                ox, oy = self._popup_geometry()
                cx = (pt.x - ox) / self.S
                cy = (pt.y - oy) / self.S
                if not (0 <= cx < T.CLIENT_W and 0 <= cy < T.CLIENT_H):
                    self.dismiss_menus()
                    return
                self._menu_btn_seen_up = False
        self.root.after(120, self._tick_menu_watch)

    def open_context_popup(self, x, y):
        """在 (x, y)（客户区设计像素）弹出右键菜单。"""
        import popup as P

        labels = [
            ("复制IP       " + f"{self.ip_part}.{self.ctx_anchor}"
             if self.ctx_anchor else "复制IP", "copyip"),
            ("复制主机名   " + self.host_names.get(self.ctx_anchor, ""), "copyname"),
            ("复制MAC地址  " + self.macs.get(self.ctx_anchor, ""), "copymac"),
            M.SEP,
            ("端口扫描(&S)", "cportscan"), ("访问共享目录", "cshare"),
            ("浏览网页(&V)", "cweb"), ("调用Ping命令", "cping"),
            ("调用Tracert(&R)", "ctracert"), ("调用Telnet(&T)", "ctelnet"),
            ("调用netstat(&N)", "cnetstat"), ("调用ARP(&A)", "carp"),
            M.SEP, ("备注信息(&M)", "cmemo"),
        ]
        items = [M.SEP if it is M.SEP else (it[0], None, it[1], None) for it in labels]
        self.close_menus()
        self.ctx_open = True
        pop = P.MenuPopup(self, items, width=200, on_fire=self._menu_fire)
        self.ctx_pop = pop
        ox, oy = self._popup_geometry()
        pop.place(ox + int(x * self.S), oy + int(y * self.S))
        self._start_menu_watch()

    def on_click(self, e):
        r = self._hit(e.x / self.S, e.y / self.S)
        # 点在下拉/右键弹层里：交给 Toplevel 自己处理（主 Canvas 收不到这些点击）
        if self.open_menu or self.ctx_open or self.combo_open:
            if r and r["kind"] == "combo_item":
                self.adapter_text = r["data"]
                self.combo_open = False
                self.refresh_fx()
                self.on_adapter_change()
                return
            # 点在菜单栏其它顶级项上 → 切换菜单；否则收起
            if r and r["kind"] == "menubar":
                self.open_menu_popup(r["key"], r["box"])
                return
            if r and r["kind"] == "combo":
                self.adapters = [a.name for a in core.get_adapters()] or [""]
                self.combo_open = True
                self.close_menus()
                self.refresh_fx()
                return
            self.close_menus()
            self.combo_open = False
            self.refresh_fx()
            if r is None:
                return

        self.focus_field = None
        if r is None:
            self.refresh_fx()
            return
        k = r["kind"]
        if k == "menubar":
            self.open_menu_popup(r["key"], r["box"])
        elif k == "combo":
            self.adapters = [a.name for a in core.get_adapters()] or [""]
            self.combo_open = True
            self.refresh_fx()
        elif k == "edit":
            self.focus_field = "ip"
            self.caret_pos = len(self.ip_part)
            self.refresh_fx()
        elif k == "button":
            self.fire("btn:" + r["key"])
        elif k == "label":
            self.fire("legend_label")
        elif k == "status":
            self.fire("status:" + r["key"])
        elif k == "block":
            self.on_block_click(r["key"])
        else:
            self.refresh_fx()

    def on_double(self, e):
        r = self._hit(e.x / self.S, e.y / self.S)
        if r and r["kind"] == "block":
            self.on_block_double(r["key"])

    def on_right(self, e):
        ex, ey = e.x / self.S, e.y / self.S
        r = self._hit(ex, ey)
        self.combo_open = False
        self.close_menus()
        if r and r["kind"] == "block":
            self.ctx_anchor = r["key"]
            self.open_context_popup(ex, ey)
        self.refresh_fx()

    def on_key(self, e):
        # Esc 关菜单（第三道兜底：弹层自己那份绑定不一定能拿到键盘焦点）
        if e.keysym == "Escape" and (self.open_menu or self.ctx_open):
            self.dismiss_menus()
            return
        # WinForms 语义：按下 Alt 才显示菜单的快捷键下划线（ShowKeyboardCues）
        if e.keysym in ("Alt_L", "Alt_R"):
            if not self.show_cues:
                self.show_cues = True
                self.build_base()
                self.refresh_fx()
            return
        if self.focus_field != "ip":
            if e.keysym == "F5":
                self.start_scan()
            return
        if e.keysym == "BackSpace":
            if self.caret_pos > 0:
                self.ip_part = self.ip_part[:self.caret_pos - 1] + self.ip_part[self.caret_pos:]
                self.caret_pos -= 1
        elif e.keysym == "Delete":
            self.ip_part = self.ip_part[:self.caret_pos] + self.ip_part[self.caret_pos + 1:]
        elif e.keysym == "Left":
            self.caret_pos = max(0, self.caret_pos - 1)
        elif e.keysym == "Right":
            self.caret_pos = min(len(self.ip_part), self.caret_pos + 1)
        elif e.keysym == "Home":
            self.caret_pos = 0
        elif e.keysym == "End":
            self.caret_pos = len(self.ip_part)
        elif e.keysym in ("Return", "KP_Enter"):
            self.focus_field = None
            self.start_scan()
        elif e.keysym == "Escape":
            self.focus_field = None
        elif e.char and 32 <= ord(e.char[0]) < 127:
            self.ip_part = self.ip_part[:self.caret_pos] + e.char + self.ip_part[self.caret_pos:]
            self.caret_pos += 1
        self.cv.itemconfig(self.cv.find_withtag("title")[0],
                           text=self.ip_part + "网段IP使用情况")
        self.refresh_fx()

    # ------------------------------------------------------------------ 动作分发
    def fire(self, act):
        if act is None:
            return
        if act.startswith("cmd:"):
            core.run_cmd(["cmd", "/c", "start", "", act[4:]], timeout=3)
            return
        if act.startswith("btn:"):
            name = act[4:]
            if name == "开始":
                self.start_scan()
            elif name == "停止":
                self.stop_scan()
            elif name == "列表展示":
                from dialogs import show_list
                show_list(self)
            elif name == "导出":
                self.export()
            elif name in ("不通", "正常"):
                self.copy_legend(name)
            return
        if act.startswith("status:"):
            key = act[7:]
            if key == "host":                    # statusHostName_Click → 打开选项
                from dialogs import open_dialog
                open_dialog(self, "config")
            elif key == "ip":                    # statusIP_Click → 复制活动 IP
                val = self.status["ip"].replace(T.STATUS_IP_PREFIX, "")
                self.cv.clipboard_clear()
                self.cv.clipboard_append(val)
                self.set_status("tip", "IP已复制到剪贴板")
            elif key == "fetch":                 # statusFecthName_Click
                self.set_status("host", T.STATUS_HOSTNAME_ON)
                self.set_status("tip", "开始获取主机名")
            return
        if act in ("localip", "ipsegment", "addresscalc", "portscan",
                   "processport", "wifi", "memomanager", "config", "about", "diyhelp"):
            from dialogs import open_dialog
            open_dialog(self, act)
        elif act.startswith("copy"):
            self.ctx_copy(act)
        elif act.startswith("c"):
            self.ctx_command(act)

    # ------------------------------------------------------------------ 扫描
    def on_block_click(self, n):
        if self.scanning:
            return
        ip = f"{self.ip_part}.{n}"
        self.cv.clipboard_clear()
        self.cv.clipboard_append(ip)
        self.set_status("tip", "IP已复制到剪贴板")
        self.ping_one(n)

    def on_block_double(self, n):
        ip = f"{self.ip_part}.{n}"
        from dialogs import run_ip_command
        run_ip_command(self, ip, "ping")

    def ping_one(self, n):
        def work():
            alive, _ = core.ping_once(f"{self.ip_part}.{n}", 500)
            self.ui_q.put(("block", n, 1 if alive else 2))
        import threading
        threading.Thread(target=work, daemon=True).start()

    def start_scan(self):
        if self.scanning:
            return
        ips = [f"{self.ip_part}.{i}" for i in range(1, 255)]
        if not self.ip_part or self.ip_part.count(".") != 2:
            messagebox.showwarning(T.TITLE_TEXT, "IP 段格式应为 a.b.c")
            return
        self.scanning = True
        self.cancel_ev = None
        import threading
        self.cancel_ev = threading.Event()
        self.ok_count = self.ng_count = 0
        for i in range(1, 255):
            self.set_block(i, 0)
        self.stat_text = "---"
        self.set_status("tip", "开始扫描IP")

        def on_result(hr):
            self.ui_q.put(("result", hr))

        def work():
            core.scan(ips, on_result, timeout_ms=500, workers=64,
                      want_name=True, want_mac=True, cancel=self.cancel_ev)
            self.ui_q.put(("done", None))

        threading.Thread(target=work, daemon=True).start()

    def stop_scan(self):
        if self.cancel_ev:
            self.cancel_ev.set()
        self.scanning = False
        self.set_status("tip", "用户取消了操作")

    def set_block(self, n, state):
        """改色块填充色。

        色块是「描边实心块 + 内层填充块」两层，所以直接重画内层那块。
        """
        b = self.blocks.get(n)
        if not b:
            return
        self.block_state[n] = state
        col = (n - 1) % T.BLOCK_COLS
        row = (n - 1) // T.BLOCK_COLS
        x = T.BLOCK_X0 + col * T.BLOCK_PITCH_X
        y = T.BLOCK_Y0 + row * T.BLOCK_PITCH_Y
        nn = T.lw() * self._px
        if "fill" in b:
            self.cv.delete(b["fill"])
        b["fill"] = self.cv.create_rectangle(
            *self._rect(x + nn, y + nn, T.BLOCK_W - 2 * nn, T.BLOCK_H - 2 * nn),
            fill=STATE_FILL[state], outline="", tags=("base", "blockfill"))
        # 后画的填充块会盖住数字，把文字提到最上层
        self.cv.tag_raise(b["text"])

    def set_status(self, key, text):
        """更新状态栏某个面板的文本。

        key：tip(程序提示) / fetch(抓取进度) / host(主机名查询开关) /
             friendly(Tip 轮播) / ip(活动IP) / time(时间)
        """
        if self.status.get(key) == text:
            return
        self.status[key] = text
        self.refresh_fx()

    def _pump(self):
        try:
            while True:
                msg = self.ui_q.get_nowait()
                kind = msg[0]
                if kind == "block":
                    _, n, st = msg
                    self.set_block(n, st)
                elif kind == "result":
                    _, hr = msg
                    n = int(hr.ip.rsplit(".", 1)[1]) if "." in hr.ip else 0
                    self.set_block(n, 1 if hr.alive else 2)
                    if hr.alive:
                        self.ok_count += 1
                        if hr.hostname:
                            self.host_names[n] = hr.hostname
                        if hr.mac:
                            self.macs[n] = hr.mac
                    else:
                        self.ng_count += 1
                    self.stat_text = f"数量合计：正常 {self.ok_count}，不通 {self.ng_count}"
                elif kind == "done":
                    self.scanning = False
                    self.set_status("tip", "扫描完毕")
                elif kind == "caret":
                    self.caret_on = msg[1]
                    self.refresh_fx()
        except queue.Empty:
            pass
        # 状态栏时钟 + Tip 轮播（对齐原版 Timer_Tick：Interval=1000ms）
        # IPSCANER_FREEZE=1 时冻结这两者，用于和「时钟未出字、Tip 恰好是那一条」的
        # 原版截图做逐像素比对（截图那一帧正好是这个状态）。
        if not os.environ.get("IPSCANER_FREEZE", "").strip():
            now = datetime.now()
            sec = now.strftime("%S")
            if sec != self._tick_s:
                self._tick_s = sec
                self.set_status("time", now.strftime(T.STATUS_TIME_FMT))
                if now.second % 10 == 0:            # [SRC] 449 行
                    if not self.tip_queue:
                        import random
                        self.tip_queue = list(self.tip_list)
                        random.shuffle(self.tip_queue)
                    self.set_status("friendly", self.tip_queue.pop(0))
        # 输入框光标闪烁（原版 TextBox 的默认行为）
        if self.focus_field == "ip":
            self._caret_tick = getattr(self, "_caret_tick", 0) + 1
            if self._caret_tick % 8 == 0:
                self.caret_on = not self.caret_on
                self.refresh_fx()
        self.root.after(60, self._pump)

    def on_adapter_change(self):
        """网卡切换 —— 对齐原版 cmbAdapter_SelectedIndexChanged：更新本地 IP。"""
        for a in core.get_adapters():
            if a.name == self.adapter_text and a.ip:
                self.local_ip = a.ip
                if a.ip.count(".") == 3:
                    self.ip_part = a.ip.rsplit(".", 1)[0]
                    self.caret_pos = len(self.ip_part)
                break
        self.build_base()
        self.refresh_fx()

    def export(self):
        from tkinter import filedialog
        p = filedialog.asksaveasfilename(defaultextension=".csv",
                                        filetypes=[("Excel 逗号分隔", "*.csv")],
                                        initialfile=f"IPScaner_{self.ip_part}.csv")
        if not p:
            return
        rows = []
        for i in range(1, 255):
            st = self.block_state.get(i, 0)
            if st == 0:
                continue
            rows.append([f"{self.ip_part}.{i}",
                         "正常" if st == 1 else ("有备注" if st == 3 else "不通"),
                         self.host_names.get(i, ""),
                         self.macs.get(i, ""),
                         self.memos.get(f"{self.ip_part}.{i}", "")])
        core.export_csv(p, rows, ["IP", "状态", "主机名", "MAC", "备注"])
        messagebox.showinfo(T.TITLE_TEXT, "导出成功")

    def copy_legend(self, which):
        if self.stat_text == "---":
            messagebox.showwarning(T.TITLE_TEXT, "请先扫描IP段")
            return
        want = 2 if which == "不通" else 1
        lines = [f"IP段: {self.ip_part}, 状态【{which}】地址共有"
                 f"{self.ng_count if want == 2 else self.ok_count}个"]
        for i in range(1, 255):
            if self.block_state.get(i) == want:
                ip = f"{self.ip_part}.{i}"
                extra = ""
                if want == 1:
                    extra = f"  {self.host_names.get(i,'')} {self.macs.get(i,'')}"
                lines.append(ip + extra)
        self.cv.clipboard_clear()
        self.cv.clipboard_append("\n".join(lines))
        messagebox.showinfo(T.TITLE_TEXT, lines[0] + "，已复制剪贴版")

    def ctx_copy(self, act):
        n = self.ctx_anchor
        val = {"copyip": f"{self.ip_part}.{n}",
               "copyname": self.host_names.get(n, ""),
               "copymac": self.macs.get(n, "")}[act]
        self.cv.clipboard_clear()
        self.cv.clipboard_append(val)
        self.set_status("tip", "IP已复制到剪贴板")

    def ctx_command(self, act):
        n = self.ctx_anchor
        ip = f"{self.ip_part}.{n}"
        from dialogs import run_ip_command
        run_ip_command(self, ip, act[1:])
