from __future__ import annotations

from dataclasses import dataclass
import time

try:
    import psutil  # type: ignore
except Exception:  # noqa: BLE001
    psutil = None


@dataclass(slots=True, frozen=True)
class SystemMetrics:
    cpu_percent: float
    ram_used_gb: float
    ram_total_gb: float
    disk_read_mb_s: float = 0.0
    disk_write_mb_s: float = 0.0


@dataclass(slots=True, frozen=True)
class DiskIoSample:
    timestamp: float
    read_bytes: int
    write_bytes: int


def _bytes_to_gb(size_bytes: float) -> float:
    return size_bytes / (1024 ** 3)


def read_system_metrics() -> SystemMetrics:
    if psutil is None:
        return SystemMetrics(cpu_percent=0.0, ram_used_gb=0.0, ram_total_gb=0.0)
    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=None)
    return SystemMetrics(
        cpu_percent=float(cpu),
        ram_used_gb=round(_bytes_to_gb(mem.used), 2),
        ram_total_gb=round(_bytes_to_gb(mem.total), 2),
    )


def read_disk_io_sample() -> DiskIoSample | None:
    if psutil is None:
        return None
    counters = psutil.disk_io_counters()
    if counters is None:
        return None
    return DiskIoSample(
        timestamp=time.monotonic(),
        read_bytes=int(getattr(counters, "read_bytes", 0) or 0),
        write_bytes=int(getattr(counters, "write_bytes", 0) or 0),
    )


def disk_io_rates_mb_s(previous: DiskIoSample | None, current: DiskIoSample | None) -> tuple[float, float]:
    if previous is None or current is None:
        return 0.0, 0.0
    elapsed = max(0.0, float(current.timestamp) - float(previous.timestamp))
    if elapsed <= 0.0:
        return 0.0, 0.0
    read_mb_s = max(0.0, float(current.read_bytes - previous.read_bytes) / (1024 ** 2) / elapsed)
    write_mb_s = max(0.0, float(current.write_bytes - previous.write_bytes) / (1024 ** 2) / elapsed)
    return read_mb_s, write_mb_s
