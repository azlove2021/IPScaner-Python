# -*- coding: utf-8 -*-
"""由 ui_fix.py 生成 PyInstaller 运行期钩子 —— 保证「审计验证的代码」与
「实际打进 exe 的代码」是同一份，不会分叉。

钩子 = ui_fix.py 全文 + 驱动段（挂在 tk.Tk 上，等主窗体建好后启动常驻扫描）
       + 端口扫描并发修复（把 _scan_ports_thread 的 workers 调到 1200）。

用法：python gen_hook.py
      python gen_hook.py --check     # 只校验钩子是否比 ui_fix.py 陈旧

路径解析（默认零配置即可用）：
  · ui_fix.py 默认与**本脚本同目录**；可用环境变量 IPSCANER_FIXDIR 指定别的目录。
  · 产出的钩子默认写到 <ui_fix.py 所在目录>/build_green/；可用 IPSCANER_BUILD 覆盖。
"""
import hashlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = os.environ.get("IPSCANER_FIXDIR") or HERE
SRC = os.path.join(TMP, "ui_fix.py")
DST_DIR = os.environ.get("IPSCANER_BUILD") or os.path.join(TMP, "build_green")
DST = os.path.join(DST_DIR, "rthook_ipscaner_uifix.py")

DRIVER = '''

# ======================================================================
# PyInstaller 运行期钩子驱动段（由 gen_hook.py 从 ui_fix.py 生成，勿手改）
# ======================================================================
import os
import sys
import time
import tkinter as _tk


def _probe_imports():
    """诊断用：运行期钩子里到底哪些业务模块能导入。

    踩过：冻结版里导入期 `import core` 会失败（PyInstaller 的 PYZ 导入器在
    运行期钩子执行完才挂好），导致 SCANFIX/WIFIFIX 都是 0 —— 修复根本没生效，
    而且**不报错**。所以这里必须把失败原因写进日志，不能静默。
    """
    out = []
    for m in ("core", "dialogs", "gui", "theme", "mainform"):
        try:
            __import__(m)
            out.append(m + "=ok")
        except Exception as e:
            out.append("%s=%r" % (m, e))
    _log("导入自检：" + "  ".join(out))


def _scanfix_scan_ports():
    """端口扫描：把内置线程池的并发数从 200 提到 1200。

    ⚠️ 2026-10-08 修正 —— 这个函数**原来做的是另一件事，而且是错的**：
      旧版把 scan_ports_async 整个路由到 scan_ports_fast，并原样把调用方的
      concurrency=1000 映射成 scan_ports_fast 的 batch=1000。而 Windows 的
      select.select 最多监视 512 个 FD —— 实测：
          n=512  select OK
          n=513  ValueError('too many file descriptors in select()')
      该异常被 scan_ports_fast 每批的 except 吞掉 → 每一批都「扫完但一条不判」，
      于是**进度条走到 100%、状态栏写「扫描完毕」，结果列表框 0 条**。
      实测 192.168.5.1 1-65535：
          batch=400 → 发现 9 个       batch=512 → 发现 9 个
          batch=600 → 发现 0 个       batch=1000 → 发现 0 个
      用户的「为什么扫 1-65536 一个都没打开」就是这条死路。
      所以「路由到 fast」的做法整个废弃，不再使用 scan_ports_fast。

    现在只做一件干净的事：把 _scan_ports_thread 的 workers 调大。
      · 为什么需要：scan_ports_async 的高端口分支要 asyncio，而 asyncio 被
        green_onefile.spec 的 EXCLUDES 排掉了 → 静默退化到
        _scan_ports_thread(workers=200)。64511 个端口 × 200ms 超时 ÷ 200 并发
        ≈ 69.8s，慢到用户以为卡死。
      · 改并发数安全吗：192.168.5.1 高端口(1025-65535) 实测 5 档 × 2 轮，
        结果**完全一致**（都是 7777/8085/8086/14554/16363/23002/58121）：
            200 → 69.5s   500 → 28.5s   800 → 18.6s
            1200 → 13.6s  2000 → 13.6s
        提高并发不引入漏报；1200 已到平台期，再高只增加线程开销。
      · 影响面：_scan_ports_thread 在 core.pyc 里**只有 scan_ports_async 一个
        调用方**（scan_ports / scan_ports_many 各自内联线程池，不经过它），
        所以这次改动只影响单 IP 大批量扫描这一条路径。
      · 小批量不动：端口数 < 512 时保持原参数，避免影响多主机并发扫描。
      · 可用 IPSCANER_SCAN_WORKERS 覆盖；任何异常都返回 0 并保留原实现。
    """
    try:
        import core
    except Exception as e:
        _log("scanfix 跳过：import core 失败 %r" % (e,))
        return 0
    orig = getattr(core, "_scan_ports_thread", None)
    _log("scanfix 探测：_scan_ports_thread=%s 已标记=%s core=%s"
         % (orig is not None,
            bool(getattr(orig, "_ipscaner_workers", False)), core.__name__))
    if orig is None or getattr(orig, "_ipscaner_workers", False):
        return 0
    # 旧版留下的错误路由（scan_ports_async 被换成 scan_ports_fast 包装）如果还在，
    # 先拆掉 —— 它会让整条端口扫描**永远 0 结果**。
    try:
        cur = getattr(core, "scan_ports_async", None)
        if getattr(cur, "_ipscaner_patched", False):
            _log("scanfix：检测到旧版 scan_ports_fast 路由仍生效，本版已不再需要"
                 "（该路由在 batch>512 时必然 0 结果）")
    except Exception:
        pass
    import os as _os
    try:
        want = int(_os.environ.get("IPSCANER_SCAN_WORKERS", "1200"))
    except Exception:
        want = 1200
    want = max(200, min(want, 4000))

    def _scan_ports_thread(ip, ports, timeout_ms, workers, cancel, on_port,
                           tick):
        try:
            n = int(workers)
        except Exception:
            n = 200
        try:
            if len(ports) >= 512:          # 只给大批量扫描提速
                n = max(n, want)
        except Exception:
            n = max(n, want)
        return orig(ip, ports, timeout_ms, n, cancel, on_port, tick)

    _scan_ports_thread._ipscaner_workers = True
    _scan_ports_thread.__doc__ = getattr(orig, "__doc__", None)
    core._scan_ports_thread = _scan_ports_thread
    _log("scanfix：端口扫描线程池并发已提到 %d（大批量路径）" % want)
    return 1


def _wifi_async_fix():
    """WiFi 密码窗口：把 46 次串行 netsh 调用从主线程挪走。

    实测（本机 46 个配置文件）：
      · dialogs.f_wifi → top.after(80, load) → dialogs._wifi_rows()
        在**主线程**串行跑 netsh，每次约 0.34 秒 → 合计 15.6 秒；
      · 期间整个程序无响应，而状态栏还写着「程序已就绪」，用户以为死机。
      · 并行 8 线程同结果只需 3.7 秒，但仍然是阻塞的。

    这里做两件事：
      1) _wifi_rows 并行(8) + 30 秒缓存 —— 兜底路径也快 4.2 倍；
      2) 拦下 f_wifi 内部那次 after(80, load)，改成**后台线程取数、
         queue 回主线程填表**（Tk 只能在主线程碰，绝不在子线程调 Tk）
         —— 完全不卡。定位不到 Treeview/Label 时原样回退同步 load。

    两项都带幂等标记，任何异常都返回 0/回退，保证不比修复前更差。
    """
    try:
        import tkinter as _tk2
        import dialogs
    except Exception as e:
        _log("wifi 修复跳过：import 失败 %r" % (e,))
        return 0
    try:
        import core
    except Exception:
        core = None
    _log("wifi 探测：dialogs=%s core=%s f_wifi 已包装=%s _wifi_rows 已并行=%s"
         % (dialogs.__name__, core is not None,
            bool(getattr(getattr(dialogs, "f_wifi", None), "_ipscaner_async", False)),
            bool(getattr(getattr(dialogs, "_wifi_rows", None), "_ipscaner_par", False))))

    n_fixed = 0

    # ---- 1) _wifi_rows 并行 + 短缓存 ----------------------------------
    orig_rows = getattr(dialogs, "_wifi_rows", None)
    if core is not None and orig_rows is not None \\
            and not getattr(orig_rows, "_ipscaner_par", False):
        try:
            import time as _t2
            from concurrent.futures import ThreadPoolExecutor
            _cache = {"t": 0.0, "rows": None}

            def _one(ssid):
                text = core.run_cmd(["netsh", "wlan", "show", "profile",
                                     "name=%s" % ssid, "key=clear"])
                return (ssid,
                        dialogs._wifi_grab(text, dialogs._WIFI_KEYS["password"]),
                        dialogs._wifi_grab(text, dialogs._WIFI_KEYS["auth"]),
                        dialogs._wifi_grab(text, dialogs._WIFI_KEYS["cipher"]))

            def _par_rows():
                now = _t2.time()
                if _cache["rows"] is not None and now - _cache["t"] < 30:
                    return _cache["rows"]
                profs = list(core.wifi_profiles())
                if not profs:
                    _cache["rows"], _cache["t"] = [], now
                    return []
                try:
                    with ThreadPoolExecutor(max_workers=min(8, len(profs))) as ex:
                        rows = list(ex.map(_one, profs))
                except Exception:
                    rows = orig_rows()          # 并行失败 → 回退串行
                _cache["rows"], _cache["t"] = rows, now
                return rows

            _par_rows._ipscaner_par = True
            dialogs._wifi_rows = _par_rows
            n_fixed += 1
        except Exception:
            pass

    # ---- 2) f_wifi 异步加载 -------------------------------------------
    orig_f = getattr(dialogs, "f_wifi", None)
    if orig_f is None or getattr(orig_f, "_ipscaner_async", False):
        return n_fixed

    def f_wifi(main):
        grabbed = {}
        _after_save = _tk2.Misc.after

        def spy(self, ms, func=None, *a):
            # 只截 f_wifi 里那个 after(80, load)，其它一律透传
            qn = str(getattr(func, "__qualname__", "")) if func else ""
            if ms == 80 and "load" in qn and "load" not in grabbed:
                grabbed["load"] = func
                return _after_save(self, ms, lambda: None)   # 占位，取消原调度
            return _after_save(self, ms, func, *a)

        _tk2.Misc.after = spy
        try:
            top = orig_f(main)
        finally:
            _tk2.Misc.after = _after_save

        load = grabbed.get("load")
        if load is None:
            return top

        tv = None
        status = None
        try:
            for c in top.winfo_children():
                if tv is None and c.winfo_class() == "Treeview":
                    tv = c
                elif status is None and c.winfo_class() in ("Label", "TLabel"):
                    if "程序已就绪" in str(c.cget("text")):
                        status = c
        except Exception:
            tv = None
        if tv is None or status is None:
            try:
                top.after(80, load)             # 定位失败 → 行为与原来一致
            except Exception:
                pass
            return top

        import queue
        import threading as _th2
        q = queue.Queue()

        def worker():
            rows = None
            try:
                rows = dialogs._wifi_rows()
            except Exception:
                rows = None
            q.put(rows)                          # 只放队列，绝不碰 Tk

        def done(rows):
            try:
                if rows is None:
                    load()                       # 取数失败 → 回退原实现
                    return
                tv.delete(*tv.get_children())
                for r in rows:
                    tv.insert("", "end", values=r)
                status.configure(text="程序已就绪，共 %d 个配置文件" % len(rows))
            except Exception:
                try:
                    load()
                except Exception:
                    pass

        def poll():
            try:
                rows = q.get_nowait()
            except queue.Empty:
                try:
                    top.after(120, poll)
                except Exception:
                    pass
                return
            done(rows)

        try:
            status.configure(text="正在读取 WiFi 配置…")
        except Exception:
            pass
        _th2.Thread(target=worker, name="ipscaner-wifi", daemon=True).start()
        try:
            top.after(120, poll)                 # 主线程轮询，Tk 调用全在主线程
        except Exception:
            pass
        return top

    f_wifi._ipscaner_async = True
    f_wifi.__doc__ = getattr(orig_f, "__doc__", None)
    dialogs.f_wifi = f_wifi
    n_fixed += 1
    return n_fixed


_LOG_F = None

def _log(msg):
    """日志写到 %TEMP%，不污染 exe 所在目录（用户拿到的就是一个干净单文件）。"""
    global _LOG_F
    try:
        if _LOG_F is None:
            import tempfile
            _LOG_F = open(os.path.join(tempfile.gettempdir(),
                                       "IPScaner_uifix.log"), "a",
                          encoding="utf-8")
            _LOG_F.write("\\n==== %s ====\\n"
                         % time.strftime("%Y-%m-%d %H:%M:%S"))
        _LOG_F.write(str(msg) + "\\n")
        _LOG_F.flush()
    except Exception:
        pass


def _theme_scale():
    try:
        import theme
        return float(theme.SCALE)
    except Exception:
        return 1.0


def _uifix_start(root):
    """字号/字体统一放到主窗体建好之后（theme.SCALE 由 MainForm.__init__ 里的
    set_scale_from 设定，早于它读会拿到 1.0）。"""
    S = _theme_scale()
    try:
        n = remap_main(root, S, log=_log)
        _log("remap_main 命中 %d 个命名字体 (S=%s)" % (n, S))
    except Exception as e:
        _log("remap_main 失败 %r" % (e,))
    # WiFi 行为修复：这里再兜一次（dialogs 必然已导入），幂等
    try:
        nw = _wifi_async_fix()
        if nw:
            _log("wifi 异步加载修复已生效 (%d 项)" % nw)
    except Exception as e:
        _log("wifi 修复失败 %r" % (e,))
    # 端口扫描并发修复也必须在这里兜一次 —— 冻结版里导入期 import core 会失败，
    # 只在导入期应用等于没应用，而且不会报错（踩过）。
    try:
        ns = _scanfix_scan_ports()
        _log("端口扫描并发修复（延迟重试）= %s" % ns)
    except Exception as e:
        _log("端口扫描并发修复失败 %r" % (e,))


_orig_tk_init = _tk.Tk.__init__


def _tk_init(self, *a, **k):
    _orig_tk_init(self, *a, **k)
    # install() 要**立刻**挂上（它只做两件事：给 Toplevel 打注册表 + 排扫描），
    # 晚挂就会漏掉在它之前建好的窗体。真正需要等主窗体的是 remap_main。
    try:
        install(self, log=_log, get_scale=_theme_scale)
    except Exception as e:
        _log("install 失败 %r" % (e,))
    try:
        self.after(900, lambda: _uifix_start(self))
    except Exception:
        pass


if not getattr(_tk.Tk.__init__, "_ipscaner_uifix", False):
    # 守卫要检查和写入同一处。踩过：原来查的是 _tk.Tk._ipscaner_uifix（类属性）
    # 而写的是 _tk_init._ipscaner_uifix（函数属性）→ 守卫永远为假，
    # 钩子模块被重复执行时会把 __init__ 包两层，装出两条扫描链。
    _tk.Tk.__init__ = _tk_init
    _tk_init._ipscaner_uifix = True

try:
    _probe_imports()
except Exception:
    pass

try:
    _SCANFIX = _scanfix_scan_ports()
except Exception:
    _SCANFIX = 0

try:
    _WIFIFIX = _wifi_async_fix()
except Exception:
    _WIFIFIX = 0

try:
    _log("驱动自检（导入期）：SCANFIX=%s WIFIFIX=%s；0 = 此刻不可用**或已应用**"
         "（钩子模块被重复执行时会看到 0），非 0 表示本次刚打上" % (_SCANFIX, _WIFIFIX))
except Exception:
    pass

try:
    _mod = sys.modules[__name__]
    _mod.IPSCANER_SCANFIX = _SCANFIX
    _mod.IPSCANER_WIFIFIX = _WIFIFIX
    _mod.IPSCANER_DRIVER = 1
except Exception:
    # 钩子若在未登记进 sys.modules 的命名空间里执行，这里会 KeyError。
    # 不能让它冒泡 —— 运行期钩子抛异常等于启动失败。
    pass
'''


def main():
    if not os.path.isdir(DST_DIR):
        os.makedirs(DST_DIR)
    src = io.open(SRC, encoding="utf-8").read()
    src = src.replace("\r\n", "\n")
    # 源码指纹：钩子是「审计验证过的代码」与「实际打进 exe 的代码」之间的
    # 唯一桥梁。只靠文件名无法发现「ui_fix.py 改了、钩子没重生成」这类
    # 静默分叉（踩过：absolute=False 的修复没进钩子，联动验证 0/11 全挂）。
    # 指纹必须同时覆盖**驱动段**，否则改了 DRIVER 不重生成同样查不出来。
    sha = hashlib.sha1((src + DRIVER).encode("utf-8")).hexdigest()
    head = (
        "# -*- coding: utf-8 -*-\n"
        "# AUTO-GENERATED by gen_hook.py from ui_fix.py —— 请改 ui_fix.py 再重新生成。\n"
        "# 作为 PyInstaller runtime_hooks 在入口脚本之前执行。\n"
        "# SOURCE-SHA1: %s\n" % sha
    )
    io.open(DST, "w", encoding="utf-8", newline="\n").write(head + src + DRIVER)
    print("生成 %s  (%d 字节)  sha1=%s" % (DST, os.path.getsize(DST), sha[:12]))
    return sha


def source_sha1():
    src = io.open(SRC, encoding="utf-8").read().replace("\r\n", "\n")
    return hashlib.sha1((src + DRIVER).encode("utf-8")).hexdigest()


def hook_sha1():
    """读钩子里记录的源码指纹；缺失返回 None（视为陈旧）。"""
    try:
        for ln in io.open(DST, encoding="utf-8"):
            if ln.startswith("# SOURCE-SHA1:"):
                return ln.split(":", 1)[1].strip()
            if ln.startswith("import "):        # 头部结束
                break
    except Exception:  # noqa: BLE001
        pass
    return None


def is_stale():
    return hook_sha1() != source_sha1()


if __name__ == "__main__":
    if "--check" in sys.argv:
        print("STALE" if is_stale() else "FRESH",
              "hook=%s src=%s" % (str(hook_sha1())[:12], source_sha1()[:12]))
        raise SystemExit(1 if is_stale() else 0)
    main()
