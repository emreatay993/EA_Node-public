from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ea_node_editor.telemetry.system_metrics import (
    DiskIoSample,
    SystemMetrics,
    disk_io_rates_mb_s,
    read_disk_io_sample,
    read_system_metrics,
)

EngineState = Literal["ready", "running", "paused", "error"]


@dataclass(frozen=True, slots=True)
class StatusPresentation:
    icon: str
    text: str


@dataclass(frozen=True, slots=True)
class MetricsPresentation:
    text: str


class ShellStatusService:
    def __init__(self) -> None:
        self._previous_disk_io_sample: DiskIoSample | None = read_disk_io_sample()

    def collect_system_metrics(self) -> SystemMetrics:
        metrics = read_system_metrics()
        current_disk_io_sample = read_disk_io_sample()
        disk_read_mb_s, disk_write_mb_s = disk_io_rates_mb_s(
            self._previous_disk_io_sample,
            current_disk_io_sample,
        )
        self._previous_disk_io_sample = current_disk_io_sample
        return SystemMetrics(
            cpu_percent=metrics.cpu_percent,
            ram_used_gb=metrics.ram_used_gb,
            ram_total_gb=metrics.ram_total_gb,
            disk_read_mb_s=disk_read_mb_s,
            disk_write_mb_s=disk_write_mb_s,
        )

    def engine_status(self, state: EngineState, details: str = "") -> StatusPresentation:
        text = str(state).capitalize()
        if details:
            text = f"{text} ({details})"
        icon_map = {
            "ready": "R",
            "running": "Run",
            "paused": "P",
            "error": "!",
        }
        return StatusPresentation(icon=icon_map.get(state, "E"), text=text)

    def job_counters(self, *, running: int, queued: int, done: int, failed: int) -> StatusPresentation:
        return StatusPresentation(icon="J", text=f"R:{running} Q:{queued} D:{done} F:{failed}")

    def system_metrics(
        self,
        *,
        fps: float | None,
        cpu_percent: float,
        ram_used_gb: float,
        ram_total_gb: float,
        disk_read_mb_s: float = 0.0,
        disk_write_mb_s: float = 0.0,
        show_fps: bool = True,
    ) -> MetricsPresentation:
        parts = []
        if show_fps and fps is not None:
            parts.append(f"FPS:{max(0.0, float(fps)):.0f}")
        parts.append(f"CPU:{float(cpu_percent):.0f}%")
        parts.append(f"RAM:{float(ram_used_gb):.1f}/{float(ram_total_gb):.1f} GB")
        parts.append(f"Disk R:{max(0.0, float(disk_read_mb_s)):.1f} W:{max(0.0, float(disk_write_mb_s)):.1f} MB/s")
        return MetricsPresentation(
            text=" ".join(parts)
        )

    def notification_counters(self, *, warnings: int, errors: int) -> StatusPresentation:
        return StatusPresentation(icon="N", text=f"W:{warnings} E:{errors}")


__all__ = [
    "EngineState",
    "MetricsPresentation",
    "ShellStatusService",
    "StatusPresentation",
]
