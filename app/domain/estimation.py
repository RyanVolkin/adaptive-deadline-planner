from math import ceil


HISTORY_LIMIT = 5
MIN_PROGRESS_PCT = 10
MIN_FACTOR = 0.5
MAX_FACTOR = 2


class EstimationEngine:
    """Estimates for validated inputs; adjustment expects 0-99% completion."""

    def estimate_ratio(self, actual, original):
        if actual == 0:
            return None
        return actual / original

    def history_factor(self, ratios):
        if not ratios:
            return 1.0
        factor = sum(ratios) / len(ratios)
        return max(MIN_FACTOR, min(MAX_FACTOR, factor))

    def starting_estimate(self, original, factor):
        # Avoid adding a minute from floating-point rounding.
        return ceil(round(original * factor, 9))

    def pace_total(self, actual, pct):
        return actual * 100 / pct

    def adjusted_estimate(self, starting, actual, pct):
        if actual == 0 or pct < MIN_PROGRESS_PCT:
            return starting

        blended = ceil((starting + self.pace_total(actual, pct)) / 2)
        return max(ceil(MIN_FACTOR * starting), min(MAX_FACTOR * starting, blended))

    def remaining_work(self, adjusted, pct):
        return ceil(adjusted * (100 - pct) / 100)
