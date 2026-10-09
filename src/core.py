# -*- coding: utf-8 -*-
"""
IPScaner Python 复刻 —— 核心逻辑层（零 GUI 依赖，可单独测试）

设计原则（对齐原版 IPScaner V1.25 的架构）：
  1. 不自己实现协议 —— 调 arp / ping / netstat / netsh / tasklist，解析文本输出
  2. 能白嫖标准库就白嫖 —— ipaddress / socket / concurrent.futures / re / csv
  3. 零第三方依赖 —— 只用 CPython 自带模块
"""
from __future__ import annotations

import csv
import ipaddress
import os
import re
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

IS_WIN = sys.platform.startswith("win")
_NO_WINDOW = 0x08000000 if IS_WIN else 0  # CREATE_NO_WINDOW


# --------------------------------------------------------------------------
# 命令执行（含中文 Windows 的编码回退 —— 这是原版 1.20 踩过的坑）
# --------------------------------------------------------------------------
_ENCODINGS = ("gbk", "utf-8", "cp936", "cp1252")


def run_cmd(args, timeout=15):
    """执行命令并返回 stdout 文本。按 gbk → utf-8 → cp936 → cp1252 依次尝试解码。

    原版 FormWiFiViewer 里那段 `ReadProfiles(gbk) ?? ReadProfiles(utf8) ?? ReadProfiles(default)`
    就是这个逻辑的 C# 版；这里是它的 Python 等价物。
    """
    try:
        p = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout,
            creationflags=_NO_WINDOW,
            shell=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    raw = p.stdout or b""
    for enc in _ENCODINGS:
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        text = raw.decode("utf-8", "replace")
    return text


# --------------------------------------------------------------------------
# 数据模型
# --------------------------------------------------------------------------
@dataclass
class HostResult:
    ip: str
    alive: bool = False
    rtt_ms: int | None = None
    hostname: str = ""
    mac: str = ""
    memo: str = ""
    checked_at: str = ""

    @property
    def status(self):
        return "正常" if self.alive else "不通"


@dataclass
class Adapter:
    name: str
    ip: str = ""
    mask: str = ""
    mac: str = ""
    gateway: str = ""
    dns: list = field(default_factory=list)
    dhcp: bool = False

    @property
    def prefix(self):
        try:
            return ipaddress.IPv4Network(f"0.0.0.0/{self.mask}").prefixlen
        except Exception:
            return 24


@dataclass
class PortRow:
    proto: str
    local: str
    port: str
    pid: str
    name: str = ""
    path: str = ""


# --------------------------------------------------------------------------
# 本机网卡（解析 ipconfig /all —— 纯标准库，不依赖 WMI）
# --------------------------------------------------------------------------
def get_adapters():
    text = run_cmd(["ipconfig", "/all"])
    adapters = []
    cur = None
    for line in text.splitlines():
        if not line.strip():
            continue
        # 适配器头：无缩进、以冒号结尾
        if not line.startswith(" ") and line.rstrip().endswith(":"):
            if cur and cur.ip:
                adapters.append(cur)
            cur = Adapter(name=line.rstrip().rstrip(":"))
            continue
        if cur is None or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip().lower(), val.strip()
        if "ipv4" in key and val and not val.startswith("169.254") and not val.startswith("127."):
            # 支持 "IPv4 地址 . . . . . . . . . . . . : 192.168.1.5(首选)"
            cur.ip = val.split("(")[0].strip()
        elif "子网掩码" in key or "subnet mask" in key:
            cur.mask = val
        elif "物理地址" in key or "physical address" in key:
            cur.mac = val.replace("-", ":").upper()
        elif "默认网关" in key or "default gateway" in key:
            if val and not cur.gateway:
                cur.gateway = val
        elif "dhcp 已启用" in key or "dhcp enabled" in key:
            cur.dhcp = val.lower().startswith(("是", "yes"))
        elif "dns 服务器" in key or "dns servers" in key:
            m = re.match(r"^(\d+\.\d+\.\d+\.\d+)", val)
            if m:
                cur.dns.append(m.group(1))
    if cur and cur.ip:
        adapters.append(cur)
    # IPv6 段落里的 DNS 行会污染，去重
    for a in adapters:
        a.dns = list(dict.fromkeys(a.dns))
    return adapters


def get_local_ip():
    """取一个能出网的本地 IPv4（不发实际数据包）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# --------------------------------------------------------------------------
# MAC 表（arp -a —— 与原生版同一招）
# --------------------------------------------------------------------------
_MAC_RE = re.compile(r"([0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2}")


def arp_table():
    """返回 {ip: mac}。arp -a 输出格式随系统语言/版本变化，所以用宽松正则扫。"""
    table = {}
    for line in run_cmd(["arp", "-a"]).splitlines():
        m = _MAC_RE.search(line)
        if not m:
            continue
        ips = re.findall(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
        if ips:
            table[ips[0]] = m.group(0).upper().replace("-", ":")
    return table


# --------------------------------------------------------------------------
# 单个主机的探测
# --------------------------------------------------------------------------
def ping_once(ip, timeout_ms=800):
    """调系统 ping。返回 (是否通, 往返毫秒)。"""
    if not IS_WIN:
        args = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), ip]
    else:
        args = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    text = run_cmd(args, timeout=(timeout_ms / 1000.0) + 3)
    if not text:
        return False, None
    # TTL= 是唯一可靠的"收到回复"标志；注意别写成字符类 [TTL=]
    alive = re.search(r"TTL\s*=", text, re.IGNORECASE) is not None
    if not alive:
        return False, None
    m = re.search(r"(?:时间|time)\s*[=<]\s*(\d+)\s*ms", text, re.IGNORECASE)
    return True, (int(m.group(1)) if m else 0)


def tcp_probe(ip, port, timeout=0.6):
    """TCP 兜底探测 —— 对应原版的 PortInsteadPing。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((ip, port)) == 0


def resolve_hostname(ip):
    try:
        name = socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        return ""
    # 有些路由器/DNS 对未知主机原样回显查询的 IP，这种情况视为"没查到"
    if not name or name == ip:
        return ""
    for suffix in ("domain", ".local"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def probe_host(ip, timeout_ms=800, fallback_ports=(), want_name=False, want_mac=False, arp=None):
    alive, rtt = ping_once(ip, timeout_ms)
    if not alive and fallback_ports:
        alive = any(tcp_probe(ip, int(p), timeout_ms / 1000.0) for p in fallback_ports)
        rtt = None
    r = HostResult(ip=ip, alive=alive, rtt_ms=rtt)
    if alive and want_name:
        r.hostname = resolve_hostname(ip)
    if alive and want_mac and arp is not None:
        r.mac = arp.get(ip, "")
    import datetime
    r.checked_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return r


# --------------------------------------------------------------------------
# 批量扫描（对应原版的 Ping_PingCompleted + 并发节流 + 取消）
# --------------------------------------------------------------------------
def expand_segment(prefix, start=1, end=254, skip_network=True):
    """'192.168.1' -> ['192.168.1.1', ..., '192.168.1.254']

    用 stdlib 的 ipaddress 代替原版手写的 IpToUInt/UIntToIp 位运算。
    """
    base = prefix.rstrip(".")
    nets = []
    for i in range(start, end + 1):
        if skip_network and i in (0, 255):
            continue
        nets.append(f"{base}.{i}")
    return nets


def ips_from_cidr(cidr, usable_only=True):
    net = ipaddress.ip_network(cidr, strict=False)
    hosts = list(net.hosts()) if usable_only else list(net)
    return [str(h) for h in hosts]


def scan(ips, on_result=None, timeout_ms=800, workers=64, fallback_ports=(),
         want_name=False, want_mac=False, cancel=None, progress=None):
    """并发扫描。on_result(HostResult) 在每台主机完成后即回调（UI 侧负责 marshal）。"""
    arp = arp_table() if want_mac else None
    done = 0
    total = len(ips)
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(probe_host, ip, timeout_ms, fallback_ports,
                        want_name, want_mac, arp): ip
            for ip in ips
        }
        for fut in as_completed(futs):
            if cancel is not None and cancel.is_set():
                for f in futs:
                    f.cancel()
                break
            try:
                r = fut.result()
            except Exception:
                r = HostResult(ip=futs[fut])
            results.append(r)
            done += 1
            if on_result:
                on_result(r)
            if progress:
                progress(done, total)
    results.sort(key=lambda r: ipaddress.IPv4Address(r.ip))
    return results


# --------------------------------------------------------------------------
# 端口占用（netstat -ano + tasklist —— 与原生版同一招）
# --------------------------------------------------------------------------
_NETSTAT_RE = re.compile(
    r"^\s*(TCP|UDP)\s+(\S+):(\d+)\s+\S+\s+(\S+)\s+(\d+)\s*$", re.IGNORECASE
)


def netstat_ports():
    rows = []
    for line in run_cmd(["netstat", "-ano"]).splitlines():
        m = _NETSTAT_RE.match(line)
        if not m:
            continue
        proto, local, port, state, pid = m.groups()
        rows.append(PortRow(proto.upper(), local, port, pid, state))
    return rows


def process_names(pids):
    """批量查 PID → 进程名。tasklist 一次全量比逐个查快得多。"""
    mapping = {}
    text = run_cmd(["tasklist", "/FO", "CSV", "/NH"])
    reader = csv.reader(text.splitlines())
    for row in reader:
        if len(row) >= 2:
            try:
                mapping[row[1].strip()] = row[0].strip()
            except IndexError:
                continue
    return {p: mapping.get(p, "") for p in pids}


def kill_pid(pid):
    return run_cmd(["taskkill", "/F", "/PID", str(pid)])


# --------------------------------------------------------------------------
# WiFi 密码（netsh —— 与原生版同一招）
# --------------------------------------------------------------------------
def wifi_profiles():
    text = run_cmd(["netsh", "wlan", "show", "profiles"])
    # 中英文双模板，修掉原版"硬编码中文正则"的坑
    pat = re.compile(r"(?:所有用户配置文件|All User Profile)\s*:\s*(.+)")
    return [m.group(1).strip() for m in pat.finditer(text)]


def wifi_password(ssid):
    text = run_cmd(["netsh", "wlan", "show", "profile", f"name={ssid}", "key=clear"])
    pat = re.compile(r"(?:关键内容|Key Content)\s*:\s*(.+)")
    m = pat.search(text)
    return m.group(1).strip() if m else ""


def wifi_all():
    return [(s, wifi_password(s)) for s in wifi_profiles()]


# --------------------------------------------------------------------------
# 子网计算器（ipaddress 一句话搞定原版 NetworkCalculator 的 208 行）
# --------------------------------------------------------------------------
def subnet_calc(ip, prefixlen):
    net = ipaddress.ip_network(f"{ip}/{prefixlen}", strict=False)
    hosts = list(net.hosts()) if net.num_addresses > 2 else []
    return {
        "network": str(net.network_address),
        "broadcast": str(net.broadcast_address),
        "netmask": str(net.netmask),
        "wildcard": str(net.hostmask),
        "prefix": prefixlen,
        "total": net.num_addresses,
        "usable": max(0, net.num_addresses - 2),
        "first": str(hosts[0]) if hosts else "-",
        "last": str(hosts[-1]) if hosts else "-",
    }


# --------------------------------------------------------------------------
# 导出（CSV，与原版一致 —— 0 行 OOXML）
# --------------------------------------------------------------------------
def export_csv(path, rows, header):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


def hosts_to_csv(path, results):
    return export_csv(
        path,
        [[r.ip, r.hostname, r.mac, r.status, r.memo, r.checked_at] for r in results],
        ["IP", "名称", "MAC", "状态", "备注", "时间"],
    )


if __name__ == "__main__":
    print("本机 IPv4 :", get_local_ip())
    print("网卡数    :", len(get_adapters()))
    for a in get_adapters()[:3]:
        print(f"  - {a.name}  {a.ip}/{a.prefix}  {a.mac}  gw={a.gateway}")
    print("ARP 表条数:", len(arp_table()))
    print("端口条数  :", len(netstat_ports()))
    print("子网计算  :", subnet_calc("192.168.1.100", 24))
