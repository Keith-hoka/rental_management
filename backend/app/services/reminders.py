def _bucket(days_left: int, thresholds: list[int]) -> int | None:
    """Smallest threshold T with days_left <= T when days_left >= 0, else None."""
    if days_left < 0:
        return None
    for threshold in sorted(thresholds):
        if days_left <= threshold:
            return threshold
    return None
