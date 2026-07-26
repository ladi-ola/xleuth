def sub_outcome_vwap(
    prices_and_volumes: list[tuple[float, float]],
) -> float | None:
    total_volume = 0.0
    weighted_sum = 0.0

    for price, volume in prices_and_volumes:
        if volume <= 0:
            continue
        weighted_sum += price * volume
        total_volume += volume

    if total_volume <= 0:
        return None

    return weighted_sum / total_volume


def basket_vwap(
    constituents: list[tuple[float, float]],
) -> float | None:
    total_volume = 0.0
    weighted_sum = 0.0

    for price, volume in constituents:
        if volume <= 0:
            continue
        weighted_sum += price * volume
        total_volume += volume

    if total_volume <= 0:
        return None

    return weighted_sum / total_volume