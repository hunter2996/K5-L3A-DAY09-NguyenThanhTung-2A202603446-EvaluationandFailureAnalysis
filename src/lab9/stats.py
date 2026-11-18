"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
import operator
from collections.abc import Sequence

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def _validate_labels(human: Sequence[str], judge: Sequence[str]) -> list[tuple[str, str]]:
    if len(human) != len(judge):
        raise ValueError(f"label length mismatch: {len(human)} != {len(judge)}")
    return [(str(h).strip().upper(), str(j).strip().upper()) for h, j in zip(human, judge)]


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    pairs = _validate_labels(human, judge)
    tp = sum(1 for h, j in pairs if h == POS and j == POS)
    fp = sum(1 for h, j in pairs if h != POS and j == POS)
    fn = sum(1 for h, j in pairs if h == POS and j != POS)
    tn = sum(1 for h, j in pairs if h != POS and j != POS)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    """Return (precision, recall) with FAIL as positive; 0.0 when denominator is 0."""
    cm = confusion(human, judge)
    p = cm["tp"] / (cm["tp"] + cm["fp"]) if (cm["tp"] + cm["fp"]) > 0 else 0.0
    r = cm["tp"] / (cm["tp"] + cm["fn"]) if (cm["tp"] + cm["fn"]) > 0 else 0.0
    return p, r


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    cm = confusion(human, judge)
    n = cm["tp"] + cm["fp"] + cm["fn"] + cm["tn"]
    if n == 0:
        raise ValueError("cohen_kappa undefined for empty labels")
    p_o = (cm["tp"] + cm["tn"]) / n
    p_h_pos = (cm["tp"] + cm["fn"]) / n
    p_j_pos = (cm["tp"] + cm["fp"]) / n
    p_h_neg = (cm["tn"] + cm["fp"]) / n
    p_j_neg = (cm["tn"] + cm["fn"]) / n
    p_e = p_h_pos * p_j_pos + p_h_neg * p_j_neg
    if abs(1.0 - p_e) <= 1e-12:
        raise ValueError("cohen_kappa undefined when p_e == 1")
    return (p_o - p_e) / (1.0 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denom = sensitivity + specificity - 1.0
    if abs(denom) <= 1e-12:
        return max(0.0, min(1.0, float(observed_rate)))
    raw = (observed_rate + specificity - 1.0) / denom
    return max(0.0, min(1.0, float(raw)))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    if len(a) != len(b):
        raise ValueError(f"paired sequences must have equal length: {len(a)} != {len(b)}")
    if not a:
        return (0.0, 0.0, 0.0)
    import numpy as np
    from scipy import stats as scipy_stats

    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    diff = arr_a - arr_b
    if np.all(diff == 0.0):
        return (0.0, 0.0, 0.0)
    mean_diff = float(np.mean(diff))
    if len(diff) == 1 or np.all(diff == diff[0]):
        return (mean_diff, mean_diff, mean_diff)
    res = scipy_stats.bootstrap(
        (arr_a, arr_b),
        lambda x, y, axis=-1: np.mean(x - y, axis=axis),
        paired=True,
        n_resamples=n_resamples,
        confidence_level=confidence,
        method="percentile",
        rng=np.random.default_rng(rng),
    )
    return (mean_diff, float(res.confidence_interval.low), float(res.confidence_interval.high))


def _validate_k_args(n: int, c: int, k: int) -> tuple[int, int, int]:
    for name, val in (("n", n), ("c", c), ("k", k)):
        if isinstance(val, bool):
            raise ValueError(f"{name} must be an integer, got bool")
    try:
        ni, ci, ki = operator.index(n), operator.index(c), operator.index(k)
    except TypeError as exc:
        raise ValueError(f"invalid (n, c, k)=({n!r}, {c!r}, {k!r})") from exc
    if ni <= 0 or ki <= 0 or ki > ni or ci < 0 or ci > ni:
        raise ValueError(f"invalid (n, c, k)=({ni}, {ci}, {ki})")
    return ni, ci, ki


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    ni, ci, ki = _validate_k_args(n, c, k)
    if ni - ci < ki:
        return 1.0
    return 1.0 - math.comb(ni - ci, ki) / math.comb(ni, ki)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    ni, ci, ki = _validate_k_args(n, c, k)
    if ci < ki:
        return 0.0
    return math.comb(ci, ki) / math.comb(ni, ki)
