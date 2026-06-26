# system_monitor.py
# Background PC performance monitor
# Logs CPU, GPU, RAM, Disk, Network every 2 seconds
# Shared via JSON file — read by vision_monitor

import threading
import time
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# ============== CONFIG ==============
SCRIPT_DIR = Path(__file__).parent
LOG_FILE = SCRIPT_DIR / "system_log.json"
SAMPLE_INTERVAL = 2  # seconds between samples
MAX_SAMPLES = 900    # 30 min @ 2s = 900 samples

# ============== DEPENDENCIES ==============
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import wmi
    WMI_AVAILABLE = True
    _wmi = wmi.WMI()
except ImportError:
    WMI_AVAILABLE = False
    _wmi = None

try:
    import pynvml
    pynvml.nvmlInit()
    NVML_AVAILABLE = True
except Exception:
    NVML_AVAILABLE = False

# ============== STATE ==============
_samples = []
_lock = threading.Lock()
_running = False
_last_save = 0
SAVE_INTERVAL = 5  # write to file every N seconds

# ============== HARDWARE POLLING ==============
def _get_cpu():
    if not PSUTIL_AVAILABLE:
        return {}
    try:
        return {
            "usage_pct": psutil.cpu_percent(interval=0),
            "freq_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
            "cores": psutil.cpu_count(),
            "threads": psutil.cpu_count(logical=True),
        }
    except Exception:
        return {}

def _get_ram():
    if not PSUTIL_AVAILABLE:
        return {}
    try:
        vm = psutil.virtual_memory()
        return {
            "total_gb": round(vm.total / (1024**3), 1),
            "used_gb": round(vm.used / (1024**3), 1),
            "free_gb": round(vm.available / (1024**3), 1),
            "usage_pct": vm.percent,
        }
    except Exception:
        return {}

def _get_gpu():
    gpus = []
    # Try pynvml first (NVIDIA)
    if NVML_AVAILABLE:
        try:
            n = pynvml.nvmlDeviceGetCount()
            for i in range(n):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(handle)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                temp = 0
                try:
                    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU) or 0
                except Exception:
                    pass
                gpus.append({
                    "name": name,
                    "usage_pct": util.gpu,
                    "mem_used_mb": round(mem.used / (1024**2), 0),
                    "mem_total_mb": round(mem.total / (1024**2), 0),
                    "mem_usage_pct": round(mem.used / mem.total * 100, 1),
                    "temp_c": temp,
                    "type": "nvidia",
                })
        except Exception:
            pass

    # Fallback: WMI for non-NVIDIA or extra info
    if not gpus and WMI_AVAILABLE:
        try:
            for gpu in _wmi.Win32_VideoController():
                gpus.append({
                    "name": gpu.Name,
                    "driver": gpu.DriverVersion,
                    "vram_total_mb": int(int(gpu.AdapterRAM or 0) / (1024**2)),
                    "type": "generic",
                })
        except Exception:
            pass

    return {"gpus": gpus}

def _get_disk():
    if not PSUTIL_AVAILABLE:
        return {}
    try:
        parts = []
        for p in psutil.disk_partitions():
            if p.fstype:
                try:
                    u = psutil.disk_usage(p.mountpoint)
                    parts.append({
                        "drive": p.device,
                        "total_gb": round(u.total / (1024**3), 0),
                        "free_gb": round(u.free / (1024**3), 1),
                        "usage_pct": u.percent,
                    })
                except Exception:
                    pass
        return {"disks": parts}
    except Exception:
        return {}

def _get_network():
    if not PSUTIL_AVAILABLE:
        return {}
    try:
        net = psutil.net_io_counters()
        return {
            "sent_mb": round(net.bytes_sent / (1024**2), 1),
            "recv_mb": round(net.bytes_recv / (1024**2), 1),
        }
    except Exception:
        return {}

def _get_game_process() -> dict:
    """Detect if a known game is running and get its stats."""
    if not PSUTIL_AVAILABLE:
        return {}

    GAME_PROCESSES = {
        "VALORANT": "RiotGames",
        "ForzaHorizon": ["ForzaHorizon", "Forza Horizon"],
        "EldenRing": ["EldenRing", "eldenring"],
        "Diablo": ["Diablo", "Diablo II", "Diablo IV"],
        "CS2": ["cs2", "Counter-Strike"],
        "Genshin": ["GenshinImpact"],
        "Dota2": ["dota2"],
    }

    detected = {}
    for game, names in GAME_PROCESSES.items():
        try:
            for p in psutil.process_iter(['name', 'cpu_percent', 'memory_info']):
                name = (p.info['name'] or '').lower()
                for n in names:
                    if n.lower() in name:
                        vm = p.info['memory_info']
                        detected[game] = {
                            "process": p.info['name'],
                            "usage_pct": p.cpu_percent(interval=0),
                            "ram_mb": round(vm.rss / (1024**2), 1),
                        }
        except Exception:
            pass
    return {"games": detected}

# ============== COLLECT ==============
def collect() -> dict:
    ts = datetime.now()
    sample = {
        "timestamp": ts.isoformat(),
        "epoch_ms": int(ts.timestamp() * 1000),
        **_get_cpu(),
        **_get_ram(),
        **_get_gpu(),
        **_get_disk(),
        **_get_network(),
        **_get_game_process(),
    }
    return sample

def _save_to_file():
    global _last_save
    now = time.time()
    if now - _last_save < SAVE_INTERVAL:
        return
    _last_save = now
    with _lock:
        data = {
            "updated": datetime.now().isoformat(),
            "count": len(_samples),
            "samples": list(_samples)
        }
    try:
        with open(LOG_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

# ============== ANALYSIS ==============
def analyze_samples(samples: list) -> dict:
    """Analyze collected samples and return performance summary."""
    if not samples:
        return {}

    cpu_vals = [s.get("usage_pct", 0) for s in samples]
    ram_vals = [s.get("usage_pct", 0) for s in samples]

    # GPU usage
    gpu_usages = []
    for s in samples:
        for gpu in s.get("gpus", []):
            if "usage_pct" in gpu:
                gpu_usages.append(gpu["usage_pct"])

    analysis = {
        "duration_sec": (samples[-1]["epoch_ms"] - samples[0]["epoch_ms"]) / 1000,
        "sample_count": len(samples),
        "cpu_avg": round(sum(cpu_vals) / len(cpu_vals), 1) if cpu_vals else 0,
        "cpu_max": max(cpu_vals) if cpu_vals else 0,
        "ram_avg": round(sum(ram_vals) / len(ram_vals), 1) if ram_vals else 0,
        "ram_max": max(ram_vals) if ram_vals else 0,
        "gpu_avg": round(sum(gpu_usages) / len(gpu_usages), 1) if gpu_usages else 0,
        "gpu_max": max(gpu_usages) if gpu_usages else 0,
    }

    # Bottleneck detection
    bottlenecks = []
    if analysis["cpu_avg"] > 90:
        bottlenecks.append("CPU at high usage (>90%) — upgrade CPU or reduce physics settings")
    if analysis["gpu_avg"] > 95:
        bottlenecks.append("GPU at high usage (>95%) — upgrade GPU or reduce graphics settings")
    if any(s.get("usage_pct", 0) > 90 for s in samples):
        bottlenecks.append("RAM usage high (>90%) — consider adding more RAM")
    if samples and samples[0].get("free_gb", 999) < 4:
        bottlenecks.append("Low free RAM — background apps consuming memory")

    analysis["bottlenecks"] = bottlenecks

    # Lag detection
    lag_frames = []
    for i, s in enumerate(samples):
        cpu = s.get("usage_pct", 0)
        if cpu > 95:
            lag_frames.append({"idx": i, "timestamp": s["timestamp"], "cause": "CPU spike", "value": cpu})
        if gpu_usages and i < len(gpu_usages) and gpu_usages[i] < 30:
            lag_frames.append({"idx": i, "timestamp": s["timestamp"], "cause": "GPU idle", "value": gpu_usages[i]})

    analysis["lag_events"] = lag_frames[:10]  # max 10 events

    # Game detected
    games_detected = set()
    for s in samples:
        for g in s.get("games", []):
            games_detected.add(g)
    analysis["games_detected"] = list(games_detected)

    return analysis

# ============== FORMAT FOR AI ==============
def format_system_summary(analysis: dict) -> str:
    if not analysis:
        return "No system data available."

    lines = []
    lines.append(f"PC PERFORMANCE OVER {analysis['duration_sec']:.0f}s ({analysis['sample_count']} samples):")
    lines.append(f"  CPU avg: {analysis['cpu_avg']}% (max: {analysis['cpu_max']}%)")
    lines.append(f"  RAM avg: {analysis['ram_avg']}% (max: {analysis['ram_max']}%)")
    lines.append(f"  GPU avg: {analysis['gpu_avg']}% (max: {analysis['gpu_max']}%)")

    if analysis.get("games_detected"):
        lines.append(f"  Games detected: {', '.join(analysis['games_detected'])}")

    if analysis.get("bottlenecks"):
        lines.append(f"\n  BOTTLENECKS:")
        for b in analysis["bottlenecks"]:
            lines.append(f"    - {b}")

    if analysis.get("lag_events"):
        lines.append(f"\n  LAG EVENTS ({len(analysis['lag_events'])} detected):")
        for e in analysis["lag_events"][:5]:
            lines.append(f"    - {e['timestamp'][11:19]}: {e['cause']} at {e['value']}%")

    return "\n".join(lines)

# ============== READ FROM FILE (for vision_monitor) ==============
def get_samples_from_file(minutes: int = 5) -> list:
    if not LOG_FILE.exists():
        return []
    try:
        with open(LOG_FILE) as f:
            data = json.load(f)
        cutoff = (datetime.now().timestamp() - minutes * 60) * 1000
        return [s for s in data.get("samples", []) if s.get("epoch_ms", 0) >= cutoff]
    except Exception:
        return []

def get_latest_from_file() -> dict:
    if not LOG_FILE.exists():
        return {}
    try:
        with open(LOG_FILE) as f:
            data = json.load(f)
        samples = data.get("samples", [])
        return samples[-1] if samples else {}
    except Exception:
        return {}

# ============== START/STOP ==============
def start():
    global _running
    _running = True

    def loop():
        while _running:
            try:
                sample = collect()
                with _lock:
                    _samples.append(sample)
                    if len(_samples) > MAX_SAMPLES:
                        _samples.pop(0)
                _save_to_file()
            except Exception:
                pass
            time.sleep(SAMPLE_INTERVAL)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return (f"System monitor started. "
            f"Sampling every {SAMPLE_INTERVAL}s. "
            f"psutil: {'ON' if PSUTIL_AVAILABLE else 'OFF'}, "
            f"wmi: {'ON' if WMI_AVAILABLE else 'OFF'}")

def stop():
    global _running
    _running = False
    _save_to_file()
    with _lock:
        count = len(_samples)
    return f"Stopped. {count} samples collected."

# ============== CLI ==============
if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print("""System Monitor - PC Performance Recorder

Usage:
  python system_monitor.py --start     Start monitoring in background
  python system_monitor.py --status    Show latest readings
  python system_monitor.py --report 5  - Analyze last 5 minutes
  python system_monitor.py --stop      Stop monitoring

Run --start once, it keeps running. Import or read JSON for data.
""")
    elif "--start" in args:
        print(start())
        print("Monitoring running. Press Ctrl+C to stop.")
        try:
            while _running:
                time.sleep(1)
        except KeyboardInterrupt:
            print(stop())
    elif "--status" in args:
        latest = get_latest_from_file()
        if not latest:
            print("No data yet. Run --start first.")
        else:
            print(f"Latest sample: {latest.get('timestamp', '?')}")
            print(f"  CPU: {latest.get('usage_pct', '?')}% @ {latest.get('freq_mhz', '?')}MHz | {latest.get('cores', '?')}c/{latest.get('threads', '?')}t")
            print(f"  RAM: {latest.get('used_gb', '?')}/{latest.get('total_gb', '?')}GB ({latest.get('usage_pct', '?')}%)")
            gpus = latest.get("gpus", [])
            if gpus:
                for g in gpus:
                    u = g.get("usage_pct", "?")
                    t = g.get("temp_c", "?")
                    print(f"  GPU: {g.get('name', '?')[:40]} | {u}% | {g.get('mem_used_mb','?')}/{g.get('mem_total_mb','?')}MB | {t}C")
            disks = latest.get("disks", [])
            if disks:
                for d in disks[:2]:
                    print(f"  Disk {d.get('drive','?')}: {d.get('free_gb','?')}GB free ({d.get('usage_pct','?')}% used)")
    elif "--report" in args:
        mins = 5
        try:
            idx = args.index("--report")
            mins = int(args[idx + 1])
        except Exception:
            pass
        samples = get_samples_from_file(minutes=mins)
        if not samples:
            print(f"No data for last {mins} minutes. Start monitor first.")
        else:
            analysis = analyze_samples(samples)
            print(f"\n=== PERFORMANCE REPORT ({mins} min) ===")
            print(format_system_summary(analysis))
    elif "--stop" in args:
        print(stop())
