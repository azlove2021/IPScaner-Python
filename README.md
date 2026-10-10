# IPScaner · 局域网 IP 扫描工具（Python 复刻版）

> **单文件绿色版** · 免安装 · Python 3.10 + Tkinter 复刻 · 当前版本 **v1.27.0**
>
> 双击即用，不写注册表、不依赖运行库、不需要装 Python。

原版 IPScaner 是一个用 .NET WinForms 写的局域网扫描小工具。本项目用 **Python 3.10 + Tkinter 完整复刻**了它的界面与功能，并在复刻基础上做了**现代化视觉改版**（对齐 macOS 液态玻璃风格）与**一批缺陷修复**，最后打包成**单个 exe**（约 7.9 MB）。

---

## ✨ 功能一览

### 主界面
- **254 个 IP 色块矩阵** —— 一眼看清整个网段里哪些 IP 在线
- 网卡下拉选择（宽度自适应，长网卡名不再被截断）
- 窗口可自由**缩放 / 最大化**，界面元素随比例重排
- 工具栏：开始扫描 / 停止 / 导出 / 详情 / 复制
- 状态栏实时统计（在线数 / 离线数 / 扫描进度）
- 系统托盘：可最小化到托盘，右键菜单显示 / 隐藏 / 退出

### 快捷工具

| 功能 | 说明 |
|---|---|
| 修改本地 IP | 一键设置本机网卡的 IP / 掩码 / 网关 / DNS |
| **IP 批量扫描** | 输入任意 IP 列表（**可跨网段**）或按网段批量生成，表格化结果 |
| IP 地址计算器 | 掩码 ↔ 前缀换算、网段与广播地址计算 |
| 端口扫描 | 指定 IP + 端口范围，检测开放端口 |
| 系统端口查看 | 列出本机监听端口及其所属进程 |
| WiFi 密码 | 查看本机已保存的 WiFi 密码 |

### 备注管理
- 给任意 IP 打业务备注（"这是打印机"、"这是 NAS"、"测试机不要动"…）
- **主界面右键 IP 色块 → 备注信息**，即时编辑
- 批量扫描结果表里**右键任意结果行**也能直接编辑备注
- 备注持久化到 `%APPDATA%\IPScaner-Py\memos.json`，重启自动回填

### windows 命令（19 项系统工具快捷入口）
控制面板 · 卸载程序 · 区域语言 · 日期和时间 · 网络连接 · 防火墙 · Internet 属性 · 计算机管理 · 组策略 · 注册表 · 服务 · 系统属性 · **环境变量** · 用户账户 · 设备管理 · 电源选项 · 设备和打印机 · 磁盘管理 · 我的命令（可自定义）

### IP 色块右键菜单（13 项）
复制 IP / 主机名 / MAC · 端口扫描 · 访问共享目录 · 浏览网页 · 调用 Ping / Tracert / Telnet / netstat / ARP · **备注信息** · **导入IP表格**

---

## 🆕 v1.27.0 新增

针对"**手上有张表，里面是不同网段的 IP，想直接 ping 一遍**"这个场景：

### 1. 主界面工具栏「导入IP」
- 主界面工具栏最右新增 **「导入IP」** 按钮
- 点一下 → 选一个 **.xlsx / .csv / .txt** → 自动打开批量扫描窗、灌入 IP、**直接开始 ping**
- 表格里混着不同网段也没关系（如 `192.168.5.65` / `10.20.30.40` / `172.16.8.9` 一起扫）
- 重复 IP 自动去重、结果按 IP 排序

### 2. IP 色块右键菜单也能导入
- 右键任意 IP 色块 → 菜单末尾新增 **「导入IP表格(&I)」**
- 与工具栏按钮走**同一条链路**；批量扫描窗已经开着就**直接复用**，不会重复弹窗

### 3. 修掉一个真机才会暴露的坑
- 「导入 IP 表格」弹出的是 Windows 的 **Vista 版文件对话框（DirectUI）**，
  在部分机器上**收不到任何合成输入**（自动化测试工具点不动它）。
  本项目改用 **UI Automation（COM）** 通道驱动，端到端验证全程真实跑通：
  CSV → 去重 3 个目标 → 自动开扫 → 结果表 3 行 → 完成提示
  「扫描完成，共 3 台主机，正常 0 台」。

---

## 🆕 v1.26.0 新增

针对"一次要扫几百个 IP、要标注用途、还要把结果导出来交差"的真实场景：

### 1. IP 备注 + Excel 导出
- 主界面**右键任意 IP 色块 → 备注信息**，即可给这个 IP 写用途说明
- 批量扫描的**结果表上右键**，同样能直接编辑/清空备注
- 点「导出结果」导出的不再是 CSV，而是**真正的 .xlsx**：
  - 「结果」工作表：**IP / 状态 / 主机名 / MAC / 备注** —— 一眼看出**哪些 IP 通、哪些不通、以及每个 IP 的备注**
  - 「统计」工作表：总数 / 在线 / 离线汇总
- 备注立即写盘（同步落盘 + 原子替换），不怕断电丢数据

### 2. 批量导入表格
- 批量扫描窗底部新增 **「导入表格」** 按钮
- 支持 **.xlsx / .csv / .txt** 三种格式
- 自动从表格里提取四段式 IP 地址，**允许不同网段混在同一个文件里**，一次全扫

### 3. 文档与开源
- 本 README
- 关键源码 + 可复现的构建链路上传到 GitHub

---

## 🚀 快速开始

### 方式一：直接使用（推荐）

1. 到 [**Releases**](https://github.com/azlove2021/IPScaner-Python/releases) 下载 `IPScaner_v1.27.0_portable_win64.exe`
2. 双击运行 —— 单文件绿色版，无需安装、无需 Python 环境

> 也可以直接点这个链接：
> <https://github.com/azlove2021/IPScaner-Python/releases/latest/download/IPScaner_v1.27.0_portable_win64.exe>
>
> 下载后可对照同目录的 `SHA256SUMS.txt` 校验：
> `cd4c58974e2c88b3db442bdd781f0e52bf3cf6874d4d460c294228eb525e0d79`
>
> （注：GitHub Releases 会把资产名里的非 ASCII 字符替换成 `.`，所以发布包用的是英文名。）

### 方式二：从源码运行

```bash
python src/gui.py
```

依赖：**仅标准库**（tkinter / socket / subprocess / csv / zipfile / ctypes…），不需要 pip install。

---

## 📖 使用说明

### 导入一个表格里的 IP（跨网段，v1.27.0）

1. 点主界面工具栏最右的 **「导入IP」**（或右键任意 IP 色块 → **导入IP表格(&I)**）
2. 选一个 `.xlsx` / `.csv` / `.txt` —— 里面的 IP **可以不在同一网段**
3. 程序会自动打开批量扫描窗、灌入 IP 并 **直接开始 ping**；
   重复 IP 自动去重、结果按 IP 排序，扫完弹出「扫描完成，共 N 台主机，正常 M 台」

> 批量扫描窗已经开着的话会**直接复用**，不会重复弹窗。

### 给某个 IP 加备注

1. 扫描完成后，在**主界面**找到目标 IP 色块
2. **右键 → 备注信息**，弹出备注编辑窗
3. 填写内容 → 点「保存」（写入磁盘后窗口自动关闭）
4. 下次打开程序，备注会自动回填到对应 IP

### 批量扫描 → 加备注 → 导出 Excel（推荐流程）

1. 菜单 **快捷工具 → IP批量扫描**
2. 准备要扫描的 IP，二选一：
   - 用顶部 **开始 / 结束 / 网段** 三个输入框 + **生成** 按钮批量生成
   - 或点底部 **导入表格**，选一个 `.xlsx` / `.csv` / `.txt`（**IP 可以不在同一网段**）
3. 点 **开始扫描**，等待结果表填满
4. 在结果行上 **右键 → 编辑备注**，给特殊 IP 写注释
5. 点 **导出结果** → 保存为 `.xlsx`
   → 表格里是 **IP / 状态 / 主机名 / MAC / 备注**，另附统计表

---

## 📸 界面截图

### 主界面

工具栏最右是 v1.27.0 新增的 **「导入IP」**：

![主界面](screenshots/01_main.png)

### 主界面「导入IP」→ 跨网段自动开扫（v1.27.0）

点「导入IP」选中表格后，自动灌 IP 并开扫，结果直接回填结果表：

![导入后自动开扫](screenshots/15_import_by_main_btn.png)

扫完弹出完成提示：

![扫描完成提示](screenshots/16_scan_done.png)

### 右键菜单 → 「导入IP表格」（v1.27.0）

右键任意 IP 色块，菜单**末尾**就是新入口：

![右键菜单导入项](screenshots/14_ctx_menu_import.png)

### 快捷工具菜单

![快捷工具菜单](screenshots/02_tools_menu.png)

### IP 批量扫描（结果表 + 备注 + 导入表格 + 导出结果）

![批量扫描](screenshots/04_batch_scan.png)

### 批量扫描底栏（导入表格 / 定时扫描 / 导出结果）

![批量扫描底栏](screenshots/05_import_btn.png)

### 导入表格 → 灌入 IP 列表 → 开始扫描

选一个 `.xlsx` / `.csv` / `.txt`，里面的 IP **可以不在同一网段**：

![导入表格打开对话框](screenshots/10_import_dlg.png)

导入后会提示去重排序后的目标数，IP 自动灌进左侧列表：

![导入成功提示](screenshots/12_import_prompt.png)

![导入结果 IP 列表](screenshots/11_import_result.png)

### 导出 Excel

![导出保存对话框](screenshots/06_export_dlg.png)

### IP 色块右键菜单 → 备注信息

![右键菜单](screenshots/07_ctx_menu.png)

![备注编辑](screenshots/08_memo_edit.png)

### 端口扫描

![端口扫描](screenshots/09_portscan.png)

---

## 🛠 从源码构建单文件 exe

```bash
# 需要 Python 3.10（用 3.11+ 打的包在部分 Win10 上会有兼容问题）
pip install pyinstaller

# ① 准备构建工作区（下面统称 build_green/）
#    绿色版原程序只发布 .pyc，本仓库不含原版字节码，所以工作区要自己拼：
#      build_green/
#      ├── main_opt.py                 ← 拷贝自 src/main_opt.py
#      ├── core/dialogs/gui/mainform/  ← 拷贝自 src/*.py（或用你自己提取的 .pyc）
#      ├── menu_def/popup/theme.py
#      └── assets/                     ← 拷贝自 src/assets/

# ② 由 ui_fix.py 生成运行期钩子（默认写到 ui_fix.py 同目录下的 build_green/）
cd uifix
python gen_hook.py
python gen_hook.py --check     # 应打印 FRESH hook=<sha> src=<sha>

# ③ 把 spec + 钩子放进 build_green/ 后打包
python -m PyInstaller --noconfirm green_onefile.spec
# 产物：build_green/dist/IPScaner.exe
```

> `gen_hook.py` 默认认为 `ui_fix.py` 与它同目录、钩子输出到 `<该目录>/build_green/`；
> 布局不同时用 `IPSCANER_FIXDIR` / `IPSCANER_BUILD` 两个环境变量覆盖即可。

构建链路是三层的，改代码时**必须按顺序**：

```
src/*.py（或绿色版提取的 *.pyc）   ← 复刻源码 / 权威字节码
        ↓
uifix/ui_fix.py                   ← 运行期修复层（所有改动都写这里）
        ↓  gen_hook.py
build_green/rthook_ipscaner_uifix.py   ← 生成的运行时钩子
        ↓  PyInstaller + green_onefile.spec
build_green/dist/IPScaner.exe     ← 单文件成品
```

> ⚠️ 改完 `ui_fix.py` 一定要**重新跑 `gen_hook.py`** 再打包，否则 exe 里还是老逻辑。
> `python gen_hook.py --check` 会打印 `FRESH hook=<sha> src=<sha>`，两个 sha 一致才算新鲜。

---

## 📁 目录结构

```
IPScaner-Python/
├── README.md
├── LICENSE / NOTICE.md     # MIT 许可 + 上游作品与合规说明
├── src/                    # 复刻源码（界面层 + 业务层）
│   ├── gui.py              #   入口：命令行参数 / DPI 感知 / 初始化
│   ├── mainform.py         #   主窗体：单 Canvas 手绘整个客户区
│   ├── popup.py            #   菜单弹出层（独立的 WS_POPUP Toplevel）
│   ├── dialogs.py          #   13 个子窗体
│   ├── theme.py            #   尺寸 / 颜色 / 字体的唯一真源
│   ├── menu_def.py         #   5 个顶级菜单 + 全部菜单项
│   ├── core.py             #   零 GUI 的业务逻辑（扫描 / MAC / 网卡枚举）
│   ├── build.py            #   一键打包
│   └── assets/             #   24 个图标资源
├── uifix/                  # 运行期修复层（本项目的关键代码）
│   ├── ui_fix.py           #   ★ 全部修复 + 新功能都在这里
│   ├── gen_hook.py         #   把 ui_fix.py 编译成 PyInstaller 运行时钩子
│   └── green_onefile.spec  #   单文件打包 spec
├── screenshots/            # 12 张界面截图（README 引用）
└── docs/                   # 逆向分析报告 / UI 审计 / 开发计划 / 验收报告
```

> `build_green/`（构建工作区）**不在仓库里** —— 它包含从绿色版原程序提取的业务模块
> 字节码，属于原版产物。首次构建时按上一节的说明自行拼装即可。

---

## 🔍 技术要点

- **为什么要有"运行期修复层"？**
  绿色版原程序只发布了 `.pyc` 字节码，没有源码。为了既能修 bug 又不破坏原字节码，
  本项目用 **PyInstaller runtime hook** 在导入期对模块做**猴补丁（monkey patch）**：
  所有修复与新功能都写在 `uifix/ui_fix.py`，打包时由 `gen_hook.py` 生成钩子注入。
  好处是**原 `.pyc` 一行不动**，修复可随时增删、可灰度回滚。

- **主界面为什么是"单 Canvas 手绘"？**
  原版 WinForms 的色块矩阵是 254 个独立控件的绝对定位。Tk 里用同等数量的 widget
  会有明显的绘制开销，于是复刻版把整个客户区画在一张 Canvas 上，色块矩阵按
  `主题常量 × DPI 缩放系数` 网格重绘，缩放时整幅重排。

- **菜单为什么要走独立 Toplevel？**
  Canvas 有裁剪边界，23 项的 `windows命令` 下拉会撞上状态栏导致最后几项被压住。
  `popup.py` 用 `Toplevel + overrideredirect + 自绘 Canvas` 实现真·弹出层，
  支持超出主窗口、空间不足自动上翻、子菜单悬停展开、点外部/Esc 关闭。
  （Windows 上原版的 `ToolStripDropDown` 本来就是独立的 `WS_POPUP` 窗口，
  所以这样做反而更贴近原版行为。）

- **扫描不卡界面 / 不闪退**
  扫描跑在工作线程，但 **Tk 不是线程安全的** —— 工作线程直接调 `after()` /
  `Treeview` 方法会触发 Tcl 分配器竞态，表现为**间歇性进程直接消失（无异常、无报错）**。
  修复层装了全局**线程编组垫片**：非主线程的 `after/after_idle/after_cancel`
  与 `Treeview` 读写统一排队，由主线程轮询派发。

- **零依赖读写 .xlsx**
  导出没有引入 openpyxl / xlsxwriter，而是用标准库 `zipfile` + 手写 OOXML
  生成 `.xlsx`（全部单元格走 `inlineStr`，不用维护 sharedStrings 表），
  导入则用 `zipfile` + `xml.etree.ElementTree` 把单元格文本摊平后正则捞 IP ——
  保证单文件 exe 体积不膨胀。

- **打包排除清单是"运行时才炸"的高危区**
  `--exclude-module` 裁多了不会在构建期报错，只会在用户点到那个功能时抛
  `ModuleNotFoundError`，而它往往又被 `except` 吞成一句提示框。
  本项目踩过两次：`decimal`（`fractions` 在函数体内延迟 import）和
  `xml`（读 xlsx 用）。**凡是函数体内的延迟 import，静态分析都扫不到** ——
  定稿排除清单前，必须拿实际用到的模块名去交叉比对一遍。

- **`--windowed` 打包后异常会被静默吞掉**
  冻结版没有控制台，`sys.stderr is None`，Tk 默认的 `report_callback_exception`
  连打印都做不到 —— 按钮回调里出任何错都表现为"点了没反应"。
  修复层接管了它，把异常写进 `%TEMP%\IPScaner_uifix.log`。

---

## 🐞 缺陷修复清单（复刻版相对原版）

| # | 问题 | 处理 |
|---|---|---|
| 1 | 菜单下拉被 Canvas 裁剪，`windows命令` 最后几项点不到 | 改独立弹出层 |
| 2 | 大量文字对比度不足、看不清 | 按主题重设前景/背景色 |
| 3 | 子窗体风格陈旧（十几年前的 WinForms 观感） | 全面现代化改版 |
| 4 | **IP 批量扫描扫描完成后闪退**，看不到结果 | 线程安全垫片（见上） |
| 5 | 端口扫描 1–65536 一个都扫不到 | 修扫描实现 |
| 6 | 「环境变量」等 windows 命令点击报错 | 修命令参数 |
| 7 | 以太网适配器名称显示不全 | 下拉宽度自适应 |
| 8 | 菜单项选中时的浅蓝方块错位 | 高亮块按缩放系数归位 |
| 9 | 子窗体"先弹出小窗、等一会儿才变大" | 首帧即终态 |
| 10 | 窗口不能放大/缩小 | 恢复 `WS_THICKFRAME` / `WS_MAXIMIZEBOX` |
| 11 | 备注弹窗的「保存/关闭」被压成 8px 废条 | 绝对设计坐标归位 |
| 12 | 部分菜单打开有几百毫秒延迟 | 弹层预热与缓存 |
| 13 | **打包版「导入表格」报 `No module named 'xml'`** —— 打包排除清单误排了 `xml` / `pyexpat`，而 `xml.etree.ElementTree` 是在**函数体内**延迟 import 的，静态分析扫不到；源码态有完整标准库所以根本测不出来 | 从排除清单恢复 |

---

## ⚠️ 已知限制

- 仅支持 **Windows**（依赖 Win32 API：`WMI`、`PrintWindow`、`WS_POPUP` 等）
- 打包用 **Python 3.10**，在部分老版本 Win10 上 3.11+ 打的包会有兼容问题
- 「修改本地 IP」「WiFi 密码」等功能需要**管理员权限**才能生效
- 端口扫描为 TCP connect 扫描，受目标防火墙策略影响
- 主窗体一次性扫描 254 个 IP 约需 15 秒（受 ping 超时影响，可调）

---

## 📄 免责声明

本项目为**学习与自用**目的对一款局域网工具做的界面/功能复刻与维护。

- 请**仅对你自己拥有或已获得授权扫描**的网络使用本工具
- 未经授权对他人网络进行端口扫描 / 主机探测可能**违反法律法规**
- 使用本工具产生的任何后果由使用者自行承担
- 本工具**不联网、不上报数据**，扫描结果与备注仅保存在本机

原版程序版权归其原作者所有。本仓库只包含复刻代码与运行期修复层，不含原版二进制。
详见 [NOTICE.md](NOTICE.md)。

---

## 📜 许可

复刻代码与运行期修复层以 **MIT** 协议开源，详见 [LICENSE](LICENSE)。
