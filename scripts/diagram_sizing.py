"""Boost-aware sizing for the graphviz architecture diagrams.

Every demo renders its diagram twice. Once at the default font for the post,
and once with DIAGRAM_FONT_BOOST set so the text survives being scaled down
onto a social card. The boost is where the trouble is.

A `diagrams` node is a `shape=none` box holding an icon with the label drawn
underneath it, and the box height is hardcoded to 1.9 inches plus 0.4 for each
extra label line. Nothing in that is aware of the font size. Boost the font and
the label grows while its box does not, so it drops out of the bottom, and
because a cluster is sized from the boxes it contains rather than from what is
drawn, the label lands on the cluster boundary.

`node_height` grows the box by what the larger text actually needs, and
`cluster_margin` adds slack around the cluster for the labels that are wider
than their node. Both are identity at boost 0, so the diagrams embedded in the
posts render exactly as they did before.

Do not set an explicit width to solve the horizontal case. graphviz scales the
icon up to fill the box, and the label then sits on the artwork instead.

    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
    from diagram_sizing import BOOST, cluster_margin, fs, node_height
"""

import os

BOOST = int(os.environ.get("DIAGRAM_FONT_BOOST", "0"))

# Roughly the line box a point of font size occupies, in points.
_LINE_RATIO = 1.4


def fs(size):
    """Font size with the boost applied, as graphviz wants it, a string."""
    return str(int(size) + BOOST)


def node_height(lines=1):
    """Node height in inches that holds `lines` of label at the boosted font."""
    return str(round(1.9 + 0.4 * (lines - 1) + lines * BOOST * _LINE_RATIO / 72, 2))


def cluster_margin(base=25):
    """Cluster padding in points, widened so long labels stay inside."""
    return str(base + BOOST * 7)
