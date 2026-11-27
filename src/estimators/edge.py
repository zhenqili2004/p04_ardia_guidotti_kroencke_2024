"""
EDGE: Efficient Discrete Generalized Estimator of bid-ask spreads.

Numeric logic is bit-identical to upstream; only the input parameter type
annotations were corrected from `np.array` (which is a function, not a type,
and triggers Pyright errors) to `numpy.typing.ArrayLike`.

The moment conditions themselves are computed in `edge_moments.py` (moved
there unchanged), so that EDGE is computed in one place and the extension's
diagnostics can reuse the per-bar moments. `edge()` only takes the signed
root of the squared spread that `edge_moments()` returns.

Adapted from bidask (https://github.com/eguidotti/bidask), (c) 2024
Emanuele Guidotti, MIT License; see LICENSE-bidask.txt in this folder.
"""

from typing import Any

import numpy as np

from .edge_moments import edge_moments

# `_Vec` is intentionally `Any`: the function accepts anything array-like at
# runtime (numpy ndarray, pandas Series, list, tuple, ExtensionArray, ...)
# and immediately coerces via `np.asarray`. Expressing this precisely with
# numpy's ArrayLike / pandas-stubs' Series unions ends up chasing pandas
# internal types (ExtensionArray, Categorical) that stubs do not mark as
# ArrayLike-compatible, so Any is the pragmatic signature.
_Vec = Any


def edge(
    open: _Vec,
    high: _Vec,
    low: _Vec,
    close: _Vec,
    sign: bool = False,
) -> float:
    """
    Efficient Estimation of Bid-Ask Spreads from Open, High, Low, and Close Prices

    Implements the efficient estimator of bid-ask spreads from open, high, low,
    and close prices described in Ardia, Guidotti, & Kroencke (JFE, 2024):
    https://doi.org/10.1016/j.jfineco.2024.103916

    Parameters
    ----------
    - `open`: array-like
        Vector of open prices sorted in ascending order of the timestamp.
    - `high`: array-like
        Vector of high prices sorted in ascending order of the timestamp.
    - `low`: array-like
        Vector of low prices sorted in ascending order of the timestamp.
    - `close`: array-like
        Vector of close prices sorted in ascending order of the timestamp.
    - `sign`:
        Whether to return signed estimates.

    Returns
    -------
    float
        The spread estimate. A value of 0.01 corresponds to a spread of 1%.
    """
    s2 = edge_moments(open, high, low, close).s2

    # compute signed root
    s = np.sqrt(np.abs(s2))
    if sign:
        s *= np.sign(s2)

    # return the spread
    return float(s)
