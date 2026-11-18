"""
Bid-ask spread estimators from OHLC prices.

This subpackage ports the EDGE family of estimators from the reference
implementation in https://github.com/eguidotti/bidask (MIT License),
which accompanies the paper:

    Ardia, D., Guidotti, E., Kroencke, T.A. (2024).
    Efficient Estimation of Bid-Ask Spreads from Open, High, Low, and Close
    Prices. Journal of Financial Economics, 161, 103916.
    https://doi.org/10.1016/j.jfineco.2024.103916

The upstream functions are reproduced here (see individual module headers for
the exact upstream commit) so that our own tests can treat the installed
`bidask` package as an independent oracle: this package contains our own
implementation; `bidask` is what we test against.

Competitor estimators (Roll 1984; Corwin & Schultz 2012; Abdi & Ranaldo 2017)
are not in the bidask package and are to be added as sibling modules.
"""

from .edge import edge
from .edge_expanding import edge_expanding
from .edge_rolling import edge_rolling

__all__ = ["edge", "edge_rolling", "edge_expanding"]
