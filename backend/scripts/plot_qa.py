"""Scientific QA figure for supplied parameter fixtures; no frontend implementation."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]


def main():
    bundle = json.loads((BACKEND / "artifacts" / "four_curve_plot.json").read_text())
    time_us = np.asarray(bundle["time_s"]) * 1e6
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    for i, curve in enumerate(bundle["curves"]):
        label = "Target reference" if i == 0 else f"Parameter fixture {i}"
        voltage_kV = np.asarray(curve["voltage_V"]) / 1000
        for axis in axes:
            axis.plot(
                time_us,
                voltage_kV,
                label=label,
                linewidth=2 if i == 0 else 1.2,
                linestyle="-" if i == 0 else "--",
            )
    axes[0].set_xlim(0, 12)
    axes[0].set_title("Front comparison")
    axes[1].set_xlim(0, min(time_us[-1], 200))
    axes[1].set_title("Full impulse comparison")
    for axis in axes:
        axis.set_xlabel("Time (µs)")
        axis.set_ylabel("Voltage (kV)")
        axis.grid(alpha=0.25)
        axis.legend(loc="upper right", fontsize=8)
    figure.suptitle(
        "Four-curve reconstruction QA — supplied parameter fixtures; not measured or inferred samples",
        fontsize=10,
    )
    destination = BACKEND.parent / "docs" / "verification" / "waveform_fixture_qa.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=160)
    plt.close(figure)


if __name__ == "__main__":
    main()
