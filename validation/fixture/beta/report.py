"""Input rows have exactly name (str) and count (nonnegative int)."""


def summarize(rows):
    """Return records, total, maximum; all are zero for empty input."""
    raise NotImplementedError("B1")


def top_names(rows, limit):
    """Names by decreasing count, then alphabetically; reject negative limit."""
    raise NotImplementedError("B2")


def render(summary):
    """Stable compact JSON with sorted keys, Unicode retained, newline at end."""
    raise NotImplementedError("B3")


def from_csv(text):
    """Parse and combine with alpha, summarize, then render."""
    raise NotImplementedError("B4")
