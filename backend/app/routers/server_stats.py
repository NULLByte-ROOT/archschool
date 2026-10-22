import time
from typing import List

import psutil
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import models
from ..dependencies import get_current_owner

router = APIRouter()

# psutil.cpu_percent(interval=None) needs a first (meaningless) call before it
# starts returning real percentages; priming here keeps every request fast.
psutil.cpu_percent(interval=None)

_BOOT_TIME = psutil.boot_time()


class UsageReading(BaseModel):
    """One "used vs total" reading in percent + absolute bytes."""

    used: int
    total: int
    percent: float


class CpuReading(BaseModel):
    percent: float
    """Whole-CPU utilisation since the previous call (0..100)."""
    per_core: List[float]
    core_count: int
    load_1: float
    load_5: float
    load_15: float


class ServerStatsOut(BaseModel):
    cpu: CpuReading
    memory: UsageReading
    disk: UsageReading
    swap: UsageReading
    uptime_seconds: int
    timestamp: float


def _usage(part: str, total: int, percent: float) -> UsageReading:
    return UsageReading(
        used=total - part, total=total, percent=round(percent, 1)
    )


@router.get("/", response_model=ServerStatsOut)
def live_stats(_: models.User = Depends(get_current_owner)):
    """Live host metrics (psutil). Owner-only by design — `polled` reading is
    a plain GET, so no WebSocket state is involved and blue-green verifier
    flows are untouched.
    """
    cpu = psutil.cpu_percent(interval=None)
    per_core = psutil.cpu_percent(interval=None, percpu=True)
    load = psutil.getloadavg()

    virtual = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")

    return ServerStatsOut(
        cpu=CpuReading(
            percent=cpu,
            per_core=[round(c, 1) for c in per_core],
            core_count=psutil.cpu_count(logical=True) or len(per_core) or 0,
            load_1=load[0],
            load_5=load[1],
            load_15=load[2],
        ),
        memory=UsageReading(
            used=virtual.used,
            total=virtual.total,
            percent=round(virtual.percent, 1),
        ),
        disk=UsageReading(
            used=disk.used,
            total=disk.total,
            percent=round(disk.percent, 1),
        ),
        swap=UsageReading(
            used=swap.used,
            total=swap.total,
            percent=round(swap.percent, 1),
        ),
        uptime_seconds=int(time.time() - _BOOT_TIME),
        timestamp=time.time(),
    )
