"""Kubernetes observation acquisition for the common AHBN inputs.

The adapter owns only measurement and normalization.  It never chooses a
mode or fanout.  Each call to :meth:`snapshot_and_reset` closes one local
observation window and resets interval counters.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading


@dataclass(frozen=True)
class ObservationSnapshot:
    d: float
    l: float
    u: float
    c: float
    duplicate_window_received: int
    duplicate_window_duplicates: int
    latency_window_count: int
    latency_raw: float
    churn_join_count: int
    churn_leave_count: int
    neighbor_count: int


class KubernetesObservationAdapter:
    """Collect interval-local, normalized observations ``d,l,u,c``."""

    def __init__(self, latency_max_seconds: float = 1.0) -> None:
        if latency_max_seconds <= 0:
            raise ValueError("latency_max_seconds must be positive")
        self.latency_max_seconds = float(latency_max_seconds)
        self.received = 0
        self.duplicates = 0
        self.latency_sum = 0.0
        self.latency_count = 0
        self.joins = 0
        self.leaves = 0
        self._lock = threading.Lock()

    def record_receive(self, *, duplicate: bool, latency_seconds: float) -> None:
        with self._lock:
            self.received += 1
            self.duplicates += int(duplicate)
            self.latency_sum += max(0.0, float(latency_seconds))
            self.latency_count += 1

    def record_join(self, count: int = 1) -> None:
        with self._lock:
            self.joins += max(0, int(count))

    def record_leave(self, count: int = 1) -> None:
        with self._lock:
            self.leaves += max(0, int(count))

    @staticmethod
    def utilization(overload_ms: int) -> float:
        """Normalized local processing pressure; magnitude is not the metric."""
        return 1.0 if int(overload_ms) > 0 else 0.0

    def snapshot_and_reset(
        self, *, overload_ms: int, neighbor_count: int
    ) -> ObservationSnapshot:
        with self._lock:
            d = self.duplicates / self.received if self.received else 0.0
            latency_raw = self.latency_sum / self.latency_count if self.latency_count else 0.0
            l = min(1.0, latency_raw / self.latency_max_seconds)
            c = min(1.0, (self.joins + self.leaves) / max(int(neighbor_count), 1))
            result = ObservationSnapshot(
                d=d, l=l, u=self.utilization(overload_ms), c=c,
                duplicate_window_received=self.received,
                duplicate_window_duplicates=self.duplicates,
                latency_window_count=self.latency_count,
                latency_raw=latency_raw,
                churn_join_count=self.joins,
                churn_leave_count=self.leaves,
                neighbor_count=max(0, int(neighbor_count)),
            )
            self.received = self.duplicates = 0
            self.latency_sum = 0.0
            self.latency_count = 0
            self.joins = self.leaves = 0
        return result
