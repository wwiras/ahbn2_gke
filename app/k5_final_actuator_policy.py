"""Pure experiment-local S0/S5-C6 fanout mappings."""

TREATMENTS = {"S0", "S5-C6"}


def actuator_state(score: float) -> str:
    if score <= -0.25:
        return "LOW"
    if score >= 0.25:
        return "HIGH"
    return "MODERATE"


def requested_fanout(treatment: str, state: str, eligible_count: int) -> int:
    if treatment not in TREATMENTS:
        raise ValueError(f"unsupported actuator treatment: {treatment}")
    if state not in {"LOW", "MODERATE", "HIGH"}:
        raise ValueError(f"unsupported actuator state: {state}")
    ne = max(0, int(eligible_count))
    if treatment == "S0":
        return min({"LOW": 2, "MODERATE": 3, "HIGH": 4}[state], ne)
    base = {
        "LOW": (ne + 2) // 3,
        "MODERATE": (2 * ne + 2) // 3,
        "HIGH": ne,
    }[state]
    return min(base, 6, ne)
