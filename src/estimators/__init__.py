"""
Bid-ask spread estimators from OHLC prices.

The upstream functions are reproduced here (see individual module headers for
the exact upstream commit) so that our own tests can treat the installed
`bidask` package as an independent oracle: this package contains our own
implementation; `bidask` is what we test against.

Competitor estimators (Roll 1984; Corwin & Schultz 2012; Abdi & Ranaldo 2017)
are not in the bidask package and are to be added as sibling modules.

`edge_moments` exposes EDGE's per-bar moment conditions (x1, x2 and the four
DGE building blocks); `edge()` is computed from it.
"""

from .abdi_ranaldo import abdi_ranaldo
from .corwin_schultz import corwin_schultz
from .edge import edge
from .edge_expanding import edge_expanding
from .edge_moments import EdgeMoments, edge_moments
from .edge_rolling import edge_rolling
from .roll import roll

__all__ = [
    "edge",
    "edge_moments",
    "EdgeMoments",
    "edge_rolling",
    "edge_expanding",
    "roll",
    "corwin_schultz",
    "abdi_ranaldo",
]
