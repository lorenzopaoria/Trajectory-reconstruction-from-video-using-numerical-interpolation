"""WGS84 coordinates and local East/North/Up conversion."""

import numpy as np


def geodetic_to_enu(latitude, longitude, altitude=None, origin=None):
    """Return metres in a tangent plane at origin=(lat, lon, ellipsoid height).

    If altitude is omitted, project onto the WGS84 ellipsoid (height=0).
    This avoids assuming the vertical datum of an external GPS altitude field.
    """
    lat, lon = np.broadcast_arrays(
        np.asarray(latitude, dtype=float), np.asarray(longitude, dtype=float),
    )
    height = np.zeros_like(lat) if altitude is None else np.broadcast_to(altitude, lat.shape)
    if lat.size == 0 or not all(np.isfinite(a).all() for a in (lat, lon, height)):
        raise ValueError("Coordinates must be finite and nonempty")
    if np.any(np.abs(lat) > 90) or np.any(np.abs(lon) > 180):
        raise ValueError("Latitude/longitude outside their ranges")
    if origin is None:
        origin = (lat.flat[0], lon.flat[0], height.flat[0])

    def ecef(latitude_deg, longitude_deg, h):
        phi, lam = np.deg2rad(latitude_deg), np.deg2rad(longitude_deg)
        a = 6378137.0
        f = 1 / 298.257223563
        e2 = f * (2 - f)
        radius = a / np.sqrt(1 - e2 * np.sin(phi) ** 2)
        return np.stack((
            (radius + h) * np.cos(phi) * np.cos(lam),
            (radius + h) * np.cos(phi) * np.sin(lam),
            (radius * (1 - e2) + h) * np.sin(phi),
        ), axis=-1)

    delta = ecef(lat, lon, height) - ecef(*origin)
    phi, lam = np.deg2rad(origin[:2])
    rotation = np.array([
        [-np.sin(lam), np.cos(lam), 0],
        [-np.sin(phi) * np.cos(lam), -np.sin(phi) * np.sin(lam), np.cos(phi)],
        [np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)],
    ])
    return delta @ rotation.T
