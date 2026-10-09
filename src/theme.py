# -*- coding: utf-8 -*-
"""主题常量 —— 全部数值来自 IPScaner V1.25 反编译源码 + 原版截图逐像素实测。

坐标全部是「窗体客户区」坐标（不含标题栏），单位 = 像素。
原版截图是 2 倍尺寸，所有 image 坐标 ÷2 后填入下表。

数据来源标注：
  [SRC] = 反编译 C# 源码 InitializeComponent 中的字面值
  [MEAS] = 原版截图逐像素扫描实测
"""
import os
import sys

# ----------------------------------------------------------------- 窗体
CLIENT_W, CLIENT_H = 835, 486          # [SRC] base.ClientSize
TITLE_TEXT = "局域网IP扫描工具"          # [SRC] this.Text
TITLE_VER = "  Ver: 1.25.0"            # [SRC] Text + "  Ver: " + Application.ProductVersion

# ----------------------------------------------------------------- 颜色
C_FACE = "#F0F0F0"          # [MEAS] SystemColors.Control，窗体与控件底色
C_MENU_BG_L = "#F0F0F0"     # [MEAS] MenuStrip 水平渐变左端
C_MENU_BG_R = "#F8F8F8"     # [MEAS] MenuStrip 水平渐变右端

# [MEAS] MenuStrip 底色：GDI GradientFill 的分带渐变，实测边界（1x 逻辑像素）
#       0..27 F0 / 27..80 F1 / 80..187 F2 / ... / 825..835 FC
MENU_GRAD = [
    (0, "#F0F0F0"), (27, "#F1F1F1"), (80, "#F2F2F2"), (187, "#F3F3F3"),
    (240, "#F4F4F4"), (293, "#F5F5F5"), (399, "#F6F6F6"), (453, "#F7F7F7"),
    (506, "#F8F8F8"), (612, "#F9F9F9"), (665, "#FAFAFA"), (719, "#FBFBFB"),
    (825, "#FCFCFC"),
]
C_WHITE = "#FFFFFF"
C_BTN_FACE = "#FDFDFD"      # [MEAS] 按钮面（FlatStyle=Flat 的内层高光）
C_BTN_BORDER = "#D0D0D0"    # [MEAS] 按钮外框（= SystemColors.ControlDark）
C_BTN_BORDER_B = "#BABABA"  # [MEAS] 按钮外框下沿（略深）
C_ACCENT = "#0078D4"        # [MEAS] SystemColors.Highlight，获得焦点的按钮外框 + 蓝色小标题
C_ACCENT_DARK = "#006BBE"   # [MEAS] 焦点按钮外框下沿
C_GROUP_FRAME = "#DCDCDC"   # [MEAS] GroupBox 蚀刻边框

C_SKYBLUE = "#87CEEB"       # [SRC] Color.SkyBlue    —— 默认/未扫描
C_LIMEGREEN = "#32CD32"     # [SRC] Color.LimeGreen  —— 通讯正常
C_INDIANRED = "#CD5C5C"     # [SRC] Color.IndianRed  —— 通讯不通
C_MEMO_BLUE = "#0000FF"     # [SRC] Color.Blue       —— 有备注
C_ORANGERED = "#FF4500"     # [SRC] Color.OrangeRed  —— 本机 IP（前景+边框）
C_BLACK = "#000000"
C_RED = "#FF0000"           # [SRC] statusHostName.LinkColor
C_MENU_HILIGHT = "#0078D4"  # [SRC] SystemColors.MenuHighlight（状态栏 Tip 文字）

C_STATUS_SEP = "#A0A0A0"    # [MEAS] 状态栏面板分隔竖线
C_COMBO_BORDER_T = "#D2D2D2"  # [MEAS]
C_COMBO_BORDER_B = "#BCBCBC"  # [MEAS]
C_EDIT_BORDER = "#ECECEC"     # [MEAS] 文本框上/左
C_EDIT_BORDER_R = "#E6E6E6"   # [MEAS] 文本框右
C_EDIT_BORDER_B = "#838383"   # [MEAS] 文本框下沿（明显更深）
C_ARROW = "#6E6E6E"          # [MEAS] 下拉箭头

# 下拉菜单（ToolStripProfessionalRenderer 默认配色）
C_DD_BG = "#F0F0F0"
C_DD_BORDER = "#A0A0A0"
C_DD_MARGIN_LINE = "#E0E0E0"
C_DD_HILIGHT = "#C6E2FF"
C_MENU_SELECT = "#C9E4FF"   # [MEAS] 顶级菜单项悬停高亮（MenuItemSelected）
C_DD_SEP = "#E0E0E0"
C_DD_TEXT_DISABLED = "#9A9A9A"

# ----------------------------------------------------------------- 字体
# tkinter 用「负数」字号表示像素高度（绕开 DPI 缩放），保证像素级对齐。
#
# 全部来自反编译源码的 InitializeComponent（[SRC]）+ 原版截图墨迹实测（[MEAS]）。
# 实测方法见 scripts/font_audition.py：把候选字体渲染出来，与原版同一字符串的
# 「墨迹列剖面」对比，r=1.000 即完全一致。
F_DEFAULT = ("宋体", -12)       # [SRC] 未显式设置的窗体默认字体（分组框标题、lblStat、
                                #       btnDetail/btnExport、cmbAdapter —— 都是 9pt）
F_10PT = ("宋体", -14)          # [SRC] Font("宋体", 10f)，字符串含 CJK 时
# [MEAS] 同一 宋体 10f，GDI 给「纯 ASCII」走的是 13px 点阵（不是 14px）：
#   "172.19.80" 原版墨迹 60x9 / 125 像素 == Tk 宋体 -13（-14 会得到 61x10 / 142）；
#   "列表展示" 这类 CJK 只有 -14 才对得上（47x12/193 属于 9pt，见下）。
#   Tk 一个字号只能给一档，所以按内容挑 —— 见 mainform._f10_for()。
F_10PT_ASCII = ("宋体", -13)
F_BLOCK = ("微软雅黑", -12)      # [SRC] Font("微软雅黑", BtnFontSize=9f) —— 色块数字
F_TITLE = ("微软雅黑", -16)      # [SRC] Font("微软雅黑", 12f) —— 蓝色大标题
F_DD = ("微软雅黑", -12)        # 下拉菜单项：ToolStrip 默认字体
F_MENU = ("微软雅黑", -12)      # [MEAS] MenuStrip 顶级项（未设字体 → SystemFonts.MenuFont）
F_STATUS = ("微软雅黑", -12)    # [MEAS] StatusStrip 7 个面板（同上）

# [MEAS] 关键佐证：menu 项「快捷工具(T)」原版墨迹 63x12，微软雅黑 -12 逐列 r=1.000；
#        statusIP 全串推进宽度 261 == 微软雅黑 -12 的 measure（宋体 -12 为 276）。
#        而「图例：」原版墨迹 32x14 只有宋体 -14 能 r=1.000 —— 与源码 宋体 10f 完全吻合。

# ----------------------------------------------------------------- 菜单栏
MENU_H = 24                 # [SRC] menuStrip1.Size.Height
MENU_PAD_L, MENU_PAD_T = 3, 1   # [SRC] menuStrip1.Padding(3,1,0,1)
MENU_ITEM_H = 22            # [SRC] 顶级项 Size = (w, 22)
MENU_ICON = 16              # [SRC] ImageScalingSize 28 但图标本身 16x16，ImageScaling=None
MENU_ICON_LEFT = 4          # [MEAS] 图标图像左边距（相对菜单项左边缘）
MENU_TEXT_LEFT = 23         # [MEAS] 文字起点（相对菜单项左边缘）；原版墨迹落在 L+26/123/229/331/455
MENU_TEXT_DY = -1           # [MEAS] 相对 h/2 的垂直修正（原版墨迹 y 6..17，Tk 直接居中会落到 7..18）
# [SRC] WinForms 默认 ShowKeyboardCues=false —— 只有按下 Alt 之后才画 &X 的下划线。
# 原版截图里没有下划线，所以默认不画（按下 Alt 再显示，与原版行为一致）。
MENU_KEYBOARD_CUES = False

# [MEAS] 5 个顶级项的运行时实际宽度 —— 由原版截图的「图标墨迹 + 文字墨迹」起点反推：
#   图标在 L+4、文字在 L+22 都能对上（icon1 7 icon2 104 icon3 210 icon4 312 icon5 436/437），
#   由此得到 3 / 100 / 206 / 308 / 432 起点，相邻差即本表。
#   注意：与设计器序列化的 99/104/102/126/76 不同 —— 那是设计字体下的值，运行时按
#   SystemFonts.MenuFont(微软雅黑 9pt) 重新 AutoSize 过。
MENU_ITEM_W = [97, 106, 102, 124, 76]

# ----------------------------------------------------------------- 工具栏 groupBox1
GB1 = (0, 24, 835, 48)      # [SRC] Location/Size，Dock=Top
GB1_FRAME_INSET = 7         # [MEAS] GroupBox 为标题预留的高度 → 框线在 y+7

# 控件： (x, y, w, h)  —— y 已折算为「客户区绝对坐标」= 24 + 源码相对 y
CMB_ADAPTER = (7, 43, 74, 20)      # [SRC] Location(7,19) Size(74,20)
TXT_IPPART = (85, 43, 90, 23)      # [SRC] Location(85,19) Size(90,23)
BTN_START = (177, 42, 56, 22)      # [SRC] Location(177,18) Size(56,22)
BTN_STOP = (245, 42, 56, 22)
LBL_LEGEND = (319, 46)             # [SRC] Location(319,22) AutoSize 49x14
BTN_NG = (359, 42, 56, 22)         # [SRC] 不通
BTN_OK = (420, 42, 56, 22)         # [SRC] 正常
BTN_DETAIL = (480, 42, 79, 23)     # [SRC] Location(480,18) Size(79,23)
BTN_EXPORT = (563, 42, 56, 23)     # [SRC] Location(563,18) Size(56,23)
LBL_STAT = (623, 47)               # [SRC] Location(623,23) AutoSize 23x12
LBL_LEGEND_TEXT = "图例："          # [SRC] label1.Text
LBL_STAT_TEXT = "---"              # [SRC] lblStat.Text
LBL_LEGEND_PAD = 3                 # [MEAS] 控件 x=319 -> 墨迹 x=323
LBL_STAT_PAD = 2                   # [MEAS] 控件 x=623 -> 墨迹 x=625
LBL_STAT_DY = 6                    # [MEAS] lblStat 文字垂直锚点（sy+6 → 墨迹行落在 y=52）
TXT_IP_PAD = (3, 2)                # [MEAS] 文本框内边距（左 3，顶 2）
TXT_IP_DY = -3                     # [MEAS] 相对 y+h/2 的修正（原文贴顶不居中）
CMB_TEXT_PAD = 4                   # [MEAS] 下拉框文字左边距（控件 x=7 -> 墨迹 x=11）
# [MEAS] 文字裁剪线 = x + w - CMB_TEXT_CLIP_R。WinForms 的 DropDownList 把文字画在
#        「控件宽 - 下拉按钮宽」之内，超宽部分连半个字形都不画（原版 "vEthernet (WSL)"
#        只露出 "vEtherne" + 一点点 t，墨迹止于 x=60；控件右沿 80，箭头左沿 63）。
CMB_TEXT_CLIP_R = 20               # 裁剪线 7+74-20 = 61 → 墨迹止于 60 ✓
# [MEAS] 下拉箭头 = 1px 粗的 V 形，但不是一条折线 —— 原版两条臂在底部各占一格、
#        中间不相连（左臂 x68..71 / 右臂 x72..75，都在 y52 起、y55 收），
#        用折线画会因为斜接多出像素。
# ⚠️ Tk 的 create_line 不画「末点」那个像素（实测：给 (68,52)-(71,55) 只得
#    68,52/69,53/70,54），所以每条线段都要把终点往外多推 1 格。
CMB_ARROW = ((68, 52, 72, 56), (72, 55, 76, 51))

# [MEAS] FlatStyle 按钮的分层几何（相对控件 (x, y, w, h)，逻辑像素）。
#   实测基准「开始」btnStart = (177, 42, 56, 22)：
#     外框   墨迹 x178..231 / y43..62   →  列 231 在 y47..59 是 #0078D4（右框）
#                                        →  = (x+1, y+1, w-2, h-2)
#     面色块 墨迹 x181..228 / y46..59   →  = (x+4, y+4, w-8, h-8)
#     中间那圈 #FDFDFD 高光由前两层相减自动得到。
#   ⚠️ 别被 y=44 那一行骗到：圆角弧会把右框临时拉到 x+53，只有中部行才露出真位置。
#   注意：外框四角在原版是 GDI+ 抗锯齿圆角（半径≈3），这里只能用直角近似。
BTN_FRAME_D = (1, 1, 2, 2)      # x+L, y+T, w-Wd, h-Hd
BTN_FACE_D = (4, 4, 8, 8)

BTN_ICON_PAD = 3            # [MEAS] 图标左内边距
# [MEAS] 图标按钮的文字右端锚点 —— 必须相对「控件」算，不能相对外框：
#   detail (x480 w79) 墨迹右端 550 → anchor="e" 的 tx = 552 = x+w-7
#   export (x563 w56) 墨迹右端 610 →                tx = 612 = x+w-7
BTN_TEXT_RIGHT = 7
# [MEAS] 文字垂直修正：GDI 按「墨迹框」居中、Tk 按「字体行框」居中，差 1px，
#        但差值随字号变 —— 必须分开设：
#          图标按钮（宋体 9pt）: 原版「列表展示」墨迹 y47..58，Tk 直画 y48..59 → -1
#          居中按钮（宋体 10pt）: 原版「开始」  墨迹 y46..59，Tk 直画 y45..58 →  0
BTN_TEXT_DY = -1            # 图标按钮（宋体 9pt）
BTN_TEXT_DY_C = 0           # 居中按钮（宋体 10pt）
# [MEAS] 居中按钮（无图标）的水平修正：Tk 居中后墨迹整体右偏 1px
#        （原版「开始」墨迹 190..216，Tk 直画 191..217）。
BTN_TEXT_DX = -1

# GroupBox 标题
GB_CAP_PAD_X = 8            # [MEAS] 标题文字起点 = 分组框左 + 8（上边线在左 +7 处断开）
GB_CAP_DY = -1              # [MEAS] 标题文字垂直修正（原版墨迹 y72..83，Tk 直画 y73..84）

# ----------------------------------------------------------------- 扫描结果 groupBox2
GB2 = (0, 72, 835, 388)     # [SRC] Location/Size
GB2_CAPTION = "扫描结果"     # [SRC] groupBox2.Text

# 蓝色小标题
TITLE_CENTER = (415.5, 97.5)  # [SRC] lblTitle 绝对 (4,88) Size(827,21) TextAlign=MiddleCenter
                              # [MEAS] 文字中心实测 (416.5, 99) → Tk 居中需减 2/1

# 色块矩阵：[MEAS] 第 1 格外框左上 (5,111)，外框 39x24，外框间距 41x26
BLOCK_W, BLOCK_H = 39, 24   # [SRC] BtnWidth / BtnHeight（BtnFontSize=9 时）
BLOCK_X0, BLOCK_Y0 = 5, 112 # [SRC] flowLayoutPanel 绝对 (4,111) + Margin(1)
BLOCK_DIGIT_DX = -2               # [MEAS] 色块数字：Tk measure 比 GDI 宽 4px，居中后右移 2px
BLOCK_PITCH_X, BLOCK_PITCH_Y = 41, 26   # [SRC] W+2*Margin / H+2*Margin
BLOCK_MARGIN = 1            # [SRC] button.Margin = new Padding(1)
BLOCK_COUNT = 254           # [SRC] for (i = 1; i < 255; i++)
BLOCK_COLS = 20             # [MEAS] flowLayoutPanel 宽度 827 / 41 = 20 列
BLOCK_TEXT_ALIGN = "top"    # [SRC] button.TextAlign = TopCenter

# ----------------------------------------------------------------- 状态栏
STATUS_Y, STATUS_H = 460, 26    # [SRC] statusStrip1.Location.y / Size.Height
STATUS_PAD_L, STATUS_PAD_R = 1, 10   # [SRC] statusStrip1.Padding(1,0,10,0)
STATUS_ITEM_H = 21              # [SRC] 各 ToolStripStatusLabel.Size.Height

# [SRC→MEAS] 面板宽度与文字位置的规则，由设计器序列化的 Size 反解 + 截图像素验证：
#   面板宽 = 文字推进宽度 + STATUS_PAD_BASE + (BorderSides.Left ? STATUS_BORDER_W : 0)
#   文字起点 = 面板左 + STATUS_TEXT_PAD + (BorderSides.Left ? STATUS_TEXT_PAD_B : 0)
#   验证：statusTip "程序准备就绪"(72) → 80 ✓ 与序列化 Size(80,21) 一致
#         statusHostName "已禁用主机名查询"(96) → 108 ✓ 序列化 Size(108,21)
#         statusFriendlyTip2 "你知道吗？"(60) → 72 ✓ 序列化 Size(72,21)
#         statusIP "  "(7) → 19≈20 ✓ 序列化 Size(20,21)
#         statusTime " "(4) → 16 ✓ 序列化 Size(16,21)
#   截图实测分隔线 81 / 189 / 522 也完全对上（189-81=108, 512+10=522）。
STATUS_PAD_BASE = 8             # 面板宽 = 文字宽 + 8（+ 边框 4）
STATUS_BORDER_W = 4             # BorderSides.Left 额外占宽
STATUS_TEXT_PAD = 3             # 无边框面板：文字相对面板左的偏移
STATUS_TEXT_PAD_B = 2           # 有左边框时再 +2（含 1px 线）
STATUS_SEP_INSET = 3            # [MEAS] 左分隔竖线上下内缩
STATUS_TOP_LINE = "#D7D7D7"     # [MEAS] 状态栏上沿线

STATUS_READY = "程序准备就绪"                 # [SRC] 250 行
STATUS_HOSTNAME_OFF = "已禁用主机名查询"      # [SRC] QueryHostNameEnabled=false
STATUS_HOSTNAME_ON = "已启用主机名查询"       # [SRC] 1052 行
STATUS_IP_PREFIX = "活动IP:"                  # [SRC] 263 行
STATUS_TIME_FMT = "%Y-%m-%d %H:%M:%S"        # [SRC] 448 行 ToString 格式

# [SRC] InitTipList（435-441 行）—— 18 条，每 10 秒轮换一条
TIP_LIST = [
    "Tip:右击某一个IP小色块，可调出ping命令窗口",
    "Tip:右击某一个IP小色块，可复制IP、计算机名、MAC地址",
    "注意:开启【主机名查询】功能,将会降低查询效率",
    "Tip:点击【不通】图例,可复制所有通讯【异常】的IP地址",
    "Tip:点击【正常】图例,可复制所有通讯【正常】的IP地址",
    "Tip:点击【IP小色块】,可快速复制IP地址",
    "Tip:鼠标右击【IP小色块】,在右键菜单中,点击菜单可复制到剪粘板",
    "Tip:点击顶部IP下拉框,可切换IP扫描段",
    "Tip:快捷工具中的所有工具,都可以打开多个哦",
    "Tip:想扫描A类的多段IP,可以使用快捷工具中的【IP批量扫描】",
    "Tip:快捷工具中的【修改本地IP】,支持历史IP快速切换",
    "Tip:快捷工具中的【端口扫描】,可以查看计算机开放了哪些端口",
    "Tip:快捷工具中的【IP批量扫描】,可快速扫描指定的批量IP",
    "Tip:鼠标悬停在【IP小色块】上,会显示计算机名称和MAC地址",
    "Tip:单击【IP小色块】,可以快速查询计算机名称和MAC地址",
    "Tip:本工具只支持查询 当前电脑所在网段下的所有MAC地址",
    "Tip:外部工具栏中可快速打开本地控制面板中的某些设置项",
    "Tip:小色块的双击功能支持自定义",
]

# ----------------------------------------------------------------- 交互
DOUBLE_CLICK_MS = 200       # [SRC] ConfigInfo.DoubleClickTime 默认 200

# [MEAS] 原版截图那一帧状态栏轮播的正是这条 Tip
#        （Tip 区墨迹 194..504 = 推进宽 311，TIP_LIST 里唯一匹配）
SHOT_TIP = "Tip:右击某一个IP小色块，可复制IP、计算机名、MAC地址"
SHOT_TIP_INDEX = 1          # SHOT_TIP 在 TIP_LIST 里的下标（命令行传中文易被转码毁掉）

# ----------------------------------------------------------------- 参考帧整组
# 「原版截图那一帧」需要同时钉住 4 个状态量，少一个差异率就虚高：
#   1. --scale=1        客户区 835×486，与还原后的 1× 真值同为设备像素
#   2. --ip + --adapter  标题、网卡下拉框、被高亮的那个色块
#   3. --tip-index       状态栏 Tip（不钉就会轮播）
#   4. --freeze          冻结时钟面板 + Tip 轮播，停在截图那一刻
# ⚠️ 活动 IP 必须**强制指定**：原版截图时本机网卡是
#    172.19.80.1 / 192.168.56.1 / 192.168.5.65，而现在本机已经变了
#    （实测变成 51.10.x.x），不指定的话状态栏右半整段对不上。
SHOT_LOCAL_IP = "172.19.80.1"
SHOT_ADAPTER = "vEthernet (WSL)"
SHOT_ACTIVE_IPS = "172.19.80.1; 192.168.56.1; 192.168.5.65"
# 同步位置：scripts/run_app.ps1 与 scripts/run_exe.ps1 的 -Shot 分支（那两个文件
# 必须保持纯 ASCII，无法 import 本模块，只能手工同步）。

# ----------------------------------------------------------------- 资源目录
# 运行时缩放：本表所有数值都是「96 DPI 设计单位」。
# 原版 WinForms 在 200% DPI 下会自动放大 2 倍（AutoScaleMode=Font），
# 老师提供的原版截图正是 200% 下拍的 —— 所以这里也按系统 DPI 等比放大，
# 保证在任何缩放比例的机器上观感都与原版一致。
SCALE = 1.0

# 允许强制指定缩放（用于与原版截图做 1:1 比对）：IPSCANER_SCALE=2.0
SCALE_ENV = "IPSCANER_SCALE"


def get_system_dpi(root=None):
    """取当前系统的真实 DPI。进程 DPI 感知时拿到的是 96·缩放比。"""
    try:
        import ctypes

        hdc = ctypes.windll.user32.GetDC(0)
        dpi = int(ctypes.windll.gdi32.GetDeviceCaps(hdc, 88))  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        if dpi > 0:
            return float(dpi)
    except Exception:  # noqa: BLE001
        pass
    if root is not None:
        try:
            return float(root.winfo_fpixels("1i"))
        except Exception:  # noqa: BLE001
            pass
    return 96.0


def set_scale_from(root=None):
    """按 DPI 计算缩放比。

    96→1.0 ／ 120→1.25 ／ 144→1.5 ／ 168→1.75 ／ 192→2.0，
    量化到 1/4 档，避免 DPI 读数抖动。
    """
    global SCALE

    forced = os.environ.get(SCALE_ENV, "").strip()
    if forced:
        try:
            SCALE = max(1.0, float(forced))
            return SCALE
        except ValueError:
            pass

    dpi = get_system_dpi(root)
    SCALE = max(1.0, round(dpi / 96.0 * 4) / 4.0)
    return SCALE


def u(v):
    """设计单位 → 实际像素。"""
    return int(round(v * SCALE))


def ub(box):
    """(x, y, w, h) 设计单位 → 实际像素。"""
    return tuple(u(v) for v in box)


def lw(v=1):
    """逻辑线宽（1px）→ 设备像素。

    WinForms 的 1px 边框在高 DPI 下会被 DrawXxx 放大成 SCALE 像素，
    而 Tk 的线宽是设备像素，所以必须自己乘。
    """
    return max(1, int(round(v * SCALE)))


def assets_dir():
    """兼容 PyInstaller 单文件模式（sys._MEIPASS）与源码运行。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "assets")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def font_available(name):
    try:
        import tkinter.font as tkfont
        return name in tkfont.families()
    except Exception:  # noqa: BLE001
        return False


def resolve_font(spec):
    """字体缺失时回退到系统常见中文字体。"""
    name, size = spec
    for cand in (name, "Microsoft YaHei", "微软雅黑", "SimSun", "宋体", "TkDefaultFont"):
        try:
            if cand == "TkDefaultFont" or font_available(cand):
                return (cand, size)
        except Exception:  # noqa: BLE001
            continue
    return spec
