"""asset_bundle_profiler.py – tracks asset bundling durations."""


class AssetBundleProfiler:
    def __init__(self):
        self._samples: list[float] = []

    def record(self, duration_ms: float) -> None:
        self._samples.append(duration_ms)

    def avg_ms(self) -> float:
        return sum(self._samples) / len(self._samples) if self._samples else 0.0
