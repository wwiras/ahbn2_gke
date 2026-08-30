"""Pure experiment-local frozen S0/S5 fanout mappings."""

TREATMENTS = {"S0", "S5"}


def requested_fanout(treatment: str, score: float) -> int:
    if treatment not in TREATMENTS:
        raise ValueError(f"unsupported actuator treatment: {treatment}")
    z = float(score)
    if z <= -0.25:
        budget = 2
    elif z < 0.25:
        budget = 3
    elif treatment == "S0" or z < 0.90:
        budget = 4
    elif z < 1.50:
        budget = 5
    else:
        budget = 6
    return budget
