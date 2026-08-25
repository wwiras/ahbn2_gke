"""Frozen canonical AHBN controller port from ControlSim v0.61.

This module is deliberately free of Kubernetes, experiment, and sensor logic.
Given the same normalized ``(d, l, u, c)`` sequence it produces the same state
and decisions as ``AHBNProj/ahbn/v0.61/ahbn/control.py``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class AHBNParams:
    alpha: float = 0.3
    d0: float = 0.0
    l0: float = 0.0
    u0: float = 0.0
    c0: float = 0.0
    w_d: float = -1.0
    w_l: float = 1.0
    w_u: float = 1.0
    w_c: float = 1.0
    kappa: float = 1.0
    beta: float = 1.0
    min_fanout: int = 2
    max_fanout: int = 4
    default_fanout: int = 3
    mode_threshold: float = 0.5


@dataclass
class AHBNState:
    d_hat: float = 0.0
    l_hat: float = 0.0
    u_hat: float = 0.0
    c_hat: float = 0.0
    score: float = 0.0
    weight: float = 0.5
    mode: str = "gossip"
    fanout: int = 3


@dataclass(frozen=True)
class AHBNDecision:
    raw_d: float
    raw_l: float
    raw_u: float
    raw_c: float
    d_hat: float
    l_hat: float
    u_hat: float
    c_hat: float
    duplication_score_contribution: float
    latency_score_contribution: float
    utilization_score_contribution: float
    churn_score_contribution: float
    score: float
    weight: float
    mode: str
    fanout: int
    mode_changed: bool
    fanout_changed: bool


class CanonicalAHBNController:
    """The environment-independent AHBN state transition."""

    def __init__(self, params: AHBNParams | None = None) -> None:
        self.params = params or AHBNParams()

    @staticmethod
    def clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def ewma(self, old: float, new: float) -> float:
        new = self.clamp(float(new), 0.0, 1.0)
        return self.params.alpha * new + (1.0 - self.params.alpha) * old

    @staticmethod
    def sigmoid(value: float) -> float:
        if value >= 0.0:
            z = math.exp(-value)
            return 1.0 / (1.0 + z)
        z = math.exp(value)
        return z / (1.0 + z)

    def update(
        self,
        state: AHBNState,
        duplicate_obs: float,
        latency_obs: float,
        utilization_obs: float,
        churn_obs: float,
    ) -> AHBNDecision:
        raw_d = self.clamp(float(duplicate_obs), 0.0, 1.0)
        raw_l = self.clamp(float(latency_obs), 0.0, 1.0)
        raw_u = self.clamp(float(utilization_obs), 0.0, 1.0)
        raw_c = self.clamp(float(churn_obs), 0.0, 1.0)
        old_mode, old_fanout = state.mode, state.fanout

        state.d_hat = self.ewma(state.d_hat, raw_d)
        state.l_hat = self.ewma(state.l_hat, raw_l)
        state.u_hat = self.ewma(state.u_hat, raw_u)
        state.c_hat = self.ewma(state.c_hat, raw_c)

        p = self.params
        d_part = p.w_d * (state.d_hat - p.d0)
        l_part = p.w_l * (state.l_hat - p.l0)
        u_part = p.w_u * (state.u_hat - p.u0)
        c_part = p.w_c * (state.c_hat - p.c0)
        state.score = d_part + l_part + u_part + c_part
        state.weight = self.clamp(
            self.sigmoid(p.kappa * state.score), 0.0, 1.0
        )
        state.mode = "gossip" if state.weight >= p.mode_threshold else "cluster"
        span = p.max_fanout - p.min_fanout
        raw_fanout = p.min_fanout + p.beta * state.weight * span
        state.fanout = int(round(self.clamp(raw_fanout, p.min_fanout, p.max_fanout)))

        return AHBNDecision(
            raw_d, raw_l, raw_u, raw_c,
            state.d_hat, state.l_hat, state.u_hat, state.c_hat,
            d_part, l_part, u_part, c_part,
            state.score, state.weight, state.mode, state.fanout,
            state.mode != old_mode, state.fanout != old_fanout,
        )
