# Trajectory Reconstruction from Video Using Numerical Interpolation

This project studies the reconstruction of vehicle trajectories from
traffic videos recorded with a fixed camera. Some trajectory samples are
artificially hidden and reconstructed using different interpolation
methods; the estimates are then compared with the original samples.

The complete workflow is:

```text
video → detection and tracking → observed trajectories
      → sample masking → interpolation
      → pixel evaluation
      → road-plane calibration
      → metric and kinematic evaluation
```

## Main results

The main benchmark uses:

- 2 Urban Tracker videos processed in full;
- 12 short illustrative clips;
- 5.517 gaps shared by all methods;
- gaps of 3, 6, 12, and 24 frames;
- 4 visible points before and 4 after each gap;
- 8 interpolation methods;
- 44.136 evaluations without numerical failures;
- 406 gaps fully contained within the calibrated metric areas.

For these scenes, **linear S1 is the most accurate and stable method**:

- it achieves the best ADE and RMS for position;
- it keeps kinematic error lower on long gaps;
- it has a lower computational cost;
- it does not introduce global oscillations like high-degree polynomials.

**Natural S3** and **constrained S3** are regular alternatives with
similar performance. Vandermonde, Lagrange, and Newton represent the same
polynomial on the same nodes: the formulation and evaluation change, not
the interpolating function. S2 and Floater–Hormann are extensions added to
the comparison.

### Reconstruction comparison

![Error comparison as the gap varies](reports/generated/course/course_comparison.png)

### Metric comparison on the road plane

![Error comparison in pixels and meters](reports/generated/ground/metric_comparison.png)

The metric comparison uses only the 406 gaps for which both the visible
and hidden points belong to the calibrated area. The reference is the
projection of the YOLO/ByteTrack observations, not an independent GPS
measurement.

### Calibration coverage

![Valid calibration areas](reports/generated/ground/calibration_coverage.png)

### Effect of interpolation nodes

![Runge experiment and Chebyshev nodes](reports/generated/course/experiments/chebyshev_runge.png)

The synthetic experiment shows that, for high-degree global polynomials,
Chebyshev nodes reduce oscillations compared with equally spaced nodes.

## Kinematics

Velocity, acceleration, and heading are not interpolated with a separate
model. The East and North metric coordinates are interpolated and their
derivatives are computed:

$$
v_E(t)=E'(t),\qquad v_N(t)=N'(t),\qquad
V(t)=\sqrt{v_E(t)^2+v_N(t)^2}
$$

$$
\theta(t)=
\left[
\frac{180}{\pi}\mathrm{atan2}(v_E(t),v_N(t))+360
\right]\mathbin{\%} 360
$$

The corresponding computation is:

```python
v_e = model_e.derivative(query_times, order=1)
v_n = model_n.derivative(query_times, order=1)
a_e = model_e.derivative(query_times, order=2)
a_n = model_n.derivative(query_times, order=2)
speed = np.hypot(v_e, v_n)
heading = (np.degrees(np.arctan2(v_e, v_n)) + 360) % 360
heading[speed < 0.5] = np.nan
```

The kinematic evaluation was performed on the 406 valid metric gaps.
The reference is obtained using finite differences on the complete
projected trajectory; it is therefore a descriptive estimate based on
YOLO/ByteTrack, not independent GPS or inertial ground truth.

For 24-frame gaps:

| Method | Velocity MAE (m/s) | Acceleration MAE (m/s²) | Heading MAE (°) |
|---|---:|---:|---:|
| S1 | 0,7607 | 19,5135 | 24,2816 |
| Natural S3 | 0,9262 | 20,0055 | 26,9254 |
| Clamped S3 | 0,9276 | 20,0034 | 26,9037 |
| S2 | 1,4928 | 21,6733 | 35,2215 |
| Vandermonde / Lagrange / Newton | 8,7811 | 90,9516 | 69,3162 |
| Floater–Hormann | 27,1535 | 271,3230 | 81,0957 |

Complete report: [KINEMATICS.md](data/urbantracker/results/ground/KINEMATICS.md).

## Compared methods

### Course methods

- interpolation in the monomial basis using a Vandermonde matrix;
- Lagrange polynomials;
- Newton form with divided differences and Horner's scheme;
- linear S1 spline;
- natural cubic S3 spline;
- constrained cubic spline;
- periodic cubic spline;
- Chebyshev nodes;
- trigonometric interpolation for periodic data.

### Project extensions

- quadratic S2 spline;
- Floater–Hormann barycentric rational interpolation;
- benchmark on real videos;
- extraction of velocity, acceleration, and heading;
- road-plane calibration and conversion to metric coordinates.

## Data and experimental protocol

The videos used are:

| Scene | Frames | Approximate duration |
|---|---:|---:|
| Sherbrooke | 4.000 | 2 min 13 s |
| René-Lévesque | 8.501 | 4 min 44 s |

The trajectories are constructed from the *bottom center* point of the
bounding boxes:

$$
u=\frac{u_{\min}+u_{\max}}{2},\qquad v=v_{\max}.
$$

YOLO11n detects the cars and ByteTrack maintains their identities over
time. The protocol is *post-tracking*: identities are assigned before
sample masking.

The main metrics are:

$$
\mathrm{ADE}
=\frac{1}{M}\sum_{i=1}^{M}\lVert P_i-\widehat P_i\rVert_2,
$$

$$
\mathrm{RMS}_P
=\sqrt{\frac{1}{M}\sum_{i=1}^{M}
\lVert P_i-\widehat P_i\rVert_2^2}
$$

## Videos and clips

- [Index of the 12 short clips](reports/generated/course/clips/INDEX.md)
- [Complete René-Lévesque video](reports/generated/static_full/full_reconstruction_urban_rene.mp4)
- [Complete Sherbrooke video](reports/generated/static_full/full_reconstruction_urban_sherbrooke.mp4)
- [Pixel benchmark report](reports/generated/course/RESULTS.md)
- [Metric comparison report](reports/generated/ground/RESULTS.md)

Preview of a complete reconstruction:

![Reconstruction snapshot](reports/generated/static_full/snapshot_urban_rene_04250.jpg)

## Repository structure

```text
.
├── relazione_progetto.pdf       # Final report
├── src/                         # Pipeline code
├── tests/                       # Numerical and geometric tests
├── configs/                     # Experiment configurations
├── calibration/                 # Calibrations and checkpoint templates
├── data/                        # Prepared datasets, tracking, and results
├── reports/generated/           # Produced tables, plots, clips, and videos
├── reports/latex/               # LaTeX source and Overleaf package
├── models/                      # YOLO models
└── docs/                        # Operational documentation
```

The final report is available directly in the root:
[relazione_progetto.pdf](relazione_progetto.pdf).

## Reproduction

From the main directory:

```bash
python3 -m unittest discover -s tests -v

python3 -m src.benchmark
python3 -m src.course_experiments
python3 -m src.passage_clips
python3 -m src.course_report --verify-clips

python3 -m src.project_ground
python3 -m src.metric_benchmark
python3 -m src.kinematic_benchmark
python3 -m src.ground_report

python3 reports/latex/build_report.py
```

For the Python environment:

```bash
pip install -r docs/requirements.txt
```

Video tracking and encoding may require FFmpeg, CUDA, and NVENC.
Operational details are available in [docs/esecuzione.md](docs/esecuzione.md).

## Additional documentation

- [Methods and experiments](docs/metodi_ed_esperimenti.md)
- [Road-plane calibration](docs/calibrazione.md)
- [Pipeline execution](docs/esecuzione.md)
- [Fixed-camera videos](docs/video_camera_fissa.md)
- [LaTeX source of the report](reports/latex/relazione_progetto.tex)
- [Complete kinematics report](data/urbantracker/results/ground/KINEMATICS.md)

## Limitations and interpretation

- The reference comes from YOLO/ByteTrack, not from independent manual
  annotations.
- Metric calibration is valid only in the area covered by the control
  points and the road plane.
- Calibration residuals do not replace independent checkpoints.
- Heading and acceleration are more sensitive to noise and interpolant
  oscillations than position.
- The quantitative conclusions apply to these scenes, these masks, and
  this experimental configuration.
