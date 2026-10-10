# -*- coding: utf-8 -*-
"""IPScaner UI 统一修复层（可独立运行，也可被运行期钩子内联）。

诊断结论（全部有实测数字支撑，见 notes/UI审计报告.md）
------------------------------------------------------
1) 子窗体比主窗体小 1/3 —— 这是「文字看不清」与「风格旧」的同一个根因
   主窗体按 SCALE 渲染：本机 DPI=144 → theme.SCALE=1.5，主窗体客户区 1252x729，
   菜单/状态栏字体 = 微软雅黑 -18px（行高 24，每字宽 15.4px）。
   而 10 个子窗体一律按**设计像素 1:1** 建：
       `dialogs._font()` 返回 ('宋体', -12)  → 行高只有 12，每字宽 9.4px
   即子窗体文字只有主窗体的 **一半**，而且宋体是 Vista 之前的 UI 字体，
   小字号下发丝笔画发虚 —— 用户说的「很多文字都看不清」「十几年前的风格」即此。

   注意：这不是 replica 的 bug，绿色版原版也这样（原版 WinForms 子窗体没做
   DPI 自适应），所以按 SCALE 放大子窗体是「还原原版意图」。

2) 子窗体里还有 4 个窗体客户区装不下内容，控件被 place 静默裁掉
   （wifi 的「导出保存的密码」按钮整体不可见 —— 实测底边 445 > 客户区 422）
   另有 1 个完全被遮挡的冗余 Canvas 撑到 808px。

3) ttk 样式表把 Treeview 字体写死成「宋体 -12 / -11 bold」，改控件无效。

为什么可以安全等比缩放
----------------------
实测 10 个子窗体：**place 定位 100%、相对定位 0 个、缺 width/height 的 0 个**，
Canvas 内容只有「标题框」5 条线 + 1 个标题字。等比缩放不改变任何相对关系，
因此不会新产生重叠；4 个装不下的窗体按同样比例加高即可。

设计约束
--------
· 只用标准库 + tkinter，Python 3.10 可用（要能塞进 PyInstaller 运行期钩子）。
· 幂等：靠控件属性标记，重复调用不叠加。
· 绝不改写命名字体：改用「给控件/画布项显式设字体」，避免污染主窗体共用的字体。
· 容错：任何单个控件失败都不影响整体，全部 try/except 包住。
"""

DIALOG_FAMILY = "微软雅黑"
DESIGN_PX = -12          # 原版设计字号（负值=像素）
PX_STEP = (-1, -2, -3)   # 裁字时逐级回退的像素数（在目标字号上减）

SONG = ("宋体", "SimSun", "NSimSun", "新宋体", "simsun")
# 等宽字体不能换成微软雅黑（会毁掉列对齐）→ 换现代等宽 Consolas
FIXED_MAP = {"新宋体": "Consolas", "Fixedsys": "Consolas",
             "Terminal": "Consolas", "SimSun-ExtB": "Consolas"}
# dialogs.grid() 里硬编码的 ttk 样式
TTK_STYLES = ("Wb.Treeview", "Wb.Treeview.Heading")

# 客户区装不下内容的窗体：设计像素下的最小客户区
# （实测底边/右沿：portscan 671、wifi 445、addresscalc 333、ipsegment 715 右沿）
FORM_MIN = {
    "portscan": (670, 674),
    "wifi": (545, 448),
    "ipsegment": (717, 547),
    "addresscalc": (452, 336),
}

_M_SIZED = "_ipscaner_sized"
_M_SCALE = "_ipscaner_S"


def _theme():
    """取**已导入**的 theme 模块。

    修复层改的是产品运行期的行为，必须用产品那一份 theme（它带着
    set_scale_from 之后算出来的 SCALE），自己再 import 一份会拿到 SCALE=1.0
    的副本 —— 实测踩过。
    """
    try:
        import sys as _sys
        return _sys.modules.get("theme")
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ 小工具
def _spec_of(w):
    try:
        v = w.cget("font")
        if v:
            return str(v)
    except Exception:  # noqa: BLE001
        pass
    return None


def _is_named(spec):
    return bool(spec) and spec.startswith("font") and spec[4:].isdigit()


def _measure(tk_, spec, text):
    try:
        return int(float(tk_.call("font", "measure", spec, text)))
    except Exception:  # noqa: BLE001
        return 0


def _fam_of(tk_, spec):
    try:
        return str(tk_.call("font", "actual", spec, "-family"))
    except Exception:  # noqa: BLE001
        return ""


def _size_of(tk_, spec):
    try:
        return int(float(tk_.call("font", "actual", spec, "-size")))
    except Exception:  # noqa: BLE001
        return 0


def _text_of(w):
    try:
        t = w.cget("text")
        return str(t) if t else ""
    except Exception:  # noqa: BLE001
        return ""


def _pad_of(w):
    p = 0
    for prop in ("padx", "bd", "highlightthickness"):
        try:
            p += int(w.cget(prop))
        except Exception:  # noqa: BLE001
            pass
    return p


def _geo(w):
    return (w.winfo_x(), w.winfo_y(), w.winfo_width(), w.winfo_height())


def _all(w):
    res = []

    def walk(x):
        for k in x.winfo_children():
            res.append(k)
            walk(k)

    try:
        walk(w)
    except Exception:  # noqa: BLE001
        pass
    return res


def _scale_px(px, S):
    """设计像素 → 实际像素。负值=像素，正值=点（也要按比例放大）。"""
    if px == 0:
        return px
    if px < 0:
        return int(round(px * S))
    return int(round(px * S))


def _px_of_spec(tk_, spec):
    """把某个字体 spec 折算成「设计像素」：实际像素 / S 后再取负。"""
    sz = _size_of(tk_, spec)
    if sz < 0:
        return sz          # 已经是像素
    if sz > 0:
        return -sz         # 点 → 当像素处理（Tk 在 96dpi 下 1pt≈1.33px，
        #                    这里只用于「相对大小」判断，绝对值由 DESIGN_PX 兜底）
    return DESIGN_PX


# ------------------------------------------------------------------ 0. 主窗体
def remap_main(root, S=1.0, family=DIALOG_FAMILY, log=None):
    """主窗体：字体统一到 `family, DESIGN_PX*S`（即与主窗体自身字体同量级）。

    主窗体已按 SCALE 渲染（自身字体 = -12*S，画布坐标已乘 S），所以**不能动几何**；
    但画布上还残留 11 处宋体（font1/font2/font3：开始/停止/导出/列表展示/图例…），
    行高 18/20/21 与主窗体自身字体的 24 不齐 —— 同行一大一小。

    为什么要连字号一起归一，而不只换族：只换族时 font2(宋体 10pt) 会变成
    雅黑 10pt → 行高 28，反而比主窗体基准 24 **更大**（实测确实如此）。
    统一设成 -12*S = -18px 后 275 项全部行高 24，且比"只换族"更小/相等，
    不会引入新的撑破风险（已用画布 containment 复核）。

    固定宽度字体（新宋体/Fixedsys/Terminal）只换族为 Consolas、保持字号，
    否则列对齐会毁掉。
    """
    tk_ = root.tk
    tgt_px = _scale_px(DESIGN_PX, S)
    hit = 0
    try:
        names = list(tk_.call("font", "names"))
    except Exception:  # noqa: BLE001
        names = []
    for n in names:
        fam = _fam_of(tk_, n)
        if fam in FIXED_MAP:
            try:
                tk_.call("font", "configure", n, "-family", FIXED_MAP[fam])
                hit += 1
                if log is not None:
                    log("主窗体等宽字体 %s %s -> %s" % (n, fam, FIXED_MAP[fam]))
            except Exception:  # noqa: BLE001
                pass
        elif fam in SONG:
            try:
                tk_.call("font", "configure", n, "-family", family, "-size", tgt_px)
                hit += 1
                if log is not None:
                    log("主窗体命名字体 %s %s -> %s %d" % (n, fam, family, tgt_px))
            except Exception:  # noqa: BLE001
                pass
    return hit


def _ready(win):
    """窗口几何是否已由窗口管理器结算。

    必须判这个：Tk 在窗口还没 map 完时 `win.geometry()` 会返回占位值 **1x1**，
    子控件的 winfo_x/y/width/height 也全是 0/请求值。实测踩坑：拿到 1x1 后
    把窗体设成 2x2、控件全被钳成 8x8 —— 整个窗体被压扁。
    """
    try:
        win.update_idletasks()
        return win.winfo_width() > 1 and win.winfo_height() > 1
    except Exception:  # noqa: BLE001
        return False


def design_size(key):
    """从 dialogs.FORMS 取设计尺寸（不依赖窗口自报），并按 FORM_MIN 抬到够装。"""
    w = h = None
    try:
        import dialogs
        spec = (getattr(dialogs, "FORMS", {}) or {}).get(key)
        if spec and len(spec) >= 3:
            w, h = int(spec[1]), int(spec[2])
    except Exception:  # noqa: BLE001
        pass
    if w is None:
        return None
    if key in FORM_MIN:
        mw, mh = FORM_MIN[key]
        w, h = max(w, mw), max(h, mh)
    return w, h


# ------------------------------------------------------------------ 1. 子窗体等比放大
def scale_dialog(win, S, key=None, family=DIALOG_FAMILY, log=None, absolute=True):
    """把子窗体从设计像素(1:1)放大到与主窗体同比例(S)。

    目标字号 = DESIGN_PX * S（本机 1.5 → -18px，与主窗体 tk_f_menu 完全一致）。

    absolute=True ：S 是「绝对缩放比」，窗体尺寸取 FORMS 设计值 × S。
    absolute=False：S 是「相对比例」，窗体尺寸取**当前尺寸 × S**
                    （用于主窗体 Ctrl+滚轮改比例后，把已打开的子窗体跟着放大）。

    返回 None 表示「窗口几何还没结算，这轮跳过」—— 调用方必须下轮重试，
    不能把 None 当成功（否则会拿占位尺寸把窗体压扁）。
    """
    if S <= 0:
        return {"places": 0, "fonts": 0, "items": 0, "canvas": 0}
    if not _ready(win):
        return None
    tk_ = win.tk
    stat = {"places": 0, "fonts": 0, "items": 0, "canvas": 0}
    tgt_px = _scale_px(DESIGN_PX, S)

    # ---- ⓪ 先快照全部后代的 (x,y,w,h)，必须在改任何东西之前读
    #     为什么不能只看 place_info()['width']：place 允许只给 x,y，
    #     尺寸由 widget 自身的 width/height 选项决定（Canvas 常见），
    #     这类控件 place_info()['width'] 是空串，会被漏掉 ——
    #     实测漏掉了 ipsegment 的 (160,470,144,338) canvas（坐标缩了、尺寸没缩）。
    nodes = []

    def snap(w):
        for c in w.winfo_children():
            try:
                pi = c.place_info()
            except Exception:  # noqa: BLE001
                pi = {}
            if pi:
                ww, hh = c.winfo_width(), c.winfo_height()
                if ww <= 1:
                    ww = c.winfo_reqwidth()
                if hh <= 1:
                    hh = c.winfo_reqheight()
                nodes.append((c, c.winfo_x(), c.winfo_y(), ww, hh))
            snap(c)

    try:
        snap(win)
    except Exception:  # noqa: BLE001
        pass

    # ---- ① 窗体自身尺寸：优先用 FORMS 设计值推导（确定性），退而读当前几何
    try:
        cur = win.geometry()
        size = cur.split("+")[0]
        cw, ch = (int(v) for v in size.split("x"))
        pos = "+" + cur.split("+", 1)[1] if "+" in cur else ""
        if key:
            win._ipscaner_key = key
        dk = design_size(key) if (key and absolute) else None
        if dk:
            w, h = dk
        else:
            w, h = cw, ch
        nw, nh = int(round(w * S)), int(round(h * S))
        if key in FORM_MIN:
            mw, mh = FORM_MIN[key]
            nw = max(nw, int(round(mw * S)))
            nh = max(nh, int(round(mh * S)))
        # 平台上限：Tk/Windows 会把超过 maxsize 的请求**静默钳掉**
        # （实测屏幕 960 高 → maxsize 高 941，请求 946 结算成 941）。
        # 这里先自己钳，免得日志报的和实际几何对不上，也免得下面
        # 「拉回屏内」按一个根本落不了地的尺寸去算 ny。
        clamped = False
        try:
            mx, my = win.maxsize()
            if mx and mx > 1 and nw > mx:
                nw, clamped = mx, True
            if my and my > 1 and nh > my:
                nh, clamped = my, True
        except Exception:  # noqa: BLE001
            pass
        if clamped and log is not None:
            log("窗体 %s 请求 %dx%d 超过平台上限 → 压到 %dx%d"
                % (key, int(round(w * S)), int(round(h * S)), nw, nh))
        # 记下本次请求的**目标客户区尺寸**：clamp_settled() 靠它判断
        # winfo 尺寸有没有结算（wm geometry 是异步的，见 clamp_settled 头注）。
        try:
            win._ipscaner_target = (nw, nh)
        except Exception:  # noqa: BLE001
            pass
        win.geometry("%dx%d%s" % (nw, nh, pos))
        if log is not None:
            log("窗体 %s %dx%d -> %dx%d%s" % (key, w, h, nw, nh,
                                             "" if dk else " (读当前几何)"))
        # 放大后可能跑出屏幕 → 把左上角拉回屏内（保持尺寸不变）
        try:
            if pos:
                px_, py_ = (int(v) for v in pos[1:].split("+", 1))
                sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
                nx = min(px_, max(0, sw - nw - 8))
                ny = min(py_, max(0, sh - nh - 40))
                if (nx, ny) != (px_, py_):
                    win.geometry("%dx%d+%d+%d" % (nw, nh, nx, ny))
                    if log is not None:
                        log("位置拉回屏内 (%d,%d) -> (%d,%d)" % (px_, py_, nx, ny))
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass

    # ---- ② 统一缩放 place 几何（含自动尺寸控件）
    for c, x, y, w, h in nodes:
        try:
            c.place_configure(x=int(round(x * S)), y=int(round(y * S)),
                              width=max(1, int(round(w * S))),
                              height=max(1, int(round(h * S))))
            stat["places"] += 1
        except Exception:  # noqa: BLE001
            pass

    # ---- ③ 控件字体（含 Canvas 内容）
    for c in _all(win):
        try:
            spec = _spec_of(c)
            if spec:
                fam = _fam_of(tk_, spec)
                if fam in SONG or fam in FIXED_MAP or _is_named(spec):
                    c.configure(font=(family, tgt_px))
                    stat["fonts"] += 1
            if c.winfo_class() == "Canvas":
                stat["canvas"] += 1
                _scale_canvas(c, S, family, tgt_px, stat, log)
        except Exception:  # noqa: BLE001
            pass

    # ---- ④ ttk 样式（Treeview 字号写死在样式表里）
    fix_ttk(win, family=family, px=tgt_px, log=log)
    # ---- ⑤ 层叠缺陷纠正（必须放在这里：scale_dialog 每次都从
    #     winfo_width/height 重新快照再 place 回去，所以任何在它**之后**
    #     才做的修正，都会在下一轮 sweep 被乘回去（实测修复无效）。
    #     放在函数内、几何刚落定的这一刻，每轮都会纠正一次。
    try:
        fix_overlaps(win, log=log)
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("层叠修复失败 %r" % (e,))
    # ---- ⑤b 残留死控件收尾（连同 ⑤ 一起放在函数内，理由相同）
    try:
        hide_dead_combos(win, S, log=log)
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("死控件收尾失败 %r" % (e,))
    # ---- ⑥ 现代化主题（苹果风浅色）：颜色/边框/按钮/滚动条。
    #     与 ⑤ 同级的理由相同：必须在 scale_dialog 内部做，
    #     且全部幂等（重跑是空操作），滚动条靠 yscrollcommand 判重。
    try:
        beautify_dialog(win, S, log=log)
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("主题美化失败 %r" % (e,))
    return stat


# ------------------------------------------------------------------ 4.96 现代化主题
# 2026-10-07 用户要求：「UI 太丑、排版不清楚、很多滚动条没有」，
# 风格对齐苹果液态玻璃 —— 已确认的验收口径是**风格方向**（现代浅色主题），
# 不做真·毛玻璃模糊（Tk 做不了 vibrancy，强上半透明只会牺牲可读性）。
#
# 设计语言（取自 Apple HIG 的浅色体系）：
#   窗体底 #F5F5F7（systemGray6）｜ 内容卡片 #FFFFFF ｜ 主文字 #1D1D1F
#   次文字 #86868B ｜ 边框 #D2D2D7 ｜ 强调色 Apple Blue 系（按对比度自动压暗
#   到白字 ≥4.5，Apple 原版 #007AFF 白字只有 ~4.0，直接抄会重蹈对比度覆辙）
#
# 实现约束：全部是 place 布局 + 字节码不可改 → 只能运行时改外观选项，
# 不重排坐标（那会把已修好的几何全打乱）。滚动条是唯一允许动的几何：
# 把控件宽度收 14px、在旁边放一个 ttk.Scrollbar。

APPLE_BG = "#F5F5F7"        # 窗体底色（Apple systemGray6）
APPLE_CARD = "#FFFFFF"      # 内容卡片
APPLE_TEXT = "#1D1D1F"      # 主文字
APPLE_TEXT2 = "#6E6E73"     # 次文字
APPLE_BORDER = "#D2D2D7"    # 描边
APPLE_SELECT = "#E8F0FE"    # 悬停/选中浅蓝
APPLE_ACCENT_BASE = "#007AFF"   # Apple Blue（原始值，白字对比度不足）
APPLE_SB = 14               # 滚动条宽（设计 px，随 S 缩放）

# 产品「悬浮高亮」用的颜色（theme.C_MENU_SELECT，实测 #C9E4FF）。
# 我们靠它把画布上的悬浮方块认出来 → 改成描边环。
HOVER_SEL = "#C9E4FF"


def _hover_sel():
    """取 theme.C_MENU_SELECT（取不到就用实测值兜底）。"""
    try:
        import sys as _sys
        _T = _sys.modules.get("theme")
        v = getattr(_T, "C_MENU_SELECT", None)
        if isinstance(v, str) and v.startswith("#"):
            return v
    except Exception:  # noqa: BLE001
        pass
    return HOVER_SEL


_APPLE_ACCENT_CACHE = None


def _apple_accent():
    """把 Apple Blue 压暗到白字对比度 ≥4.5 的版本（缓存）。"""
    global _APPLE_ACCENT_CACHE
    if _APPLE_ACCENT_CACHE:
        return _APPLE_ACCENT_CACHE
    acc = APPLE_ACCENT_BASE
    cur = _rgb(acc)
    for _ in range(60):
        c = contrast_hex("#FFFFFF", acc)
        if c is not None and c >= 4.5:
            break
        cur = tuple(max(0, int(v * 0.94)) for v in cur)
        acc = "#%02X%02X%02X" % cur
    _APPLE_ACCENT_CACHE = acc
    return acc


# 看起来像「主操作」的按钮文案 → 蓝底白字；其余 → 白卡灰边
_ACCENT_WORDS = ("开始", "计算", "生成", "确定", "保存", "扫描")


def install_apple_theme(root, log=None):
    """全局 ttk 样式表：Treeview/滚动条/Combobox/按钮 的现代浅色外观。"""
    try:
        from tkinter import ttk
    except Exception:  # noqa: BLE001
        return False
    try:
        st = ttk.Style(root)
        try:
            st.theme_use("clam")
        except Exception:  # noqa: BLE001
            pass
        st.configure("Treeview",
                     background=APPLE_CARD, fieldbackground=APPLE_CARD,
                     foreground=APPLE_TEXT, borderwidth=0)
        st.configure("Treeview.Heading",
                     background=APPLE_BG, foreground=APPLE_TEXT,
                     relief="flat", borderwidth=1)
        st.map("Treeview.Heading", background=[("active", APPLE_SELECT)])
        st.map("Treeview",
               background=[("selected", APPLE_SELECT)],
               foreground=[("selected", APPLE_TEXT)])
        st.configure("Vertical.TScrollbar",
                     background="#C7C7CC", troughcolor=APPLE_BG,
                     bordercolor=APPLE_BG, arrowcolor=APPLE_TEXT2,
                     relief="flat", borderwidth=0)
        st.map("Vertical.TScrollbar", background=[("active", "#AEAEB2")])
        st.configure("TCombobox",
                     fieldbackground=APPLE_CARD, background=APPLE_CARD,
                     foreground=APPLE_TEXT, bordercolor=APPLE_BORDER)
        st.configure("TCheckbutton", background=APPLE_BG, foreground=APPLE_TEXT)
        if log is not None:
            log("Apple 风 ttk 主题已安装（accent=%s）" % _apple_accent())
        return True
    except Exception:  # noqa: BLE001
        return False


def _is_scrollable(c):
    return c.winfo_class() in ("Treeview", "Text", "Listbox")


def ensure_scrollbars(win, S, log=None):
    """给缺滚动条的 Treeview/Text/Listbox 补一个（用户点名「很多滚动条没有」）。

    判重：yscrollcommand 非空 = 已有，跳过（天然幂等）。
    几何：把控件宽度收 SB px，在旁边放滚动条 —— place 布局下唯一安全的做法。
    """
    added = []
    try:
        from tkinter import ttk
    except Exception:  # noqa: BLE001
        return added
    sb_px = max(10, int(APPLE_SB * S))
    for c in win.winfo_children():
        try:
            if not _is_scrollable(c):
                continue
            try:
                if c.cget("yscrollcommand"):
                    continue                       # 已有
            except Exception:  # noqa: BLE001
                continue
            info = c.place_info()
            if not info:
                continue
            x = int(info.get("x") or c.winfo_x())
            y = int(info.get("y") or c.winfo_y())
            wv, hv = info.get("width"), info.get("height")
            w = int(wv) if wv not in (None, "") else c.winfo_width()
            h = int(hv) if hv not in (None, "") else c.winfo_height()
            if w <= sb_px + 40 or h <= 40:
                continue
            sb = ttk.Scrollbar(win, orient="vertical", command=c.yview)
            c.configure(yscrollcommand=sb.set)
            c.place_configure(width=w - sb_px)
            sb.place(x=x + w - sb_px, y=y, width=sb_px, height=h)
            added.append((c.winfo_class(), x, y, w, h))
            if log is not None:
                log("补滚动条 %s @%d,%d %dx%d" % (c.winfo_class(), x, y, w, h))
        except Exception:  # noqa: BLE001
            pass
    return added


def beautify_dialog(win, S=1.0, log=None):
    """子窗体现代化：统一底色/文字色/描边/按钮样式 + 补滚动条。幂等。"""
    done = {"label": 0, "btn": 0, "entry": 0, "sb": 0}
    try:
        if not win.winfo_exists():
            return done
        win.configure(bg=APPLE_BG)
    except Exception:  # noqa: BLE001
        return done
    accent = _apple_accent()
    for c in win.winfo_children():
        try:
            cls = c.winfo_class()
            if cls == "Label":
                c.configure(bg=APPLE_BG, fg=APPLE_TEXT)
                done["label"] += 1
            elif cls == "Button":
                txt = ""
                try:
                    txt = c.cget("text") or ""
                except Exception:  # noqa: BLE001
                    pass
                if any(k in txt for k in _ACCENT_WORDS):
                    c.configure(bg=accent, fg="#FFFFFF",
                                activebackground=accent, activeforeground="#FFFFFF",
                                relief="flat", bd=0, cursor="hand2",
                                highlightthickness=0)
                else:
                    c.configure(bg=APPLE_CARD, fg=APPLE_TEXT,
                                activebackground=APPLE_SELECT,
                                activeforeground=APPLE_TEXT,
                                relief="flat", bd=0, cursor="hand2",
                                highlightthickness=1,
                                highlightbackground=APPLE_BORDER,
                                highlightcolor=accent)
                done["btn"] += 1
            elif cls == "Entry":
                c.configure(bg=APPLE_CARD, fg=APPLE_TEXT, relief="flat", bd=0,
                            highlightthickness=1,
                            highlightbackground=APPLE_BORDER,
                            highlightcolor=accent,
                            insertbackground=APPLE_TEXT)
                done["entry"] += 1
            elif cls == "Text":
                c.configure(bg=APPLE_CARD, fg=APPLE_TEXT, relief="flat", bd=0,
                            highlightthickness=1,
                            highlightbackground=APPLE_BORDER,
                            highlightcolor=accent)
                done["entry"] += 1
            elif cls == "Checkbutton":
                c.configure(bg=APPLE_BG, fg=APPLE_TEXT,
                            activebackground=APPLE_BG,
                            selectcolor=APPLE_CARD)
            elif cls == "Canvas":
                pass                                  # 自绘区域不动
        except Exception:  # noqa: BLE001
            pass
    done["sb"] = len(ensure_scrollbars(win, S, log=log))
    return done


def beautify_main(root, log=None):
    """主窗体轻修饰：只动窗口级默认字体与底色，不碰 IP 网格画布。"""
    try:
        root.configure(bg=APPLE_BG)
        root.option_add("*Toplevel*background", APPLE_BG)
        return True
    except Exception:  # noqa: BLE001
        return False



def _scale_canvas(cv, S, family, tgt_px, stat, log=None):
    """Canvas 内容 = 标题框（5 条 line + 1 个标题 text），about 窗另有一张 image。

    cv.scale 会把 line/text 的**坐标**一起缩放，但不会缩放字号、更不会缩放图片
    （Tk 的 canvas scale 只动坐标）。所以字号单独设，图片用 image copy 的
    -zoom/-subsample 做 1.5 倍（3:2）。
    """
    try:
        cv.scale("all", 0, 0, S, S)
    except Exception:  # noqa: BLE001
        return
    try:
        items = cv.find_all()
    except Exception:  # noqa: BLE001
        return
    for i in items:
        try:
            t = cv.type(i)
            if t == "text":
                cv.itemconfigure(i, font=(family, tgt_px))
                stat["items"] += 1
            elif t == "image":
                if _zoom_item(cv, i, S, stat) and log is not None:
                    log("画布图片放大 %.2fx" % S)
        except Exception:  # noqa: BLE001
            pass


def _zoom_item(cv, item, S, stat):
    """用纯 Tcl 把画布上的图片放大 S 倍（3:2 → 1.5）。

    不能走 tkinter.PhotoImage(name=...) —— 它的 __init__ 会执行
    `image create photo <name>`，对一个已存在的图名会直接报
    「image already exists」；只能 raw Tcl：先 copy 到临时图，再带
    -zoom/-subsample copy 到新图。
    """
    tk_ = cv.tk
    num, den = int(round(S * 4)), 4
    from math import gcd
    g = gcd(num, den)
    num, den = num // g, den // g
    if (num, den) == (1, 1):
        return False
    name = cv.itemcget(item, "image")
    if not name:
        return False
    try:
        src = str(tk_.call("image", "create", "photo"))     # 临时中转
        dst = str(tk_.call("image", "create", "photo"))
        tk_.call(src, "copy", name)
        tk_.call(dst, "copy", src, "-zoom", num, "-subsample", den)
        tk_.call("image", "delete", src)
        cv.itemconfigure(item, image=dst)
        stat["items"] += 1
        return True
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------ 2. ttk 样式
def fix_ttk(win, family=DIALOG_FAMILY, px=DESIGN_PX, log=None):
    """dialogs.grid() 把 Treeview 表头/正文字体写死成「宋体 -12 / -11 bold」，
    不在控件 font 选项上，改控件没用，必须改 ttk 样式表。

    rowheight 同步放大：字体行高 24，rowheight=30 才不会顶格。
    """
    out = []
    try:
        from tkinter import ttk
    except Exception:  # noqa: BLE001
        return out
    for st in TTK_STYLES:
        try:
            head = st.endswith("Heading")
            ttk.Style(win).configure(
                st, font=(family, px, "bold") if head else (family, px),
                **({} if head else {"rowheight": abs(px) + 12})
            )
            out.append(st)
            if log is not None:
                log("ttk %s -> %s %d%s" % (st, family, px, " bold" if head else ""))
        except Exception:  # noqa: BLE001
            pass
    return out


# ------------------------------------------------------------------ 3. 裁字自我修复
def _row_limit(w):
    """同排右侧邻居之前、父客户区之内 —— 加宽的最大右沿（像素）。"""
    try:
        par = w.master
        x, y, ww, wh = _geo(w)
        limit = par.winfo_width() - 2
    except Exception:  # noqa: BLE001
        return None
    for s in par.winfo_children():
        if s is w:
            continue
        try:
            sx, sy, sw, sh = _geo(s)
        except Exception:  # noqa: BLE001
            continue
        if sw <= 1 and sh <= 1:
            continue
        if (sy < y + wh - 1) and (sy + sh > y + 1) and sx >= x + ww - 1:
            limit = min(limit, sx - 4)
    return limit


def repair_clipping(win, family=DIALOG_FAMILY, log=None):
    """文字宽于控件 → 先加宽（安全范围内），加不下就降字号。返回处理清单。"""
    tk_ = win.tk
    fixed, faded, stuck = [], [], []

    def _one(w):
        text = _text_of(w)
        if not text or "\n" in text:
            return
        spec = _spec_of(w)
        if not spec:
            return
        try:
            if not w.place_info():
                return
        except Exception:  # noqa: BLE001
            return
        x, y, ww, wh = _geo(w)
        if ww <= 1:
            return
        need = _measure(tk_, spec, text)
        pad = _pad_of(w)
        avail = ww - pad
        if need <= avail + 1:
            return
        limit = _row_limit(w)
        if limit is not None:
            target = min(need + pad + 2, limit - x)
            if target > ww:
                try:
                    w.place_configure(width=target)
                    fixed.append((text, ww, target))
                    return
                except Exception:  # noqa: BLE001
                    pass
        base = _size_of(tk_, spec)
        for step in PX_STEP:
            px = (base - step) if base < 0 else (base + step)
            try:
                w.configure(font=(family, px))
            except Exception:  # noqa: BLE001
                break
            if _measure(tk_, w.cget("font"), text) <= avail + 1:
                faded.append((text, px))
                return
        stuck.append((text, need, avail))

    for k in _all(win):
        try:
            _one(k)
        except Exception:  # noqa: BLE001
            pass
    if log is not None:
        for t in fixed:
            log("加宽 %r %d -> %d" % (t[0][:24], t[1], t[2]))
        for t in faded:
            log("降字号 %r -> %dpx" % (t[0][:24], t[1]))
        for t in stuck:
            log("仍不足 %r 需%d 可用%d" % (t[0][:24], t[1], t[2]))
    return {"fixed": fixed, "faded": faded, "stuck": stuck}


# ------------------------------------------------------------------ 4. 越界钳制
def clamp_overflow(win, log=None):
    """把超出客户区的直接子控件**收短**（只改高/宽，绝不移动）。

    超出部分本来就被 place 裁掉看不见，收短后可见区域完全一致 ——
    视觉零变化、几何归零。ipsegment 那个被完全遮挡的冗余 Canvas（撑到 808px）
    就是这样归零的。
    """
    done = []
    try:
        if not win.winfo_exists():
            return done
        CW, CH = win.winfo_width(), win.winfo_height()
    except Exception:  # noqa: BLE001
        return done
    for c in win.winfo_children():
        try:
            info = c.place_info()
            if not info or "width" not in info or "height" not in info:
                continue
            x, y, w, h = _geo(c)
            if w <= 1 or h <= 1:
                continue
            nw, nh = w, h
            if x + w > CW:
                nw = max(8, CW - x)
            if y + h > CH:
                nh = max(8, CH - y)
            if (nw, nh) == (w, h):
                continue
            c.place_configure(width=nw, height=nh)
            done.append((c.winfo_class(), x, y, w, h, nw, nh))
            if log is not None:
                log("钳制 %s (%d,%d) %dx%d -> %dx%d"
                    % (c.winfo_class(), x, y, w, h, nw, nh))
        except Exception:  # noqa: BLE001
            pass
    return done


# 等 winfo 尺寸追平 geometry() 请求的轮询参数（25ms × 40 ≈ 1s 上限）
_CLAMP_SETTLE_TRIES = 40
_CLAMP_SETTLE_MS = 25


def clamp_settled(win, log=None, tries=0):
    """**等窗口几何结算之后**再 repair_clipping + clamp_overflow。

    ⚠️ 为什么必须有这个函数（2026-10-09 缺陷13 修复的**自伤**，真机截图发现）：
      `win.geometry("864x946")` 只是把请求**写进 WM 队列**，是**异步**的；
      Tk 的 winfo_width/height 要等收到 WM 的 ConfigureNotify 才更新，而
      `update_idletasks()` **只刷空闲回调、不处理 WM 消息** —— 所以
      geometry() 刚调完的那个瞬间，winfo_height() 还是缩之前的旧值。

      defer_show 原来就在这里**同步**调 clamp_overflow：它读 CH=631（旧值，
      目标是 946），于是把 y≥631 的每一行都 `nh = max(8, 631-y)` ——
      「一键设置IP」的「历史IP：」标签 + 保存设置/关闭按钮全被钳成 **8px 高的
      废条**（真机截图 exe_1259_d13_localip.png 底部那两条细条就是它们）。

    正确做法：拿 scale_dialog 记下的 `_ipscaner_target` 当期望值，winfo 追平了
    再钳；追不平（窗口被关、被平台钳到别的值、极慢）就**放弃**并把原因写日志
    —— 越界部分本来就被 place 裁掉看不见，放弃的视觉后果为零，交给 sweep 的
    稳态分支兜底即可（那时窗口已 map 完，winfo 一定是准的）。

    返回 True 表示已结算并钳过。
    """
    try:
        if not win.winfo_exists():
            return False
    except Exception:  # noqa: BLE001
        return False
    tgt = getattr(win, "_ipscaner_target", None)
    try:
        ww, hh = win.winfo_width(), win.winfo_height()
    except Exception:  # noqa: BLE001
        return False
    if tgt and abs(ww - tgt[0]) <= 2 and abs(hh - tgt[1]) <= 2:
        try:
            repair_clipping(win, log=log)
            clamp_overflow(win, log=log)
        except Exception:  # noqa: BLE001
            pass
        return True
    if tries < _CLAMP_SETTLE_TRIES:
        try:
            win.after(_CLAMP_SETTLE_MS,
                      lambda: clamp_settled(win, log=log, tries=tries + 1))
            return False
        except Exception:  # noqa: BLE001
            pass
    if log is not None:
        log("钳制延后：%r winfo=%dx%d 未追平目标 %s（放弃，交给 sweep 稳态）"
            % (win.title(), ww, hh, tgt))
    return False


# ------------------------------------------------------------------ 4.9 控件层叠冲突消解
# 2026-10-04 像素级截图验收新发现的三类缺陷（前两轮因抓不到图而误判为「无问题」）：
#
#   缺陷 1  备注信息管理：Treeview 底边 806 > 按钮行顶边 773，垂直重叠 33px
#           → 4 个按钮（新增/修改/删除/导入剪贴板数据）**只露出下半截文字**。
#              实测 888x592 下 Treeview 849x459+18+114，按钮行 +540 起。
#   缺陷 2  IP地址计算器：「可用地址:」+18+111 与「IP/掩码位:」+18+117
#           y 差 6px、x 起点相同 → 两个 Label **100% 叠印**，笔画互相穿插。
#           另有两组重复标签（[11]/[24] 都是"掩码:"，[13]/[25] 都是"网络:"），
#           位置完全相同 —— 控件被重复创建，后建的盖住先建的。
#   缺陷 4  「关于」窗体内的只读 Text 仍显示旧版本号（标题栏已改，窗体内是副本）。
#
# 本函数只动**几何**（place 的 x/y/width/height），不碰业务逻辑、不重建控件。
# 幂等：打 tag `_LAYFIX_TAG`，同一控件不会被反复搬动。
#
# 为什么不在 src/ 改：交付的 exe 是从绿色版**字节码**打包的，改 src/ 不生效；
# 运行时改几何对所有已打包版本都生效，是唯一一条对存量 exe 有效的路。

# 需要「让位」的大面积控件：把这些当作遮挡源处理
_BLOCKER_CLASSES = ("Treeview", "Listbox", "Text", "Canvas", "Entry")


def _children_geo(win):
    """→ [(widget, x, y, w, h, cls)]，只取 place 定位且有面积的直接子控件。

    ⚠️ 踩过的坑：**不能用 `c.winfo_x/y/width/height` 当 place 坐标**。
    `winfo_x/y` 是**父窗体坐标系**里的绝对位置（多算了窗体边框/标题栏，
    实测差 5~50px），而 `place_info()['x']` 才是布局坐标。
    同样 `place` 允许只给 x/y、尺寸由控件自身选项决定（Canvas 常见），
    此时 `place_info()['width']` 是空串 —— 必须回退到 winfo_*，
    否则整个 Canvas 家族会被静默漏掉（实测 _children_geo 曾返回空列表）。
    """
    out = []
    for c in win.winfo_children():
        try:
            if not c.winfo_exists():
                continue
            # ⚠️ `overrideredirect()` **只有 Toplevel 有**，普通控件
            # (Canvas/Button/Label/Treeview) 调它会 AttributeError。
            # 之前直接调且被 except 静默吞掉 → 整个列表恒为空 → 修复全程空转。
            if hasattr(c, "overrideredirect") and c.overrideredirect():
                continue
            info = c.place_info()
            if not info:
                continue
            x = int(info.get("x") or c.winfo_x())
            y = int(info.get("y") or c.winfo_y())
            # width/height 可能缺省或空串（Canvas 常见），回退到实际尺寸
            wv = info.get("width")
            hv = info.get("height")
            w = int(wv) if wv not in (None, "") else c.winfo_width()
            h = int(hv) if hv not in (None, "") else c.winfo_height()
            if w <= 1 or h <= 1:
                continue
            out.append((c, x, y, w, h, c.winfo_class()))
        except Exception:  # noqa: BLE001
            pass
    return out


def _overlap(a, b):
    """两个 (x,y,w,h) 的重叠像素数。"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ox = min(ax + aw, bx + bw) - max(ax, bx)
    oy = min(ay + ah, by + bh) - max(ay, by)
    if ox <= 0 or oy <= 0:
        return 0, 0
    return ox, oy


def fix_overlap_memo(win, log=None):
    """缺陷 1：备注信息管理 —— 列表压住底部按钮行。

    判据：Treeview 的底边**超过**最靠下的按钮行顶边 4px 以上，
    且横向确实与该按钮有交集。动作：把 Treeview 收短到按钮行上方留 6px 缝。

    实测值：Treeview 849x459+18+114（底 573），按钮行 +540（顶 540）
            → 需收短 459 → 420（差 39px，即 33px 重叠 + 6px 缝）。
    """
    done = []
    try:
        if not win.winfo_exists():
            return done
        kids = _children_geo(win)
        trees = [k for k in kids if k[5] == "Treeview"]
        btns = [k for k in kids if k[5] == "Button"]
        if not trees or not btns:
            return done
        for tw, tx, ty, twid, tht, _ in trees:
            # 最靠下的按钮行（y 最大）
            band = max(btns, key=lambda b: b[2])
            bx, by, bw, bh = band[1], band[2], band[3], band[4]
            ox, oy = _overlap((tx, ty, twid, tht), (bx, by, bw, bh))
            if oy <= 4 or ox <= 0:
                continue
            limit = by - 6                      # 按钮行上方留 6px 缝
            nh = limit - ty
            if nh >= tht - 4 or nh < 40:         # 收益太小或会压扁，跳过
                continue
            try:
                tw.place_configure(height=nh)
                done.append(("Treeview", ty, tht, nh))
                if log is not None:
                    log("缺陷1 Treeview 收短 %d -> %d（让出按钮行）" % (tht, nh))
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return done


def fix_overlap_calc(win, log=None):
    """缺陷 2：IP 地址计算器 —— 两个 Label 叠印。

    判据：两个 Label 的 x 起点相同、宽度有重叠、|Δy| < 高（即垂直叠印），
    且两者**文字都非空且不同**。动作：把 y 较大的那个下移到前一个的底边之下。
    同位置同文字的重复控件（[11]/[24]、[13]/[25]）直接隐藏后建的那个。
    """
    done = []
    try:
        if not win.winfo_exists():
            return done
        labels = [k for k in _children_geo(win) if k[5] == "Label"]
        used = set()
        for i, (a, ax, ay, aw, ah, _) in enumerate(labels):
            if id(a) in used:
                continue
            ta = (_text_of(a) or "").strip()
            for b, bx, by, bw, bh, _ in labels[i + 1:]:
                if id(b) in used:
                    continue
                tb = (_text_of(b) or "").strip()
                if not ta or not tb:
                    continue
                ox, oy = _overlap((ax, ay, aw, ah), (bx, by, bw, bh))
                if ox <= 2 or oy <= 2:
                    continue
                same_x = abs(ax - bx) <= 2
                # 已被移出客户区的（x/y 远大于窗体尺寸）跳过，避免反复搬动
                try:
                    CW0, CH0 = win.winfo_width(), win.winfo_height()
                except Exception:  # noqa: BLE001
                    CW0 = CH0 = 0
                if ax > CW0 + 8 or ay > CH0 + 8:
                    used.add(id(a))
                    continue
                # ⚠️ 判据（踩坑后修正）：**文字不同 + y 相同**是「表头 Label
                #   + 内容 Label」的设计（about 窗 '产品名称' 与
                #   '局域网IP扫描工具' 同为 360,28，anchor 不同、故意重叠），
                #   **不是缺陷，不能动**。只有下面两种才算。
                if ta != tb and ay == by:
                    continue
                try:
                    if ta == tb and same_x:
                        # 完全重复：后建的盖住先建的。
                        # ⚠️ 用「移到客户区外」而不是 `place_forget()` ——
                        # place_forget 会让控件脱离布局树，后续 `_all()` /
                        # `winfo_children()` 遍历到它时行为不稳（实测
                        # addresscalc 窗体抓图静默退出、about 段日志全空）。
                        # 移到客户区外视觉完全一致，但控件还活着，可逆。
                        try:
                            CW, CH = win.winfo_width(), win.winfo_height()
                            b.place_configure(x=CW + 40, y=CH + 40)
                            used.add(id(b))
                            done.append(("Label-dup", tb, "moved-off"))
                            if log is not None:
                                log("缺陷2 移出重复标签 %r" % tb)
                        except Exception:  # noqa: BLE001
                            pass
                    elif same_x and ay != by:
                        # 文字不同且叠印：把 y 大的那个下移
                        hi, lo = (b, by) if by > ay else (a, ay)
                        ref = ay if by > ay else by
                        hgt = ah if by > ay else bh
                        nhy = ref + hgt + 4
                        hi.place_configure(y=nhy)
                        used.add(id(hi))
                        done.append(("Label", "%r|%r" % (ta, tb), ref, nhy))
                        if log is not None:
                            log("缺陷2 标签下移 %r/%r  y=%d -> %d" % (ta, tb, ref, nhy))
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass
    return done


def fix_btn_cut(win, log=None):
    """缺陷 5：按钮右/左缘被 z 序更高的**大容器**盖住，文字被切。

    实测（ipsegment，1076x820）：'停止扫描' (150,528,124,40) 被
    Canvas (240,192,824,507) 横向切入 34px → 文字变成「停止扫扌」。

    判据：Button 的一侧（x 方向）伸进了另一个**创建更晚**（z 序更高）
    的大容器（Canvas/Treeview/Listbox/Frame）里，且被切宽度 > 2px。
    动作：把 Button 的宽度收窄到容器的左边界 - 4px 缝。

    只处理 x 方向切入（垂直切入是布局问题，不动）——实测缺陷 1 那种
    「下边界被压」是反过来的（容器压按钮），已由 fix_overlap_memo 负责。
    """
    done = []
    try:
        if not win.winfo_exists():
            return done
        kids = _children_geo(win)
        order = {id(c): i for i, c in enumerate(win.winfo_children())}
        blockers = [k for k in kids
                    if k[5] in ("Canvas", "Treeview", "Listbox", "Frame")]
        btns = [k for k in kids if k[5] == "Button"]
        for b, bx, by, bw, bh, _ in btns:
            zi = order.get(id(b), 0)
            for c, cx, cy, cw, ch, ccls in blockers:
                if order.get(id(c), 0) <= zi:      # 必须 z 序更高（后创建）
                    continue
                if cy >= by + bh - 2 or cy + ch <= by + 2:
                    continue                      # y 不相交，无横向切入
                # 右侧切入
                if cx > bx and cx < bx + bw - 2:
                    nw = cx - 4 - bx
                    if 24 < nw < bw - 2:
                        b.place_configure(width=nw)
                        done.append(("Btn-right", c.cget("text") if ccls == "Button" else "", bw, nw))
                        if log is not None:
                            log("缺陷5 按钮右侧被 %s 盖 %dpx，收窄 %d -> %d"
                                % (ccls, bx + bw - cx, bw, nw))
                        bw = nw                        # 收窄后继续看左边
                # 左侧切入
                elif cx + cw > bx and cx + cw < bx + bw - 2:
                    cut = bx + bw - (cx + cw)
                    nw = bw - cut - 4
                    if 24 < nw < bw - 2:
                        b.place_configure(x=cx + cw + 4, width=nw)
                        done.append(("Btn-left", "", bw, nw))
                        if log is not None:
                            log("缺陷5 按钮左侧被 %s 盖 %dpx" % (ccls, cut))
                        break
    except Exception:  # noqa: BLE001
        pass
    return done


def fix_about_version(win, log=None):
    """缺陷 4：「关于」窗体内的只读 Text 仍显示旧版本号。

    标题栏走的是 theme.TITLE_VER（set_version 已改），但窗体内那段说明文字
    是**启动时从常量复制进去的副本**，改常量不会回写。做法：按行做
    「Ver: x.y.z」→「Ver: BUILD_VERSION」的替换。
    """
    done = []
    try:
        if not win.winfo_exists() or "关于" not in (win.title() or ""):
            return done
        for c in _all(win):
            if c.winfo_class() != "Text":
                continue
            try:
                cur = c.get("1.0", "end-1c")
            except Exception:  # noqa: BLE001
                continue
            # ⚠️ 实测原文是 `局域网IP扫描工具  Ver 1.25.0` ——
            # **Ver 后面没有冒号**（标题栏的 TITLE_VER 才带 `Ver:`）。
            # 所以正则必须同时兼容 `Ver:` 与 `Ver ` 两种写法。
            import re as _re
            new = _re.sub(r"Ver:?\s*\d+(?:\.\d+)+", "Ver " + BUILD_VERSION, cur)
            if new != cur:
                # about 的 Text 是 **disabled（只读展示）**，直接 delete/insert
                # 会抛 TclError。先存原 state，写完恢复。
                try:
                    st = c.cget("state")
                except Exception:  # noqa: BLE001
                    st = "normal"
                try:
                    if st != "normal":
                        c.configure(state="normal")
                    c.delete("1.0", "end-1c")
                    c.insert("1.0", new)
                    if st != "normal":
                        c.configure(state=st)
                    done.append(new)
                    if log is not None:
                        log("缺陷4 about 版本号已同步为 %s" % BUILD_VERSION)
                except Exception as e:  # noqa: BLE001
                    if log is not None:
                        log("缺陷4 改写失败 %r" % (e,))
    except Exception:  # noqa: BLE001
        pass
    return done


def fix_config_bottom(win, log=None):
    """缺陷6（2026-10-07 验收量化）：选项配置窗的「保存」按钮压住
    「备注色块颜色」标签右端 27x11px。

    根因是**原始设计图**就排不下：设计高 352，按钮行 y318..341、
    色块行 y331..352，两行本就相交；缩放后等比放大成 27x11px 遮挡。

    修法：把色块行（标签 + 3 个色块 Canvas）整体下移 Δ，窗体加高 Δ。

    ⚠️ 几何读取戒律（踩过两次，别再犯）：
      · 控件几何必须读 place_info（配置值，place_configure 后立即可读），
        不能读 winfo_*（惰性，布局前是旧值/1px 占位）；
      · 本函数**只能挂在 sweep 稳态分支**，不能放进 scale_dialog ——
        实测在 scale_dialog 内读 win.geometry() 拿到的是**待生效的旧值**
        268x352，+Δ 后写回去直接把 ① 刚请求的 402x528 覆盖回设计尺寸，
        后续 clamp_overflow 看窗小控件大，把全窗控件钳成 8px 高的废条。
    幂等：修完后标签与按钮不再重叠，下一轮检测不到重叠直接返回。
    """
    try:
        key = getattr(win, "_ipscaner_key", None)
        if key != "config" and str(win.title()) != "选项配置":
            return []
    except Exception:  # noqa: BLE001
        return []
    try:
        kids = win.winfo_children()
        lab = btn = None
        for c in kids:
            try:
                cls = c.winfo_class()
                if cls == "Label" and c.cget("text") == "备注色块颜色":
                    lab = c
                elif cls == "Button" and c.cget("text") == "保存":
                    btn = c
            except Exception:  # noqa: BLE001
                pass
        if lab is None or btn is None:
            return []

        def _geo(c):
            try:
                pi = c.place_info()
            except Exception:  # noqa: BLE001
                pi = {}
            x = pi.get("x"); y = pi.get("y")
            w = pi.get("width"); h = pi.get("height")
            try:
                x = float(x) if x not in (None, "") else float(c.winfo_x())
                y = float(y) if y not in (None, "") else float(c.winfo_y())
                w = float(w) if w not in (None, "") else float(c.winfo_width())
                h = float(h) if h not in (None, "") else float(c.winfo_height())
            except Exception:  # noqa: BLE001
                return None
            return x, y, w, h

        gl = _geo(lab); gb = _geo(btn)
        if gl is None or gb is None:
            return []
        lx, ly, lw, lh = gl
        bx, by, bw, bh = gb
        if bh <= 2:                            # 布局未结算，下轮再来
            return []
        ox = min(lx + lw, bx + bw) - max(lx, bx)
        oy = min(ly + lh, by + bh) - max(ly, by)
        if ox <= 0 or oy <= 0:
            return []                          # 已无遮挡：幂等空操作
        gap = max(4, int(round(4 * (getattr(win, "_ipscaner_S", 1.5) or 1.5))))
        delta = int(round((by + bh) + gap - ly))
        if delta <= 0:
            return []
        # 色块行 = 标签 + 与标签同一水平线的小 Canvas（30x32 的色块）
        moved = []
        for c in kids:
            try:
                if c is lab:
                    c.place_configure(y=int(ly + delta))
                    moved.append("label")
                    continue
                if c.winfo_class() == "Canvas":
                    gc = _geo(c)
                    if gc and abs(gc[1] - (ly - 4)) <= 12 and gc[2] <= 60:
                        c.place_configure(y=int(gc[1] + delta))
                        moved.append("swatch")
            except Exception:  # noqa: BLE001
                pass
        # 窗体加高 Δ（稳态下 geometry() 返回的是已生效值，安全）
        try:
            cur = win.geometry()
            size, _, pos = cur.partition("+")
            cw, ch = (int(v) for v in size.split("x"))
            win.geometry("%dx%d%s" % (cw, ch + delta, "+" + pos if pos else ""))
        except Exception:  # noqa: BLE001
            pass
        if log is not None:
            log("缺陷6 config 色块行下移 %dpx、窗体加高（消除保存按钮遮挡）" % delta)
        return moved
    except Exception:  # noqa: BLE001
        return []


def fix_overlaps(win, log=None):
    """总入口：在 sweep 里对每个子窗体跑一遍。"""
    out = []
    for fn in (fix_overlap_memo, fix_overlap_calc, fix_btn_cut,
               fix_about_version):
        try:
            out.extend(fn(win, log=log) or [])
        except Exception:  # noqa: BLE001
            pass
    return out


# ------------------------------------------------- 4.99 残留死控件（一键设置IP）
# 2026-10-09 修完缺陷13 的自伤（底部按钮被钳成 8px）后，真机截图里「保存设置 /
# 关闭」右边重新露出**两个空的、没有标签的下拉框** —— 一开始怀疑是我改出来的，
# 查证后确认是产品原版就带的死控件：
#     反编译 src/dialogs.py:332-333
#         combo(top, 400, 526, 52, 29, ["", "1", "2", "3"], 0)
#         combo(top, 460, 526, 84, 29, ["", "1", "2"], 0)
#     dialogs.combo() 只做 place + current()，**不绑 command、不接 variable**，
#     两个控件的值从头到尾没人读 → 纯残留（多半是原 WinForms 版某个「重试/
#     并发数」选择器，迁到 Python 版时丢了标签）。
# 判据（三条全中才收）：① 窗体是「一键设置IP」；② 控件是 Combobox 且 place 的
# y 落在设计 526（按钮行）；③ **没有任何事件绑定**（有绑定的放过，宁可不修）。
# 动作只用 place_forget()：控件本体和它的值为都还在，随时可回滚。
_DEAD_COMBO_KEYS = ("一键设置IP",)
_DEAD_COMBO_ROW_Y = 526.0
_DEAD_COMBO_ROW_TOL = 6.0


def hide_dead_combos(win, S, log=None):
    """收掉「一键设置IP」里两个无名、无绑定的残留下拉框（原版自带）。"""
    out = []
    try:
        title = str(win.title())
    except Exception:  # noqa: BLE001
        return out
    if not any(k in title for k in _DEAD_COMBO_KEYS):
        return out
    S = float(S) or 1.0
    for c in list(win.winfo_children()):
        try:
            if c.winfo_class() != "TCombobox":
                continue
            info = c.place_info()
            if not info:
                continue
            yv = info.get("y")
            if yv in (None, ""):
                continue
            y_design = float(yv) / S
            if abs(y_design - _DEAD_COMBO_ROW_Y) > _DEAD_COMBO_ROW_TOL:
                continue
            if c.bind():                     # 有任何脚本级绑定 → 放过
                continue
            if c.cget("values") and str(c.get()) not in ("", "0"):
                continue                     # 有实际取值 → 放过
            c.place_forget()
            out.append(("TCombobox", int(info.get("x") or 0),
                        int(info.get("y") or 0), y_design))
            if log is not None:
                log("收起残留死控件 TCombobox @设计(%s,%d)（原名 %r，无绑定）"
                    % (info.get("x"), int(y_design), title))
        except Exception:  # noqa: BLE001
            pass
    return out


# ------------------------------------------------------------------ 4.8 悬浮高亮
# 缺陷9（用户 2026-10-08 反馈「有些 button 悬浮的时候还是会显示浅蓝色的方块」，
# 像素级取证 + 反汇编定位）：
#   产品 refresh_fx 末尾：
#       if self.hover and self.hover[0] == 'button':
#           b = self._box_of('button', self.hover[1])   # regions 存的是设计 1:1 坐标
#           if b: self._hover_rect(b)
#   _hover_rect → create_rectangle(*b, fill=T.C_MENU_SELECT, outline='', tags='fx')
#   两个后果：
#     ① 矩形建在**设计坐标**上（on_motion 里 `_hit(e.x/S, e.y/S)` 也印证 regions
#        是设计坐标）→ 悬浮瞬间方块出现在错位处，要等最多 500ms 才被 sweep 搬正；
#     ② 不透明矩形是 refresh_fx 里**最后**画的 = 最上层，正好盖住按钮自己的文字
#        → 用户看到「一个没有字的浅蓝方块」。实测截图 #C9E4FF 占 2656px，
#        块内无任何文字像素；测试架复现：id=1082 rectangle(265,62,350,96)
#        fill=#C9E4FF，层序在 text id=42('开始') 之上。
#
# 修法：包一层 _hover_rect —— 建完立刻
#   · 按 S 归位（并打 _RESNAP_TAG，避免 sweep 再搬一次）
#   · 改成**描边环**：外扩 3S px、fill='' ≈ 透明、outline=苹果强调色、宽 2S
#     （环落在按钮四周的底色上，六种面色都能看清；不遮面也不遮字）
#   · 同区域文字 tag_raise 到最上（双保险）
# 幂等：函数属性标记；矩形每次悬浮新建，所以每轮都要处理它。
# 可用 IPSCANER_NO_HOVER_RING=1 关闭（A/B 对照）。

def ring_hover_rect(cv, it, S, log=None):
    """把产品画的不透明悬浮方块改成描边环（就地改，幂等）。"""
    try:
        if cv.type(it) != "rectangle":
            return False
        if cv.gettags(it) and "ipscaner_ring" in cv.gettags(it):
            return False
    except Exception:  # noqa: BLE001
        return False
    try:
        x0, y0, x1, y1 = cv.coords(it)
        pad = max(2, int(round(3 * S)))
        cv.coords(it, x0 - pad, y0 - pad, x1 + pad, y1 + pad)
        cv.itemconfigure(it, fill="", outline=_apple_accent(),
                         width=max(2, int(round(2 * S))))
        cv.addtag_withtag("ipscaner_ring", it)
        try:
            cv.addtag_withtag(_RESNAP_TAG, it)   # 别让 sweep 再搬一次
        except Exception:  # noqa: BLE001
            pass
        bb = cv.bbox(it)
        if bb:
            for t in cv.find_overlapping(*bb):
                try:
                    if cv.type(t) == "text":
                        cv.tag_raise(t)
                except Exception:  # noqa: BLE001
                    pass
        if log is not None:
            log("缺陷9 悬浮高亮改为描边环 %s（原不透明方块 #C9E4FF 会盖住按钮文字）"
                % (tuple(bb) if bb else "",))
        return True
    except Exception:  # noqa: BLE001
        return False


def patch_hover_rect(root=None, log=None):
    """给 MainForm._hover_rect 包一层（懒安装：mainform 导入后才生效）。"""
    import os as _os
    if _os.environ.get("IPSCANER_NO_HOVER_RING") == "1":
        return 0
    try:
        import sys as _sys
        _M = _sys.modules.get("mainform")
        if _M is None or not hasattr(_M, "MainForm"):
            return 0
        orig = _M.MainForm._hover_rect
        if getattr(orig, "_ipscaner_ring", False):
            return 1
    except Exception:  # noqa: BLE001
        return 0

    def _hover_ring(self, *a, **k):
        try:
            r = orig(self, *a, **k)
        except Exception:  # noqa: BLE001
            r = None
        # 原函数刚建的矩形是「最后建 = 最上层」，取 find_all 末尾即可
        try:
            cv = self.cv
            S = float(getattr(self, "S", 1.0) or 1.0)
            items = cv.find_all()
            bx = None
            try:
                hv = getattr(self, "hover", None)
                # ⚠️ kind 必须从 hover[0] 取，不能写死 "button"：
                #    写死会让 menubar 悬浮（kind='menubar'）永远 _box_of 不到框 →
                #    bx=None → 整段转换被跳过（踩过，见缺陷10 的注释）。
                #    这里再显式限定 button：菜单项的高亮是 polygon、走
                #    fix_menubar_hover，不该被本函数改成描边环。
                if hv and hv[0] == "button":
                    bx = self._box_of(hv[0], hv[1])
            except Exception:  # noqa: BLE001
                bx = None
            if items and bx and len(bx) == 4:
                it = items[-1]
                bb = cv.bbox(it)
                # 三重校验，避免误伤（下拉列表里的 hover 行也用同色）：
                #   ① 是矩形 ② 颜色=悬浮高亮色 ③ bbox 落在该按钮的设计框
                #      （未归位）或缩放框（已归位）附近
                if bb and cv.type(it) == "rectangle" \
                        and cv.itemcget(it, "fill") == _hover_sel():
                    tol = max(4, int(round(4 * S)))
                    in_design = (abs(bb[0] - bx[0]) <= tol
                                 and abs(bb[1] - bx[1]) <= tol)
                    in_scaled = (abs(bb[0] - bx[0] * S) <= tol
                                 and abs(bb[1] - bx[1] * S) <= tol)
                    if in_design or in_scaled:
                        # 设计坐标 → 先按 S 归位（不能盲缩：zoom 场景下可能
                        # 已经是缩放坐标，盲缩会缩两次）
                        if in_design and not in_scaled:
                            cv.scale(it, 0, 0, S, S)
                        ring_hover_rect(cv, it, S, log=log)
        except Exception:  # noqa: BLE001
            pass
        return r

    _hover_ring._ipscaner_ring = True
    _M.MainForm._hover_rect = _hover_ring
    if log is not None:
        log("缺陷9 已接管 MainForm._hover_rect（悬浮高亮 → 描边环）")
    return 1


def sweep_hover_rings(cv, boxes, S, log=None):
    """sweep 兜底：把画布上残留的不透明悬浮方块（#C9E4FF）改成描边环。

    只处理 bbox 落在某个按钮**缩放框**内的矩形 —— 同样用 #C9E4FF 的组合框
    下拉列表在别处，不会被误伤。
    """
    n = 0
    try:
        for it in list(cv.find_all()):
            try:
                if cv.type(it) != "rectangle":
                    continue
                if cv.itemcget(it, "fill") != _hover_sel():
                    continue
                bb = cv.bbox(it)
                if not bb:
                    continue
                inside = False
                for _label, (bx, by, bw, bh) in boxes:
                    if (bb[0] >= bx * S - 8 and bb[1] >= by * S - 8
                            and bb[2] <= (bx + bw) * S + 8
                            and bb[3] <= (by + bh) * S + 8):
                        inside = True
                        break
                if inside and ring_hover_rect(cv, it, S, log=log):
                    n += 1
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return n


# ------------------------------------------------------------------ 4.6b 顶级菜单项悬浮高亮
# 缺陷10（2026-10-08，用户第 21 轮「为什么有些 button 悬浮还是浅蓝方块」的延伸）：
#   工具条按钮走 MainForm._hover_rect（不透明矩形 → 已改描边环），但
#   **顶级菜单项压根不走它** —— mainform.refresh_fx 直接画一个圆角 polygon。
#   源码模式实测（hover 到「快捷工具」，菜单项设计框 (3,1,100,23)）：
#       id=1171 polygon bbox=(1, -1, 102, 25)  fill=#E9F1FD   tags=['fx']
#       id=1173 text    bbox=(38, 5, 134, 29)  fill=#1A1A1A   tags=['fx','current']
#                                                       text='快捷工具(T)'
#   两条关键事实：
#     ① 高亮块画在**设计坐标**上（region box 外扩 2px），而菜单文字/图标是
#        **缩放坐标**（缩放到 145x33）→ 高亮只有菜单项的 2/3 大、还偏左上，
#        看上去正是「一个贴错位置的浅蓝方块」；
#     ② 文字被重新画成 fx text 叠在块上层，所以**字没被盖住** ——
#        与按钮（字被盖住）是两种不同的坏法，但对用户的观感是同一件事。
#   修法：包一层 MainForm.refresh_fx，悬浮对象是 menubar 时把这块按 S 归位
#   （cv.scale 就地缩放，1:1 → 设计×S），幂等标记打在图形上（每次 refresh_fx
#   都会重建这块，所以要每轮处理、靠 tag 防二次缩放）。
#   为什么保留填充底色、不改成描边环：菜单栏的惯例就是「整块高亮」
#   （WinForms / macOS 都如此），用户抱怨的是**尺寸位置错**，不是「有底色」。
#   可用 IPSCANER_NO_MENU_FIX=1 关闭（A/B 对照）。
MENUBAR_HOVER_FALLBACK = "#E9F1FD"
_MENU_FIX_TAG = "ipscaner_menufix"


def _menubar_hover_colors():
    """菜单项高亮的全部底色候选（返回大写集合）。

    ⚠️ 踩过：theme 里有两档 —— MENUBAR_HOVER='#E9F1FD'（普通悬浮）与
    MENUBAR_ACTIVE='#DCE8FA'（菜单展开/激活态）。只认第一档时，运行中一旦切到
    激活态，归位逻辑就静默失效（真机复现：B 态 ROI 主色 (220,232,250)×1237，
    高亮块仍是设计坐标）。所以整族都认。
    """
    out = set()
    try:
        import sys as _sys
        _T = _sys.modules.get("theme")
        for name in ("MENUBAR_HOVER", "MENUBAR_ACTIVE", "MENUBAR_HOVER_EDGE",
                     "MENUBAR_BG"):
            v = getattr(_T, name, None)
            if isinstance(v, str) and v.startswith("#"):
                out.add(v.upper())
    except Exception:  # noqa: BLE001
        pass
    out.add(MENUBAR_HOVER_FALLBACK.upper())
    try:
        out.add(_hover_sel().upper())
    except Exception:  # noqa: BLE001
        pass
    return out


def _menubar_hover_color():
    """取 theme.MENUBAR_HOVER（真机实测 #E9F1FD），取不到用兜底值。"""
    try:
        import sys as _sys
        _T = _sys.modules.get("theme")
        v = getattr(_T, "MENUBAR_HOVER", None)
        if isinstance(v, str) and v.startswith("#"):
            return v
    except Exception:  # noqa: BLE001
        pass
    return MENUBAR_HOVER_FALLBACK


def fix_menubar_hover(form, log=None):
    """把菜单项高亮块（**悬浮态 + 激活态**）从设计坐标搬到「设计×S」。

    2026-10-09 补修（缺陷11，用户「点击一些菜单时还是会出现这个蓝色方块，
    比如关于菜单」）：
      原实现只看 `form.hover[0] == 'menubar'`，于是**点击**菜单之后
      （open_menu 有值、鼠标已经移开菜单栏 / hover 被清掉）——此时产品
      refresh_fx 仍按 `active` 画一块 MENUBAR_ACTIVE —— 这块永远修不到，
      停在设计坐标上。真机/源码态实测（S=1.5）：
          hover=('menubar','about')  →  polygon bbox=(646,-1,764,37)  ✅ 正确
          open_menu='about', hover=None → polygon bbox=(430,-1,510,25) ❌ 设计坐标
      正确位置应是 (646,-1,764,37)。而这一块正好落在「windows命令」的
      左半边上方（design x 432..508 vs wincmd 的 462..648）——
      用户看到的就是「一个浅蓝色小方块压在 windows命令 左边」。

    另一个必须知道的机制（这轮反汇编才确认）：主画布 ScaledCanvas **只重写了
    create_text / create_rectangle / create_line**，`create_polygon` 没重写 ——
    而菜单栏高亮正好是 `_rounded_rect` 用 create_polygon 画的。所以它天生
    不会被画布按 S 缩放，必须由本函数搬。（按钮面同理，走 resnap_toolbar。）

    幂等仍靠图形 tag：refresh_fx 每次都重建这块，所以每轮都要处理，靠 tag 防二次缩放。
    """
    n = 0
    try:
        cv = form.cv
        S = float(getattr(form, "S", 1.0) or 1.0)
        if S <= 1.0:
            return 0
        hv = getattr(form, "hover", None)
        hkey = hv[1] if (hv and hv[0] == "menubar") else None
        okey = getattr(form, "open_menu", None)
        # 需要归位的菜单项 = 激活态 ∪ 悬浮态（两者可能是不同的项，产品会各画一块）
        targets = []
        for r in (getattr(form, "regions", None) or []):
            try:
                if r.get("kind") != "menubar":
                    continue
                k = r.get("key")
                if k != okey and (hkey is None or k != hkey):
                    continue
                b = r.get("box")
                if b and len(b) == 4:
                    targets.append((k, tuple(float(v) for v in b)))
            except Exception:  # noqa: BLE001
                continue
        if not targets:
            return 0
        want = _menubar_hover_colors()
        sel = _hover_sel().upper()
        tol = max(6, int(round(6 * S)))
        items = list(cv.find_all())
        moved = []
        for _key, b in targets:
            for it in items:
                try:
                    typ = cv.type(it)
                    if typ not in ("polygon", "rectangle"):
                        continue
                    if _MENU_FIX_TAG in cv.gettags(it):
                        continue
                    fill = cv.itemcget(it, "fill")
                    if not isinstance(fill, str) or not fill.startswith("#"):
                        continue
                    up = fill.upper()
                    if up not in want and up != sel:
                        continue
                    bb = cv.bbox(it)
                    if not bb:
                        continue
                    # 只认「贴着这个菜单项设计框」的那一块（外扩 2px 的圆角块）：
                    # 左上角对齐 + 右下不超出设计框太多。
                    # 已按 S 归位过的块 bb[2] 会远大于 b[2]+tol → 这里天然不会二次缩放。
                    if not (abs(bb[0] - b[0]) <= tol and abs(bb[1] - b[1]) <= tol):
                        continue
                    if bb[2] > b[2] + tol or bb[3] > b[3] + tol:
                        continue
                    cv.scale(it, 0, 0, S, S)
                    cv.addtag_withtag(_MENU_FIX_TAG, it)
                    try:
                        cv.addtag_withtag(_RESNAP_TAG, it)
                    except Exception:  # noqa: BLE001
                        pass
                    moved.append(it)
                    n += 1
                except Exception:  # noqa: BLE001
                    pass
        for it in moved:
            # 菜单文字是 refresh_fx 里后建的 fx text，层序天然在块之上；
            # 但别的修复可能动过层序 → 把落在新块范围内的文字再抬一次，
            # 保证「高亮永远在字下面」。
            try:
                bb = cv.bbox(it)
                if not bb:
                    continue
                for t in cv.find_overlapping(*bb):
                    try:
                        if cv.type(t) == "text":
                            cv.tag_raise(t)
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:  # noqa: BLE001
                pass
        if n and log is not None:
            log("缺陷10/11 菜单项高亮归位 %d 块（悬浮或激活态；原画在设计坐标，"
                "只有菜单项的 2/3 大）" % n)
    except Exception:  # noqa: BLE001
        pass
    return n


def patch_refresh_fx(root=None, log=None):
    """给 MainForm.refresh_fx 包一层：菜单项高亮每次重建后立刻归位。"""
    import os as _os
    if _os.environ.get("IPSCANER_NO_MENU_FIX") == "1":
        return 0
    try:
        import sys as _sys
        _M = _sys.modules.get("mainform")
        if _M is None or not hasattr(_M, "MainForm"):
            return 0
        # ⚠️ 幂等标记必须打在**类**上，不能打在 orig 函数上！
        #    本文件有两个补丁都要包 MainForm.refresh_fx（本函数 + 4.55 的
        #    patch_adapter_fit），谁后装谁就把方法换成自己的包装函数，
        #    于是另一个下次再来时 `getattr(orig, 标记)` 拿到的是**对方的包装**
        #    （没有自己的标记）→ 判定「没装过」→ 再包一层、再记一条日志。
        #    两者互相拆台 → 每个 sweep 都多套一层，实测 30 秒内日志涨到 1.1MB，
        #    refresh_fx 被嵌套上千层（越用越卡，最终 RecursionError）。
        #    类属性不受「方法被替换」影响，天然幂等。
        if getattr(_M.MainForm, "_ipscaner_menufix_done", False):
            return 1
        orig = _M.MainForm.refresh_fx
        if getattr(orig, "_ipscaner_menufix", False):
            _M.MainForm._ipscaner_menufix_done = True
            return 1
    except Exception:  # noqa: BLE001
        return 0

    def _refresh_fx_menu(self, *a, **k):
        try:
            r = orig(self, *a, **k)
        except Exception:  # noqa: BLE001
            r = None
        try:
            fix_menubar_hover(self, log=log)
        except Exception:  # noqa: BLE001
            pass
        return r

    _refresh_fx_menu._ipscaner_menufix = True
    _M.MainForm.refresh_fx = _refresh_fx_menu
    _M.MainForm._ipscaner_menufix_done = True       # 类级幂等标记，见上
    if log is not None:
        log("缺陷10 已接管 MainForm.refresh_fx（菜单项悬浮高亮归位）")
    return 1


# ------------------------------------------------------------------ 4.7 备注编辑面板
# 缺陷7（2026-10-07 子代理验收发现，memo_edit_probe 实锤）：
#   备注管理窗点「新增/修改」弹出的**内嵌编辑面板**（IP地址标签+输入框+
#   备注内容标签+Text+保存/关闭 共 6 件）是点击时才创建的，晚于
#   scale_dialog 的首次缩放 → sweep 稳态只补字体不补几何，面板永远停在
#   1:1 设计尺寸（t0/t1/t2 三时刻位置纹丝不动，实锤不自愈）。
#   面板自身还有一处**原始设计缺陷**：IP 输入框设计宽 187（右沿 267），
#   「保存」按钮左沿 210 → 输入框被按钮压住 57px（1:1 下就存在）。
#
# 识别不能靠坐标（混合坐标系下查询行 Entry 与面板按钮也"重叠"），
# 只能靠**创建顺序**：面板 6 件比窗体原有 11 件晚创建，在
# winfo_children() 里排在「IP地址：」标签之后。
#
# ⚠️ 缺陷15（2026-10-10 做需求36「主页右键备注」时发现，**本修复层自伤**）：
#   上一版这里「读当前几何再乘 S」，而 scale_dialog ② 步也会把**窗体全部
#   子控件**乘一次 S —— 面板于是被乘两次：
#     · sweep 第 1 轮  first=True  → scale_dialog 连刚建的面板一起 ×S
#     · sweep 第 2 轮  first=False → 稳态分支再调 fix_memo_panel，又 ×S
#   合计 ×S²（S=1.5 → ×2.25）。实测「保存」按钮：设计 (210,14,70,24)
#   → 实测 (472,32,157,54)，右沿 629 冲出客户区 476，被 clamp_overflow 的
#   `max(8, CW-x)` 钳成 **8px 宽**；「关闭」同样。裸跑对照（不带钩子）
#   是正常的 70px —— 所以这是自伤，不是原版问题。
#   触发条件极日常：**第一次**在主页右键某个 IP →「备注信息」时，
#   `memomanager` 这个窗口键还没被占，mkform 必然新建窗口 → 必然走 first 分支。
#
# 修法：几何改成**按设计常量绝对定位**（跑多少遍结果都一样 → 天然幂等），
#   不再「读现值再乘 S」。顺带不再依赖 _ipscaner_panel_scaled 标记（那个
#   标记只防自己重复，防不住 scale_dialog），也不再需要「几何未结算守卫」
#   —— 绝对定位根本不读现值。
MEMO_PANEL_BOXES = (
    (14, 18,  63, 14),    # ①「IP地址：」Label
    (80, 14, 124, 21),    # ② IP 输入框（原设计 187 → 124：右沿让到「保存」左沿 -6）
    (14, 46,  77, 14),    # ③「备注内容：」Label
    (14, 62, 189, 88),    # ④ 备注 Text
    (210, 14, 70, 24),    # ⑤「保存」
    (210, 44, 70, 24),    # ⑥「关闭」
)
MEMO_PANEL_TEXT = 3       # ④ 在 MEMO_PANEL_BOXES 里的下标


def _drop_memo_card(win):
    """面板已关闭 → 把垫底白卡一并收掉，否则留一块悬空白矩形。"""
    try:
        card = getattr(win, "_memo_panel_card", None)
        if card is not None:
            try:
                card.destroy()
            except Exception:  # noqa: BLE001
                pass
            win._memo_panel_card = None
    except Exception:  # noqa: BLE001
        pass


def _memo_panel_needs(widgets, tgt, sbw):
    """6 件控件是否已经不都在目标几何上（不在 → 需要重排）。

    只读 place_info（配置值，写完即可读）——winfo 是惰性结算的，
    刚 place_configure 完立刻读会拿到旧值。
    """
    for i, (c, t) in enumerate(zip(widgets, tgt)):
        want = t
        if i == MEMO_PANEL_TEXT:
            want = (t[0], t[1], max(1, t[2] - sbw), t[3])
        try:
            pi = c.place_info()
            got = (int(float(pi.get("x") or 0)), int(float(pi.get("y") or 0)),
                   int(float(pi.get("width") or 0)),
                   int(float(pi.get("height") or 0)))
        except Exception:  # noqa: BLE001
            return True
        if got != want:
            return True
    return False


def _place_memo_card(win, widgets, tgt, S, log=None):
    """面板底下垫一张白卡片：6 件控件直接浮在查询行/表格上时，
    背景会从缝隙里透出来，看着像排版事故（2026-10-07 截图实锤）。
    卡片 = 面板并集外扩一圈；建好把控件逐个 lift 回卡片之上，
    保持「背景 < 卡片 < 面板控件」的层序。
    """
    try:
        import tkinter as _tk2
        pad = max(6, int(round(9 * S)))
        x0 = min(t[0] for t in tgt) - pad
        y0 = min(t[1] for t in tgt) - pad
        x1 = max(t[0] + t[2] for t in tgt) + pad
        y1 = max(t[1] + t[3] for t in tgt) + pad
        card = getattr(win, "_memo_panel_card", None)
        if card is None or not card.winfo_exists():
            card = _tk2.Frame(win, bg=APPLE_CARD, highlightthickness=1,
                              highlightbackground=APPLE_BORDER)
            win._memo_panel_card = card
        card.place_configure(x=x0, y=y0, width=x1 - x0, height=y1 - y0)
        for c in list(win.winfo_children()):
            try:
                if c is card:
                    continue
                if c in widgets:
                    c.lift()
                    continue
                if c.winfo_class() != "TScrollbar":
                    continue
                gx, gy, gw, gh = _geo(c)
                if x0 - pad * 2 <= gx <= x1 + pad * 2 \
                        and y0 - pad * 2 <= gy <= y1 + pad * 2:
                    c.lift()
            except Exception:  # noqa: BLE001
                pass
        # 标签底色随卡片走：beautify 统一刷的是窗体灰 #F5F5F7，
        # 落到白卡上就是一块灰斑（实测截图可见）
        for c in widgets:
            try:
                if c.winfo_class() == "Label":
                    c.configure(bg=APPLE_CARD)
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("缺陷7 垫卡异常 %r" % (e,))


def fix_memo_panel(win, S, log=None):
    """把备注编辑面板绝对定位到「设计 × S」。返回 True 表示本轮动过几何。"""
    try:
        kids = list(win.winfo_children())
    except Exception:  # noqa: BLE001
        return False
    # 不设窗体标题/_ipscaner_key 门槛：面板一打开，窗体标题就被产品代码
    # 改成「备注 」（实测），sweep 每轮重写的 _ipscaner_key 随之变成
    # None —— 第一版按 title/key 判窗被这个骗过，永远 return False。
    # 判别改看**面板特征本身**：「IP地址：」标签 + 其后的 Text +
    # 保存/关闭按钮。其它窗体凑不齐这套签名：
    #   config 有保存/关闭但无 Text、无 IP地址标签；localip 有 IP地址标签
    #   但无 Text；ipsegment 有 Text 但标签是「输入IP扫描段：」。
    label_ip = None
    for i, c in enumerate(kids):
        try:
            if c.winfo_class() == "Label" and c.cget("text") == "IP地址：":
                label_ip = i
                break
        except Exception:  # noqa: BLE001
            pass
    if label_ip is None:
        _drop_memo_card(win)
        return False                          # 面板未打开

    tail = kids[label_ip:]
    panel_text = btn_save = btn_close = entry_ip = label_memo = None
    for c in tail:
        try:
            cls = c.winfo_class()
            if cls == "Text" and panel_text is None:
                panel_text = c
            elif cls == "Button" and c.cget("text") == "保存" and btn_save is None:
                btn_save = c
            elif cls == "Button" and c.cget("text") == "关闭" and btn_close is None:
                btn_close = c
            elif cls == "Entry" and entry_ip is None:
                entry_ip = c
            elif cls == "Label" and c.cget("text") == "备注内容：" \
                    and c is not tail[0] and label_memo is None:
                label_memo = c
        except Exception:  # noqa: BLE001
            pass
    if panel_text is None or btn_save is None or btn_close is None:
        _drop_memo_card(win)
        return False                          # 签名不齐 / 无面板

    widgets = [tail[0], entry_ip, label_memo, panel_text, btn_save, btn_close]
    if any(c is None for c in widgets):
        return False                          # 半成品面板（缺件）→ 不动

    tgt = [(int(round(bx * S)), int(round(by * S)),
            max(1, int(round(bw * S))), max(1, int(round(bh * S))))
           for (bx, by, bw, bh) in MEMO_PANEL_BOXES]
    sbw = max(10, int(APPLE_SB * S))

    # ---- 稳定态：6 件已全在目标几何 → 空过（零开销、不刷日志）----
    if not _memo_panel_needs(widgets, tgt, sbw):
        _place_memo_card(win, widgets, tgt, S, log=log)
        return False

    # ---- 绝对定位（几何 + 字体）----
    tgt_px = _scale_px(DESIGN_PX, S)
    for c, (x, y, w, h) in zip(widgets, tgt):
        try:
            c.place_configure(x=x, y=y, width=w, height=h)
            spec = _spec_of(c)
            if spec:
                fam = _fam_of(win.tk, spec)
                if fam in SONG or fam in FIXED_MAP or _is_named(spec):
                    c.configure(font=(DIALOG_FAMILY, tgt_px))
        except Exception:  # noqa: BLE001
            pass

    # ---- 面板 Text 右侧那条滚动条（beautify_dialog 的 ensure_scrollbars
    #      补的）必须跟着 Text 一起归位，否则会停在旧位置 ----
    tx, ty, tw, th = tgt[MEMO_PANEL_TEXT]
    try:
        panel_text.place_configure(width=max(1, tw - sbw))
    except Exception:  # noqa: BLE001
        pass
    for c in kids:
        try:
            if c.winfo_class() != "TScrollbar":
                continue
            gx, gy, _gw, _gh = _geo(c)
            if tx - sbw <= gx <= tx + tw + sbw and ty - th <= gy <= ty + th:
                c.place_configure(x=tx + tw - sbw, y=ty, width=sbw, height=th)
                break
        except Exception:  # noqa: BLE001
            pass

    # 面板控件晚于 beautify_dialog 创建，还是原生灰 → 补一遍主题（幂等）
    try:
        beautify_dialog(win, S, log=log)
    except Exception:  # noqa: BLE001
        pass
    _place_memo_card(win, widgets, tgt, S, log=log)
    if log is not None:
        log("缺陷7/15 备注编辑面板绝对归位 S=%.2f：保存 (%d,%d) %dx%d，"
            "关闭 (%d,%d) %dx%d"
            % (S, tgt[4][0], tgt[4][1], tgt[4][2], tgt[4][3],
               tgt[5][0], tgt[5][1], tgt[5][2], tgt[5][3]))
    return True


# ------------------------------------------------------------------ 4.5 工具条按钮归位
# 缺陷（用户 2026-09-29 截图直接暴露，坐标全部实测，见 notes/UI审计报告.md）：
#   每个工具条按钮 = **1 个 polygon（面）+ 1 个 text（字）**，两者坐标系不一致：
#       · 面：画在「设计 1:1」坐标上（未乘 S）
#       · 字：画在「设计 x S」坐标上（已乘 S）
#   本机 S=1.5 实测：
#       开始  面 canvas(176,41)-(234,65)   字 canvas(284,70)-(328,91)
#       停止  面 canvas(244,41)-(302,65)   字 canvas(386,70)-(430,91)
#   → 面比自己的字高 21px，飘到菜单栏分隔带上（截图 y44..61 那排彩色块就是它）；
#     白字 #FFFFFF 落在窗体底色 #F4F6F8 上 → 对比度 1.00，肉眼完全不可见。
#   机械判据：6 个按钮的「实测色块 x0 / 设计 x」恒为 1.00；若已按 S 缩放应为
#   1/S = 0.667。实测 0.998 / 1.004 / 1.003 / 1.006 / 1.010 / 1.004。
#   这不是修复层引入的 —— 带钩子 / 不带钩子 A/B 结果完全一致（绿色版原样）。
#
# 修复必须两步一起做：
#   ① 把「面」搬回 设计 x S 位置（cv.scale 就地缩放几何），让它包住自己的字；
#   ② 按「面」的真实亮度选字色 —— 只要①不做②，白字落到
#      #0078D4/#E15B5B/#34C77B 上对比度是 4.58/3.57/2.18，**仍然看不清**。
#      改后 4.59/5.88/9.60，全部 ≥ AA 的 4.5。
#   为什么不反过来压暗面色：C_SKYBLUE/C_INDIANRED/C_LIMEGREEN **同时是 IP 格子的
#   状态色**（#A9D8F2 在截图里有 39.5 万像素，就是网格），改主题会波及整个网格。
#   另外两个独立反编译出来的源码里，这一行本来就写的是 T.C_BLACK，属于还原设计值。
#
# 幂等：搬过的图形打 tag _RESNAP_TAG（重复跑不会二次缩放）；字色改完对比度自然
#       达标，再跑是空操作。

_RESNAP_TAG = "ipscaner_resnap"
BTN_BOXES = (("BTN_START", "开始"), ("BTN_STOP", "停止"), ("BTN_NG", "不通"),
             ("BTN_OK", "正常"), ("BTN_DETAIL", "列表展示"),
             ("BTN_EXPORT", "导出"))
MIN_CONTRAST = 4.5
DARK_TEXT = "#000000"
LIGHT_TEXT = "#FFFFFF"
BOX_TOL = 3               # 设计框容差（px），给外描边留量


def _rgb(s):
    """'#RRGGBB' / '#RGB' / '#RRRRGGGGBBB' → (r,g,b)，失败返回 None。"""
    s = (s or "").strip()
    if not s.startswith("#"):
        return None
    h = s[1:]
    try:
        if len(h) == 3:
            return tuple(int(c * 2, 16) for c in h)
        if len(h) == 6:
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        if len(h) == 12:
            return tuple(int(h[i:i + 4], 16) >> 8 for i in (0, 4, 8))
    except Exception:  # noqa: BLE001
        return None
    return None


def _lin(v):
    v = v / 255.0
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def _rel_lum(rgb):
    return 0.2126 * _lin(rgb[0]) + 0.7152 * _lin(rgb[1]) + 0.0722 * _lin(rgb[2])


def contrast_hex(fg, bg):
    """WCAG 对比度。任一颜色解析失败返回 None。"""
    a, b = _rgb(fg), _rgb(bg)
    if a is None or b is None:
        return None
    la, lb = _rel_lum(a), _rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def pick_text_color(faces, prefer=DARK_TEXT):
    """按背景（面色）集合选一个能看清的字色。

    规则：prefer 若对**所有**面色都 ≥ MIN_CONTRAST 就用它；否则退回让
    「最差那个面色」对比度最大的那个候选。这样 6 个按钮能用同一个字色，
    不会出现一个白一个黑的花脸。
    """
    cands = (prefer, LIGHT_TEXT if prefer == DARK_TEXT else DARK_TEXT)
    for c in cands:
        cs = [contrast_hex(c, f) for f in faces]
        if all(v is not None and v >= MIN_CONTRAST for v in cs):
            return c
    best, best_worst = None, -1.0
    for c in (DARK_TEXT, LIGHT_TEXT):
        cs = [contrast_hex(c, f) or 0.0 for f in faces]
        if cs and min(cs) > best_worst:
            best, best_worst = c, min(cs)
    return best


def _main_canvas(root):
    """主窗体的工具条画布 = root 下面积最大的 Canvas。"""
    best, best_area = None, 0
    try:
        stack = list(root.winfo_children())
    except Exception:  # noqa: BLE001
        return None
    while stack:
        w = stack.pop()
        try:
            stack.extend(w.winfo_children())
        except Exception:  # noqa: BLE001
            pass
        try:
            if w.winfo_class() != "Canvas":
                continue
            area = w.winfo_width() * w.winfo_height()
        except Exception:  # noqa: BLE001
            continue
        if area > best_area:
            best, best_area = w, area
    return best


def resnap_toolbar(root, S=None, log=None):
    """工具条按钮：面搬回 设计 x S + 字色按面色定。返回统计字典。"""
    stat = {"scan": 0, "moved": 0, "retext": 0, "faces": 0}
    cv = _main_canvas(root)
    if cv is None:
        if log is not None:
            log("按钮归位：未找到主画布，跳过")
        return stat
    try:
        import theme as _T
    except Exception:  # noqa: BLE001
        return stat
    if S is None:
        try:
            S = float(_T.SCALE)
        except Exception:  # noqa: BLE001
            S = 1.0
    if not S or S <= 0:
        return stat

    boxes = []
    for key, label in BTN_BOXES:
        box = getattr(_T, key, None)
        if box and len(box) == 4:
            boxes.append((label, tuple(float(v) for v in box)))
    if not boxes:
        return stat

    # 一次遍历：把每个画布项分到「1:1 设计框（要搬）」或「设计xS 框（已就位）」。
    unscaled, onface = [], {}
    try:
        items = list(cv.find_all())
    except Exception:  # noqa: BLE001
        return stat
    stat["scan"] = len(items)
    for it in items:
        try:
            typ = cv.type(it)
            if typ not in ("polygon", "rectangle", "line"):
                continue
            bb = cv.bbox(it)
            if not bb:
                continue
            x0, y0, x1, y1 = bb
        except Exception:  # noqa: BLE001
            continue
        for label, (bx, by, bw, bh) in boxes:
            # 1:1 设计框：几何还没乘 S → 要搬
            if (x0 >= bx - BOX_TOL and y0 >= by - BOX_TOL
                    and x1 <= bx + bw + BOX_TOL and y1 <= by + bh + BOX_TOL):
                unscaled.append((it, label, (x0, y0, x1, y1)))
                break
            # 设计xS 框：已经就位（可能是上一轮搬过的）
            if (x0 >= bx * S - BOX_TOL and y0 >= by * S - BOX_TOL
                    and x1 <= (bx + bw) * S + BOX_TOL
                    and y1 <= (by + bh) * S + BOX_TOL):
                if typ in ("polygon", "rectangle") and label not in onface:
                    onface[label] = it
                break

    for it, label, bb in unscaled:
        # 幂等标记：搬过就不搬第二次。
        # 注意 Canvas 的 tag 操作有两个坑：
        #   · `cv.addtag(newtag, tagOrId)` 的参数顺序是 **tag 在前、item 在后**；
        #     写成 `cv.addtag(item, TAG)` 会被 Tcl 当成「把 item 当 tag、把 TAG 当
        #     searchSpec」→ 抛 unknown search command。踩过：这一抛被 except 吞掉，
        #     几何照样被搬走了，但计数器是 0、日志一行没有 —— 排查时极难发现。
        #   · 所以这里用语义明确的 addtag_withtag(TAG, item)。
        try:
            if _RESNAP_TAG in cv.gettags(it):
                continue
        except Exception:  # noqa: BLE001
            pass
        try:
            cv.scale(it, 0, 0, S, S)
        except Exception:  # noqa: BLE001
            continue                     # 没搬成就不计数、不打标记，下一轮重来
        stat["moved"] += 1
        try:
            cv.addtag_withtag(_RESNAP_TAG, it)
        except Exception:  # noqa: BLE001
            pass
        try:
            typ = cv.type(it)
        except Exception:  # noqa: BLE001
            typ = ""
        if typ in ("polygon", "rectangle") and label not in onface:
            onface[label] = it
        if log is not None:
            log("按钮面归位 %s bbox=%s -> x%.3f" % (label, bb, S))

    # 面颜色 → 决定统一字色
    faces = []
    for label, _box in boxes:
        it = onface.get(label)
        if it is None:
            continue
        try:
            f = cv.itemcget(it, "fill")
        except Exception:  # noqa: BLE001
            continue
        if _rgb(f) is not None and f not in faces:
            faces.append(f)
    stat["faces"] = len(faces)
    if not faces:
        bg = getattr(_T, "C_FACE", None) or "#F4F6F8"
        faces = [bg]
    want = pick_text_color(faces, prefer=DARK_TEXT)
    if want is None:
        return stat
    # 注意：这行摘要只在真正改了东西时打印（否则 500ms 一轮会刷屏）——
    # 见函数末尾的收尾日志。
    if log is not None and stat["moved"]:
        log("按钮面色 %s → 统一字色 %s" % (faces, want))

    face_of = {}
    for label, _box in boxes:
        it = onface.get(label)
        if it is None:
            continue
        try:
            face_of[label] = cv.itemcget(it, "fill")
        except Exception:  # noqa: BLE001
            pass

    for label, (bx, by, bw, bh) in boxes:
        cx, cy = (bx + bw / 2.0) * S, (by + bh / 2.0) * S
        half_w, half_h = bw * S * 0.75, bh * S * 0.75
        for it in items:
            try:
                if cv.type(it) != "text":
                    continue
                if cv.itemcget(it, "text") != label:
                    continue
                bb = cv.bbox(it)
                if not bb:
                    continue
                if (abs((bb[0] + bb[2]) / 2.0 - cx) > half_w
                        or abs((bb[1] + bb[3]) / 2.0 - cy) > half_h):
                    continue
                cur = cv.itemcget(it, "fill")
            except Exception:  # noqa: BLE001
                continue
            if cur == want:
                continue
            bg = face_of.get(label) or (getattr(_T, "C_FACE", None) or "#F4F6F8")
            old_c = contrast_hex(cur, bg)
            new_c = contrast_hex(want, bg)
            if new_c is not None and (old_c is None or new_c > old_c + 0.01):
                try:
                    cv.itemconfigure(it, fill=want)
                    stat["retext"] += 1
                    if log is not None:
                        log("按钮标签 %s: %s -> %s（对 %s 对比度 %s -> %s）"
                            % (label, cur, want, bg,
                               None if old_c is None else round(old_c, 2),
                               round(new_c, 2)))
                except Exception:  # noqa: BLE001
                    pass
    if log is not None and stat["retext"]:
        log("按钮标签改色 %d 个 → %s（对 %s 对比度 %s）"
            % (stat["retext"], want, faces,
               [round(contrast_hex(want, f) or 0, 2) for f in faces]))
    # ---- 悬浮高亮兜底（缺陷9）：产品在 refresh_fx 末尾用不透明 #C9E4FF
    #      矩形画在最上层盖住按钮文字 → 统一改成描边环。主路径是
    #      patch_hover_rect 包住 _hover_rect（事件驱动、无延迟），这里只兜
    #      补丁安装之前就画出来的那些残留。
    try:
        stat["ring"] = sweep_hover_rings(cv, boxes, S, log=log)
    except Exception:  # noqa: BLE001
        pass
    return stat


def darken_until(fg, bg, target=MIN_CONTRAST, floor=0.30):
    """保持色相把 fg 压暗，直到对 bg 的对比度 >= target；返回最接近原色的解。

    只按**同一个色相**降亮度（等比乘 RGB），所以「橙=你自己的 IP」这种
    语义色还认得出，只是变深。最多压到 floor 倍，压不动就返回 None。
    """
    rgb = _rgb(fg)
    if rgb is None or _rgb(bg) is None:
        return None
    k = 1.0
    while k >= floor:
        c = tuple(int(round(v * k)) for v in rgb)
        con = contrast_hex("#%02X%02X%02X" % c, bg)
        if con is not None and con >= target:
            return "#%02X%02X%02X" % c
        k -= 0.02
    return None


# 低于这个对比度连「大字 AA」(3.0) 都过不了 → 必须自动改
HARD_CONTRAST = 3.0

# fix_canvas_contrast 的增量扫描状态（见该函数 docstring 的性能说明）
_CONTRAST_SEEN = set()
_CONTRAST_SEEN_MAX = 40000


def fix_canvas_contrast(root, S=None, log=None):
    """主画布上「连大字 AA 都过不了」的文字按同色相压暗。

    实测（2026-09-29）只有一处：#F26B1D 的「本机 IP 格」压在 #A9D8F2 格底上，
    对比度 2.00 —— 连 3.0 都不到，是真正的"看不清"。
    3.0~4.5 之间的（如状态栏 #FF0000 on #FFFFFF = 4.00）**不动**：
    那是语义色，且对大字达 AA，只登记给人判断。
    幂等：改完对比度达标，再跑不再命中。

    ⭐ 2026-10-09 性能重写（用户实测「打开菜单有几百 ms 延迟」的真凶）：
    原实现每轮 sweep 都做**全量**重扫 ——
        for 每个文字项: for 每个底色块: cv.bbox(底色块)      ← 笛卡尔积
    真机 S=1.5 实测：sweep 每 500ms 一轮、单轮 335ms，其中本函数占 321ms，
    3 秒内 cv.bbox() 被调了 436,512 次（Tcl 往返 0.8s），把 Tk 主线程常年
    占到「一个核的 37%」。点击事件排在它后面 → 用户看到的就是几百 ms 延迟。
    重写为两条，语义不变：
      ① **增量**：检查过的文字项 id 记进 _CONTRAST_SEEN，稳定态 todo 为空。
         主画布是手绘单 Canvas，格底/文字建一次就长期存在，refresh_fx 只重建
         tag=fx 的一小撮，所以增量扫描天然贴合它的变更粒度。
      ② **bbox 共享**：底色块的 bbox 每轮只算一次（一次 O(块数) 而非 O(文字×块数)）。
    几何还读不到的项**不**标记已处理 —— 宁可下轮再看，也不能漏修。
    """
    stat = {"fixed": 0, "soft": 0, "new": 0, "cached": 0}
    cv = _main_canvas(root)
    if cv is None:
        return stat
    try:
        bgs = {}
        texts = []
        for i in cv.find_all():
            ty = cv.type(i)
            if ty == "text":
                texts.append(i)
            elif ty in ("rectangle", "oval", "polygon"):
                f = cv.itemcget(i, "fill")
                if f:
                    bgs[i] = f
        seen = _CONTRAST_SEEN
        todo = [i for i in texts if i not in seen]
        stat["cached"] = len(texts) - len(todo)
        if not todo:
            return stat
        stat["new"] = len(todo)
        # ② 底色块 bbox 只算一次，所有待查文字共用
        fbb = {}
        for i in bgs:
            try:
                fbb[i] = cv.bbox(i)
            except Exception:  # noqa: BLE001
                fbb[i] = None
        for i in todo:
            try:
                t = cv.itemcget(i, "text")
            except Exception:  # noqa: BLE001
                seen.add(i)
                continue
            if not t or not t.strip():
                seen.add(i)
                continue
            try:
                bb = cv.bbox(i)
            except Exception:  # noqa: BLE001
                bb = None
            if not bb:
                continue          # ⚠️ 不标记 —— 几何还没生效，下轮再查
            fg = cv.itemcget(i, "fill")
            bg = _bg_under(cv, bb, bgs, fbb)
            seen.add(i)
            if not bg:
                continue
            con = contrast_hex(fg, bg)
            if con is None:
                continue
            if con >= HARD_CONTRAST:
                if con < MIN_CONTRAST:
                    stat["soft"] += 1
                continue
            new = darken_until(fg, bg, target=MIN_CONTRAST)
            if new is None:
                continue
            try:
                cv.itemconfigure(i, fill=new)
            except Exception:  # noqa: BLE001
                continue
            stat["fixed"] += 1
            if log is not None:
                log("画布对比度过低修复 %r: %s -> %s（对 %s 对比度 %.2f -> %.2f）"
                    % (t[:16], fg, new, bg, con,
                       contrast_hex(new, bg) or 0))
        if len(seen) > _CONTRAST_SEEN_MAX:
            # 画布反复重建会让 id 无限增长 → 到顶就重建为「当前这批」，
            # 代价是下一轮多扫一次全量，可接受。
            seen.clear()
            seen.update(texts)
    except Exception:  # noqa: BLE001
        pass
    return stat


def _bg_under(cv, bb, fills, fbb=None):
    """文字背后的底色 =「bbox 包含文字中心」的**面积最小**的填充项。

    取最小而不是最大：主窗体是单 Canvas 手绘，色块/格底层层叠上去，
    取最大会把格底判成窗体底色，从而漏掉"白字落在浅面上"这类问题。

    fbb：可选的 {item_id: bbox} 预算表。传了就不再逐项 cv.bbox()。
    ⚠️ 2026-10-09：这张表是本次性能修复的关键 —— 原来每查一个文字都要把
       全部底色块各 cv.bbox() 一次，真机 3 秒内打了 436,512 次 Tcl 往返。
    """
    if not bb:
        return None
    cx, cy = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
    best, best_area = None, None
    for i, f in fills.items():
        if fbb is not None:
            ob = fbb.get(i)
        else:
            try:
                ob = cv.bbox(i)
            except Exception:  # noqa: BLE001
                continue
        if not ob:
            continue
        if ob[0] <= cx <= ob[2] and ob[1] <= cy <= ob[3]:
            area = (ob[2] - ob[0]) * (ob[3] - ob[1])
            if best_area is None or area < best_area:
                best, best_area = f, area
    return best


# ------------------------------------------------------------------ 4.55 网卡名规范化
# 2026-10-08 用户实测：「以太网适配器那里，字体显示不全」。
#
# 根因是两个缺陷叠在一起：
#
#  ① core.get_adapters() 把 ipconfig /all 的**表头整行**当成了网卡名。
#     本机 ipconfig /all 的原样表头（实测抓的）：
#         以太网适配器 以太网:
#         无线局域网适配器 WLAN:
#         未知适配器 utun6:
#         以太网适配器 VMware Network Adapter VMnet1:
#     于是 Adapter.name = '以太网适配器 以太网'（10 字）。
#     而 .NET 的 NetworkInterface.Name 给的是「以太网」（3 字）——
#     多出来的「以太网适配器 」是 ipconfig 加的**本地化类型前缀**，不是网卡名。
#
#  ② 主窗体网卡下拉框设计宽 (7,43,74,20)，S=1.5 后文字可用宽度只有 50 设计 px
#     （= (74 - 4 - 20)），而 '以太网适配器 以太网' 实测 76 设计 px（114 实机 px）。
#     refresh_fx 末尾那块「拿底色矩形把溢出部分盖掉」的裁剪逻辑（见 mainform
#     refresh_fx 里「溢出尾巴」那段注释）就把后面「 以太网」整段切没了。
#     用户在 1187px 宽的主界面上，只能看到信息量最低的「以太网适配器」——
#     真正的网卡名一个字都不剩。这就是「字体显示不全」。
#
# 修法：
#  A. 包 core.get_adapters()，把 name 的本地化类型前缀剥掉，还原成真名
#     （以太网 / WLAN / utun6 / VMware Network Adapter VMnet1 …）。
#     ⭐ 顺带修好一个还没被发现的缺陷：f_localip.save 会把 name 原样交给 netsh
#        （core.set_static_ip / set_dynamic_ip / set_dns 都是
#         `netsh interface ... name=<adapter>`），而 netsh 只认真名 ——
#        带前缀的 '以太网适配器 以太网' 在 netsh 里根本找不到接口，改 IP 必失败。
#  B. 包 MainForm.refresh_fx：画之前先算可用宽度，超宽就按**字符边界**截断并补
#     「…」。绝不再让底色矩形切到半个字形（"半个字" 是这次最刺眼的症状）。
_ADAPTER_PREFIX_RE = None


def _adapter_prefix_re():
    global _ADAPTER_PREFIX_RE
    if _ADAPTER_PREFIX_RE is None:
        import re as _re
        # ⚠️ 必须是**类型前缀白名单**，不能写成 `^.*?(?:适配器|adapter)\s+`。
        #    后者看着更「通用」，但**不幂等**：对已经规范化过的
        #        'VMware Network Adapter VMnet1'
        #    非贪婪匹配会命中内层的 "Network Adapter "，剥成 'VMnet1' ——
        #    把用户真正的网卡名毁掉。而 refresh_fx 会对 adapter_text 再规范一次
        #    （见 patch_adapter_fit 的①自愈），所以这条链上是真会走到的。
        #    白名单写法只吃 ipconfig 会加的那几种类型词，重复调用是恒等的。
        _ADAPTER_PREFIX_RE = _re.compile(
            "^(?:"
            "以太网适配器|无线局域网适配器|未知适配器|隧道适配器|蓝牙网络连接|"
            "Ethernet adapter|Wireless LAN adapter|Unknown adapter|"
            "Tunnel adapter|Bluetooth Network Connection"
            ")\\s+",
            _re.IGNORECASE,
        )
    return _ADAPTER_PREFIX_RE


def normalize_adapter_name(name):
    """剥掉 ipconfig 表头的本地化类型前缀，返回真正的网卡名。

    '以太网适配器 以太网'                        -> '以太网'
    '以太网适配器 VMware Network Adapter VMnet1' -> 'VMware Network Adapter VMnet1'
    '未知适配器 utun6'                          -> 'utun6'
    'Ethernet adapter Ethernet'                -> 'Ethernet'
    剥完为空（怪串）时原样返回，绝不返回空名。
    **幂等**：normalize_adapter_name(normalize_adapter_name(x)) == normalize_adapter_name(x)。
    只吃白名单里的类型前缀，所以 'VMware Network Adapter VMnet1' 这种
    「真名里自己带 Adapter」的不会被误伤。
    """
    if not isinstance(name, str) or not name:
        return name
    try:
        m = _adapter_prefix_re().match(name)
    except Exception:  # noqa: BLE001
        return name
    if not m:
        return name
    stripped = name[m.end():].strip()
    return stripped or name


def patch_get_adapters(root=None, log=None):
    """core.get_adapters() 的 name 统一剥掉本地化类型前缀（幂等）。"""
    import os as _os
    if _os.environ.get("IPSCANER_NO_ADAPTER_FIX") == "1":
        return 0
    try:
        import sys as _sys
        _C = _sys.modules.get("core")
        if _C is None or not hasattr(_C, "get_adapters"):
            return 0
        orig = _C.get_adapters
        if getattr(orig, "_ipscaner_namefix", False):
            return 1
    except Exception:  # noqa: BLE001
        return 0

    def get_adapters():
        ads = orig()
        try:
            for a in ads:
                try:
                    new = normalize_adapter_name(a.name)
                    if new != a.name:
                        a.name = new
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        return ads

    get_adapters._ipscaner_namefix = True
    get_adapters.__doc__ = getattr(orig, "__doc__", None)
    _C.get_adapters = get_adapters
    if log is not None:
        log("网卡名规范化已接管 core.get_adapters（剥掉「以太网适配器 」这类前缀）")
    return 1


def fit_text(measure, text, avail, ellipsis="…"):
    """把 text 按**字符边界**裁到 avail 宽度内，裁了就补省略号。

    measure: callable(str) -> 宽度（与 avail 同单位）
    绝不返回「半个字形」的串 —— 画布没有裁剪区，宽度只能自己算准。
    """
    if not text or avail <= 0:
        return ""
    try:
        if measure(text) <= avail:
            return text
    except Exception:  # noqa: BLE001
        return text
    try:
        ell_w = measure(ellipsis)
    except Exception:  # noqa: BLE001
        ell_w = 0
    out = ""
    acc = 0
    for ch in text:
        try:
            w = measure(ch)
        except Exception:  # noqa: BLE001
            w = 0
        if acc + w + ell_w > avail:
            break
        out += ch
        acc += w
    return (out + ellipsis) if out else ""


def patch_adapter_fit(root=None, log=None):
    """网卡下拉框的文字改成「按字符边界截断 + 省略号」（幂等）。

    包一层 MainForm.refresh_fx：画之前把 self.adapter_text 临时替换成放得下的
    版本，画完立刻还原 —— 下拉列表读的是 self.adapters（完整名单），不受影响。
    """
    import os as _os
    if _os.environ.get("IPSCANER_NO_ADAPTER_FIX") == "1":
        return 0
    try:
        import sys as _sys
        _M = _sys.modules.get("mainform")
        _T = _sys.modules.get("theme")
        if _M is None or _T is None or not hasattr(_M, "MainForm"):
            return 0
        # ⚠️ 幂等标记打在**类**上（同 patch_refresh_fx 的说明）：本函数与缺陷10
        #    的补丁都会替换 MainForm.refresh_fx，函数级标记会被对方覆盖掉，
        #    结果是每个 sweep 都再套一层。
        if getattr(_M.MainForm, "_ipscaner_adapterfit_done", False):
            return 1
        orig = _M.MainForm.refresh_fx
        if getattr(orig, "_ipscaner_adapterfit", False):
            _M.MainForm._ipscaner_adapterfit_done = True
            return 1
    except Exception:  # noqa: BLE001
        return 0

    def refresh_fx(self, *a, **k):
        keep = None
        try:
            # ① 残留前缀洗掉：gui.init_state 在本补丁装上**之前**就把
            #    chosen.name 抓进了 self.adapter_text（实测 '以太网适配器 以太网'），
            #    所以不能只依赖 patch_get_adapters。这里就地规范化并写回，
            #    让状态自愈（用户不用重新选一次网卡）。
            cur = getattr(self, "adapter_text", None)
            norm = normalize_adapter_name(cur)
            if norm != cur:
                self.adapter_text = norm
                cur = norm
            keep = cur
            # ② 放不下的按字符边界截断；画完在 finally 里还原成完整（已规范化）的名
            cx0, cy0, cw, ch = _T.CMB_ADAPTER
            # 设计空间可用宽度 = 控件宽 - 左内边距 - 右侧裁剪预留（下拉箭头）
            avail = cw - int(getattr(_T, "CMB_TEXT_PAD", 0)) \
                - int(getattr(_T, "CMB_TEXT_CLIP_R", 0))
            # self._mw 返回的正是设计空间宽度（measure(text)/S），单位一致
            shown = fit_text(lambda s: self._mw(self.tk_f_default, s), cur, avail)
            if shown != cur:
                self.adapter_text = shown
        except Exception:  # noqa: BLE001
            pass
        try:
            return orig(self, *a, **k)
        finally:
            if keep is not None:
                try:
                    self.adapter_text = keep
                except Exception:  # noqa: BLE001
                    pass

    refresh_fx._ipscaner_adapterfit = True
    _M.MainForm.refresh_fx = refresh_fx
    _M.MainForm._ipscaner_adapterfit_done = True     # 类级幂等标记，见上
    if log is not None:
        log("网卡下拉框文字已改为按字符边界截断（超宽补省略号）")
    return 1


# ------------------------------------------------------------------ 4.6 网卡下拉列表
# 缺陷12（用户 2026-10-09「网卡这里看不全网卡名称」，附下拉列表截图）：
#
# 反汇编 mainform._draw_combo_list 拿到原文（line 837-838）：
#       txt = it if self._mw(self.tk_f_10, it) <= w - 6 else it[:6] + '…'
# 注意 `it[:6]` —— 字节码是 BUILD_SLICE 2 的 (None, 6)，是「**只保留前 6 个
# 字符**」，不是「去掉后 6 个」也不是按宽度裁。所以：
#       'VirtualBox Host-Only Network' → 'Virtua…'
#       'VMware Network Adapter VMnet1' → 'VMware…'
#       'vEthernet (Default Switch)'    → 'vEther…'
# 与用户截图逐字一致（源码态复现：canvas text id=2173/2174/2175/2176/2177）。
#
# 还有第二层：它量的是**组合框自身的宽度**（T.CMB_ADAPTER[2] = 74 设计px，
# 减 6 后可用 68px），而列表本来就可以比组合框宽 —— 实测最长网卡名只需要
# 200 设计px，客户区有 835px，完全放得下却只给了 74。
#
# 修法两件，都不动坐标系：
#   ① 列表宽度按最长网卡名自适应（可宽于组合框），上限到客户区右边；
#   ② 文本用 fit_text 按**字符边界**截断 —— 既不出现半个字形，也不浪费宽度。
# 行高 16 / 最多 8 行沿用原值（create_* 会按 S 缩放，所以行高看起来是 24px）。
# 列表画在**设计坐标**上（ScaledCanvas 用 self.s 缩放 create_text/create_rectangle/
# create_line），所以这里全部用设计单位，与原实现完全一致；regions 里的
# combo_item box 也照样是设计坐标，`_hit` 的命中判定不受影响。

COMBO_LIST_IH = 16          # 设计像素行高（原实现硬编码 16）
COMBO_LIST_MAX_ROWS = 8     # 原实现硬编码 8（超出不再画，原版如此）
COMBO_LIST_PAD_L = 3        # 文本左内边距（原实现 create_text(x+3)）
COMBO_LIST_PAD_R = 8        # 文本右内边距（原实现 w-6，这里给滚动余量）
COMBO_LIST_SLACK = 2        # 额外宽度余量（见 ① 的注释：抗亚像素舍入）


def patch_combo_list(root=None, log=None):
    """替换 MainForm._draw_combo_list：列表宽度自适应 + 按字符边界截断（幂等）。"""
    import os as _os
    if _os.environ.get("IPSCANER_NO_COMBO_FIX") == "1":
        return 0
    try:
        import sys as _sys
        _M = _sys.modules.get("mainform")
        if _M is None or not hasattr(_M, "MainForm"):
            return 0
        if getattr(_M.MainForm, "_ipscaner_combolist_done", False):
            return 1
        if not hasattr(_M.MainForm, "_draw_combo_list"):
            return 0
    except Exception:  # noqa: BLE001
        return 0

    def _draw_combo_list(self):
        T = _theme()
        if T is None:
            raise RuntimeError("theme 未导入")
        x, y, w, h = T.CMB_ADAPTER
        items = list(getattr(self, "adapters", None) or [])
        show = items[:COMBO_LIST_MAX_ROWS]
        # ① 列表宽度：按最长项自适应，至少与组合框同宽，不超出客户区
        #
        # ⚠️ 宽度必须**向上取整**再留 2px 余量。
        #    踩过的坑：这里原本写 `int(self._mw(...))`（向下取整），而 fit_text
        #    内部又用**全精度**重新测量一次 —— 于是 exe 里 _mw('VMware Network
        #    Adapter VMnet1') 量到 200.4 时，widest=200、text_avail=200，
        #    fit_text 判 200.4 > 200 → 最长的那几个名字永远被截成
        #    'VMware Network Adapter VMn…'（用户报的「看不全网卡名称」）。
        #    源码态恰好量到整数 200.0 才没暴露 —— 所以这个 bug 只在真机可见。
        import math as _math
        widest = 0
        for it in show:
            try:
                widest = max(widest,
                             int(_math.ceil(self._mw(self.tk_f_10, it))))
            except Exception:  # noqa: BLE001
                pass
        need = widest + COMBO_LIST_PAD_L + COMBO_LIST_PAD_R + COMBO_LIST_SLACK
        try:
            avail = int(getattr(T, "CLIENT_W", w + 200)) - int(x) - 4
        except Exception:  # noqa: BLE001
            avail = w
        lw = int(max(w, min(need, max(w, avail))))
        hh = max(1, len(show)) * COMBO_LIST_IH + 2
        by = y + h
        cv = self.cv
        self._border_rect(x, by, lw, hh, T.C_COMBO_BORDER_B, T.C_WHITE, "fx")
        text_avail = lw - COMBO_LIST_PAD_L - COMBO_LIST_PAD_R
        drawn = []
        for k, it in enumerate(show):
            iy = by + 1 + k * COMBO_LIST_IH
            if self.hover == ("combo", k):
                cv.create_rectangle(x + 1, iy, x + lw - 1, iy + COMBO_LIST_IH,
                                    fill=T.C_ACCENT, outline="", tags="fx")
                fg = T.C_WHITE
            else:
                fg = T.C_BLACK
            try:
                txt = fit_text(lambda s: self._mw(self.tk_f_10, s), it, text_avail)
            except Exception:  # noqa: BLE001
                txt = it
            if txt != it:
                drawn.append((it, txt))
            cv.create_text(x + COMBO_LIST_PAD_L, iy + COMBO_LIST_IH / 2.0,
                           text=txt, font=self.tk_f_10, fill=fg,
                           anchor="w", tags="fx")
            self.regions.append({"kind": "combo_item",
                                 "box": (x, iy, x + lw, iy + COMBO_LIST_IH),
                                 "key": k, "data": it})
        # ② 把「画了几项、几项被截断」写进日志。
        #    为什么值得单独记一行：网卡名有没有被砍**只能从渲染结果判断**，
        #    外部抓图判别「省略号 vs 完整末字」余量极小、不可靠（实测 42 像素
        #    vs 阈值 40）。让修复层自己报最准，真机验收直接查这一行。
        #    只在结果变化时写，避免 refresh_fx 每帧刷屏。
        try:
            sig = (tuple(show), lw, tuple(t[1] for t in drawn))
            if getattr(self, "_ipscaner_combolist_sig", None) != sig:
                self._ipscaner_combolist_sig = sig
                _lg = globals().get("_log")
                if callable(_lg):
                    _lg("网卡下拉列表：画出 %d 项，被截断 %d 项，列表宽 %d 设计px"
                        "（最长项 %d，可用文本宽 %d）"
                        % (len(show), len(drawn), lw, widest, text_avail))
                    for _a, _b in drawn:
                        _lg("    截断 %r -> %r" % (_a, _b))
        except Exception:  # noqa: BLE001
            pass

    _draw_combo_list.__doc__ = getattr(_M.MainForm._draw_combo_list,
                                       "__doc__", None)
    _draw_combo_list._ipscaner_combolist = True
    _M.MainForm._draw_combo_list = _draw_combo_list
    _M.MainForm._ipscaner_combolist_done = True
    if log is not None:
        log("网卡下拉列表已改为「宽度自适应 + 按字符边界截断」"
            "（原实现是硬砍前 6 个字符 → 'Virtua…'）")
    return 1


# ------------------------------------------------------------------ 4.65 系统命令启动器
# 2026-10-08 用户实测：「window命令里面的环境变量点击不了，报错」。
#
# 取证（probe_cmd.py + probe_launch.py，两次独立复现）：
#   menu_def 里「环境变量」的动作是 'cmd:sysdm.cpl,,3'；mainform.fire 的 cmd: 分支
#   把它拼成 argv = ['cmd','/c','start','','sysdm.cpl,,3'] 交给 run_cmd。
#   实测这个 argv：
#     · subprocess.run(..., capture_output=True, timeout=5) → **TimeoutExpired**，
#       进程挂住不返回（run_cmd 内部 timeout=3 同样触发，被 except 吞掉返回 ''）；
#     · 同时冒出一个标题**就叫 'sysdm.cpl,,3'** 的窗口 —— 那就是用户看到的「报错」。
#   原因：`start` 把第一个带引号的参数当窗口标题，其后整串当「文件」交 ShellExecute。
#         'sysdm.cpl,,3' 不是文件名（那是 control.exe 的「文件,窗口,页号」语法），
#         于是 ShellExecute 失败。
#   同批菜单里 'control userpasswords' / 'control printers'（动作串里带空格，
#   经 list2cmdline 加引号后同样被 start 当标题吃掉）**也是坏的**。
#
# 逐条实测哪种写法真能把目标打开（枚举顶层窗口判定，不是看返回码）：
#   ✗ cmd /c start "" sysdm.cpl,,3      → 挂住 + 报错窗
#   ✓ rundll32.exe sysdm.cpl,EditEnvironmentVariables → 真开出「环境变量」
#   ✓ control.exe sysdm.cpl,,3          → 真开出「系统属性」
#   ✓ control.exe userpasswords         → 真开出「用户帐户」
#   ✗ cmd /c start "" "control userpasswords" → 挂住 + 报错窗
#
# 修法：不再用 `cmd /c start`，按目标类型选启动器；一律 Popen + DETACHED_PROCESS
# 且**绝不捕获输出**（capture_output 的管道会被拉起的 GUI 进程继承，
# subprocess.run 就会一直等到那个进程退出 —— 这正是「卡住」的机制）。
def launch_system(target, log=None):
    """按目标类型用可靠方式打开系统工具。返回 True 表示已接管。"""
    import os as _os
    t = (target or "").strip()
    if not t:
        return False
    low = t.lower()
    DETACHED = 0x00000008          # DETACHED_PROCESS

    def _pop(argv):
        import subprocess as _sp
        _sp.Popen(argv, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, stdin=_sp.DEVNULL,
                  creationflags=DETACHED, close_fds=True)

    try:
        # ① 'control <小程序名>' —— 目标带空格，绝不能交给 start
        if low.startswith("control "):
            _pop(["control.exe", t.split(None, 1)[1].strip()])
            return True
        # ② '<x>.cpl,,[页号]' —— 「环境变量」就是这一类
        if ".cpl,," in low:
            cpl, _, tab = t.partition(",,")
            if cpl.lower().strip() == "sysdm.cpl" and tab.strip() == "3":
                # 直接开「环境变量」对话框（rundll32 的标准入口）。
                # 原版用 ,,3 是「系统属性→高级」那一页，用户还得自己找按钮；
                # 菜单名就叫「环境变量」，直接到位更贴合语义。
                _pop(["rundll32.exe", "sysdm.cpl,EditEnvironmentVariables"])
            else:
                _pop(["control.exe", t])
            return True
        # ③ '<x>.cpl' —— 必须经 control.exe；直接 CreateProcess 起 .cpl 不生效
        if low.endswith(".cpl"):
            _pop(["control.exe", t])
            return True
        # ④ 带扩展名（.msc / .exe / .bat …）—— ShellExecute 走文件关联
        if _os.path.splitext(t)[1]:
            _os.startfile(t)
            return True
        # ⑤ 无扩展名（regedit / control）—— 先按 PATH 找 exe，再退 ShellExecute
        import shutil as _sh
        exe = _sh.which(t)
        if exe:
            _pop([exe])
            return True
        _os.startfile(t)
        return True
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("系统命令 %r 启动失败 %r（已回退原实现）" % (t, e))
        return False


def patch_system_launcher(root=None, log=None):
    """把 `cmd /c start "" <目标>` 这种调用接管为可靠启动器（幂等）。

    只拦『恰好 5 个元素且前 4 个是 cmd,/c,start,""』的形状 —— 这是 mainform.fire
    里 cmd: 分支的唯一形态，不会误伤 run_cmd 的其它用途（ipconfig/arp/ping/netsh…）。
    """
    import os as _os
    if _os.environ.get("IPSCANER_NO_CMD_FIX") == "1":
        return 0
    try:
        import sys as _sys
        _C = _sys.modules.get("core")
        if _C is None or not hasattr(_C, "run_cmd"):
            return 0
        orig = _C.run_cmd
        if getattr(orig, "_ipscaner_cmdfix", False):
            return 1
    except Exception:  # noqa: BLE001
        return 0

    def run_cmd(args, timeout=8):
        try:
            if isinstance(args, (list, tuple)) and len(args) == 5:
                head = [str(x).lower() for x in args[:4]]
                if head[:3] == ["cmd", "/c", "start"] and head[3] == "":
                    if launch_system(str(args[4]), log=log):
                        return ""
        except Exception:  # noqa: BLE001
            pass
        return orig(args, timeout=timeout)

    run_cmd._ipscaner_cmdfix = True
    run_cmd.__doc__ = getattr(orig, "__doc__", None)
    _C.run_cmd = run_cmd
    if log is not None:
        log("系统命令启动器已接管 core.run_cmd（不再走 cmd /c start）")
    return 1


def apply_deferred_patches(root, log=None):
    """把「需要 mainform / theme / core 已进 sys.modules」的补丁装一遍。

    为什么单独抽出来、并且要在**两个时机**各调一次：
      · install() 挂在 Tk.__init__ 上，那时 main_opt 已经在模块级 import 过
        mainform/theme/dialogs，所以这里通常能一次装成；
      · 但冻结版里 core 有时还没进 sys.modules（PyInstaller 的 PYZ 导入器时序），
        装不上必须能重试 —— sweep() 里再调一次兜底。
      ⚠️ 时机很要紧：gui.init_state() 会把带前缀的网卡名抓进 self.adapter_text，
        它跑在 install() **之后**、sweep 的第一次（300ms）**之前**。
        只在 sweep 里装 → 第一次绘制仍是裁掉的真名（用户 2026-10-08 看到的正是这个）。
    幂等：每个 patch 自己带标记，重复调用直接返回。
    """
    res = {}
    for name, fn in (("get_adapters", patch_get_adapters),
                     ("adapter_fit", patch_adapter_fit),
                     ("system_launcher", patch_system_launcher),
                     ("popup_perf", patch_popup_perf),
                     ("combo_list", patch_combo_list),
                     ("main_resize", patch_main_resize),
                     ("req36", patch_req36)):
        try:
            res[name] = fn(root, log=log)
        except Exception as e:  # noqa: BLE001
            res[name] = -1
            if log is not None:
                log("延迟补丁 %s 安装失败 %r" % (name, e))
    return res


# ------------------------------------------------------------------ 4.7 弹窗性能
# 2026-10-09 用户实测：「为什么打开快捷工具里面的菜单，都有几百 ms 的延迟，
# 然后窗口才会变大」。真机量下来是**两处叠加**，主次分明：
#
#  ① 主因（占绝大多数）：本修复层自己的 sweep 每 500ms 跑一轮，其中
#     fix_canvas_contrast 做「文字 × 底色块」笛卡尔积的全量重扫，单轮占
#     Tk 主线程 320ms。进程空闲时也常年烧掉一个核的 37%（实测 37.4%）。
#     Tk 的单线程消息循环里，点击事件必须先排队等这段 Python 跑完 ——
#     这就是用户感知的「几百 ms」。已在本批同一处把它改成增量 + bbox 共享。
#
#  ② 次因（每开一次菜单都要付）：popup.MenuPopup.place() 第一句是
#        self.win.update_idletasks()
#     Tk 的 update_idletasks 刷的是**整个解释器的空闲队列**，不只这个弹窗：
#     主窗体 refresh_fx / 状态栏 / 工具条任何待处理的空闲工作都会在这里被
#     同步跑掉，而且记在弹窗头上。源码态 cProfile 实测：tools 菜单
#     place=128ms 里 update_idletasks 占 121ms（94%）。
#     place() 其实**不需要**它 —— 窗口尺寸 wpx/hpx 是用 self.w/self.h
#     （Python 侧布局结果）算的，而 geometry() 对**未映射**的窗口同样生效，
#     紧接着的 deiconify() 一上来就是终态尺寸（真机 6 轮探针实测：
#     弹窗首次可见时的 rect 就是终态 rect，没有 small→big 的中间态）。
#     去掉它，把空闲队列还给正常事件循环，点击即返回。
#
#  ③ 附带：进程里**第一个** -transparentcolor 窗口的首次实现约 19ms
#     （DWM 分层窗初始化；_perf_pop.py 实测带透明色 21.2ms vs 不带 2.2ms，
#     且只在第一个窗口出现）。用一次性预热把它挪到启动阶段去付，
#     别让用户第一次点菜单来付。
def patch_popup_perf(root=None, log=None):
    """改写 popup.MenuPopup.place：去掉那次「整解释器空闲队列」的同步冲刷。

    与原实现逐句对应，只删掉开头的 win.update_idletasks()。
    IPSCANER_NO_POPUP_PERF=1 可关掉（回退到原版行为，用于排查）。
    """
    import os as _os
    if _os.environ.get("IPSCANER_NO_POPUP_PERF") == "1":
        return 0
    try:
        import sys as _sys
        _P = _sys.modules.get("popup")
        if _P is None:
            return 0
        _MP = getattr(_P, "MenuPopup", None)
        if _MP is None:
            return 0
        if getattr(_MP, "_ipscaner_perf_done", False):
            return 1
    except Exception:  # noqa: BLE001
        return 0

    import tkinter as _tk

    def place(self, x, y, prefer_up=False):
        # ⚠️ 布局/夹取数学必须与原字节码逐句一致（见 _dump_place.txt）：
        #    窗口比面板大 2*pad（给阴影留边），越界先右移、再左夹、再上翻。
        S, pad = self.S, self.pad
        wpx = int(self.w * S) + 2 * pad
        hpx = int(self.h * S) + 2 * pad
        win = self.win
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        margin = getattr(_P, "SCREEN_MARGIN", 8)
        vx, vy = int(x), int(y)
        px, py = vx - pad, vy - pad
        if px + wpx > sw - margin:
            px = vx - wpx + pad
        if px < 0:
            px = 0
        if px + wpx > sw - margin:
            px = max(0, sw - margin - wpx)
        if py + hpx > sh - margin:
            flip = vy - hpx + pad
            py = flip if flip >= 0 else max(0, sh - margin - hpx)
        if py < 0:
            py = 0
        win.geometry("%dx%d+%d+%d" % (wpx, hpx, px, py))
        win.deiconify()
        win.lift()
        try:
            win.attributes("-topmost", True)
        except _tk.TclError:
            pass

    place.__doc__ = getattr(getattr(_MP, "place", None), "__doc__", None)
    place._ipscaner_popup_perf = True
    _MP.place = place
    _MP._ipscaner_perf_done = True
    if log is not None:
        log("弹窗性能：place() 不再同步冲刷全局空闲队列（去掉 update_idletasks）")
    return 1


_POPUP_WARMED = [False]


def warm_popup_windows(root=None, log=None):
    """一次性预热「-transparentcolor + overrideredirect」分层窗，然后销毁。

    为什么有用：进程里第一个这种窗口的首次实现要 ~19ms（DWM/主题初始化）。
    预热放在启动阶段（sweep 第一轮）把它付掉，用户第一次点菜单就不用等。
    ⚠️ 只 update_idletasks、**不 deiconify**：那 19ms 本来就花在
       update_idletasks 里（实测：withdrawn 状态下 update_idletasks 21.2ms），
       不 deiconify 就不会闪一下、也不会抢焦点。
    """
    if _POPUP_WARMED[0]:
        return 0
    try:
        import sys as _sys
        _P = _sys.modules.get("popup")
        if _P is None:
            # ⭐ 必须**主动**引入。mainform 是在 open_menu_popup() 里
            #    `import popup as P` 才第一次加载它的 —— 也就是说用户
            #    **第一次点菜单之前** popup 根本不在 sys.modules 里，而
            #    patch_popup_perf 只能等到下一轮 sweep（最多 500ms 后）才装得上。
            #    真机实测就踩到了：第一次点菜单仍走旧 place（带 update_idletasks）。
            #    popup 模块级只 import tkinter/menu_def（无 root 依赖），
            #    这里主动引入是安全的；引入后立刻把 place 补丁装上，
            #    保证「第一次点菜单」就已经是新实现。
            try:
                import popup as _P       # noqa: F401
            except Exception:  # noqa: BLE001
                return 0
        patch_popup_perf(root, log=log)
        import tkinter as _tk
        host = _tk._default_root
        if host is None:
            return 0
        tr = getattr(_P, "TRANSPARENT", "#FE00FE")
        w = _tk.Toplevel(host)
        w.withdraw()
        w.overrideredirect(True)
        try:
            w.configure(bg=tr)
            w.attributes("-transparentcolor", tr)
        except _tk.TclError:
            w.configure(bg=getattr(_P, "C_BORDER", "#808080"))
        _tk.Canvas(w, width=48, height=48, bg=tr,
                   highlightthickness=0, bd=0).pack()
        w.update_idletasks()          # ← 真正花那 ~19ms 的一步
        try:
            w.destroy()
        except Exception:  # noqa: BLE001
            pass
        _POPUP_WARMED[0] = True
        if log is not None:
            log("弹窗性能：透明分层窗已预热（DWM 初始化移到启动阶段）")
        return 1
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("弹窗预热失败（不影响功能）%r" % (e,))
        _POPUP_WARMED[0] = True      # 失败也不再重试，避免每轮 sweep 都报
        return 0


# ------------------------------------------------------------------ 4.85 子窗体首帧
# 缺陷13（用户 2026-10-09「我想说的是类似这个一键设置ip子菜单，为什么是先弹出
# 一个小窗口，等了一会又变大的呢」）：
#
# 反汇编 dialogs.mkform（line 53-72）原文：
#       top = tk.Toplevel(main.root)
#       top.title(title)
#       top.geometry(f"{w}x{h}")        # ← FORMS 里的**设计尺寸 1:1**
#       top.configure(bg=T.C_FACE)
#       top.resizable(resizable if resizable is not None else res, ...)
#       _OPEN[key] = top
#       return top
# 全程既没有 withdraw 也没有 deiconify —— 新建的 Toplevel 默认就是**可见**的，
# 所以窗口立刻以设计尺寸（1:1，比主窗体小 1/3）出现在屏幕上；而「把它放大到
# 设计×S」的活儿落在常驻 sweep 上（最长 500ms 一轮）→ 用户看到的就是
# 「先弹一个小窗口，等了一会又变大」。测试机 实测：localip 设计 575x660 →
# 先以 575x660 出现，约 0.1~0.5s 后才变成 862x990。
#
# 修法：新建 Toplevel 时**立刻** withdraw（与创建同一个调用栈，中间没有任何
# 一帧被画出来），等**构建完成**再「缩放 + 显示」→ 第一帧就是终态尺寸。
# 判据「构建完成」= 子孙控件数量连续两次空闲不变（产品若在构建途中调
# update() 也不会误判：数量变了就再来一轮）。
# 源码态实测（_probe_hidden.py，5 个时刻快照）：withdrawn 的 Toplevel 上
# place 子控件的 winfo_x/y/width/height 与已映射时**逐项一致**，所以缩放
# 可以在隐藏态全部做完。
# 可用 IPSCANER_NO_DEFER_SHOW=1 关闭（回退成「先小后大」原行为）。
_DEFER_ENV = "IPSCANER_NO_DEFER_SHOW"
_DEFER_BUILD_TRIES = 12
_DEFER_SCALE_TRIES = 40


def defer_is_popup(win):
    """无边框弹层（MenuPopup）：它自己在 place() 里 deiconify，不要插手。"""
    try:
        return bool(win.overrideredirect())
    except Exception:  # noqa: BLE001
        return True


def defer_hide(win, ctx):
    """新建窗体立刻隐藏，并排一次「构建完成后显示」（同一调用栈内，无闪帧）。

    ⚠️ 顺序要紧：`_ipscaner_autohide` 必须在**调用 withdraw 之后**才置位 ——
    withdraw 被本层的包装拦着（用来记录「产品自己隐藏」），如果先置位，这次
    自动隐藏会被误判成产品行为 → 窗口永远不显示（已用这个顺序避开）。
    """
    import tkinter as _tk
    if getattr(win, "_ipscaner_autohide", False):
        return
    try:
        _tk.Wm.withdraw(win)
    except Exception:  # noqa: BLE001
        return
    win._ipscaner_autohide = True
    defer_schedule(win, ctx)


def defer_schedule(win, ctx):
    if getattr(win, "_ipscaner_defer_armed", False):
        return
    win._ipscaner_defer_armed = True
    try:
        win.after_idle(lambda: defer_show(win, ctx, 0, 0))
    except Exception:  # noqa: BLE001
        defer_show(win, ctx, 0, 0)


def defer_show(win, ctx, bt=0, st=0):
    """构建完成后：缩放到 设计×S，再显示。

    bt/bt 上限：构建等待最多 _DEFER_BUILD_TRIES 个空闲轮；缩放等待最多
    _DEFER_SCALE_TRIES 次 25ms 重试。任一路上限到了都要**把窗口显示出来**
    —— 宁可退回旧行为，也不能让窗口永远不出现。
    """
    log = ctx.get("log")
    try:
        if not win.winfo_exists():
            return
    except Exception:  # noqa: BLE001
        return
    if getattr(win, "_ipscaner_shown", False):
        return                                   # 本机制已经显示过
    if defer_is_popup(win):
        return                                   # 菜单弹层自己管
    if getattr(win, "_ipscaner_user_hid", False):
        return                                   # 产品自己 withdraw 了 → 尊重它
    depth = len(_all(win))
    if getattr(win, "_ipscaner_pend_n", None) != depth and bt < _DEFER_BUILD_TRIES:
        win._ipscaner_pend_n = depth
        try:
            win.after_idle(lambda: defer_show(win, ctx, bt + 1, st))
        except Exception:  # noqa: BLE001
            pass
        return
    S = 1.0
    try:
        S = float(ctx["S"]())
    except Exception:  # noqa: BLE001
        pass
    key = None
    try:
        key = (ctx.get("keys") or {}).get(str(win.title()))
    except Exception:  # noqa: BLE001
        pass
    res = None
    try:
        res = scale_dialog(win, S, key=key, log=None)
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("首帧缩放失败 %r" % (e,))
    if res is None:
        # 几何还没结算（罕见）→ 稍后再来；实在不行就显示出来交给 sweep 兜
        if st < _DEFER_SCALE_TRIES:
            try:
                win.after(25, lambda: defer_show(win, ctx, bt, st + 1))
                return
            except Exception:  # noqa: BLE001
                pass
        if log is not None:
            log("首帧缩放放弃（几何未结算），交给 sweep 兜：%r" % (win.title(),))
    elif getattr(win, _M_SIZED, False):
        # 别人（sweep 兜底）已经缩过了 → 绝不能再缩一次，否则乘成 S²
        pass
    else:
        try:
            setattr(win, _M_SIZED, True)
            setattr(win, _M_SCALE, S)
            win.update_idletasks()
            # ⚠️ 必须用 clamp_settled（异步等几何结算），不能直接调
            #    clamp_overflow —— 那一刻 winfo 还是旧尺寸，会把底行钳成
            #    8px 废条。详见 clamp_settled 头注。
            clamp_settled(win, log=log)
        except Exception:  # noqa: BLE001
            pass
    win._ipscaner_shown = True                   # 必须在 deiconify 之前置位
    try:
        win.deiconify()
        win.lift()
    except Exception:  # noqa: BLE001
        pass
    if log is not None and res is not None:
        log("子窗体首帧即终态：%r 建完 %d 个子孙后按 S=%s 缩放并显示"
            % (win.title(), depth, S))


# ------------------------------------------------------------------ 4.86 主窗体可缩放
# 缺陷14（用户 2026-10-09「软件还是不能放大，缩小窗口呢」）：
#   实测 root.resizable() == (0, 0)，且 MainForm.__init__ / _apply_zoom 里的
#   _force_client_size() 把客户区钉死在 CLIENT_W×CLIENT_H（设计 835×486，
#   DPI 1.5 → 1252×729）—— 所以最大化按钮是灰的、拖边框也没反应。
#
#   主窗体是**固定坐标画布**：theme 里所有几何都是设计值，ScaledCanvas 把
#   create_text/create_rectangle/create_line 的坐标乘 self.s。而且 254 个 IP 格
#   本来就是 20 列 × 13 行铺满 825×450（客户区 835×486）——**放大窗口并不会
#   多出格子**。所以正确的做法不是重排版，而是把「窗口尺寸」映射成「缩放比」：
#   窗口变大 → 内容等比变大（这同时回应了之前「字太小看不清」的诉求）。
#
#   zoom 沿用 Ctrl+滚轮的既有区间 [1.0, 2.0]（zoom_by 的约定），S = DPI基准×zoom。
#   画布不再随窗口拉伸，仍按 设计×S 绘制、**锚在客户区左上**；多出来的区域是
#   窗体底色。弹层坐标不用改：_popup_geometry() 返回的正是**客户区原点**，
#   画布锚在左上时二者重合（这也是这里必须显式 anchor='nw' 的原因 ——
#   pack 的默认 anchor 是 center，居中会让所有弹层整体偏一个边距）。
#   可用 IPSCANER_NO_RESIZE=1 关闭。
ZOOM_MIN = 1.0
ZOOM_MAX = 2.0
RESIZE_DEBOUNCE_MS = 140


def _frame_extents(root):
    """窗口边框+标题栏厚度（物理像素）= GetWindowRect - GetClientRect。

    ⚠️ 实测结论见 `_probe_ms.txt`：Tk 在 Windows 上 `wm geometry` 和
    `wm minsize` **都是客户区语义**（外框由 wm 在客户区之外另加），所以
    这个函数**不该**再用来给 minsize 加偏移 —— 留着只为了「要知道外框多厚」
    这类诊断用途（本机 = (16, 39)）。
    """
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    hwnd = u.GetAncestor(root.winfo_id(), 2) or root.winfo_id()
    wr, cr = wintypes.RECT(), wintypes.RECT()
    u.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(wr))
    u.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(cr))
    return ((wr.right - wr.left) - cr.right,
            (wr.bottom - wr.top) - cr.bottom)


def refit_main(app, log=None):
    """按 app.zoom 重建主界面 = _apply_zoom 的等价物，但**不动窗口尺寸**。

    _apply_zoom 会 root.geometry(...) + _force_client_size() 把客户区掰回
    设计×S —— 那是「窗口尺寸由内容决定」的旧语义。窗口可缩放之后必须反过来
    由**窗口尺寸**决定 zoom，所以这里只保留重绘那部分。
    """
    T = _theme()
    if T is None:
        return 0
    base = float(getattr(app, "_base_scale", 1.0) or 1.0)
    S = base * float(getattr(app, "zoom", 1.0) or 1.0)
    try:
        T.SCALE = S
        app.S = S
    except Exception:  # noqa: BLE001
        return 0
    cv = getattr(app, "cv", None)
    try:
        cv.configure(width=T.u(T.CLIENT_W), height=T.u(T.CLIENT_H))
    except Exception:  # noqa: BLE001
        pass
    try:
        cv.s = S
    except Exception:  # noqa: BLE001
        pass
    try:
        app._mk_fonts()
    except Exception:  # noqa: BLE001
        pass
    try:
        import sys as _sys
        _M = _sys.modules.get("mainform")
        app.icons = {}
        for n, im in (getattr(app, "_raw_icons", {}) or {}).items():
            app.icons[n] = _M.scale_img(im, S)
    except Exception:  # noqa: BLE001
        pass
    for fn in ("build_base", "refresh_fx"):
        try:
            getattr(app, fn)()
        except Exception as e:  # noqa: BLE001
            if log is not None:
                log("%s 重绘失败 %r" % (fn, e))
    return 1


def install_main_resize(app, log=None):
    """给主窗体装「窗口尺寸 → zoom」联动（幂等，按实例标记）。"""
    import os as _os
    if _os.environ.get("IPSCANER_NO_RESIZE") == "1":
        return 0
    T = _theme()
    root = getattr(app, "root", None)
    cv = getattr(app, "cv", None)
    if T is None or root is None or cv is None:
        return 0
    if getattr(app, "_ipscaner_resize_link", False):
        return 1
    app._ipscaner_resize_link = True
    try:
        cv.pack_configure(anchor="nw")
    except Exception:  # noqa: BLE001
        pass
    try:
        root.resizable(True, True)
    except Exception:  # noqa: BLE001
        pass
    try:
        dw, dh = int(T.u(T.CLIENT_W)), int(T.u(T.CLIENT_H))
    except Exception:  # noqa: BLE001
        return 0
    try:
        # ⚠️ 实测（_probe_ms.txt）：Tk 在 Windows 上 `wm geometry` 与 `wm minsize`
        #    **都是客户区语义** —— geometry("800x500") 实测 client=800x500；
        #    minsize(1000,600) 实测 client=1000x600（外框恒 = (16,39)）。
        #    早前这里写成 dw+fw/dh+fh 是把它当外框语义了，结果拖到底时客户区
        #    是 1268x768 而不是 1252x729，zoom 永远回不到 1.0（实测 1.013）。
        root.minsize(dw, dh)
    except Exception:  # noqa: BLE001
        pass
    state = {"t": None}

    def _conf(event):
        try:
            if event.widget is not root:
                return
        except Exception:  # noqa: BLE001
            return
        # 拖边框时 Configure 会连发，防抖到停手 140ms 再重算，避免每帧重绘
        try:
            if state["t"] is not None:
                root.after_cancel(state["t"])
        except Exception:  # noqa: BLE001
            pass
        try:
            state["t"] = root.after(RESIZE_DEBOUNCE_MS, _do)
        except Exception:  # noqa: BLE001
            pass

    def _do():
        state["t"] = None
        try:
            cw, ch = app._client_size()
        except Exception:  # noqa: BLE001
            return
        if cw <= 1 or ch <= 1:
            return
        z = min(cw / float(dw), ch / float(dh))
        bounce = False
        if z < ZOOM_MIN:
            z, bounce = ZOOM_MIN, True
        elif z > ZOOM_MAX:
            z = ZOOM_MAX

        cur = float(getattr(app, "zoom", 1.0) or 1.0)
        if bounce:
            # 小于内容下限 → 把客户区掰回下限（比 minsize 精确：直接用实测客户区）
            try:
                root.geometry("%dx%d" % (dw, dh))
            except Exception:  # noqa: BLE001
                pass
        if abs(z - cur) < 0.015:
            return
        app.zoom = z
        refit_main(app, log=log)
        if log is not None:
            log("窗口缩放：客户区 %dx%d → zoom %.3f（S=%.3f）"
                % (cw, ch, z, float(getattr(app, "_base_scale", 1.0) or 1.0) * z))

    try:
        root.bind("<Configure>", _conf, add="+")
    except Exception as e:  # noqa: BLE001
        app._ipscaner_resize_link = False
        if log is not None:
            log("窗口缩放绑定失败 %r" % (e,))
        return 0
    if log is not None:
        log("主窗体已允许放大/缩小（窗口尺寸 ↔ zoom，内容等比适配；"
            "最小客户区 %dx%d）" % (dw, dh))
    return 1


def patch_main_resize(root=None, log=None):
    """接管 MainForm：登记实例 + 装可缩放联动（幂等）。"""
    import os as _os
    if _os.environ.get("IPSCANER_NO_RESIZE") == "1":
        return 0
    try:
        import sys as _sys
        _M = _sys.modules.get("mainform")
        if _M is None or not hasattr(_M, "MainForm"):
            return 0
        M = _M.MainForm
        if getattr(M, "_ipscaner_resize_done", False):
            app = getattr(root, "_ipscaner_app", None)
            return install_main_resize(app, log=log) if app is not None else 1
        orig_init = M.__init__
        orig_fx = M.refresh_fx

        def __init__(self, *a, **k):
            orig_init(self, *a, **k)
            try:
                self.root._ipscaner_app = self
            except Exception:  # noqa: BLE001
                pass
            install_main_resize(self, log=log)

        def refresh_fx(self, *a, **k):
            r = orig_fx(self, *a, **k)
            # 兜底登记：本补丁若晚于 MainForm 构造才装上（mainform 刚进
            # sys.modules 的那一轮），__init__ 包装永远轮不到，refresh_fx 是
            # 唯一每轮都会拿到 self 的地方。
            try:
                if getattr(self.root, "_ipscaner_app", None) is not self:
                    self.root._ipscaner_app = self
                install_main_resize(self, log=log)
            except Exception:  # noqa: BLE001
                pass
            return r

        __init__._ipscaner_resize = True
        refresh_fx._ipscaner_resize = True
        M.__init__ = __init__
        M.refresh_fx = refresh_fx
        M._ipscaner_resize_done = True
        app = getattr(root, "_ipscaner_app", None)
        if app is not None:
            install_main_resize(app, log=log)
        return 1
    except Exception:  # noqa: BLE001
        return 0


# ------------------------------------------------------------------ 4.8 版本号覆盖
# 绿色版把版本号**硬编码在字节码常量**里（实测）：
#   gui.APP_VERSION  = '1.25.0'
#   theme.TITLE_VER  = '  Ver: 1.25.0'
#   dialogs.ASSEMBLY['version'] = '1.25.0.0'
# 改 src/ 不会影响已打包的 exe（跑的是 build_green/*.pyc），所以必须在
# 运行期改常量。时机很关键：mainform 建窗时执行
#   root.title(T.TITLE_TEXT + T.TITLE_VER)
# 所以要在**第一次 title() 之前**改掉 theme.TITLE_VER。
BUILD_VERSION = "1.27.0"          # 本修复层对应的交付版本


def set_version(log=None, ver=None):
    """把运行态的版本号常量改成 BUILD_VERSION，并重设已建窗口的标题。

    返回 (改了几个模块, 标题是否已重设)。
    """
    import sys
    ver = ver or BUILD_VERSION
    changed = []

    # 1) 常量覆盖
    for mod, attr, new in (("gui", "APP_VERSION", ver),
                            ("theme", "TITLE_VER", "  Ver: " + ver),
                            ("theme", "TITLE_TEXT", None)):
        m = sys.modules.get(mod)
        if m is None:
            continue
        old = getattr(m, attr, None)
        if new is None or old == new:
            continue
        try:
            setattr(m, attr, new)
            changed.append("%s.%s: %r -> %r" % (mod, attr, old, new))
        except Exception:  # noqa: BLE001
            pass

    # dialogs.ASSEMBLY 是 dict，就地改其中的 version
    d = sys.modules.get("dialogs")
    if d is not None:
        asm = getattr(d, "ASSEMBLY", None)
        if isinstance(asm, dict) and asm.get("version") != ver + ".0":
            old = asm.get("version")
            asm["version"] = ver + ".0"
            changed.append("dialogs.ASSEMBLY['version']: %r -> %r"
                           % (old, asm["version"]))

    # 2) 标题重设（窗口可能已经建出来了）
    #    注意：主窗体是 root **本身**，不在 winfo_children() 里，必须单独处理。
    titled = False
    th = sys.modules.get("theme")
    if th is not None:
        ttext = getattr(th, "TITLE_TEXT", "")
        want = ttext + getattr(th, "TITLE_VER", "")
        import tkinter as _tk
        cands = []
        if _tk._default_root is not None:
            cands.append(_tk._default_root)
            cands.extend(_tk._default_root.winfo_children())
        for w in cands:
            try:
                cur = w.title()
                # 只改「本来就是这个产品标题」的窗口，避免误改子窗体标题
                if cur and cur.startswith(ttext) and cur != want:
                    w.title(want)
                    titled = True
            except Exception:  # noqa: BLE001
                continue

    if log is not None:
        if changed:
            log("版本号覆盖为 %s：%s" % (ver, "；".join(changed)))
        else:
            log("版本号已是 %s，无需覆盖" % ver)
    return changed, titled


# ============================== 4.87 需求36：备注增强 / Excel 导出 / 导入 IP 表格
# 用户 2026-10-10 需求 36 三条：
#   1) 批量 ping 几百个 IP 时，能对特殊 IP 备注用途；并能导出 Excel
#      —— 哪些通、哪些不通、各自的备注
#   2) 能批量导入一个表格里的 IP（可能**不是一个网段**）再 ping
#   3) README + 上传 GitHub（与本层无关，见仓库）
#
# 现状（全部由 build_green/*.pyc 反汇编 + 活体探针确认；src/ 里混着
# 「复刻版未实现」的桩，不可信）：
#   · 主页右键 →「备注信息(&M)」**本来就有**：
#       mainform._draw_context_menu → run_ip_command(ip,'cmemo') → _memo_edit
#   · 备注只存在内存 MainForm.memos（键 = 完整 IP 字符串），**从不落盘** → 关掉就丢
#   · 主窗体 export 只遍历 range(1,255) 再拼 self.ip_part
#     → **只能导当前那一个 /24**，跨网段批量扫描的结果一条都导不出来
#   · 批量扫描弹窗的结果表有「备注」列，但 on_result 里硬编码传 '' → 永远是空的
#   · 两处导出都走 core.export_csv（CSV，utf-8-sig）；core 里**没有任何
#     xlsx/OOXML 写出器** —— 用户要的「导出 excel 表格」得自己写
#   · core.parse_ip_input **本来就是逐行解析**的（CIDR / 连续范围 / 单网段 /
#     单个 IP 混在一段文本里也认），所以「跨网段任意 IP 列表」的扫描引擎
#     早就支持，缺的只是「从表格文件导入」这个入口
#
# 本层做的事：
#   A. memos.json 持久化（%APPDATA%\IPScaner-Py\memos.json，与 ip_history.json 同目录）
#   B. 重写 _memo_edit：独立窗口键 / 不误刷跨网段格子 / 保存即落盘
#   C. 批量扫描结果表右键「编辑备注 / 清空备注」+ 已有备注自动回填
#   D. 纯标准库 xlsx 写出器（zipfile + 手写 OOXML），接到两处导出上
#   E. 纯标准库 xlsx 读取器 + IP 抽取 + 「导入表格」按钮
#
# 可用 IPSCANER_NO_REQ36=1 整体关闭（A/B 对照）。

REQ36_OFF = "IPSCANER_NO_REQ36"


def _req36_on():
    import os as _o
    return _o.environ.get(REQ36_OFF) != "1"


# ------------------------------------------------------------ A. xlsx 写出器
def _xesc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;")
            .replace("\r", " ").replace("\n", " "))


def _xcol(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _xname(s):
    """工作表名：去掉 OOXML 禁用的 []:*?/\\ 并截到 31 字符。"""
    out = []
    for ch in str(s):
        out.append("_" if ch in "[]:*?/\\" else ch)
    return ("".join(out) or "Sheet")[:31]


def _xsheet(header, rows, widths=None):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/'
           'spreadsheetml/2006/main">',
           '<sheetViews><sheetView workbookViewId="0">'
           '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft"'
           ' state="frozen"/></sheetView></sheetViews>']
    if widths:
        out.append("<cols>")
        for i, w in enumerate(widths):
            out.append('<col min="%d" max="%d" width="%s" customWidth="1"/>'
                       % (i + 1, i + 1, w))
        out.append("</cols>")
    out.append("<sheetData>")
    out.append('<row r="1" ht="21" customHeight="1">')
    for i, v in enumerate(header):
        out.append('<c r="%s1" s="1" t="inlineStr"><is><t xml:space="preserve">'
                   '%s</t></is></c>' % (_xcol(i), _xesc(v)))
    out.append("</row>")
    for ri, row in enumerate(rows, start=2):
        out.append('<row r="%d">' % ri)
        for i, v in enumerate(row):
            out.append('<c r="%s%d" t="inlineStr"><is><t xml:space="preserve">'
                       '%s</t></is></c>' % (_xcol(i), ri, _xesc(v)))
        out.append("</row>")
    out.append("</sheetData></worksheet>")
    return "".join(out)


_XLSX_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<fonts count="2">'
    '<font><sz val="11"/><name val="\u5fae\u8f6f\u96c5\u9ed1"/></font>'
    '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/>'
    '<name val="\u5fae\u8f6f\u96c5\u9ed1"/></font>'
    '</fonts>'
    '<fills count="3">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FF0078D4"/>'
    '<bgColor indexed="64"/></patternFill></fill>'
    '</fills>'
    '<borders count="1"><border/></borders>'
    '<cellStyleXfs count="1">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="2">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0"'
    ' applyFont="1" applyFill="1" applyAlignment="1">'
    '<alignment vertical="center"/></xf>'
    '</cellXfs>'
    '<cellStyles count="1">'
    '<cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    '</styleSheet>')


def write_xlsx(path, sheets, log=None):
    """极简 xlsx 写出：sheets = [(表名, 表头, 行, 列宽), ...]。

    纯 zipfile + 手写 OOXML，**不依赖 openpyxl**：要冻结进单文件 exe，
    多一个三方库就多一份打包风险，而我们写的只是字符串表格。
    所有单元格用 inlineStr —— 本工具的列（IP/状态/主机名/MAC/备注）本来就是文本，
    这样也不用维护 sharedStrings 表。
    """
    import zipfile

    n = len(sheets)
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
          'content-types">',
          '<Default Extension="rels" ContentType="application/vnd.'
          'openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.'
          'openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.'
          'openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    for i in range(n):
        ct.append('<Override PartName="/xl/worksheets/sheet%d.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.'
                  'spreadsheetml.worksheet+xml"/>' % (i + 1))
    ct.append("</Types>")

    wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
          '2006/main" xmlns:r="http://schemas.openxmlformats.org/'
          'officeDocument/2006/relationships"><sheets>']
    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
            '2006/relationships">']
    for i, sh in enumerate(sheets):
        wb.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>'
                  % (_xesc(_xname(sh[0])), i + 1, i + 1))
        rels.append('<Relationship Id="rId%d" Type="http://schemas.'
                    'openxmlformats.org/officeDocument/2006/relationships/'
                    'worksheet" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1))
    wb.append("</sheets></workbook>")
    rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.'
                'org/officeDocument/2006/relationships/styles" '
                'Target="styles.xml"/>' % (n + 1))
    rels.append("</Relationships>")

    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/'
                 'package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.'
                 'org/officeDocument/2006/relationships/officeDocument" '
                 'Target="xl/workbook.xml"/></Relationships>')

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", "".join(wb))
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rels))
        z.writestr("xl/styles.xml", _XLSX_STYLES)
        for i, sh in enumerate(sheets):
            z.writestr("xl/worksheets/sheet%d.xml" % (i + 1),
                       _xsheet(sh[1], sh[2], sh[3] if len(sh) > 3 else None))
    if log is not None:
        log("需求36 write_xlsx %s：%d 张表 %s"
            % (path, n, [len(s[2]) for s in sheets]))
    return path


# ------------------------------------------------------------ B. xlsx 读取器
def read_xlsx_text(path):
    """极简 xlsx 读取：把所有工作表的单元格文本摊平成一维列表。

    同样不依赖三方库。只取单元格的**展示值**（sharedStrings / inlineStr /
    数值 v），不解析样式、公式、合并单元格 —— 对「从表里捞 IP」够用。
    """
    import xml.etree.ElementTree as ET
    import zipfile

    NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    vals = []
    try:
        z = zipfile.ZipFile(path)
    except Exception as e:
        raise RuntimeError("打不开这个 xlsx（可能不是标准 Excel 文件）：%r" % (e,))
    with z:
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            try:
                sroot = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in sroot.findall(NS + "si"):
                    shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
            except Exception:
                shared = []
        sheets = sorted(n for n in names
                        if n.startswith("xl/worksheets/") and n.endswith(".xml"))
        for n in sheets:
            try:
                root = ET.fromstring(z.read(n))
            except Exception:
                continue
            for c in root.iter(NS + "c"):
                t = c.get("t")
                if t == "s":
                    v = c.find(NS + "v")
                    if v is not None and v.text is not None:
                        try:
                            vals.append(shared[int(v.text)])
                        except Exception:
                            pass
                elif t == "inlineStr":
                    isn = c.find(NS + "is")
                    if isn is not None:
                        vals.append("".join(x.text or ""
                                            for x in isn.iter(NS + "t")))
                else:
                    v = c.find(NS + "v")
                    if v is not None and v.text:
                        vals.append(v.text)
    return vals


# --------------------------------------------------------- C. IP 抽取 / 读文件
_IP4_RE = r"\d{1,3}(?:\.\d{1,3}){3}"


def extract_ip_targets(texts):
    """从任意文本/单元格里抽出 IP 目标，返回能被 core.parse_ip_input 吃掉的文本。

    只认**四段** IP：避免把「1.25.9」这类版本号当成「1.25 网段」展开成 254 个 IP。
    顺序敏感 —— 先连续范围、再 CIDR、最后单个（范围里的 IP 不能被单独重复匹配）。
    合法性交给 core.parse_ip_input 去判（999.1.1.1 会被它静默丢掉），
    这里不做第二套校验，免得两边规则漂移。
    """
    import re as _re

    tok = _re.compile(
        r"(%(ip)s)\s*-\s*(%(ip)s|\d{1,3})"        # 192.168.1.1-192.168.1.50 / -50
        r"|(%(ip)s\s*/\s*\d{1,2})"                # 192.168.1.0/24
        r"|(%(ip)s)" % {"ip": _IP4_RE})           # 单个
    found = []
    for t in texts:
        for m in tok.finditer(str(t)):
            if m.group(1):
                found.append("%s-%s" % (m.group(1), m.group(2)))
            elif m.group(3):
                found.append(m.group(3).replace(" ", ""))
            elif m.group(4):
                found.append(m.group(4))
    return "\n".join(found)


def _read_text_any(path):
    """按 utf-8-sig → gbk → utf-8 顺序试编码读纯文本。"""
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except Exception:
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def read_ip_file(path, log=None):
    """读表格/文本文件 → (去重排序后的 IP 列表, 说明文字)。"""
    import csv as _csv
    import os as _o

    ext = _o.path.splitext(path)[1].lower()
    if ext == ".xls":
        raise RuntimeError("老版 .xls 格式读不了。\n"
                           "请在 Excel 里「另存为」.xlsx 或 .csv 再导入。")
    if ext in (".xlsx", ".xlsm"):
        texts = read_xlsx_text(path)
    elif ext == ".csv":
        raw = _read_text_any(path)
        texts = [cell for row in _csv.reader(raw.splitlines()) for cell in row]
    else:
        texts = [_read_text_any(path)]

    blob = extract_ip_targets(texts)
    if not blob.strip():
        return [], "文件里没找到 IP"
    try:
        import core as _core
        ips = list(_core.parse_ip_input(blob))
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("IP 解析失败：%r" % (e,))
    return ips, "从 %d 个单元格/行解析出 %d 个目标" % (len(texts), len(ips))


# ------------------------------------------------------------ D. 备注持久化
def memos_dir():
    import os as _o
    return _o.path.join(_o.environ.get("APPDATA") or _o.path.expanduser("~"),
                        "IPScaner-Py")


def memos_path():
    import os as _o
    return _o.path.join(memos_dir(), "memos.json")


def load_memos(main, log=None):
    """启动时把磁盘备注灌回 main.memos，并把当前网段的格子刷成「有备注」。"""
    import json as _json
    import os as _o

    p = memos_path()
    if not _o.path.isfile(p):
        return 0
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = _json.load(f)
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("需求36 备注读取失败 %r" % (e,))
        return 0
    if not isinstance(data, dict):
        return 0
    try:
        if getattr(main, "memos", None) is None:
            main.memos = {}
    except Exception:  # noqa: BLE001
        return 0
    ip_part = str(getattr(main, "ip_part", "") or "")
    n = 0
    for k, v in data.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        k, v = k.strip(), v.strip()
        if not k or not v:
            continue
        try:
            main.memos[k] = v
            n += 1
        except Exception:  # noqa: BLE001
            continue
        if ip_part and k.startswith(ip_part + "."):
            last = k.rsplit(".", 1)[-1]
            if last.isdigit():
                try:
                    main.set_block(int(last), 3)
                except Exception:  # noqa: BLE001
                    pass
    if log is not None and n:
        log("需求36 备注已载入 %d 条（%s）" % (n, p))
    return n


def save_memos(main, log=None):
    """原子写（先写 .tmp 再 os.replace）。"""
    import json as _json
    import os as _o

    p = memos_path()
    try:
        d = _o.path.dirname(p)
        if d and not _o.path.isdir(d):
            _o.makedirs(d)
        tmp = p + ".tmp"
        data = dict(getattr(main, "memos", {}) or {})
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        _o.replace(tmp, p)
        if log is not None:
            # 埋点（2026-10-10）：真机「点保存后 memos.json 不变」排查用 ——
            # 有了这行就能区分「压根没调用 save_memos」和「写了但内容不对」。
            log("需求36 备注已写盘 %d 条 → %s（%d 字节）"
                % (len(data), p, _o.path.getsize(p)))
        return True
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("需求36 备注保存失败 %r" % (e,))
        return False


_MEMO_SAVE_MS = 600


def touch_memos(main, log=None, delay=None):
    """标记备注已变更，稍后合并落盘（扫描时 set_block 会被调很多次，不能每次写盘）。"""
    _ms = _MEMO_SAVE_MS if delay is None else delay
    try:
        main._ipscaner_memos_dirty = True
        _job = getattr(main, "_ipscaner_memos_job", None)
        if _job:
            if log is not None:
                log("需求36 touch_memos：已有待跑 job=%r → 只打脏标" % (_job,))
            return
        root = getattr(main, "root", None)
        if root is None:
            if log is not None:
                log("需求36 touch_memos：没有 root → 立即落盘")
            save_memos(main, log=log)
            return

        def _flush():
            try:
                main._ipscaner_memos_job = None
            except Exception:  # noqa: BLE001
                pass
            _d = getattr(main, "_ipscaner_memos_dirty", False)
            if log is not None:
                log("需求36 _flush 触发（dirty=%s，将%s落盘）"
                    % (_d, "执行" if _d else "跳过"))
            if _d:
                try:
                    main._ipscaner_memos_dirty = False
                except Exception:  # noqa: BLE001
                    pass
                _ok = save_memos(main, log=log)
                if log is not None:
                    log("需求36 _flush save_memos 返回 %s" % (_ok,))

        main._ipscaner_memos_job = root.after(_ms, _flush)
        if log is not None:
            log("需求36 touch_memos：已排 %r ms 落盘（job=%r，内存 %d 条）"
                % (_ms, main._ipscaner_memos_job, len(getattr(main, "memos", {}) or {})))
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("需求36 touch_memos 异常 %r" % (e,))


def ensure_memos_loaded(main, log=None):
    """每个实例只载一次磁盘备注。任何可能用到备注的入口都先调它。

    ⚠️ 为什么不能只在 MainForm.__init__ 里载：本层装在 Tk.__init__ 上，
    冻结版里那个时刻 mainform 还没进 sys.modules，等 sweep 兜底时
    MainForm 实例往往**已经建好**了 —— 只包 __init__ 会永远不触发。
    所以 __init__ / set_block / export / refresh_fx 四处都挂，谁先来谁载。
    """
    if getattr(main, "_ipscaner_memos_loaded", False):
        return False
    try:
        main._ipscaner_memos_loaded = True
        main._ipscaner_last_alive = getattr(main, "_ipscaner_last_alive", {}) or {}
        if getattr(main, "memos", None) is None:
            main.memos = {}
    except Exception:  # noqa: BLE001
        return False
    load_memos(main, log=log)
    try:
        main._ipscaner_memo_snap = dict(main.memos or {})
    except Exception:  # noqa: BLE001
        pass
    try:
        _bind_memos_save_on_close(main, log=log)
    except Exception:  # noqa: BLE001
        pass
    return True


def _bind_memos_save_on_close(main, log=None):
    """关窗兜底保存（<Destroy> 冒泡到根 + 接管 WM_DELETE_WINDOW）。"""
    root = getattr(main, "root", None)
    if root is None:
        return
    if getattr(root, "_ipscaner_memos_close_hooked", False):
        return
    root._ipscaner_memos_close_hooked = True

    def _on_destroy(ev):
        try:
            if ev.widget is not root:
                return
        except Exception:  # noqa: BLE001
            pass
        save_memos(main, log=log)

    try:
        root.bind("<Destroy>", _on_destroy, add="+")
    except Exception:  # noqa: BLE001
        pass

    try:
        prev = root.protocol("WM_DELETE_WINDOW")

        def _on_close():
            save_memos(main, log=log)
            if prev:
                try:
                    root.tk.call(prev)
                    return
                except Exception:  # noqa: BLE001
                    pass
            try:
                root.destroy()
            except Exception:  # noqa: BLE001
                pass

        root.protocol("WM_DELETE_WINDOW", _on_close)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------ E. 主窗体侧补丁
def patch_main_memos(MainForm, log=None):
    """备注持久化：包 __init__ / set_block / export / refresh_fx。"""
    if getattr(MainForm, "_ipscaner_memos_init_done", False):
        return 0
    n = 0

    if not getattr(MainForm.__init__, "_ipscaner_req36", False):
        orig_init = MainForm.__init__

        def __init__(self, *a, **k):
            orig_init(self, *a, **k)
            ensure_memos_loaded(self, log=log)

        __init__._ipscaner_req36 = True
        MainForm.__init__ = __init__
        n += 1

    if not getattr(MainForm.set_block, "_ipscaner_req36", False):
        orig_sb = MainForm.set_block

        def set_block(self, *a, **k):
            r = orig_sb(self, *a, **k)
            ensure_memos_loaded(self, log=log)
            try:
                idx = a[0] if a else k.get("n")
                st = a[1] if len(a) > 1 else k.get("st")
                # 记「通/不通」的真实值：状态 3（有备注）会把它盖掉，
                # 导出时要靠这个还原出通断
                if st in (1, 2):
                    self._ipscaner_last_alive[idx] = (st == 1)
            except Exception:  # noqa: BLE001
                pass
            try:
                cur = dict(self.memos or {})
                if cur != getattr(self, "_ipscaner_memo_snap", None):
                    self._ipscaner_memo_snap = cur
                    touch_memos(self, log=log)
            except Exception:  # noqa: BLE001
                pass
            return r

        set_block._ipscaner_req36 = True
        MainForm.set_block = set_block
        n += 1

    if not getattr(MainForm.export, "_ipscaner_req36", False):
        orig_exp = MainForm.export

        def export(self, *a, **k):
            ensure_memos_loaded(self, log=log)
            return export_main_xlsx(self, log=log)

        export._ipscaner_req36 = True
        MainForm.export = export
        n += 1

    # refresh_fx 是「主循环每秒都会调到」的那一个 —— 装在 __init__ 之后
    # 也能在一秒内把备注载进来（见 ensure_memos_loaded 头注）。
    try:
        if not getattr(MainForm.refresh_fx, "_ipscaner_req36", False):
            orig_rf = MainForm.refresh_fx

            def refresh_fx(self, *a, **k):
                ensure_memos_loaded(self, log=log)
                return orig_rf(self, *a, **k)

            refresh_fx._ipscaner_req36 = True
            MainForm.refresh_fx = refresh_fx
            n += 1
    except Exception:  # noqa: BLE001
        pass

    MainForm._ipscaner_memos_init_done = True
    if log is not None and n:
        log("需求36 备注持久化已接管 MainForm 的 %d 个入口" % n)
    return n


def export_main_xlsx(self, log=None):
    """替代 mainform.MainForm.export：默认导 .xlsx（另存可选 .csv）。

    与原版的三处差别：
      ① 原版只有 CSV（filetypes 写的是「Excel 逗号分隔」）；
      ② 原版「状态」列里 3 会被写成「有备注」，**把通断盖掉了** ——
         用了 _ipscaner_last_alive 把通断还原出来；
      ③ 加一张「统计」表（总数/通/不通/有备注）。
    """
    from tkinter import filedialog, messagebox

    try:
        p = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel 工作簿", "*.xlsx"), ("Excel 逗号分隔", "*.csv")],
            initialfile="IPScaner_%s" % (getattr(self, "ip_part", "") or "",))
    except Exception:  # noqa: BLE001
        return None
    if not p:
        return None

    ip_part = str(getattr(self, "ip_part", "") or "")
    bs = getattr(self, "block_state", {}) or {}
    hn = getattr(self, "host_names", {}) or {}
    macs = getattr(self, "macs", {}) or {}
    memos = getattr(self, "memos", {}) or {}
    alive = getattr(self, "_ipscaner_last_alive", {}) or {}
    rows, up, down, memoed = [], 0, 0, 0
    for i in range(1, 255):
        st = bs.get(i, 0)
        if st == 0:
            continue
        ip = "%s.%d" % (ip_part, i)
        memo = memos.get(ip, "")
        if st == 3:
            a = alive.get(i)
            state = "通" if a is True else ("不通" if a is False else "有备注")
        elif st == 1:
            state = "通"
        else:
            state = "不通"
        if state == "通":
            up += 1
        elif state == "不通":
            down += 1
        if memo:
            memoed += 1
        rows.append([ip, state, hn.get(i, ""), macs.get(i, ""), memo])
    if not rows:
        messagebox.showinfo("IPScaner", "还没有扫描结果可以导出。")
        return None

    cols = ["IP", "状态", "主机名", "MAC", "备注"]
    stat = [["总数", str(len(rows))], ["通", str(up)], ["不通", str(down)],
            ["有备注", str(memoed)]]
    try:
        if p.lower().endswith(".csv"):
            import core as _core
            _core.export_csv(p, rows, cols)
        else:
            write_xlsx(p, [("扫描结果", cols, rows, [18, 10, 26, 20, 34]),
                           ("统计", ["项目", "数量"], stat, [12, 12])], log=log)
    except Exception as e:  # noqa: BLE001
        messagebox.showwarning("IPScaner", "导出失败：%r" % (e,))
        return None
    if log is not None:
        log("需求36 主窗体导出 %s：%d 行（通 %d / 不通 %d / 有备注 %d）"
            % (p, len(rows), up, down, memoed))
    messagebox.showinfo("IPScaner", "导出成功\n共 %d 条：通 %d，不通 %d"
                        % (len(rows), up, down))
    return p


def make_memo_edit(dialogs, log=None):
    """重写 dialogs._memo_edit（原版三个问题，见段首注释）。"""
    if getattr(dialogs, "_ipscaner_memo_edit_done", False):
        return 0

    def _memo_edit(main, ip, cb=None):
        ensure_memos_loaded(main, log=log)
        try:
            FORMS = getattr(dialogs, "FORMS", None)
            if isinstance(FORMS, dict) and "memoedit" not in FORMS:
                # 原版用 'memomanager' —— 和「备注信息管理」抢同一个窗口键，
                # 管理窗一开着，右键「备注信息」就返回那个大窗并往里再堆一套控件。
                FORMS["memoedit"] = ("备注 ", 317, 186, False)
        except Exception:  # noqa: BLE001
            pass
        # 每次都是新窗口：旧的重开会让 e_ip/e_memo 里还是上一个 IP 的内容
        try:
            old = (getattr(dialogs, "_OPEN", {}) or {}).get("memoedit")
            if old is not None and old.winfo_exists():
                old.destroy()
        except Exception:  # noqa: BLE001
            pass
        top = dialogs.mkform(main, "memoedit", geometry="317x186+300+300")
        try:
            top.title("备注 ")
        except Exception:  # noqa: BLE001
            pass
        dialogs.lbl(top, 14, 18, "IP地址：", 63, 14)
        e_ip = dialogs.entry(top, 80, 14, 187, 21, ip or "")
        dialogs.lbl(top, 14, 46, "备注内容：", 77, 14)
        e_memo = dialogs.entry(top, 14, 62, 189, 88, "", multiline=True)
        if ip and ip in (getattr(main, "memos", {}) or {}):
            try:
                e_memo.insert("1.0", str(main.memos[ip]))
            except Exception:  # noqa: BLE001
                pass

        def save():
            v = str(e_ip.get()).strip()
            memo = str(e_memo.get("1.0", "end")).strip()
            if log is not None:
                log("需求36 备注保存：ip=%r memo=%r（长度 %d）"
                    % (v, memo, len(memo)))
            if not v:
                return None
            if getattr(main, "memos", None) is None:
                main.memos = {}
            if memo:
                main.memos[v] = memo
            else:
                main.memos.pop(v, None)
            # 只有 v 属于**当前网段**才去刷主页格子
            # （原版无条件 set_block：给 10.0.0.5 备注会去刷 192.168.5.5 的格子）
            n = 0
            ip_part = str(getattr(main, "ip_part", "") or "")
            if ip_part and v.startswith(ip_part + "."):
                last = v.rsplit(".", 1)[-1]
                if last.isdigit():
                    n = int(last)
            try:
                if n and memo:
                    main.set_block(n, 3)
                elif n:
                    a = (getattr(main, "_ipscaner_last_alive", {}) or {}).get(n)
                    if a is True:
                        main.set_block(n, 1)
                    elif a is False:
                        main.set_block(n, 2)
            except Exception:  # noqa: BLE001
                pass
            # ⚠️ 这里必须**同步立即写盘**，不能只靠 touch_memos 的 600ms 合并落盘：
            #    用户点了「保存」就该存住。合并落盘是给扫描期 set_block 刷屏用的。
            #    （2026-10-10 真机实测：走合并落盘时偶发「窗口关了但 memos.json
            #     没变」—— 疑与 after 派发有关；改成立即写即彻底消除这个不确定性。）
            try:
                main._ipscaner_memos_dirty = False
                jb = getattr(main, "_ipscaner_memos_job", None)
                if jb:
                    try:
                        main.root.after_cancel(jb)
                    except Exception:  # noqa: BLE001
                        pass
                    main._ipscaner_memos_job = None
            except Exception:  # noqa: BLE001
                pass
            save_memos(main, log=log)
            try:
                top.destroy()
            except Exception:  # noqa: BLE001
                pass
            if cb is not None:
                try:
                    cb()
                except Exception:  # noqa: BLE001
                    pass

        dialogs.btn(top, 210, 14, 70, 24, "保存", save, default=True)
        dialogs.btn(top, 210, 44, 70, 24, "关闭", top.destroy)
        return top

    dialogs._memo_edit = _memo_edit
    dialogs._ipscaner_memo_edit_done = True
    if log is not None:
        log("需求36 已接管 dialogs._memo_edit（独立窗口键 / 跨网段保护 / 落盘）")
    return 1


# ------------------------------------------------ F. 批量扫描弹窗增强
IMPORT_BTN_BOX = (170, 477, 96, 26)     # 设计像素：底部「定时扫描」条左侧的空白处
IMPORT_HINT_BOX = (280, 481, 160, 16)

# ---- 需求37：主界面「导入IP」入口 --------------------------------------------------
# 工具栏那一行最右端是空白的：BTN_EXPORT 到 x=619，LBL_STAT「---」占 623..646，
# 再往右到 CLIENT_W(835) 全空。所以按钮放 652 起、宽 78，与既有按钮同一条 y=42。
MAIN_IMPORT_BTN = (652, 42, 78, 23)     # 设计像素 (x, y, w, h)
MAIN_IMPORT_TEXT = "导入IP"             # 按钮文案，同时也是 fire() 的动作后缀
MAIN_IMPORT_MENU_TEXT = "导入IP表格(&I)"  # 右键菜单里的那一项
MAIN_IMPORT_ACT = "cimport"             # 右键菜单动作名

# 批量扫描窗的当前实例（由 patch_ipsegment 记录）。
# 用途：主界面「导入IP」要先把目标灌进那个窗，已经开着就得复用，
# 不能每次调用 f_ipsegment 都新开一个 —— 用户会看到两个一样的窗口。
_IPSEC_TOP = []

IPS_EMPTY_HINT = (
    "这个文件里没找到 IP 地址。\n\n"
    "支持在任意单元格/行里直接写：\n"
    "  · 单个 IP      192.168.1.10\n"
    "  · 整个网段     192.168.1.0/24   或   192.168.1\n"
    "  · 连续范围     192.168.1.1-192.168.1.50\n"
    "可以混着写，也可以跨网段（会去重 + 按 IP 排序）。")


def _find_child(top, cls=None, text=None):
    for c in top.winfo_children():
        try:
            if cls is not None and c.winfo_class() != cls:
                continue
            if text is not None and str(c.cget("text")) != text:
                continue
            return c
        except Exception:  # noqa: BLE001
            continue
    return None


def _read_ips_into(seg, path, log=None, title="导入 IP 表格"):
    """读表格 → 抽取 IP → 写进批量窗的输入框。返回 (条数, 说明)。

    抽出来是因为有**两个入口**要走同一条路：批量窗底栏的「导入表格」，
    和主界面工具栏的「导入IP」（需求37）。两者差别只在事后说什么话/要不要自动开扫。
    """
    from tkinter import messagebox

    try:
        ips, note = read_ip_file(path, log=log)
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("导入表格：read_ip_file 抛异常 %r" % (e,))
        messagebox.showwarning(title, "读取失败：\n%r" % (e,))
        return 0, ""
    if not ips:
        messagebox.showwarning(title, IPS_EMPTY_HINT)
        return 0, note
    try:
        seg.delete("1.0", "end")
        seg.insert("1.0", "\n".join(ips) + "\n")
    except Exception as e:  # noqa: BLE001
        messagebox.showwarning(title, "写入输入框失败：%r" % (e,))
        return 0, note
    if log is not None:
        log("导入表格 %s → %d 个目标（%s）" % (path, len(ips), note))
    return len(ips), note


def _import_table(top, seg, dialogs, log=None):
    from tkinter import filedialog, messagebox

    title = "导入 IP 表格"
    if log is not None:
        log("需求36 导入表格：回调进入，准备弹 askopenfilename")
    try:
        p = filedialog.askopenfilename(
            title=title,
            filetypes=[("Excel / CSV / 文本", "*.xlsx *.xlsm *.csv *.txt"),
                       ("Excel 工作簿", "*.xlsx"), ("CSV 逗号分隔", "*.csv"),
                       ("文本文件", "*.txt"), ("全部文件", "*.*")])
        if log is not None:
            log("需求36 导入表格：askopenfilename 返回 %r" % (p,))
    except Exception as e:  # noqa: BLE001
        # ⚠️ 原来这里是**裸 return**：冻结版没有控制台，Tcl 的 tk_getOpenFile
        #    一旦不可用（Tcl 脚本被裁 / 没有 master 窗口）就静默失败，
        #    外部看到的就是「点了没反应」。改成必须留痕。
        if log is not None:
            log("需求36 导入表格：askopenfilename 抛异常 %r" % (e,))
        return
    if not p:
        if log is not None:
            log("需求36 导入表格：用户取消（返回空路径）")
        return
    n, _note = _read_ips_into(seg, p, log=log, title=title)
    if n:
        messagebox.showinfo(title, "已导入 %d 个 IP 目标（已去重排序）。\n\n"
                                   "点【开始扫描】就开始 ping 测试。" % n)


def _get_ipsec_window(main, dialogs, log=None):
    """拿到批量扫描窗：已开着就复用，否则新建。"""
    top = _IPSEC_TOP[0] if _IPSEC_TOP else None
    if top is not None:
        try:
            if top.winfo_exists():
                return top
        except Exception:  # noqa: BLE001
            pass
    try:
        return dialogs.f_ipsegment(main)
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("需求37 打开批量扫描窗失败 %r" % (e,))
        return None


def main_import_ips(main, log=None):
    """需求37：主界面「导入IP」—— 选表格 → 批量窗灌入 → 自动开始 ping。

    为什么要有它：用户的原话是「没有导入IP方便我ping测不同网段的ip」。
    「导入表格」本来已经做了，但它藏在 快捷工具 → IP批量扫描 的底栏里，
    主界面看不到入口。这个入口把整条链路缩成**主界面点一下**：
    选文件 → 批量窗自己开出来 → IP 列表填好 → 直接开扫。
    """
    from tkinter import filedialog, messagebox

    import dialogs

    title = "导入 IP 表格"
    if log is not None:
        log("需求37 主界面「导入IP」被点到了，准备弹 askopenfilename")
    try:
        p = filedialog.askopenfilename(
            title=title,
            filetypes=[("Excel / CSV / 文本", "*.xlsx *.xlsm *.csv *.txt"),
                       ("Excel 工作簿", "*.xlsx"), ("CSV 逗号分隔", "*.csv"),
                       ("文本文件", "*.txt"), ("全部文件", "*.*")])
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("需求37 askopenfilename 抛异常 %r" % (e,))
        return 0
    if not p:
        if log is not None:
            log("需求37 用户取消（返回空路径）")
        return 0
    if log is not None:
        log("需求37 选中文件 %r" % (p,))

    top = _get_ipsec_window(main, dialogs, log=log)
    if top is None:
        messagebox.showwarning(title, "打不开批量扫描窗口，导入已取消。")
        return 0
    seg = _find_child(top, cls="Text")
    if seg is None:
        messagebox.showwarning(title, "没找到批量扫描窗的 IP 输入框。")
        return 0

    n, _note = _read_ips_into(seg, p, log=log, title=title)
    if not n:
        return 0

    # 把窗口推到用户眼前（批量窗是主窗的 transient，主窗若被别的窗口压着就看不见）
    try:
        top.deiconify()
        top.lift()
    except Exception:  # noqa: BLE001
        pass
    try:
        main.set_status("tip", "已导入 %d 个 IP，正在开始 ping 测试…" % n)
    except Exception:  # noqa: BLE001
        pass

    started = False
    try:
        b = _find_child(top, cls="Button", text="开始扫描")
        if b is not None and str(b.cget("state")) != "disabled":
            b.invoke()                      # 真点那个按钮，走产品自己的扫描逻辑
            started = True
            if log is not None:
                log("需求37 已自动触发「开始扫描」（%d 个目标）" % n)
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("需求37 自动开始扫描失败 %r" % (e,))
    if not started:
        # 自动开扫没成（按钮被禁用等）→ 至少把「接下来点哪儿」说清楚
        if log is not None:
            log("需求37 自动开扫未触发，退回提示用户手点")
        messagebox.showinfo(title, "已导入 %d 个 IP 目标（已去重排序）。\n\n"
                                   "点批量窗里的【开始扫描】就开始 ping 测试。" % n)
    return n



def export_table_xlsx(tv, log=None):
    """把批量扫描结果表导成 Excel / CSV（从表格控件读，而不是闭包里的 result_rows）。"""
    from tkinter import filedialog, messagebox

    try:
        cols = [str(c) for c in tv.cget("columns")]
    except Exception:  # noqa: BLE001
        cols = ["IP地址", "状态", "主机名", "MAC", "备注"]
    rows, up, down, memoed = [], 0, 0, 0
    for it in tv.get_children():
        try:
            vals = [str(v) for v in tv.item(it, "values")]
        except Exception:  # noqa: BLE001
            continue
        if not any(v.strip() for v in vals):
            continue
        rows.append(vals)
        st = vals[1].strip() if len(vals) > 1 else ""
        if st in ("正常", "通"):
            up += 1
        elif st in ("不通", "超时", "超时/不通"):
            down += 1
        if len(vals) > 4 and vals[4].strip():
            memoed += 1
    if not rows:
        messagebox.showinfo("IP批量扫描", "暂无结果可导出")
        return None
    try:
        p = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel 工作簿", "*.xlsx"), ("Excel 逗号分隔", "*.csv")],
            initialfile="IPScaner_batch_%d" % len(rows))
    except Exception:  # noqa: BLE001
        return None
    if not p:
        return None
    stat = [["总数", str(len(rows))], ["通", str(up)], ["不通", str(down)],
            ["有备注", str(memoed)]]
    try:
        if p.lower().endswith(".csv"):
            import core as _core
            _core.export_csv(p, rows, cols)
        else:
            write_xlsx(p, [("扫描结果", cols, rows,
                            [18, 8, 26, 20, 34][:max(1, len(cols))]),
                           ("统计", ["项目", "数量"], stat, [12, 12])], log=log)
    except Exception as e:  # noqa: BLE001
        messagebox.showwarning("IP批量扫描", "导出失败：%r" % (e,))
        return None
    if log is not None:
        log("需求36 批量导出 %s：%d 行（通 %d / 不通 %d / 有备注 %d）"
            % (p, len(rows), up, down, memoed))
    messagebox.showinfo("IP批量扫描",
                        "导出成功\n共 %d 条：通 %d，不通 %d，有备注 %d"
                        % (len(rows), up, down, memoed))
    return p


def decorate_ipsegment(main, top, dialogs, log=None):
    """给批量扫描弹窗挂：右键备注、备注回填、「导入表格」按钮、xlsx 导出。"""
    if getattr(top, "_ipscaner_req36_done", False):
        return 0
    import tkinter as _tk

    tv = _find_child(top, cls="Treeview")
    if tv is None:
        return 0
    seg = _find_child(top, cls="Text")
    top._ipscaner_req36_done = True

    try:
        S = float(getattr(top, "_ipscaner_S", 1.0) or 1.0)
    except Exception:  # noqa: BLE001
        S = 1.0
    if getattr(top, _M_SIZED, False):
        S = float(getattr(top, _M_SCALE, S) or S)

    # ---- ① 「导入表格」按钮 + 一行提示（底部条有 450px 空白，不挤左列）----
    try:
        if seg is not None and _find_child(top, cls="Button",
                                          text="导入表格") is None:
            box = IMPORT_BTN_BOX
            hb = IMPORT_HINT_BOX
            if S != 1.0:
                box = tuple(int(round(v * S)) for v in box)
                hb = tuple(int(round(v * S)) for v in hb)
            font = (DIALOG_FAMILY, _scale_px(DESIGN_PX, S))
            b = _tk.Button(top, text="导入表格", font=font, bg=APPLE_CARD,
                           fg=APPLE_TEXT, relief="flat", bd=0, cursor="hand2",
                           highlightthickness=1, highlightbackground=APPLE_BORDER,
                           activebackground=APPLE_SELECT,
                           activeforeground=APPLE_TEXT,
                           command=lambda: _import_table(top, seg, dialogs, log))
            # ---- 事件送达取证 ----
            # 实例级 <Button-1> 绑定先于 class binding（command）执行。
            # 有这条日志 = 鼠标点击真的落在按钮上；没有 = 事件被别的东西吃掉了
            # （窗口没激活 / 被覆盖 / 命中测试错位），跟"按钮业务逻辑"无关。
            # 自动化点击排查时这是第一手证据，别再用坐标反推去猜。
            try:
                def _on_press(_e, _log=log):
                    if _log is not None:
                        try:
                            _log("需求36「导入表格」收到 <Button-1> 局部(%d,%d)"
                                 % (_e.x, _e.y))
                        except Exception:  # noqa: BLE001
                            pass
                b.bind("<Button-1>", _on_press)
            except Exception:  # noqa: BLE001
                pass
            b.place(x=box[0], y=box[1], width=box[2], height=box[3])
            h = _tk.Label(top, text="（结果行上点右键可编辑备注）", font=font,
                          bg=APPLE_BG, fg=APPLE_TEXT2, anchor="w")
            h.place(x=hb[0], y=hb[1], width=hb[2], height=hb[3])
            if log is not None:
                # ⚠️ 这里打的是**刚 place 下去**的框。本层早于 scale_dialog 运行，
                #    所以 S 还没定（实测 S=1.0），框 == 设计框；最终位置由
                #    scale_dialog ②（所有子控件 ×S）决定。为了不误导排查，
                #    再排一个 900ms 后回读**真实终态**的日志。
                log("需求36 批量扫描：已加「导入表格」按钮 place=%s（设计 %s，此刻 S=%.2f）"
                    % (box, IMPORT_BTN_BOX, S))
                try:
                    def _log_final(_b=b, _S=S):
                        try:
                            log("需求36 导入表格按钮终态 x=%d y=%d w=%d h=%d"
                                "（设计 %s × S=%.2f → 期望 %s）"
                                % (_b.winfo_x(), _b.winfo_y(), _b.winfo_width(),
                                   _b.winfo_height(), IMPORT_BTN_BOX, _S,
                                   tuple(int(round(v * _S)) for v in IMPORT_BTN_BOX)))
                        except Exception:  # noqa: BLE001
                            pass
                    top.after(900, _log_final)
                except Exception:  # noqa: BLE001
                    pass
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("需求36 导入表格按钮创建失败 %r" % (e,))

    # ---- ①b 回读窗内**所有**按钮的屏幕坐标（自动化点击的权威取证）----
    # ⚠️ 为什么必须打屏幕坐标：真机验收脚本用 SendInput 点击，必须拿到
    #    SetCursorPos 级别的绝对坐标。winfo_rootx/rooty 就是屏幕像素，
    #    能直接和 click() 的参数对齐；而 winfo_x/y 是相对父容器的，
    #    控件一旦嵌在 Frame 里就会算错（2026-10-10 查「点导出结果没反应」
    #    时正是卡在这个坐标系上，最后靠这条日志才定位到真身）。
    try:
        def _walk_all(_w, _acc=None):
            if _acc is None:
                _acc = []
            try:
                for _c in _w.winfo_children():
                    _acc.append(_c)
                    _walk_all(_c, _acc)
            except Exception:  # noqa: BLE001
                pass
            return _acc

        def _dump_buttons():
            try:
                rows = []
                occl = []
                for _w in _walk_all(top):
                    try:
                        if _w.winfo_class() != "Button":
                            continue
                    except Exception:  # noqa: BLE001
                        continue
                    try:
                        _t = _w.cget("text")
                    except Exception:  # noqa: BLE001
                        _t = "?"
                    try:
                        _st = "?"
                        try:
                            _st = str(_w.cget("state"))
                        except Exception:  # noqa: BLE001
                            pass
                        _cm = "?"
                        try:
                            _cm = "有" if str(_w.cget("command")) else "空★"
                        except Exception:  # noqa: BLE001
                            pass
                        rows.append("%r 屏幕(%d,%d) %dx%d state=%s cmd=%s"
                                    % (str(_t), _w.winfo_rootx(), _w.winfo_rooty(),
                                       _w.winfo_width(), _w.winfo_height(), _st, _cm))
                    except Exception:  # noqa: BLE001
                        continue
                    # ---- 遮挡体检：按钮正中心那个屏幕点，最顶层控件还是它自己吗？----
                    # 一个同色（或透明）的 Frame / Canvas 盖在按钮上时，按钮**看起来正常**，
                    # 但点击永远送不到它 —— 这是"点了没反应"最阴的一种。
                    try:
                        _cx = _w.winfo_rootx() + _w.winfo_width() // 2
                        _cy = _w.winfo_rooty() + _w.winfo_height() // 2
                        _under = top.winfo_containing(_cx, _cy)
                        if _under is not _w:
                            _un = "None" if _under is None else str(_under)
                            _uc = ("?" if _under is None
                                   else str(getattr(_under, "winfo_class", lambda: "?")()))
                            occl.append("%r 中心(%d,%d) 下面是 %s(%s)"
                                        % (str(_t), _cx, _cy, _un, _uc))
                    except Exception:  # noqa: BLE001
                        pass
                if log is not None:
                    log("需求36 批量窗按钮终态（共 %d 个）：%s"
                        % (len(rows), " ｜ ".join(rows)))
                    if occl:
                        log("需求36 ★按钮遮挡体检：%d 个按钮中心被别的控件盖住 → %s"
                            % (len(occl), " ｜ ".join(occl)))
                    else:
                        log("需求36 按钮遮挡体检：所有按钮中心点都是自己（无遮挡）")
            except Exception:  # noqa: BLE001
                pass
        top.after(1200, _dump_buttons)
    except Exception:  # noqa: BLE001
        pass

    # ---- ② 结果表右键 → 编辑/清空备注 ----
    try:
        menu = _tk.Menu(top, tearoff=0)
        top._ipscaner_rowmenu = menu
    except Exception:  # noqa: BLE001
        menu = None

    def _row(ev):
        try:
            item = tv.identify_row(ev.y)
        except Exception:  # noqa: BLE001
            return None, None
        if not item:
            return None, None
        try:
            vals = tv.item(item, "values")
        except Exception:  # noqa: BLE001
            return None, None
        if not vals:
            return None, None
        ip = str(vals[0] or "").strip()
        return (ip, item) if ip else (None, None)

    def _sync(item, ip):
        try:
            tv.set(item, "备注", (getattr(main, "memos", {}) or {}).get(ip, ""))
        except Exception:  # noqa: BLE001
            pass

    def _popup(ev):
        ip, item = _row(ev)
        if not ip:
            return
        try:
            tv.selection_set(item)
        except Exception:  # noqa: BLE001
            pass
        if menu is None:
            return
        try:
            menu.delete(0, "end")
            menu.add_command(label="编辑备注(&M)…",
                             command=lambda: _do_edit(ip, item))
            if (getattr(main, "memos", {}) or {}).get(ip):
                menu.add_command(label="清空备注", command=lambda: _do_clear(ip, item))
            menu.tk_popup(ev.x_root, ev.y_root)
        except Exception:  # noqa: BLE001
            pass
        finally:
            try:
                menu.grab_release()
            except Exception:  # noqa: BLE001
                pass

    def _do_edit(ip, item):
        dialogs._memo_edit(main, ip, lambda: _sync(item, ip))

    def _do_clear(ip, item):
        try:
            (main.memos or {}).pop(ip, None)
        except Exception:  # noqa: BLE001
            pass
        # 清备注是**显式动作**，同步落盘（和「保存」一个道理，不走 600ms 合并）
        save_memos(main, log=log)
        _sync(item, ip)

    try:
        tv.bind("<Button-3>", _popup, add="+")
        if log is not None:
            log("需求36 批量扫描：结果表已绑右键备注")
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("需求36 结果表右键绑定失败 %r" % (e,))

    # ---- ③ 已有备注自动回填（扫描期间新行不断插入，靠轻量轮询兜）----
    def _backfill():
        try:
            if not top.winfo_exists():
                return
        except Exception:  # noqa: BLE001
            return
        try:
            memos = getattr(main, "memos", {}) or {}
            if memos:
                for it in tv.get_children():
                    vals = tv.item(it, "values")
                    if not vals or len(vals) < 5:
                        continue
                    if str(vals[4] or "").strip():
                        continue
                    ip = str(vals[0] or "").strip()
                    m = memos.get(ip, "")
                    if m:
                        tv.set(it, "备注", m)
        except Exception:  # noqa: BLE001
            pass
        try:
            top.after(700, _backfill)
        except Exception:  # noqa: BLE001
            pass

    try:
        ensure_memos_loaded(main, log=log)
        top.after(700, _backfill)
    except Exception:  # noqa: BLE001
        pass

    # ---- ④ 「导出结果」改成 .xlsx（读表格，不读闭包里的 result_rows）----
    try:
        exp = _find_child(top, cls="Button", text="导出结果")
        if exp is not None:
            def _do_export(_tv=tv, _t=top, _log=log):
                # ⚠️ 入口日志：用来区分「点击事件压根没到按钮」和「到了但导出内部出错」。
                #    自动化点击是最容易骗人的环节——坐标对了不代表事件送达
                #    （可能被透明控件盖住、按钮 disabled、或事件被 shim 吃掉）。
                if _log is not None:
                    _log("需求36 导出按钮被点到了 → export_table_xlsx（表格 %d 行）"
                         % (len(_tv.get_children()) if _tv is not None else -1))
                return export_table_xlsx(_tv, log=_log)

            exp.configure(command=_do_export)
            exp._ipscaner_export = "xlsx"      # 验收脚本用它确认接管成功
            try:
                exp.configure(bg=_apple_accent(), fg="#FFFFFF",
                              activebackground=_apple_accent(),
                              activeforeground="#FFFFFF")
            except Exception:  # noqa: BLE001
                pass
            if log is not None:
                log("需求36 批量扫描：「导出结果」已改为 Excel(.xlsx)")
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("需求36 导出按钮接管失败 %r" % (e,))
    return 1


def patch_main_import(mainform, log=None):
    """需求37：主界面「导入IP」入口 —— 工具栏按钮 + IP色块右键菜单项。

    三个补丁点（都不动产品字节码，只包一层）：
      ① `MainForm._draw_toolbar_base`：画完原按钮再补画我们的按钮。
         build_base() 每次都先 `cv.delete("base")` + `regions=[]`，所以这里
         **天然幂等**，重复调用不会叠出多个按钮。
      ② `MainForm.fire(act)`：工具栏点击走 `fire("btn:<文案>")`，
         菜单点击走 `fire(<动作名>)` —— 两条路都汇到这一个方法，包它一处就够。
      ③ `popup.MenuPopup.__init__`：右键菜单的构建点在产品的
         `open_context_popup()` 里，`labels` 是**局部变量**，没法从外面改。
         但所有菜单弹出层都要过 MenuPopup 的构造 —— 在这里按「有没有 cmemo 动作」
         认出来是不是 IP 色块右键菜单，是就往末尾补一项。
         ⚠️ `cmemo` 在 menu_def.CONTEXT_MENU 里也是同一条右键菜单，
            而托盘菜单(TRAY_MENU)/5 个顶级菜单都不含它 → 判据唯一。

    幂等：MainForm 上打标记，重复安装直接返回。
    """
    MF = getattr(mainform, "MainForm", None)
    if MF is None or getattr(MF, "_ipscaner_req37_done", False):
        return 0
    MF._ipscaner_req37_done = True
    done = 0

    # ---- ① 工具栏按钮 ----
    _orig_tb = MF._draw_toolbar_base

    def _draw_toolbar_base(self):
        _orig_tb(self)
        try:
            import theme as _T
            ic = ("mnuIPSegment"
                  if self.icons.get("mnuIPSegment") is not None else None)
            self._draw_button(MAIN_IMPORT_BTN, MAIN_IMPORT_TEXT, _T.C_BTN_FACE,
                              icon=ic, font=self.tk_f_default)
        except Exception as e:  # noqa: BLE001
            if log is not None:
                log("需求37 主界面导入按钮绘制失败 %r" % (e,))

    _draw_toolbar_base._ipscaner_req37 = True
    MF._draw_toolbar_base = _draw_toolbar_base
    done += 1

    # ---- ② 动作分发 ----
    _orig_fire = MF.fire

    def fire(self, act):
        if act == ("btn:" + MAIN_IMPORT_TEXT) or act == MAIN_IMPORT_ACT:
            return main_import_ips(self, log=log)
        return _orig_fire(self, act)

    fire._ipscaner_req37 = True
    MF.fire = fire
    done += 1

    # ---- ③ 右键菜单项 ----
    try:
        import menu_def as _md
        import popup as _pp

        _orig_mp_init = _pp.MenuPopup.__init__

        def _mp_init(self, host, items, *a, **k):
            try:
                lvl = k.get("level", a[1] if len(a) > 1 else 0)
                if not lvl and any(
                        isinstance(it, tuple) and len(it) >= 3
                        and it[2] == "cmemo" for it in items):
                    items = list(items) + [
                        _md.SEP,
                        (MAIN_IMPORT_MENU_TEXT, None, MAIN_IMPORT_ACT, None)]
            except Exception:  # noqa: BLE001
                pass
            return _orig_mp_init(self, host, items, *a, **k)

        _mp_init._ipscaner_req37 = True
        _pp.MenuPopup.__init__ = _mp_init
        done += 1
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("需求37 右键菜单项安装失败 %r" % (e,))

    if log is not None:
        log("需求37 已加主界面「%s」按钮 %s + 右键菜单项「%s」（%d 处）"
            % (MAIN_IMPORT_TEXT, MAIN_IMPORT_BTN, MAIN_IMPORT_MENU_TEXT, done))
    return done


def patch_ipsegment(dialogs, log=None):
    """包 dialogs.f_ipsegment：建完窗口再挂增强（不改它的扫描逻辑）。"""
    if getattr(dialogs, "_ipscaner_ipsec_done", False):
        return 0
    orig = dialogs.f_ipsegment

    def f_ipsegment(main, *a, **k):
        top = orig(main, *a, **k)
        try:
            if top is not None:
                # 记下当前实例：主界面「导入IP」要复用它，不能再开一个窗
                _IPSEC_TOP[:] = [top]
        except Exception:  # noqa: BLE001
            pass
        try:
            decorate_ipsegment(main, top, dialogs, log=log)
        except Exception as e:  # noqa: BLE001
            if log is not None:
                log("需求36 批量扫描增强失败 %r" % (e,))
        return top

    f_ipsegment._ipscaner_req36 = True
    dialogs.f_ipsegment = f_ipsegment
    dialogs._ipscaner_ipsec_done = True
    if log is not None:
        log("需求36 已接管 dialogs.f_ipsegment（右键备注 / 导入表格 / Excel 导出）")
    return 1


def install_exc_logger(log=None):
    """把 Tk 回调里未捕获的异常写进修复层日志。

    ⚠️ 为什么必须有：冻结版（--windowed）没有控制台，`sys.stderr` 是 None，
    Tk 默认的 `report_callback_exception` 连打印都做不到 —— 于是**按钮回调里的
    任何异常都被彻底吞掉**，表现就是「点了没反应」，完全无法定位。
    （2026-10-10 查「点保存不落盘」时正是被这个坑住：既没有报错也没有日志。）
    """
    import tkinter as _tk
    if getattr(_tk.Tk, "_ipscaner_exc_logged", False):
        return 0

    def _rce(self, exc, val, tb):
        try:
            if log is not None:
                import traceback as _tb
                log("★Tk 回调异常 %s: %s\n%s"
                    % (getattr(exc, "__name__", exc), val,
                       "".join(_tb.format_exception(exc, val, tb))[-3000:]))
        except Exception:  # noqa: BLE001
            pass
        try:
            _tk.Tk.report_callback_exception(self, exc, val, tb)
        except Exception:  # noqa: BLE001
            pass

    _tk.Tk.report_callback_exception = _rce
    _tk.Tk._ipscaner_exc_logged = True
    if log is not None:
        log("修复层已接管 Tk 回调异常日志（★Tk 回调异常）")
    return 1


def patch_req36(root=None, log=None):
    """需求36 安装入口（幂等；供 apply_deferred_patches 反复调用）。"""
    if not _req36_on():
        if log is not None and not getattr(patch_req36, "_off_logged", False):
            patch_req36._off_logged = True
            log("需求36 被 %s 关闭（对照实验模式）" % REQ36_OFF)
        return 0
    done = 0
    try:
        done += install_exc_logger(log=log)
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("需求36 异常日志安装失败 %r" % (e,))
    try:
        import dialogs as _d
        done += patch_ipsegment(_d, log=log)
        done += make_memo_edit(_d, log=log)
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("需求36 dialogs 侧安装失败 %r" % (e,))
    try:
        import mainform as _mf
        done += patch_main_memos(_mf.MainForm, log=log)
        done += patch_main_import(_mf, log=log)
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("需求36 mainform 侧安装失败 %r" % (e,))
    return done


# ------------------------------------------------------------------ 5. 一体化安装
# ------------------------------------------------------------------ 4.95 线程安全垫片
# 2026-10-07 用户实测：IP 批量扫描「扫描完成会直接退出（闪退）」「经常闪退」。
# 反汇编定位（dialogs.py:518-529，见 notes/全面验收报告_20261004.md 第十节）：
#   ipsegment 的工作线程里：
#     · on_result() 每收一条结果 → top.after(0, tv.insert...)   # 254 次
#     · work() 结束           → top.after(0, messagebox.showinfo...)
#   portscan  _run.work / _emit 同款模式。
#   processport reload_.fill 在工作线程里**直接**调 tv.get_children/item。
#
# Tk 不是线程安全的：所有 Tcl 调用必须发生在创建解释器的线程（主线程）。
# 工作线程直接调 after()/Treeview 方法 → Tcl 分配器竞态 → **间歇性堆损坏
# → 进程直接消失**（无 Python 异常、无报错窗口，表现就是"闪退"）。
# 崩溃正好发生在结果回填/完成弹窗阶段 → 用户永远看不到扫描结果。
#
# 修法（不动字节码）：
#   ① Misc.after/after_idle/after_cancel 全局垫片 —— 非主线程调用改走
#      deque，由主线程 40ms 轮询统一派发；
#   ② ttk.Treeview 的读写方法同步编组（rendezvous）—— 非主线程调用
#      经队列交给主线程执行并回传结果（processport 的 fill 需要返回值）。
# 幂等：_tk.Misc 上打标记，重复 install 不会包两层。


def install_thread_shim(root, log=None):
    import threading
    import collections
    import tkinter as _tk
    try:
        from tkinter import ttk as _ttk
    except Exception:  # noqa: BLE001
        _ttk = None

    if getattr(_tk.Misc, "_ipscaner_thread_shim", False):
        return False

    main_tid = threading.get_ident()
    q = collections.deque()
    lock = threading.Lock()
    seq = [0]
    cancelled = set()

    real_after = _tk.Misc.after
    real_after_idle = _tk.Misc.after_idle
    real_after_cancel = _tk.Misc.after_cancel

    def _exec(sid, func, args):
        if sid in cancelled:
            cancelled.discard(sid)
            return
        try:
            func(*args)
        except Exception:  # noqa: BLE001
            # 回调里最常见的失败是窗体已被销毁（TclError）—— 正常生命周期，
            # 静默跳过，绝不能让一个回调炸掉整条派发链。
            pass

    def _drain():
        try:
            while True:
                with lock:
                    if not q:
                        break
                    item = q.popleft()
                sid, ms, func, args = item
                if ms and ms > 0:
                    def _later(f=func, a=args, s=sid):
                        _exec(s, f, a)
                    try:
                        real_after(root, ms, _later)
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    _exec(sid, func, args)
        finally:
            try:
                real_after(root, 40, _drain)
            except Exception:  # noqa: BLE001
                pass

    def shim_after(self, ms, func=None, *args):
        if func is None or threading.get_ident() == main_tid:
            # 主线程 / after(ms) 睡眠形式：原样放行
            if func is None:
                return real_after(self, ms)
            return real_after(self, ms, func, *args)
        with lock:
            seq[0] += 1
            sid = "shim_after#%d" % seq[0]
            try:
                ms_i = int(ms)
            except Exception:  # noqa: BLE001
                ms_i = 0
            q.append((sid, ms_i, func, args))
        return sid

    def shim_after_idle(self, func, *args):
        if threading.get_ident() == main_tid:
            return real_after_idle(self, func, *args)
        return shim_after(self, 0, func, *args)

    def shim_after_cancel(self, id):
        if isinstance(id, str) and id.startswith("shim_after#"):
            with lock:
                cancelled.add(id)
            return
        return real_after_cancel(self, id)

    _tk.Misc.after = shim_after
    _tk.Misc.after_idle = shim_after_idle
    _tk.Misc.after_cancel = shim_after_cancel

    # ---- Treeview 同步编组（processport 的 fill 在工作线程读写表格）----
    # 阻塞式 rendezvous：工作线程把 (方法, 参数) 入队后等 Event，
    # 主线程 _drain 执行并回填结果。主线程调用原样放行。
    if _ttk is not None:
        _tv_methods = ("get_children", "item", "insert", "delete",
                       "configure", "set", "focus", "selection",
                       "see", "yview", "xview", "identify_row")
        # 窗体销毁后工作线程迟到调用的安全默认值（按方法给出，避免
        # get_children 返回 None 让调用方 for 循环炸出第二类异常）
        _tv_safe = {"get_children": (), "selection": (), "item": {},
                    "focus": "", "identify_row": "",
                    "yview": (0.0, 1.0), "xview": (0.0, 1.0)}
        for _mname in _tv_methods:
            _orig = getattr(_ttk.Treeview, _mname, None)
            if _orig is None or getattr(_orig, "_ipscaner_marshal", False):
                continue

            def _mk(orig, mname):
                def _marshaled(self, *args, **kwargs):
                    if threading.get_ident() == main_tid:
                        return orig(self, *args, **kwargs)
                    ev = threading.Event()
                    box = {}

                    def _job():
                        try:
                            box["v"] = orig(self, *args, **kwargs)
                        except Exception as e:  # noqa: BLE001
                            box["e"] = e
                        finally:
                            ev.set()
                    with lock:
                        seq[0] += 1
                        q.append(("shim_after#%d" % seq[0], 0, _job, ()))
                    ev.wait(10)          # 主线程最长 10s 不应答则降级直调
                    if "e" in box:
                        e = box["e"]
                        # 「窗体已关闭，工作线程还在灌数据」是必然竞态（实测
                        # processport 的 fill 线程在窗体销毁后仍调 item，
                        # TclError 整片打到 stderr）。控件名失效属良性，
                        # 吞掉并返回安全默认值；其余异常照常抛出。
                        if "invalid command name" in str(e):
                            return _tv_safe.get(mname)
                        raise e
                    if "v" not in box:   # 超时：直调兜底（赌一把，总比卡死好）
                        return orig(self, *args, **kwargs)
                    return box["v"]
                _marshaled._ipscaner_marshal = True
                return _marshaled
            setattr(_ttk.Treeview, _mname, _mk(_orig, _mname))

    _tk.Misc._ipscaner_thread_shim = True
    try:
        real_after(root, 40, _drain)
    except Exception:  # noqa: BLE001
        pass
    if log is not None:
        log("线程安全垫片已安装（after 派发 + Treeview 编组）")
    return True


def install(root, log=None, sweep_ms=500, get_scale=None):
    """给主窗体装上「建一个子窗体就按 SCALE 修一个」的常驻扫描。

    为什么要常驻：wifi / 备注管理 等窗体会在工作线程里**后续再填控件**
    （实测 dialogs.fill 在线程里写数据），一次性修复会漏掉后到的控件。

    为什么用 Toplevel 注册表而不是 dialogs._OPEN：
      · `show_list`（IP段扫描结果）和 `f_diy`（DIY 组）**不经过 mkform**，
        不进 _OPEN，只认 _OPEN 会把它们漏掉；
      · 菜单弹层 MenuPopup 也是 Toplevel，但它已按 S 渲染，二次缩放会把菜单
        放大一倍 —— 用 `overrideredirect()` 把它们排除（弹层是无边框窗口，
        子窗体都有标题栏）。
    """
    import tkinter as _tk

    # 版本号覆盖要在**最前面** —— 必须在 root.title() 首次执行之前改掉
    # theme.TITLE_VER，否则标题栏会一直显示绿色版的 "Ver: 1.25.0"。
    # 放在幂等守卫之前：即使重复执行也只改一次（值已相同就是 no-op）。
    try:
        set_version(log=log)
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("版本号覆盖失败 %r" % (e,))

    # 线程安全垫片：修 IP 批量扫描/端口扫描/系统端口查看的「扫描完成闪退」。
    # 必须在任何子窗体创建之前装好（工作线程一启动就会调 after）。
    # 可用 IPSCANER_NO_THREAD_SHIM=1 关闭（用于崩溃复现的对照实验）。
    import os as _os
    if _os.environ.get("IPSCANER_NO_THREAD_SHIM") != "1":
        try:
            install_thread_shim(root, log=log)
        except Exception as e:  # noqa: BLE001
            if log is not None:
                log("线程垫片安装失败 %r" % (e,))
    elif log is not None:
        log("线程垫片被 IPSCANER_NO_THREAD_SHIM 关闭（对照实验模式）")

    # Apple 风现代主题（用户 2026-10-07 点名 UI 太丑）：
    # 全局 ttk 样式表 + 主窗体轻修饰；子窗体美化在 scale_dialog ⑥ 步逐窗做。
    if _os.environ.get("IPSCANER_NO_THEME") != "1":
        try:
            install_apple_theme(root, log=log)
            beautify_main(root, log=log)
        except Exception as e:  # noqa: BLE001
            if log is not None:
                log("主题安装失败 %r" % (e,))

    # 幂等：同一个 root 只装一次常驻扫描。
    # 踩过：运行期钩子模块被重复执行（PyInstaller 不把 runtime_hooks 登记进
    # sys.modules，之后 `import` 它就会**再执行一遍**）时，会装出两条扫描链、
    # remap_main 跑两遍。这里用 root 上的标记挡住。
    # ⚠️ 这段延迟补丁必须放在 _reg 早退**之前** —— 见 apply_deferred_patches 的
    #    时机说明（gui.init_state 在本函数之后、sweep 首次之前）。
    try:
        apply_deferred_patches(root, log=log)
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log("延迟补丁安装失败 %r" % (e,))

    _reg = getattr(root, "_ipscaner_reg", None)
    if _reg is not None:
        return _reg

    reg = []

    try:
        import dialogs
        key_of_title = {}
        for k, spec in (getattr(dialogs, "FORMS", {}) or {}).items():
            try:
                key_of_title[str(spec[0])] = k
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        key_of_title = {}

    state = {"S": None}

    def _cur_scale():
        if get_scale is not None:
            try:
                return float(get_scale())
            except Exception:  # noqa: BLE001
                pass
        return state["S"] or 1.0

    # 首帧机制（缺陷13）的上下文。keys 用 title → FORMS key，才能取到设计尺寸。
    ctx = {"S": _cur_scale, "keys": key_of_title, "log": log}
    import os as _os2
    _defer_on = _os2.environ.get(_DEFER_ENV) != "1"
    if not _defer_on and log is not None:
        log("子窗体首帧修复被 %s 关闭（对照实验模式）" % _DEFER_ENV)

    # 幂等守卫必须**检查和写入同一个位置**。
    # 踩过：原来检查 _tk.Toplevel._ipscaner_uifix（类属性）却写
    # _tl_init._ipscaner_uifix（函数属性），守卫永远不会为真 → 重复执行时
    # 把 __init__ 包了两层。
    if not getattr(_tk.Toplevel.__init__, "_ipscaner_uifix", False):
        _orig_tl = _tk.Toplevel.__init__

        def _tl_init(self, *a, **k):
            _orig_tl(self, *a, **k)
            try:
                reg.append(self)
            except Exception:  # noqa: BLE001
                pass
            # 缺陷13：新 Toplevel 默认是可见的，产品（dialogs.mkform / f_diy /
            # _diy_edit）既不 withdraw 也不 deiconify —— 它会先以**设计尺寸 1:1**
            # 出现在屏幕上，等 sweep（≤500ms）才被放大。这里立刻收回可见性：
            # 与创建同一个调用栈，中间没有任何一帧被画出来（没有消息泵）。
            if _defer_on:
                try:
                    defer_hide(self, ctx)
                except Exception:  # noqa: BLE001
                    pass

        _tl_init._ipscaner_uifix = True
        _tk.Toplevel.__init__ = _tl_init

    # 产品自己 withdraw 的窗体要尊重（不想现在显示）→ 记个旗标。
    # 实测 dialogs 里没人调 withdraw，但 popup.MenuPopup.__init__ 会调，
    # 以及 warm_popup_windows 的预热窗也会调。
    if not getattr(_tk.Wm.withdraw, "_ipscaner_uifix", False):
        _orig_wd = _tk.Wm.withdraw

        def _wd(self, *a, **k):
            try:
                if getattr(self, "_ipscaner_autohide", False):
                    self._ipscaner_user_hid = True
            except Exception:  # noqa: BLE001
                pass
            return _orig_wd(self, *a, **k)

        _wd._ipscaner_uifix = True
        _tk.Wm.withdraw = _wd

    # 产品若自己 deiconify（f_diy 的「已存在则前置」分支除外），也推迟到
    # 「缩放完成」之后再显示，避免绕开首帧机制又闪一下小的。
    if not getattr(_tk.Wm.deiconify, "_ipscaner_uifix", False) and _defer_on:
        _orig_di = _tk.Wm.deiconify

        def _di(self, *a, **k):
            try:
                if (getattr(self, "_ipscaner_autohide", False)
                        and not getattr(self, "_ipscaner_shown", False)
                        and not defer_is_popup(self)):
                    self._ipscaner_user_hid = False      # 显式要求显示
                    defer_schedule(self, ctx)
                    return None
            except Exception:  # noqa: BLE001
                pass
            return _orig_di(self, *a, **k)

        _di._ipscaner_uifix = True
        _tk.Wm.deiconify = _di

    def sweep():
        S = _cur_scale()
        state["S"] = S
        # 版本号兜底：install() 跑在 Tk.__init__ 里，那时 mainform 还没
        # import theme，所以第一次 set_version 会空跑（sys.modules 里没有
        # theme）。这里每轮补一次 —— 稳定态是 no-op（值已相同）。
        # 必须在主窗体 title() 之后，所以放到 sweep 而不是 install。
        try:
            import sys as _sys
            _th = _sys.modules.get("theme")
            if _th is not None and getattr(_th, "TITLE_VER", "") != \
                    "  Ver: " + BUILD_VERSION:
                set_version(log=log)
        except Exception:  # noqa: BLE001
            pass
        # 工具条按钮归位（面画在 1:1、字画在 xS）—— 每轮都跑，因为主窗体
        # 重绘工具条（refresh_fx / Ctrl+滚轮缩放）会重新建出未归位的图形。
        # 已归位的打了 tag、字色改完对比度达标，所以稳定态是空操作。
        try:
            st = resnap_toolbar(root, S, log=log)
            state["btn"] = st
        except Exception as e:  # noqa: BLE001
            if log is not None:
                log("按钮归位失败 %r" % (e,))
        # 悬浮高亮接管（缺陷9）：懒安装 —— mainform 是本轮之后才 import 的，
        # install() 挂在 Tk.__init__ 上时它还没进 sys.modules。
        try:
            patch_hover_rect(root, log=log)
        except Exception as e:  # noqa: BLE001
            if log is not None:
                log("悬浮高亮接管失败 %r" % (e,))
        # 菜单项悬浮高亮归位（缺陷10）：同样是懒安装
        try:
            patch_refresh_fx(root, log=log)
        except Exception as e:  # noqa: BLE001
            if log is not None:
                log("菜单项高亮接管失败 %r" % (e,))
        # 网卡名规范化 + 下拉框按字符边界截断 + 系统命令启动器
        # （2026-10-08：「字体显示不全」「环境变量点击不了」）
        # install() 里已装过一次；这里重试是为了兜住「install 时 core 还没进
        # sys.modules」的冻结版时序。幂等，稳定态零开销。
        apply_deferred_patches(root, log=log)
        # 主画布上「连大字 AA 都过不了」的文字按同色相压暗（本机实测 1 处）
        try:
            state["con"] = fix_canvas_contrast(root, S, log=log)
        except Exception as e:  # noqa: BLE001
            if log is not None:
                log("画布对比度修复失败 %r" % (e,))
        # 弹窗性能：预热透明分层窗（一次性，见 4.7）
        try:
            warm_popup_windows(root, log=log)
        except Exception as e:  # noqa: BLE001
            if log is not None:
                log("弹窗预热失败 %r" % (e,))
        try:
            # 注册表 + dialogs._OPEN 取并集：注册表覆盖「自建 Toplevel」
            # （show_list / f_diy），_OPEN 覆盖「install 挂注册表之前就已经建好」
            # 的窗体（踩过：测试里 500ms 开完窗体、900ms 才 install，注册表为空，
            # 结果一个窗体都没修）。
            try:
                import dialogs as _dl
                extra = list((getattr(_dl, "_OPEN", {}) or {}).values())
            except Exception:  # noqa: BLE001
                extra = []
            batch = list(reg) + [w for w in extra if w not in reg]
            for win in batch:
                try:
                    if not win.winfo_exists():
                        if win in reg:
                            reg.remove(win)
                        continue
                    if win.overrideredirect():        # 菜单弹层，已在 S 比例下
                        continue
                    # 首帧机制待处理的窗体交给 defer_show 缩放+显示，这里绝不插手
                    # （否则同一轮里会缩两次 → S²，实测会看到窗体瞬间变成 2.25 倍）
                    if (getattr(win, "_ipscaner_autohide", False)
                            and not getattr(win, "_ipscaner_shown", False)):
                        continue
                except Exception:  # noqa: BLE001
                    if win in reg:
                        try:
                            reg.remove(win)
                        except Exception:  # noqa: BLE001
                            pass
                    continue
                try:
                    key = key_of_title.get(str(win.title()))
                    win._ipscaner_key = key
                except Exception:  # noqa: BLE001
                    key = None
                first = not getattr(win, _M_SIZED, False)
                if first:
                    if log is not None:
                        log("首次修复窗体 %s (key=%s, S=%s)" % (win.title(), key, S))
                    res = scale_dialog(win, S, key=key, log=log)
                    if res is None:
                        # 几何还没结算 → 千万别标记完成，下一轮重来
                        if log is not None:
                            log("窗体 %s 几何未结算，本轮跳过" % win.title())
                        continue
                    setattr(win, _M_SIZED, True)
                    setattr(win, _M_SCALE, S)
                    root.update_idletasks()
                    # 同上：几何是异步结算的，必须等 winfo 追平再钳
                    clamp_settled(win, log=log)
                else:
                    # 主窗体 Ctrl+滚轮缩放后 S 会变（实测 1.5 → 3.0），
                    # 已打开的子窗体必须按**新/旧比例**再缩放一次，否则窗口
                    # 停在旧比例上与主窗体对不上。用相对比例而不是绝对 S，
                    # 才不会把已经缩放过一次的子窗体再按 S 乘一遍。
                    prev = getattr(win, _M_SCALE, None)
                    if prev and prev > 0 and abs(S - prev) > 1e-6:
                        setattr(win, _M_SCALE, S)
                        if log is not None:
                            log("比例变化 %s：%s -> %s，重缩放 %.3f"
                                % (win.title(), prev, S, S / prev))
                        scale_dialog(win, S / prev, key=key, log=log,
                                     absolute=False)
                        root.update_idletasks()
                        repair_clipping(win, log=log)
                        clamp_overflow(win, log=log)
                        continue
                    tgt = _scale_px(DESIGN_PX, S)
                    n = 0
                    for k in _all(win):
                        spec = _spec_of(k)
                        if not spec:
                            continue
                        fam = _fam_of(root.tk, spec)
                        if fam in SONG or fam in FIXED_MAP or _is_named(spec):
                            try:
                                k.configure(font=(DIALOG_FAMILY, tgt))
                                n += 1
                            except Exception:  # noqa: BLE001
                                pass
                    if n:
                        root.update_idletasks()
                        repair_clipping(win, log=log)
                        clamp_overflow(win, log=log)
                    # 迟到控件的几何修复：备注编辑面板（点新增/修改才创建，
                    # 晚于 scale_dialog 首次缩放）每轮检查，发现未缩放面板
                    # 就按 S 补上。非备注窗第一行标题判断即返回，开销可忽略。
                    try:
                        if fix_memo_panel(win, S, log=log):
                            root.update_idletasks()
                    except Exception as e:  # noqa: BLE001
                        if log is not None:
                            log("备注面板修复失败 %r" % (e,))
                    # config 底行遮挡修复同样只能放在稳态 —— 它需要读
                    # 已生效的窗体高度来给窗体加高（见函数头「几何读取戒律」）。
                    try:
                        if fix_config_bottom(win, log=log):
                            root.update_idletasks()
                    except Exception as e:  # noqa: BLE001
                        if log is not None:
                            log("config 底行修复失败 %r" % (e,))
        except Exception:  # noqa: BLE001
            pass
        # 注：层叠缺陷修复已移入 scale_dialog 内部（见该函数 ⑤ 步）。
        # 放在 sweep 的 scale_dialog 之后无效 —— 下一轮 sweep 会把几何乘回去。
        try:
            root.after(sweep_ms, sweep)
        except Exception:  # noqa: BLE001
            pass

    root.update_idletasks()
    try:
        root.after(300, sweep)
    except Exception:  # noqa: BLE001
        pass
    try:
        root._ipscaner_reg = reg          # 供重复调用时直接返回同一条链
    except Exception:  # noqa: BLE001
        pass
    return reg


def _scale_px_s(S):
    return _scale_px(DESIGN_PX, S)
