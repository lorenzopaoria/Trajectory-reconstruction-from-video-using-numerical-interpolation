"""Shared names, provenance and colors; bright red is reserved for the reference."""

METHODS = {
    "s1": {"label": "S1 lineare", "bgr": (255, 220, 0), "scope": "course"},
    "vandermonde": {"label": "Vandermonde", "bgr": (0, 165, 255), "scope": "course"},
    "lagrange": {"label": "Lagrange", "bgr": (60, 230, 60), "scope": "course"},
    "newton": {"label": "Newton", "bgr": (230, 70, 190), "scope": "course"},
    "s3_natural": {"label": "S3 naturale", "bgr": (255, 110, 60), "scope": "course"},
    "s3_clamped": {"label": "S3 vincolata", "bgr": (40, 225, 255), "scope": "course"},
    "s2": {"label": "S2 (estensione)", "bgr": (160, 160, 160), "scope": "extension"},
    "rational_fh": {"label": "Razionale FH (est.)", "bgr": (175, 195, 20), "scope": "introduced_family_extended_algorithm"},
    "s3_periodic": {"label": "S3 periodica", "bgr": (220, 180, 110), "scope": "course_periodic_data"},
    "trigonometric": {"label": "Trigonometrica", "bgr": (220, 220, 140), "scope": "introduced_family_periodic_data"},
}
VIDEO_METHODS = tuple(name for name in METHODS if name not in {"s3_periodic", "trigonometric"})
POLYNOMIAL_METHODS = ("vandermonde", "lagrange", "newton")
REFERENCE_BGR = (0, 0, 255)


def plot_color(method):
    return tuple(channel / 255 for channel in METHODS[method]["bgr"][::-1])
