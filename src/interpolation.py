"""Course interpolants with physical-time derivatives and no extrapolation."""

import math
import numpy as np
from numpy.polynomial import Polynomial
from scipy.interpolate import CubicSpline, PPoly, make_interp_spline


class LagrangePolynomial:
    """Direct Lagrange basis; no conversion to monomials for value evaluation."""

    def __init__(self, nodes, values):
        self.nodes, self.values = nodes, values
        self.denominators = np.array([np.prod(node - np.delete(nodes, i)) for i, node in enumerate(nodes)])

    def __call__(self, query, nu=0):
        result = np.zeros_like(query, dtype=float)
        for i, value in enumerate(self.values):
            other = np.delete(self.nodes, i)
            if nu:
                basis = Polynomial.fromroots(other) / self.denominators[i]
                result += value * basis.deriv(nu)(query)
            else:
                result += value * np.prod(query[..., None] - other, axis=-1) / self.denominators[i]
        return result


class NewtonPolynomial:
    """In-place divided differences and generalized Horner, including derivatives."""

    def __init__(self, nodes, values):
        self.nodes = nodes
        self.coefficients = values.copy()
        for order in range(1, len(nodes)):
            self.coefficients[order:] = (
                (self.coefficients[order:] - self.coefficients[order - 1:-1])
                / (nodes[order:] - nodes[:-order])
            )

    def __call__(self, query, nu=0):
        derivatives = np.zeros((nu + 1,) + query.shape)
        derivatives[0] = self.coefficients[-1]
        for i in range(len(self.nodes) - 2, -1, -1):
            for order in range(nu, 0, -1):
                derivatives[order] = ((query - self.nodes[i]) * derivatives[order]
                                      + order * derivatives[order - 1])
            derivatives[0] = self.coefficients[i] + (query - self.nodes[i]) * derivatives[0]
        return derivatives[nu]


class FloaterHormann:
    """Pole-free on the real axis in exact arithmetic; rational degree parameter d.

    The rational family is introduced in the slides. This specific stable
    barycentric construction is an explicitly labeled external extension.
    """

    def __init__(self, nodes, values, degree=3):
        self.nodes, self.values = nodes, values
        d = min(degree, len(nodes) - 1)
        if d < 0 or int(d) != d:
            raise ValueError("Rational degree must be a nonnegative integer")
        d = int(d)
        self.weights = np.zeros(len(nodes))
        for i, node in enumerate(nodes):
            for start in range(max(0, i - d), min(i, len(nodes) - d - 1) + 1):
                indices = [k for k in range(start, start + d + 1) if k != i]
                self.weights[i] += 1 / np.prod(np.abs(node - nodes[indices]))
            self.weights[i] *= (-1.0) ** (i - d)
        self.weights /= np.max(np.abs(self.weights))

    def __call__(self, query, nu=0):
        output = np.empty(query.size)
        for j, point in enumerate(query.ravel()):
            difference = point - self.nodes
            exact = np.flatnonzero(difference == 0)
            numerator, denominator = np.empty(nu + 1), np.empty(nu + 1)
            if len(exact):
                i = exact[0]
                numerator[0] = self.weights[i] * self.values[i]
                denominator[0] = self.weights[i]
                keep = np.arange(len(self.nodes)) != i
                for order in range(1, nu + 1):
                    weights = self.weights[keep] * (-1.0) ** (order - 1) / difference[keep] ** order
                    numerator[order] = weights @ self.values[keep]
                    denominator[order] = weights.sum()
            else:
                for order in range(nu + 1):
                    weights = self.weights * (-1.0) ** order / difference ** (order + 1)
                    numerator[order] = weights @ self.values
                    denominator[order] = weights.sum()
            if denominator[0] == 0 or not np.isfinite(denominator).all():
                raise FloatingPointError("Numerically singular rational denominator")
            # Divide Taylor series; at nodes the common singular factor is removed above.
            coefficients = np.empty(nu + 1)
            for order in range(nu + 1):
                correction = sum(denominator[k] * coefficients[order - k] for k in range(1, order + 1))
                coefficients[order] = (numerator[order] - correction) / denominator[0]
            output[j] = math.factorial(nu) * coefficients[nu]
        return output.reshape(query.shape)


class TrigonometricPolynomial:
    """Real Fourier interpolation system for complete or incomplete periodic grids."""

    def __init__(self, times, values, period, origin):
        if period is None or not np.isfinite(period) or period <= 0 or not np.isfinite(origin):
            raise ValueError("A known positive period is required")
        self.omega, self.origin = 2 * np.pi / period, origin
        phases = np.sort(np.mod((times - origin) / period, 1.0))
        if np.any(np.diff(np.r_[phases, phases[0] + 1]) < 1e-12):
            raise ValueError("Duplicate periodic node: do not include both period endpoints")
        count = len(times)
        self.terms = [("constant", 0)]
        for k in range(1, (count - 1) // 2 + 1):
            self.terms.extend([("cos", k), ("sin", k)])
        if count % 2 == 0:
            self.terms.append(("cos", count // 2))
        matrix = self.design(times)
        self.condition = float(np.linalg.cond(matrix))
        self.coefficients = np.linalg.solve(matrix, values)

    def design(self, times, order=0):
        columns = []
        for kind, frequency in self.terms:
            if kind == "constant":
                columns.append(np.ones_like(times) if order == 0 else np.zeros_like(times))
            else:
                angle = frequency * self.omega * (times - self.origin) + order * np.pi / 2
                function = np.cos if kind == "cos" else np.sin
                columns.append((frequency * self.omega) ** order * function(angle))
        return np.stack(columns, axis=-1)

    def __call__(self, times, nu=0):
        return self.design(times, nu) @ self.coefficients


class Interpolator:
    def __init__(self, method, *, period=None, origin=0.0, endpoint_derivatives=None, rational_degree=3):
        self.method = method
        self.period, self.origin = period, origin
        self.endpoint_derivatives = endpoint_derivatives
        self.rational_degree = rational_degree

    def fit(self, times, values):
        t = np.asarray(times, dtype=float)
        y = np.asarray(values, dtype=float)
        if (t.ndim != 1 or len(t) < 2 or y.ndim != 1 or y.shape != t.shape
                or not np.isfinite(t).all() or not np.isfinite(y).all()
                or np.any(np.diff(t) <= 0)):
            raise ValueError("Need at least two distinct increasing times and finite scalar values")
        self.times = t.copy()
        self.start, self.end = t[0], t[-1]
        self.scale = 2 / (self.end - self.start)
        tau = (t - self.start) * self.scale - 1
        if self.method == "s1":
            self.model = make_interp_spline(tau, y, k=1)
        elif self.method == "s3_natural":
            self.model = CubicSpline(tau, y, bc_type="natural", extrapolate=False)
        elif self.method == "s3_clamped":
            if self.endpoint_derivatives is None:
                n = min(3, len(t))
                left = Polynomial.fit(tau[:n], y[:n], n - 1).deriv()(tau[0])
                right = Polynomial.fit(tau[-n:], y[-n:], n - 1).deriv()(tau[-1])
            else:
                # User-supplied derivatives are in physical time, not normalized tau.
                left, right = np.asarray(self.endpoint_derivatives, dtype=float) / self.scale
            self.model = CubicSpline(tau, y, bc_type=((1, left), (1, right)), extrapolate=False)
        elif self.method == "s3_periodic":
            if y[0] != y[-1]:
                raise ValueError("Periodic spline requires matching endpoint values")
            if self.period is not None and not np.isclose(t[-1] - t[0], self.period):
                raise ValueError("Periodic spline support must span its declared period")
            self.model = CubicSpline(tau, y, bc_type="periodic", extrapolate=False)
        elif self.method == "vandermonde":
            self.model = Polynomial(np.linalg.solve(np.vander(tau, len(t), increasing=True), y))
        elif self.method == "lagrange":
            self.model = LagrangePolynomial(tau, y)
        elif self.method == "newton":
            self.model = NewtonPolynomial(tau, y)
        elif self.method == "rational_fh":
            self.model = FloaterHormann(tau, y, self.rational_degree)
        elif self.method == "trigonometric":
            self.model = TrigonometricPolynomial(t, y, self.period, self.origin)
        elif self.method == "s2":
            # Exactly one piece per observed interval, C1, with c_0=0.
            h = np.diff(tau)
            slopes = np.diff(y) / h
            b = np.empty_like(h)
            c = np.empty_like(h)
            b[0] = slopes[0]
            for i in range(len(h)):
                c[i] = (slopes[i] - b[i]) / h[i]
                if i + 1 < len(h):
                    b[i + 1] = b[i] + 2 * c[i] * h[i]
            self.model = PPoly(np.vstack((c, b, y[:-1])), tau, extrapolate=False)
        else:
            raise ValueError(f"Unknown interpolation method: {self.method}")
        return self

    def predict(self, query_times, order=0):
        if order < 0 or int(order) != order:
            raise ValueError("Derivative order must be a nonnegative integer")
        t = np.asarray(query_times, dtype=float)
        if not np.isfinite(t).all() or np.any(t < self.start) or np.any(t > self.end):
            raise ValueError("Nonfinite query or extrapolation requested")
        tau = (t - self.start) * self.scale - 1
        if self.method == "trigonometric":
            result = np.asarray(self.model(t, nu=int(order)))
        else:
            if self.method == "vandermonde":
                result = np.asarray(self.model.deriv(int(order))(tau))
            else:
                result = np.asarray(self.model(tau, nu=int(order)))
            result = result * self.scale ** order
        # Ordinary derivatives at internal knots may not exist.
        if (self.method == "s1" and order >= 1) or (self.method == "s2" and order >= 2):
            knots = np.isclose(t[..., None], self.times[1:-1], rtol=0, atol=1e-12).any(axis=-1)
            result = np.where(knots, np.nan, result)
        return result

    def derivative(self, query_times, order=1):
        return self.predict(query_times, order=order)
