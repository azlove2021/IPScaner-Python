# IPScaner 复刻版 —— 源码说明

> 项目结构（2026-09-28 整理后）：
> ```
> Project_022_IPScaner_Python复刻/
> ├── IPScaner.exe      ← 成品，双击即用（8.72 MB，PyInstaller 单文件）
> ├── src/              ← 源码（本目录）
> └── _archive_20260928/ ← 探针/比对/报告/历史存档（平时不用管）
> ```

## 目录里都有什么

| 文件 | 作用 |
|---|---|
| `gui.py` | 入口：命令行参数、DPI 感知、开机初始化 |
| `main.py` / `main_opt.py` | 打包入口（基准版 / 裁剪版） |
| `mainform.py` | 主窗体：单 Canvas 手绘整个客户区 |
| `popup.py` | **菜单弹出层**：真·Toplevel 弹出窗口（见下） |
| `theme.py` | 尺寸 / 颜色 / 字体的唯一真源 |
| `menu_def.py` | 5 个顶级菜单 + 全部菜单项 |
| `dialogs.py` | 13 个子窗体 |
| `core.py` | 零 GUI 的业务逻辑（扫描 / MAC / 网卡枚举） |
| `assets/` | 24 个图标资源 |
| `build.py` | 一键打包 |
| `slim.spec` | 极限裁剪用的 PyInstaller spec |
| `run_exe.ps1` | 启动成品 exe（用 WMI 创建进程，GUI 才留得住） |

## 怎么跑

```bash
# 从源码跑（改代码后立刻看效果）
<venv>\Scripts\python.exe src\gui.py

# 跑成品
src\run_exe.ps1
```

想复现「原版截图那一帧」做像素比对时，必须钉死 4 个状态量（见 `theme.SHOT_*`）：
`--scale=1 --ip=172.19.80.1 --adapter="vEthernet (WSL)"`
`--active-ips="172.19.80.1; 192.168.56.1; 192.168.5.65" --tip-index=1 --freeze`
漏任何一个，状态栏/标题文字就对不上，差异率会虚高。

## 怎么打包

```bash
<venv>\Scripts\python.exe src\build.py            # 出 IPScaner.exe 到项目根目录
<venv>\Scripts\python.exe src\build.py all        # 三档全建（做体积对比用）
<venv>\Scripts\python.exe src\build.py where      # 列出 exe 在哪
```

⚠️ 三条约束（都踩过）：

1. **构建工作区放系统临时目录**（脚本已默认）。放项目目录会被百度网盘的
   `.baiduyun.uploading.cfg` 瞬时文件干扰，跟 PyInstaller 的清理竞争 → 构建中断。
2. **`build.py` 必须能拿到全部 `.py` 和 `assets/`**。它用 `glob` 而不是写死清单
   —— 早期写死清单，界面层拆成多模块后直接 ImportError。
3. **写 exe 前目标路径必须不存在**。PyInstaller 覆盖已存在的 exe 时会先删它，
   而沙箱环境的 safe-delete 垫片会拦这个删除（报
   `SAFE_DELETE_BULK_CONFIRM_REQUIRED`），导致构建卡在最后一步失败。
   `build.py` 里的 `clear_target()` 就是为此存在的：先把旧 exe 挪进归档。

## 菜单为什么走独立弹出窗口

原版 WinForms 的下拉层是独立的 `WS_POPUP` 窗口，能超出主窗口、能自动上翻。
早期复刻把它画在主 Canvas 上，而 Canvas 有裁剪边界 ——
`windows命令(&C)` 那条 23 项的下拉（高 445px、底边 y=469）正好撞上
y=470 起的状态栏，最后几项被压住，表现就是「菜单点了看不到文字」。

`popup.py` 的 `MenuPopup` 用 `Toplevel + overrideredirect + 自绘 Canvas` 解决：
超出主窗口边界、空间不足自动上翻/左翻、子菜单悬停展开、点外部或 Esc 关闭、
圆角 + 细边框 + 柔和阴影 + 悬停高亮。

菜单栏顶级项仍画在主 Canvas 上（那边差异率 0.00%，没动）。

## 容易踩的坑

- **`.ps1` 脚本必须纯 ASCII**。PowerShell 5.1 把无 BOM 的 UTF-8 当 ANSI 读，
  中文注释会让脚本**静默失效**（不报错、不写日志、什么都不发生）。
  自检：`LC_ALL=C grep -c '[^ -~]' src/*.ps1` 应为 `0`。
- **别在顶层 `import multiprocessing`**，它会通过 `ssl` 拖进
  `libcrypto-3.dll` + `libssl-3.dll` 约 7.4 MB。`gui.py` 里是延迟导入且容错。
- **`--exclude-module` 裁多了是运行时才崩**，构建期不报错。每次裁剪后要实测功能，
  不能只看能不能启动（曾经把 `concurrent` 裁掉，一扫描就崩）。

## 验收状态（2026-09-28）

| 项 | 结果 |
|---|---|
| 主界面像素复刻（1×，835×486，阈值 24） | 平均差 **0.027/255**，差异>24 **0.03%** |
| 菜单栏 / 色块矩阵 / 状态栏 / 分组框标题 | 全部 **0.00%** |
| 子窗体冒烟 | **13/13** |
| 打包版 vs 源码版抓图 MD5 | **完全相同** |
| 菜单弹层（打包版实测） | 弹出 154×460 ✓ 子菜单 130×43 ✓ Esc 关闭 ✓ |

剩余 0.03% 集中在工具栏按钮外框四角：原版那圈是 GDI+ 画的**圆角矩形**
（半径≈3，四角各 2–3 个渐变像素），Tk 画布只能画直角。已判定收口。
