# -*- coding: utf-8 -*-
"""菜单弹出层 —— 真·Toplevel 弹出窗口（现代化自绘菜单）。

为什么不用主窗口的 Canvas 画菜单
--------------------------------
原版 IPScaner 的菜单分两层：

  1. MenuStrip 顶级项 —— 钉在客户区顶部，属于主窗口的一部分；
  2. ToolStripDropDown 下拉层 —— **独立弹出窗口**（Win32 里是 WS_POPUP），
     有自己的边界，因此能：
        · 超出主窗口的右边界 / 下边界；
        · 底部空间不足时自动**向上翻转**；
        · 右侧空间不足时自动**向左展开**；
        · 盖住状态栏而不被裁剪。

旧实现把下拉层也画在主窗口 Canvas 上（tags="fx"），而 Canvas 有裁剪边界，
于是「windows命令(&C)」那条 23 项的下拉（实测高 445px、底边 y=469）正好撞上
y=470 起的状态栏，最后几项被压住 / 顶到窗口底边 —— 用户看到的就是
**「菜单点了却看不到文字」**。这个问题在 Canvas 上架构性无解，只能迁到 Toplevel。

本模块做三件事
--------------
1. `MenuPopup` —— 一个自绘 Toplevel，负责一个菜单层（主菜单或子菜单）；
2. 自动避让 —— 上/下、左/右翻转，尽量完整显示；
3. 视觉现代化 —— 圆角、细边框、轻阴影、悬停高亮、分隔线留白。

主界面像素级复刻不受影响：菜单栏顶级项仍在主 Canvas 上画（那里差异率 0.00%），
本模块只接管**弹出层**。
"""
import tkinter as tk

import menu_def as M

# --- 现代化参数（只作用于弹出层，不动主界面常量） -------------------------
PAD_Y = 4               # 面板上下内边距
ITEM_H = 22             # 单项高度
SEP_H = 7               # 分隔线占高
ICON_COL = 26           # 左侧图标栏宽度（图标 16px 居中 → 两侧各 5px）
TEXT_GAP = 6            # 图标栏右沿到文字的间距
RIGHT_PAD = 14          # 文字右沿到面板右沿（为子菜单箭头留位）
ARROW_W = 12            # 子菜单箭头区宽度
MIN_W = 120             # 面板最小宽度
SCREEN_MARGIN = 4       # 距屏幕边缘的最小间距

RADIUS = 6              # 面板圆角半径（设计像素）
SHADOW = 3              # 阴影带宽度（做在面板外侧；无法做 alpha，用浅灰近色）

# Tk 的 -transparentcolor 只能全透明/全不透明，因此必须挑一个**绝不会被画到**
# 的颜色当键，否则面板边框会和底色一起变透明（踩过：原来拿 #C8C8C8 当键，
# 正好等于 C_BORDER，导致边框整圈消失、看起来像个没有边的灰块）。
TRANSPARENT = "#FE00FE"

# 配色（现代化：比原版 #F0F0F0 更干净的白底 + 轻边框）
C_BG = "#FBFBFB"
C_BORDER = "#C4C4C4"
C_SEP = "#E4E4E4"
C_HOVER = "#E8F1FB"     # 悬停底色（比原版 #C6E2FF 更克制）
C_HOVER_EDGE = "#CFE3F7"
C_TEXT = "#1A1A1A"
C_SHADOW_1 = "#E9E9E9"
C_SHADOW_2 = "#DCDCDC"


def _sub_spec(sub):
    """子菜单描述可以是 list（只给项）或 dict（menu_def 里的 {"w":..,"items":..}）。"""
    if isinstance(sub, dict):
        return sub.get("items", []), sub.get("w")
    return list(sub), None


def _round_rect(cv, x, y, w, h, r, **kw):
    """在 Canvas 上画圆角矩形（用平滑多边形近似）。"""
    r = max(0, min(r, w // 2, h // 2))
    pts = [
        x + r, y,
        x + w - r, y,
        x + w, y,
        x + w, y + r,
        x + w, y + h - r,
        x + w, y + h,
        x + w - r, y + h,
        x + r, y + h,
        x, y + h,
        x, y + h - r,
        x, y + r,
        x, y,
    ]
    return cv.create_polygon(pts, smooth=True, splinesteps=24, **kw)


class MenuPopup:
    """一个菜单弹出层。

    参数
    ----
    host          : MainForm —— 借用它的 fonts / icons / 回调
    items         : menu_def 风格的项列表（(text, icon, act, sub) 或 M.SEP）
    width         : 面板宽度（设计像素）；None 则按内容自适应
    level         : 0 = 主下拉，1 = 子菜单
    on_fire       : 选中叶子项时回调 (act)
    on_hover_item : 悬停到「含子菜单的父项」时回调 (popup, sub_items, anchor_x, anchor_y)
    on_leave_item : 移出父项时回调 (popup) —— 用于延迟收起子菜单
    """

    def __init__(self, host, items, width=None, level=0,
                 on_fire=None, on_hover_item=None, on_leave_item=None):
        self.host = host
        self.items = list(items)
        self.level = level
        self.on_fire = on_fire
        self.on_hover_item = on_hover_item
        self.on_leave_item = on_leave_item

        S = host.S
        self.S = S
        self.f = host.tk_f_dd

        # ---- 布局
        self.lay = self._layout(items, width)
        self.w = self.lay["w"]
        self.h = self.lay["h"]
        self._rows = {}                 # idx -> (iy, ih, plain, ul, icon, act, sub, raw)
        self.hover = None
        self._closed = False
        self._sub = None
        self._sub_src = None
        self._sub_timer = None

        # ---- 窗口
        self.win = tk.Toplevel(host.root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.configure(bg=TRANSPARENT)
        try:
            self.win.attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            self.win.configure(bg=C_BORDER)
        self.pad = int(S * SHADOW)
        self.cv = tk.Canvas(self.win,
                            width=int(self.w * S) + 2 * self.pad,
                            height=int(self.h * S) + 2 * self.pad,
                            bg=TRANSPARENT, highlightthickness=0, bd=0)
        self.cv.pack()

        self._draw()
        self._bind()

    # ------------------------------------------------------------ 布局
    def _layout(self, items, width):
        f = self.f
        need_w = MIN_W
        rows = []
        y = PAD_Y
        for it in items:
            if it is M.SEP:
                rows.append(("sep", y, SEP_H))
                y += SEP_H
                continue
            text, icon, act, sub = it
            plain, ul = M.strip_amp(text)
            tw = f.measure(plain)
            w_need = ICON_COL + TEXT_GAP + tw + RIGHT_PAD + (ARROW_W if sub else 0)
            need_w = max(need_w, w_need)
            rows.append(("item", y, ITEM_H, plain, ul, icon, act, sub, it))
            y += ITEM_H
        w = int(width) if width else int(need_w)
        if w < need_w:                  # 给定宽度放不下就自动加宽（宁宽不切字）
            w = int(need_w)
        w = max(w, MIN_W)
        h = y + PAD_Y
        return {"w": w, "h": h, "rows": rows, "need_w": need_w}

    # ------------------------------------------------------------ 绘制
    def _draw(self):
        cv, S, pad = self.cv, self.S, self.pad

        def X(v):
            return pad + v * S

        def Y(v):
            return pad + v * S

        W, H = self.w, self.h
        # 阴影（两级、右下偏移，做柔和感）
        _round_rect(cv, X(2), Y(3), W * S, H * S, RADIUS * S,
                    fill=C_SHADOW_2, outline="")
        _round_rect(cv, X(1), Y(2), W * S, H * S, RADIUS * S,
                    fill=C_SHADOW_1, outline="")
        # 面板
        _round_rect(cv, X(0), Y(0), W * S, H * S, RADIUS * S,
                    fill=C_BG, outline=C_BORDER, width=1)

        self._rows = {}
        for row in self.lay["rows"]:
            if row[0] == "sep":
                _, iy, ih = row
                cv.create_line(X(ICON_COL - 4), Y(iy + ih / 2),
                               X(W - 8), Y(iy + ih / 2),
                               fill=C_SEP, width=1)
                continue
            _, iy, ih, plain, ul, icon, act, sub, raw = row
            idx = int(iy)
            self._draw_icon(icon, X(ICON_COL / 2), Y(iy + ih / 2))
            self._draw_arrow(sub, X(W - RIGHT_PAD + 2), Y(iy + ih / 2))
            tx = X(ICON_COL + TEXT_GAP)
            cv.create_text(tx, Y(iy + ih / 2), text=plain, font=self.f,
                           fill=C_TEXT, anchor="w")
            if ul is not None and self.host.show_cues:
                pre = self.f.measure(plain[:ul])
                wch = self.f.measure(plain[ul])
                ly = Y(iy + ih / 2) + self.f.metrics("ascent") - 2
                cv.create_line(tx + pre, ly, tx + pre + wch, ly,
                               fill=C_TEXT, width=1)
            self._rows[idx] = (iy, ih, plain, ul, icon, act, sub, raw)

    def _draw_icon(self, icon, cx, cy, tag=None):
        if not icon:
            return
        im = self.host.icons.get(icon)
        if im is not None:
            self.cv.create_image(cx, cy, image=im, anchor="center", tags=tag)

    def _draw_arrow(self, sub, ax, cy, tag=None):
        if not sub:
            return
        self.cv.create_line(ax, cy - 3, ax + 4, cy, ax, cy + 3,
                            fill=C_TEXT, width=1, tags=tag)

    # ------------------------------------------------------------ 高亮
    def _paint_hover(self):
        cv, S, pad = self.cv, self.S, self.pad
        cv.delete("hover")
        cv.delete("hitem")
        idx = self.hover
        if idx is None or idx not in self._rows:
            return
        iy, ih, plain, ul, icon, act, sub, raw = self._rows[idx]
        x0, x1 = 3, self.w - 3
        _round_rect(cv, pad + x0 * S, pad + (iy + 1) * S,
                    (x1 - x0) * S, (ih - 2) * S, 3 * S,
                    fill=C_HOVER, outline=C_HOVER_EDGE, width=1, tags="hover")
        cv.tag_raise("hover")
        # 重画该项内容，保证压在高亮之上
        self._draw_icon(icon, pad + (ICON_COL / 2) * S,
                        pad + (iy + ih / 2) * S, tag="hitem")
        self._draw_arrow(sub, pad + (self.w - RIGHT_PAD + 2) * S,
                         pad + (iy + ih / 2) * S, tag="hitem")
        cv.create_text(pad + (ICON_COL + TEXT_GAP) * S,
                       pad + (iy + ih / 2) * S, text=plain, font=self.f,
                       fill=C_TEXT, anchor="w", tags="hitem")

    def set_hover(self, idx):
        if idx == self.hover:
            return
        self.hover = idx
        self._paint_hover()

    # ------------------------------------------------------------ 事件
    def _bind(self):
        self.cv.bind("<Motion>", self._on_motion)
        self.cv.bind("<Button-1>", self._on_click)
        self.cv.bind("<Leave>", self._on_leave)
        # Esc 关菜单。弹层是 overrideredirect 窗口，不一定拿得到键盘焦点，
        # 所以画布和窗口各绑一份；主窗体的 on_key 里还有第三道兜底。
        self.cv.bind("<Escape>", self._on_escape)
        self.win.bind("<Escape>", self._on_escape)

    def _on_escape(self, _e):
        self.host.dismiss_menus()

    def _hit(self, ex, ey):
        S, pad = self.S, self.pad
        x = (ex - pad) / S
        y = (ey - pad) / S
        if x < 0 or x > self.w or y < 0 or y > self.h:
            return None
        for idx, row in self._rows.items():
            if row[0] <= y < row[0] + row[1]:
                return idx
        return None

    def _anchor_for_row(self, iy):
        """某一行在**屏幕坐标系**里的「面板右沿 / 行顶」——子菜单就往这儿挂。

        y 要再减掉 PAD_Y：子菜单自己也有 PAD_Y 的上内边距，只有把它的**面板顶**
        对齐到父面板顶（而不是父项顶），两边的第一项才会在同一水平线上
        （否则子菜单首项比父项低 4px，实测看得出来）。
        """
        try:
            rx, ry = self.win.winfo_rootx(), self.win.winfo_rooty()
        except Exception:  # noqa: BLE001
            rx = ry = 0
        return (rx + self.pad + self.w * self.S,
                ry + self.pad + (iy - PAD_Y) * self.S)

    def _on_motion(self, e):
        idx = self._hit(e.x, e.y)
        self.set_hover(idx)
        if idx is None:
            if self.on_leave_item:
                self.on_leave_item(self)
            return
        row = self._rows[idx]
        sub = row[6]
        if sub and self.on_hover_item:
            ax, ay = self._anchor_for_row(row[0])
            items, sw = _sub_spec(sub)
            self.on_hover_item(self, items, ax, ay, row[1], sw)
        elif self.on_leave_item:
            self.on_leave_item(self)

    def _on_click(self, e):
        idx = self._hit(e.x, e.y)
        if idx is None:
            # 点在面板外的透明边 → 关菜单
            self.host.dismiss_menus()
            return
        row = self._rows[idx]
        sub = row[6]
        if sub:
            if self.on_hover_item:
                ax, ay = self._anchor_for_row(row[0])
                items, sw = _sub_spec(sub)
                self.on_hover_item(self, items, ax, ay, row[1], sw)
            return
        act = row[5]
        self.host.dismiss_menus()
        if self.on_fire and act:
            self.on_fire(act)

    def _on_leave(self, _e):
        if self.on_leave_item:
            self.on_leave_item(self)

    # ------------------------------------------------------------ 定位 / 显示
    def place(self, x, y, prefer_up=False):
        """把面板**可见区左上角**摆到屏幕 (x, y)；越界时自动上翻 / 左移。

        窗口本身比面板大 2*pad（给阴影留的边），所以窗口坐标要各减 pad。
        """
        self.win.update_idletasks()
        S, pad = self.S, self.pad
        wpx = int(self.w * S) + 2 * pad
        hpx = int(self.h * S) + 2 * pad
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()

        vx, vy = int(x), int(y)                  # 面板可见区目标位置
        px = vx - pad
        py = vy - pad

        # 右侧越界 → 向左展开
        if px + wpx > sw - SCREEN_MARGIN:
            px = vx - wpx + pad
        if px < 0:
            px = 0
        if px + wpx > sw - SCREEN_MARGIN:
            px = max(0, sw - SCREEN_MARGIN - wpx)

        # 下方越界 → 向上翻转（面板底边对齐锚点 y）
        if py + hpx > sh - SCREEN_MARGIN:
            flip = vy - hpx + pad
            py = flip if flip >= 0 else max(0, sh - SCREEN_MARGIN - hpx)
        if py < 0:
            py = 0

        self.win.geometry("%dx%d+%d+%d" % (wpx, hpx, px, py))
        self.win.deiconify()
        self.win.lift()
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass

    def contains_screen_point(self, sx, sy):
        try:
            x0, y0 = self.win.winfo_rootx(), self.win.winfo_rooty()
            return (x0 <= sx < x0 + self.win.winfo_width() and
                    y0 <= sy < y0 + self.win.winfo_height())
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------ 关闭
    def _cancel_timer(self):
        if self._sub_timer:
            try:
                self.win.after_cancel(self._sub_timer)
            except Exception:  # noqa: BLE001
                pass
            self._sub_timer = None

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._cancel_timer()
        if self._sub is not None:
            sub, self._sub = self._sub, None
            try:
                sub.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            self.win.attributes("-topmost", False)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.win.destroy()
        except Exception:  # noqa: BLE001
            pass

    @property
    def sub(self):
        return self._sub
