# Valutazione cinematica

Gap metrici valutati: **406**; esclusi dalla calibrazione: 5111.
Le derivate sono calcolate in tempo fisico dagli interpolanti di Est e Nord.
Il riferimento è ottenuto con differenze finite sulla traiettoria completa proiettata: è una stima descrittiva basata su YOLO/ByteTrack, non una ground truth indipendente.
L'heading è valutato solo quando la velocità di riferimento è almeno 0.50 m/s.

| Metodo | Gap | MAE velocità (m/s) | MAE accelerazione (m/s²) | MAE heading (°) | Campioni heading |
|---|---:|---:|---:|---:|---:|
| lagrange | 3 | 1.08070 | 44.30323 | 18.9123 | 312 |
| lagrange | 6 | 1.76763 | 46.47890 | 26.1623 | 576 |
| lagrange | 12 | 3.69793 | 66.83068 | 46.9924 | 859 |
| lagrange | 24 | 8.78110 | 90.95163 | 69.3162 | 1404 |
| newton | 3 | 1.08070 | 44.30323 | 18.9123 | 312 |
| newton | 6 | 1.76763 | 46.47890 | 26.1623 | 576 |
| newton | 12 | 3.69793 | 66.83068 | 46.9924 | 859 |
| newton | 24 | 8.78110 | 90.95163 | 69.3162 | 1404 |
| rational_fh | 3 | 1.89508 | 84.51634 | 25.1841 | 312 |
| rational_fh | 6 | 3.49057 | 108.42304 | 43.9775 | 576 |
| rational_fh | 12 | 9.91181 | 189.51002 | 66.1784 | 859 |
| rational_fh | 24 | 27.15347 | 271.32301 | 81.0957 | 1404 |
| s1 | 3 | 0.58906 | 23.10763 | 8.0560 | 312 |
| s1 | 6 | 0.80216 | 23.82960 | 11.1816 | 576 |
| s1 | 12 | 0.81048 | 22.30247 | 17.7075 | 859 |
| s1 | 24 | 0.76067 | 19.51345 | 24.2816 | 1404 |
| s2 | 3 | 1.34562 | 63.39721 | 16.4344 | 312 |
| s2 | 6 | 1.67322 | 42.25105 | 20.8762 | 576 |
| s2 | 12 | 1.92986 | 30.91516 | 27.6146 | 859 |
| s2 | 24 | 1.49281 | 21.67328 | 35.2215 | 1404 |
| s3_clamped | 3 | 0.77121 | 27.14961 | 13.0302 | 312 |
| s3_clamped | 6 | 0.94154 | 25.15086 | 14.8413 | 576 |
| s3_clamped | 12 | 1.03971 | 23.67931 | 24.7556 | 859 |
| s3_clamped | 24 | 0.92762 | 20.00337 | 26.9037 | 1404 |
| s3_natural | 3 | 0.77116 | 27.14643 | 13.0157 | 312 |
| s3_natural | 6 | 0.94193 | 25.15048 | 14.8497 | 576 |
| s3_natural | 12 | 1.03922 | 23.67728 | 24.7456 | 859 |
| s3_natural | 24 | 0.92617 | 20.00548 | 26.9254 | 1404 |
| vandermonde | 3 | 1.08070 | 44.30323 | 18.9123 | 312 |
| vandermonde | 6 | 1.76763 | 46.47890 | 26.1623 | 576 |
| vandermonde | 12 | 3.69793 | 66.83068 | 46.9924 | 859 |
| vandermonde | 24 | 8.78110 | 90.95163 | 69.3162 | 1404 |
