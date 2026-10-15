"""Cut-line geometry: alpha mask -> one smooth outer contour (+ optional holes).

Pure geometry, no I/O. All values are pixels in the alpha array's space.
"""

import cv2
import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

# The smoothed line may sit a little closer to the art than `offset`, but never
# closer than this fraction of it.
MIN_CLEARANCE = 0.8


def art_shape(alpha, threshold, min_piece_px):
    """Opaque area of `alpha` as a (Multi)Polygon, holes included.

    Pieces smaller than min_piece_px^2 (stray specks, noise in glows) are
    dropped so they don't drag the outline out to them.
    """
    # A slight blur softens jagged (non-antialiased) source edges before tracing.
    mask = (cv2.GaussianBlur(alpha, (0, 0), 2) > threshold).astype(np.uint8)
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hierarchy is None:
        return Polygon()
    hierarchy = hierarchy[0]
    pieces = []
    for i, c in enumerate(contours):
        if hierarchy[i][3] != -1 or len(c) < 3:
            continue  # holes are collected with their parent below
        holes = []
        child = hierarchy[i][2]
        while child != -1:
            if len(contours[child]) >= 3:
                holes.append(contours[child].reshape(-1, 2))
            child = hierarchy[child][0]
        # Simplifying first irons out most of the pixel staircase.
        poly = Polygon(c.reshape(-1, 2), holes).simplify(1.5).buffer(0)
        if poly.area >= min_piece_px ** 2:
            pieces.append(poly)
    if not pieces:  # everything was tiny: keep it rather than lose the sticker
        pieces = [Polygon(c.reshape(-1, 2)).buffer(0) for c in contours if len(c) >= 3]
    return unary_union(pieces)


def resample_ring(coords, spacing):
    """Evenly spaced points along a closed ring (last point not repeated)."""
    pts = np.asarray(coords, dtype=float)
    if not np.array_equal(pts[0], pts[-1]):
        pts = np.vstack([pts, pts[:1]])
    cum = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])
    n = max(16, int(cum[-1] / spacing))
    t = np.linspace(0, cum[-1], n, endpoint=False)
    return np.column_stack([np.interp(t, cum, pts[:, 0]), np.interp(t, cum, pts[:, 1])])


def gaussian_smooth_ring(coords, sigma, spacing=1.0):
    """Gaussian-smooth a closed ring's points (curvature smoothing).

    The ring is resampled every `spacing` px; `sigma` is in samples.
    """
    pts = resample_ring(coords, spacing)
    n = len(pts)
    sigma = min(sigma, n / 8)  # tiny rings: don't smooth them into a dot
    if sigma < 0.5:
        return pts
    half = int(3 * sigma)
    k = np.exp(-0.5 * (np.arange(-half, half + 1) / sigma) ** 2)
    k /= k.sum()
    out = np.empty_like(pts)
    for d in range(2):
        padded = np.concatenate([pts[-half:, d], pts[:, d], pts[:half, d]])
        out[:, d] = np.convolve(padded, k, mode="valid")
    return out


def _max_gap(region, boundary):
    """Largest distance from a point of `region` to `boundary` (vertices only)."""
    if region.is_empty:
        return 0.0
    pts = shapely.points(shapely.get_coordinates(region))
    return float(shapely.distance(pts, boundary).max())


def corridor_smooth(shape, art, offset_px, slack_px, spacing, iterations=15):
    """Smooth the outer ring while keeping it inside a corridor around the art.

    The corridor runs from MIN_CLEARANCE * offset (never closer to the art)
    to the offset shape plus `slack_px`. Repeated smoothing pulls the ring
    taut inside it: shallow wiggles (pixel steps, a row of legs) straighten
    out, deep notches the corridor follows (a crescent's inside) survive.
    """
    inner = art.buffer(offset_px * MIN_CLEARANCE)
    outer = shape.buffer(slack_px)
    shapely.prepare(inner)
    shapely.prepare(outer)
    pts = resample_ring(shape.exterior.coords, spacing)
    for _ in range(iterations):
        pts = gaussian_smooth_ring(np.vstack([pts, pts[:1]]), 6, spacing)
        for bad, edge in ((shapely.contains_xy(inner, pts[:, 0], pts[:, 1]), inner.boundary),
                          (~shapely.contains_xy(outer, pts[:, 0], pts[:, 1]), outer.boundary)):
            if bad.any():
                lines = shapely.shortest_line(shapely.points(pts[bad]), edge)
                pts[bad] = shapely.get_coordinates(lines)[1::2]
    return _largest(Polygon(pts).buffer(0))


def smooth_exterior(shape, art, offset_px, smooth_px):
    """Corridor-smooth the outer ring, smooth out the kinks the corridor
    leaves, then grow it just enough to clear the art again."""
    # Point spacing scales with the ring, so cost is the same for any size
    # and the smoothing is proportional to the sticker.
    spacing = max(2.0, shape.exterior.length / 600)
    ring = corridor_smooth(shape, art, offset_px, smooth_px * 0.66, spacing)
    ring = _largest(Polygon(gaussian_smooth_ring(ring.exterior.coords, 8, spacing)).buffer(0))
    must_cover = art.buffer(offset_px * MIN_CLEARANCE)
    grow = _max_gap(must_cover.difference(ring), ring.exterior)
    if grow > 0:
        ring = ring.buffer(grow + 0.5)
    return Polygon(ring.exterior)


def _largest(geom):
    if isinstance(geom, MultiPolygon):
        return max(geom.geoms, key=lambda g: g.area)
    return geom


def smooth_hole(hole, art, offset_px, sigma):
    """Smooth an inner ring, then shrink it until it clears the art again."""
    smooth = _largest(Polygon(gaussian_smooth_ring(hole.exterior.coords, sigma)).buffer(0))
    keep_out = art.buffer(offset_px * MIN_CLEARANCE)
    shrink = _max_gap(smooth.intersection(keep_out), smooth.exterior)
    if shrink > 0:
        smooth = _largest(smooth.buffer(-(shrink + 0.5)))
    return smooth if isinstance(smooth, Polygon) and not smooth.is_empty else None


def min_width(poly):
    """Narrow side of the minimum rotated rectangle around `poly`."""
    rect = poly.minimum_rotated_rectangle
    xy = np.asarray(rect.exterior.coords)
    sides = np.hypot(*np.diff(xy[:3], axis=0).T)
    return float(sides.min())


def cut_outline(alpha, threshold, offset_px, smooth_px, *, min_piece_px=4.0,
                hole_min_px=None):
    """Return the cut line around the opaque area of `alpha` as a Polygon.

    One outer contour: separate pieces are merged, notches narrower than
    ~2*smooth_px are rounded off, and the pixel staircase on diagonal edges is
    smoothed away. Holes are only kept (as interiors) when `hole_min_px` is set
    and they're at least that wide after offsetting.
    """
    art = art_shape(alpha, threshold, min_piece_px)
    if art.is_empty:
        return Polygon()
    shape = art.buffer(offset_px)

    # Morphological close (grow then shrink) rounds off tight inner notches that
    # scissors can't follow. Keep widening it until separate pieces fuse.
    radius = smooth_px
    for _ in range(4):
        closed = shape.buffer(radius).buffer(-radius)
        if isinstance(closed, Polygon):
            shape = closed
            break
        radius *= 2
    else:
        shape = shape.convex_hull

    shape = _largest(shape)

    # The close only rounds inward corners; outward bumps (offset staircase on
    # diagonals, rows of legs) need curve smoothing.
    outer = smooth_exterior(shape, art, offset_px, smooth_px)

    holes = []
    if hole_min_px:
        for ring in shape.interiors:
            hole = Polygon(ring)
            if min_width(hole) < hole_min_px:
                continue
            hole = smooth_hole(hole, art, offset_px, smooth_px * 0.3)
            if hole is not None and min_width(hole) >= hole_min_px * 0.5:
                holes.append(hole.exterior)
    return Polygon(outer.exterior, holes).simplify(0.3)
