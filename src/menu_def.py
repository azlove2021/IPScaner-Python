# -*- coding: utf-8 -*-
"""菜单结构 —— 逐项照抄 IPScaner V1.25 反编译源码的 InitializeComponent。

字段： (显示文本, 图标名或None, 动作id或None, 快捷键或None)
文本里的 "&X" 是 WinForms 快捷键前缀（会渲染成下划线），"&&" 表示字面 &。
分隔符用 SEP 表示。
"""

SEP = "---"

# ---------------------------------------------------------------- 顶级菜单
# [SRC] menuStrip1.Items.AddRange({ 工具, mnuMemoManage, mnuOptionSet, toolStripMenuItem2, mnuAbout })
# 尺寸：[SRC] 99x22 / 104x22 / 102x22 / 126x22 / 76x22
MENU_BAR = [
    {"id": "tools", "text": "快捷工具(&T)", "icon": "工具ToolStripMenuItem", "w": 99},
    {"id": "memo", "text": "备注管理(&M)", "icon": "mnuMemoManage", "w": 104},
    {"id": "option", "text": "选项配置(&O)", "icon": "mnuOptionSet", "w": 102},
    {"id": "wincmd", "text": "windows命令(&C)", "icon": "toolStripMenuItem2", "w": 126},
    {"id": "about", "text": "关于(&A)", "icon": "mnuAbout", "w": 76},
]

# ---------------------------------------------------------------- 下拉菜单
# 每项：(文本, 图标, 动作id, 子菜单)
DROPDOWNS = {
    # [SRC] DropDownItems 8 项，宽 164
    "tools": {
        "w": 164,
        "items": [
            ("修改本地IP(&L)", "mnuLocalIP", "localip", None),
            ("IP批量扫描(&S)", "mnuIPSegment", "ipsegment", None),
            ("IP地址计算器(&C)", "mnuAddressCalc", "addresscalc", None),
            SEP,
            ("端口扫描(&P)", "mnuPortScan", "portscan", None),
            ("系统端口查看(&V)", "mnuProcessPort", "processport", None),
            SEP,
            ("WiFi密码(&W)", "mnuWiFiView", "wifi", None),
        ],
    },
    # [SRC] mnuAbout 无子项，直接触发 AboutBox
    "memo": {
        "w": 168,
        "items": [("备注管理(&M)", "mnuMemoManage", "memomanager", None)],
    },
    "option": {
        "w": 168,
        "items": [("选项配置(&O)", "mnuOptionSet", "config", None)],
    },
    # [SRC] DropDownItems 23 项，宽 148
    "wincmd": {
        "w": 148,
        "items": [
            ("我的命令(&M)", "mnuDIY", "diy", {
                "w": 124,
                "items": [
                    ("功能说明", "mnuDIYHelp", "diyhelp", None),
                    SEP,
                ],
            }),
            SEP,
            ("控制面板(&C)", "控制面板ToolStripMenuItem", "cmd:control", None),
            ("卸载程序(&U)", "卸载程序ToolStripMenuItem", "cmd:appwiz.cpl", None),
            ("区域语言", "区域语言ToolStripMenuItem", "cmd:intl.cpl", None),
            ("日期和时间", "日期和时间ToolStripMenuItem", "cmd:timedate.cpl", None),
            SEP,
            ("网络连接(&N)", "网络连接ToolStripMenuItem", "cmd:Ncpa.cpl", None),
            ("防火墙(&F)", "windows防火墙ToolStripMenuItem", "cmd:wf.msc", None),
            ("Internet属性", "internet属性ToolStripMenuItem", "cmd:inetcpl.cpl", None),
            SEP,
            ("计算机管理", "计算机管理ToolStripMenuItem", "cmd:compmgmt.msc", None),
            ("组策略", "组策略ToolStripMenuItem", "cmd:gpedit.msc", None),
            ("注册表(&R)", "注册表ToolStripMenuItem", "cmd:regedit", None),
            ("服务(&S)", "服务ToolStripMenuItem", "cmd:services.msc", None),
            ("系统属性", "系统属性ToolStripMenuItem", "cmd:sysdm.cpl", None),
            ("环境变量(&V)", "环境变量ToolStripMenuItem", "cmd:sysdm.cpl,,3", None),
            ("用户账户", "用户账户ToolStripMenuItem", "cmd:control userpasswords", None),
            SEP,
            ("设备管理(&D)", "设备管理ToolStripMenuItem", "cmd:devmgmt.msc", None),
            ("电源选项(&P)", "电源选项ToolStripMenuItem", "cmd:powercfg.cpl", None),
            ("设备和打印机", "设备和打印机ToolStripMenuItem", "cmd:control printers", None),
            ("磁盘管理", "磁盘管理ToolStripMenuItem", "cmd:diskmgmt.msc", None),
        ],
    },
    "about": {
        "w": 168,
        "items": [("关于(&A)", "mnuAbout", "about", None)],
    },
}

# ---------------------------------------------------------------- 色块右键菜单
# [SRC] contextMenuStrip 14 项，宽 160
# 前 3 项文本由运行时改写（显示当前 IP / 主机名 / MAC）
CONTEXT_MENU = {
    "w": 160,
    "items": [
        ("请先点击IP色块", None, "copyip", None),
        ("等待查询IP信息", None, "copyname", None),
        ("再查看右键菜单", None, "copymac", None),
        SEP,
        ("端口扫描(&S)", None, "cportscan", None),
        ("访问共享目录", None, "cshare", None),
        ("浏览网页(&V)", None, "cweb", None),
        ("调用Ping命令", None, "cping", None),
        ("调用Tracert(&R)", None, "ctracert", None),
        ("调用Telnet(&T)", None, "ctelnet", None),
        ("调用netstat(&N)", None, "cnetstat", None),
        ("调用ARP(&A)", None, "carp", None),
        SEP,
        ("备注信息(&M)", None, "cmemo", None),
    ],
}

# ---------------------------------------------------------------- 托盘菜单
# [SRC] contextMenuNotify 5 项，宽 180
TRAY_MENU = {
    "w": 180,
    "items": [
        ("显示主界面(&S)", None, "trayshow", None),
        ("隐藏(&H)", None, "trayhide", None),
        SEP,
        ("关于(&A)", None, "about", None),
        ("退出(&X)", None, "exit", None),
    ],
}


def strip_amp(text):
    """去掉 WinForms 快捷键前缀，返回 (纯文本, 下划线字符序号或 None)。"""
    out, ul, i = [], None, 0
    while i < len(text):
        if text[i] == "&":
            if i + 1 < len(text) and text[i + 1] == "&":
                out.append("&")
                i += 2
                continue
            if i + 1 < len(text):
                ul = len(out)
                out.append(text[i + 1])
                i += 2
                continue
        out.append(text[i])
        i += 1
    return "".join(out), ul
