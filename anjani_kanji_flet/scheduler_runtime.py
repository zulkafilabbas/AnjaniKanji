"""Optional scheduler bridge for using the local SSP-MMC-FSRS package as-is."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .fsrs_scheduler import PACKAGE_DR_SCHEDULER_MODE


@dataclass(frozen=True, slots=True)
class SchedulerRuntimeStatus:
    """Describe scheduler package availability for the current environment."""

    package_available: bool
    status_text: str
    detail_text: str


def scheduler_runtime_status() -> SchedulerRuntimeStatus:
    """Probe whether the untouched local SSP-MMC-FSRS package can be imported."""
    try:
        _load_ssp_package()
    except Exception as exc:
        return SchedulerRuntimeStatus(
            package_available=False,
            status_text="package mode unavailable",
            detail_text=str(exc),
        )
    return SchedulerRuntimeStatus(
        package_available=True,
        status_text="package mode available",
        detail_text="using local SSP-MMC-FSRS package without modifying its source",
    )


def package_dr_interval_days(
    *,
    stability: float,
    difficulty: float,
    prev_interval: int,
    grade: int,
    desired_retention: float,
) -> int:
    """Compute the next interval from the untouched local SSP-MMC-FSRS DR policy."""
    package = _load_ssp_package()
    import torch

    policy = package.create_dr_policy(desired_retention)
    stability_tensor = torch.tensor([float(stability)], dtype=torch.float32)
    difficulty_tensor = torch.tensor([float(difficulty)], dtype=torch.float32)
    prev_interval_tensor = torch.tensor([float(prev_interval)], dtype=torch.float32)
    grade_tensor = torch.tensor([int(grade)], dtype=torch.int64)
    result = policy(stability_tensor, difficulty_tensor, prev_interval_tensor, grade_tensor)
    interval_tensor = result[0] if isinstance(result, tuple) else result
    return max(1, int(float(interval_tensor.reshape(-1)[0].item())))


def is_package_mode(mode: str) -> bool:
    """Return whether a scheduler mode requests the local package-backed runtime."""
    return mode == PACKAGE_DR_SCHEDULER_MODE


def _load_ssp_package() -> Any:
    """Import the local SSP-MMC-FSRS package from the repo checkout."""
    root = Path(__file__).resolve().parent.parent
    src_path = root / "SSP-MMC-FSRS" / "src"
    if not src_path.exists():
        raise ModuleNotFoundError("local SSP-MMC-FSRS source folder not found")
    src_text = str(src_path)
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    import ssp_mmc_fsrs  # type: ignore

    return ssp_mmc_fsrs
