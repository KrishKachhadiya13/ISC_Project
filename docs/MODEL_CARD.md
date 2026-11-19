# StegaGuard Model Card

## Detectors and the StegNet-Lite CNN (`cnn_v1`)

### Detectors in this project

| Detector | Type | Training |
|---|---|---|
| Statistical (untrained) | Average of chi-square p-value, RS and SPA estimates, threshold 0.5 | None; a transparent rule-based baseline |
| Classical ML | `HistGradientBoostingClassifier` on 1,068 hand-crafted features (chi-square, RS, SPA, LSB statistics, SPAM-lite); a Random Forest is also supported but too large to commit | `scripts/train_classical.py` on BOSSbase |
| CNN (`cnn_v1`) | StegNet-Lite, described below | `scripts/train_cnn.py` on BOSSbase |
| Ensemble | Weighted average of Classical ML and CNN; weight and thresholds chosen on validation only | `scripts/evaluate.py` |

Results below are written by `python -m scripts.make_model_card` from `results/metrics.json` and
`models/cnn_v1.json`; do not edit them by hand.

<!-- RESULTS:START -->

### Status

**Trained.** `cnn_v1` completed 35 epochs (best epoch 27) in 1.52 h on `cuda` with seed 1337; training methods: lsb_replace, lsb_match. Calibration temperature 0.541. Dataset: BOSSbase 1.01 from Kaggle (lunan0/bossbase-1-01) (splits {'test': 1500, 'train': 7000, 'val': 1500}).

Results generated: 2026-11-18T19:47:14+00:00.

### Test results

All values are on held-out, cover-disjoint test images. Brackets are bootstrap 95% intervals where computed. P_E and TPR@1%FPR are shown as – when unavailable.

#### LSB matching, keyed embedding

| bpp | Detector | ROC-AUC | P_E | TPR @ 1% FPR | Accuracy |
|---|---|---|---|---|---|
| 0.05 | Classical ML (HGB) | 0.662 [0.64, 0.68] | 0.367 [0.35, 0.38] | 0.028 | 0.559 |
| 0.05 | CNN (StegNet-Lite) | 0.885 [0.87, 0.90] | 0.198 [0.18, 0.21] | 0.327 | 0.741 |
| 0.05 | Ensemble (HGB + CNN) | 0.820 [0.81, 0.83] | 0.261 [0.24, 0.27] | 0.183 | 0.735 |
| 0.05 | Statistical (untrained) | 0.534 [0.51, 0.55] | 0.469 [0.45, 0.48] | 0.009 | 0.500 |
| 0.1 | Classical ML (HGB) | 0.781 [0.77, 0.80] | 0.282 [0.27, 0.30] | 0.059 | 0.665 |
| 0.1 | CNN (StegNet-Lite) | 0.960 [0.95, 0.97] | 0.118 [0.11, 0.13] | 0.617 | 0.869 |
| 0.1 | Ensemble (HGB + CNN) | 0.947 [0.94, 0.95] | 0.126 [0.11, 0.14] | 0.507 | 0.871 |
| 0.1 | Statistical (untrained) | 0.536 [0.52, 0.56] | 0.470 [0.45, 0.48] | 0.011 | 0.500 |
| 0.2 | Classical ML (HGB) | 0.871 [0.86, 0.88] | 0.211 [0.20, 0.22] | 0.161 | 0.774 |
| 0.2 | CNN (StegNet-Lite) | 0.987 [0.98, 0.99] | 0.065 [0.06, 0.07] | 0.810 | 0.930 |
| 0.2 | Ensemble (HGB + CNN) | 0.986 [0.98, 0.99] | 0.065 [0.05, 0.07] | 0.761 | 0.905 |
| 0.2 | Statistical (untrained) | 0.550 [0.53, 0.57] | 0.456 [0.44, 0.47] | 0.021 | 0.500 |
| 0.4 | Classical ML (HGB) | 0.926 [0.92, 0.94] | 0.156 [0.14, 0.17] | 0.275 | 0.843 |
| 0.4 | CNN (StegNet-Lite) | 0.994 [0.99, 1.00] | 0.047 [0.04, 0.05] | 0.888 | 0.946 |
| 0.4 | Ensemble (HGB + CNN) | 0.995 [0.99, 1.00] | 0.044 [0.04, 0.05] | 0.895 | 0.909 |
| 0.4 | Statistical (untrained) | 0.544 [0.52, 0.56] | 0.467 [0.45, 0.47] | 0.037 | 0.500 |
| 1 | Classical ML (HGB) | 0.977 [0.97, 0.98] | 0.081 [0.07, 0.09] | 0.698 | 0.885 |
| 1 | CNN (StegNet-Lite) | 0.996 [1.00, 1.00] | 0.036 [0.03, 0.04] | 0.931 | 0.949 |
| 1 | Ensemble (HGB + CNN) | 0.997 [1.00, 1.00] | 0.032 [0.03, 0.04] | 0.937 | 0.909 |
| 1 | Statistical (untrained) | 0.550 [0.53, 0.57] | 0.461 [0.44, 0.47] | 0.050 | 0.501 |

#### LSB matching, sequential embedding

| bpp | Detector | ROC-AUC | P_E | TPR @ 1% FPR | Accuracy |
|---|---|---|---|---|---|
| 0.05 | Classical ML (HGB) | 0.745 [0.73, 0.76] | 0.320 [0.30, 0.33] | 0.055 | 0.639 |
| 0.05 | CNN (StegNet-Lite) | 0.767 [0.75, 0.78] | 0.298 [0.28, 0.31] | 0.169 | 0.646 |
| 0.05 | Ensemble (HGB + CNN) | 0.793 [0.77, 0.81] | 0.280 [0.26, 0.29] | 0.152 | 0.691 |
| 0.05 | Statistical (untrained) | 0.509 [0.49, 0.53] | 0.485 [0.47, 0.49] | 0.013 | 0.500 |
| 0.1 | Classical ML (HGB) | 0.840 [0.83, 0.85] | 0.248 [0.23, 0.26] | 0.197 | 0.736 |
| 0.1 | CNN (StegNet-Lite) | 0.823 [0.81, 0.84] | 0.249 [0.23, 0.26] | 0.272 | 0.707 |
| 0.1 | Ensemble (HGB + CNN) | 0.869 [0.86, 0.88] | 0.206 [0.19, 0.22] | 0.285 | 0.770 |
| 0.1 | Statistical (untrained) | 0.511 [0.49, 0.53] | 0.481 [0.47, 0.49] | 0.022 | 0.500 |
| 0.2 | Classical ML (HGB) | 0.898 [0.89, 0.91] | 0.195 [0.18, 0.21] | 0.347 | 0.801 |
| 0.2 | CNN (StegNet-Lite) | 0.902 [0.89, 0.91] | 0.188 [0.17, 0.20] | 0.492 | 0.803 |
| 0.2 | Ensemble (HGB + CNN) | 0.929 [0.92, 0.94] | 0.143 [0.13, 0.15] | 0.511 | 0.856 |
| 0.2 | Statistical (untrained) | 0.520 [0.50, 0.54] | 0.474 [0.46, 0.48] | 0.033 | 0.500 |
| 0.4 | Classical ML (HGB) | 0.935 [0.93, 0.94] | 0.150 [0.14, 0.16] | 0.489 | 0.839 |
| 0.4 | CNN (StegNet-Lite) | 0.968 [0.96, 0.97] | 0.093 [0.08, 0.10] | 0.767 | 0.905 |
| 0.4 | Ensemble (HGB + CNN) | 0.976 [0.97, 0.98] | 0.086 [0.08, 0.09] | 0.781 | 0.895 |
| 0.4 | Statistical (untrained) | 0.524 [0.50, 0.54] | 0.476 [0.46, 0.48] | 0.039 | 0.500 |
| 1 | Classical ML (HGB) | 0.978 [0.97, 0.98] | 0.078 [0.07, 0.09] | 0.696 | 0.883 |
| 1 | CNN (StegNet-Lite) | 0.996 [1.00, 1.00] | 0.035 [0.03, 0.04] | 0.932 | 0.948 |
| 1 | Ensemble (HGB + CNN) | 0.997 [1.00, 1.00] | 0.032 [0.03, 0.04] | 0.939 | 0.909 |
| 1 | Statistical (untrained) | 0.520 [0.50, 0.54] | 0.472 [0.45, 0.48] | 0.045 | 0.501 |

#### LSB replacement, keyed embedding

| bpp | Detector | ROC-AUC | P_E | TPR @ 1% FPR | Accuracy |
|---|---|---|---|---|---|
| 0.05 | Classical ML (HGB) | 0.897 [0.89, 0.91] | 0.195 [0.18, 0.21] | 0.305 | 0.803 |
| 0.05 | CNN (StegNet-Lite) | 0.885 [0.87, 0.90] | 0.200 [0.18, 0.21] | 0.309 | 0.739 |
| 0.05 | Ensemble (HGB + CNN) | 0.912 [0.90, 0.92] | 0.154 [0.14, 0.17] | 0.351 | 0.839 |
| 0.05 | Statistical (untrained) | 0.866 [0.85, 0.88] | 0.165 [0.15, 0.18] | 0.023 | 0.500 |
| 0.1 | Classical ML (HGB) | 0.979 [0.97, 0.98] | 0.076 [0.07, 0.08] | 0.787 | 0.883 |
| 0.1 | CNN (StegNet-Lite) | 0.959 [0.95, 0.96] | 0.120 [0.11, 0.13] | 0.599 | 0.867 |
| 0.1 | Ensemble (HGB + CNN) | 0.974 [0.97, 0.98] | 0.091 [0.08, 0.10] | 0.675 | 0.905 |
| 0.1 | Statistical (untrained) | 0.955 [0.95, 0.96] | 0.073 [0.06, 0.08] | 0.055 | 0.500 |
| 0.2 | Classical ML (HGB) | 0.996 [0.99, 1.00] | 0.028 [0.02, 0.03] | 0.947 | 0.898 |
| 0.2 | CNN (StegNet-Lite) | 0.985 [0.98, 0.99] | 0.071 [0.06, 0.08] | 0.796 | 0.925 |
| 0.2 | Ensemble (HGB + CNN) | 0.992 [0.99, 0.99] | 0.051 [0.04, 0.06] | 0.849 | 0.909 |
| 0.2 | Statistical (untrained) | 0.994 [0.99, 1.00] | 0.023 [0.02, 0.03] | 0.875 | 0.500 |
| 0.4 | Classical ML (HGB) | 0.999 [1.00, 1.00] | 0.007 [0.00, 0.01] | 0.993 | 0.899 |
| 0.4 | CNN (StegNet-Lite) | 0.993 [0.99, 1.00] | 0.048 [0.04, 0.05] | 0.891 | 0.944 |
| 0.4 | Ensemble (HGB + CNN) | 0.997 [1.00, 1.00] | 0.029 [0.02, 0.03] | 0.920 | 0.909 |
| 0.4 | Statistical (untrained) | 0.999 [1.00, 1.00] | 0.001 [0.00, 0.00] | 0.999 | 0.500 |
| 1 | Classical ML (HGB) | 0.999 [1.00, 1.00] | 0.002 [0.00, 0.00] | 0.998 | 0.898 |
| 1 | CNN (StegNet-Lite) | 0.996 [1.00, 1.00] | 0.034 [0.03, 0.04] | 0.932 | 0.950 |
| 1 | Ensemble (HGB + CNN) | 0.998 [1.00, 1.00] | 0.022 [0.02, 0.03] | 0.954 | 0.909 |
| 1 | Statistical (untrained) | 1.000 [1.00, 1.00] | 0.000 [0.00, 0.00] | 1.000 | 0.752 |

#### LSB replacement, sequential embedding

| bpp | Detector | ROC-AUC | P_E | TPR @ 1% FPR | Accuracy |
|---|---|---|---|---|---|
| 0.05 | Classical ML (HGB) | 0.889 [0.88, 0.90] | 0.193 [0.18, 0.21] | 0.352 | 0.797 |
| 0.05 | CNN (StegNet-Lite) | 0.746 [0.73, 0.76] | 0.312 [0.29, 0.32] | 0.136 | 0.625 |
| 0.05 | Ensemble (HGB + CNN) | 0.847 [0.83, 0.86] | 0.198 [0.18, 0.21] | 0.176 | 0.761 |
| 0.05 | Statistical (untrained) | 0.873 [0.86, 0.89] | 0.167 [0.15, 0.18] | 0.038 | 0.500 |
| 0.1 | Classical ML (HGB) | 0.968 [0.96, 0.97] | 0.088 [0.08, 0.10] | 0.764 | 0.873 |
| 0.1 | CNN (StegNet-Lite) | 0.810 [0.79, 0.82] | 0.261 [0.25, 0.28] | 0.261 | 0.701 |
| 0.1 | Ensemble (HGB + CNN) | 0.909 [0.90, 0.92] | 0.127 [0.12, 0.14] | 0.332 | 0.867 |
| 0.1 | Statistical (untrained) | 0.952 [0.94, 0.96] | 0.090 [0.08, 0.10] | 0.196 | 0.500 |
| 0.2 | Classical ML (HGB) | 0.990 [0.99, 0.99] | 0.043 [0.04, 0.05] | 0.912 | 0.892 |
| 0.2 | CNN (StegNet-Lite) | 0.899 [0.89, 0.91] | 0.184 [0.17, 0.20] | 0.487 | 0.802 |
| 0.2 | Ensemble (HGB + CNN) | 0.952 [0.95, 0.96] | 0.100 [0.09, 0.11] | 0.563 | 0.898 |
| 0.2 | Statistical (untrained) | 0.989 [0.98, 0.99] | 0.040 [0.03, 0.05] | 0.754 | 0.500 |
| 0.4 | Classical ML (HGB) | 0.998 [1.00, 1.00] | 0.012 [0.01, 0.02] | 0.983 | 0.898 |
| 0.4 | CNN (StegNet-Lite) | 0.965 [0.96, 0.97] | 0.099 [0.09, 0.11] | 0.753 | 0.899 |
| 0.4 | Ensemble (HGB + CNN) | 0.984 [0.98, 0.99] | 0.075 [0.07, 0.08] | 0.801 | 0.907 |
| 0.4 | Statistical (untrained) | 0.999 [1.00, 1.00] | 0.011 [0.01, 0.01] | 0.979 | 0.503 |
| 1 | Classical ML (HGB) | 0.999 [1.00, 1.00] | 0.002 [0.00, 0.00] | 0.999 | 0.899 |
| 1 | CNN (StegNet-Lite) | 0.996 [1.00, 1.00] | 0.036 [0.03, 0.04] | 0.932 | 0.949 |
| 1 | Ensemble (HGB + CNN) | 0.998 [1.00, 1.00] | 0.023 [0.02, 0.03] | 0.949 | 0.909 |
| 1 | Statistical (untrained) | 1.000 [1.00, 1.00] | 0.000 [0.00, 0.00] | 1.000 | 0.759 |

#### HILL simulation (unseen in training), simulated embedding

| bpp | Detector | ROC-AUC | P_E | TPR @ 1% FPR | Accuracy |
|---|---|---|---|---|---|
| 0.05 | Classical ML (HGB) | 0.504 [0.47, 0.54] | 0.489 [0.45, 0.49] | 0.014 | 0.498 |
| 0.05 | CNN (StegNet-Lite) | 0.503 [0.47, 0.54] | 0.494 [0.46, 0.49] | 0.012 | 0.501 |
| 0.05 | Ensemble (HGB + CNN) | 0.504 [0.47, 0.54] | 0.489 [0.45, 0.50] | 0.014 | 0.502 |
| 0.05 | Statistical (untrained) | 0.500 [0.47, 0.53] | 0.491 [0.46, 0.50] | 0.012 | 0.500 |
| 0.1 | Classical ML (HGB) | 0.511 [0.48, 0.55] | 0.481 [0.44, 0.49] | 0.016 | 0.499 |
| 0.1 | CNN (StegNet-Lite) | 0.508 [0.47, 0.54] | 0.487 [0.45, 0.49] | 0.014 | 0.501 |
| 0.1 | Ensemble (HGB + CNN) | 0.511 [0.48, 0.55] | 0.481 [0.44, 0.49] | 0.016 | 0.501 |
| 0.1 | Statistical (untrained) | 0.497 [0.46, 0.53] | 0.485 [0.45, 0.50] | 0.010 | 0.500 |
| 0.2 | Classical ML (HGB) | 0.518 [0.48, 0.55] | 0.478 [0.44, 0.49] | 0.020 | 0.509 |
| 0.2 | CNN (StegNet-Lite) | 0.528 [0.50, 0.56] | 0.472 [0.44, 0.48] | 0.018 | 0.509 |
| 0.2 | Ensemble (HGB + CNN) | 0.523 [0.48, 0.56] | 0.479 [0.44, 0.49] | 0.020 | 0.510 |
| 0.2 | Statistical (untrained) | 0.503 [0.46, 0.54] | 0.483 [0.45, 0.50] | 0.006 | 0.500 |
| 0.4 | Classical ML (HGB) | 0.570 [0.53, 0.61] | 0.441 [0.40, 0.46] | 0.036 | 0.533 |
| 0.4 | CNN (StegNet-Lite) | 0.595 [0.56, 0.63] | 0.431 [0.39, 0.45] | 0.070 | 0.541 |
| 0.4 | Ensemble (HGB + CNN) | 0.584 [0.55, 0.62] | 0.434 [0.40, 0.45] | 0.080 | 0.548 |
| 0.4 | Statistical (untrained) | 0.508 [0.47, 0.54] | 0.478 [0.44, 0.50] | 0.010 | 0.500 |
| 1 | Classical ML (HGB) | 0.762 [0.73, 0.79] | 0.299 [0.27, 0.32] | 0.202 | 0.690 |
| 1 | CNN (StegNet-Lite) | 0.848 [0.82, 0.87] | 0.234 [0.21, 0.25] | 0.470 | 0.755 |
| 1 | Ensemble (HGB + CNN) | 0.827 [0.80, 0.85] | 0.236 [0.21, 0.26] | 0.494 | 0.760 |
| 1 | Statistical (untrained) | 0.502 [0.47, 0.54] | 0.484 [0.45, 0.50] | 0.012 | 0.500 |

#### 2-LSB replacement (unseen in training), keyed embedding

| bpp | Detector | ROC-AUC | P_E | TPR @ 1% FPR | Accuracy |
|---|---|---|---|---|---|
| 0.05 | Classical ML (HGB) | 0.721 [0.70, 0.74] | 0.333 [0.32, 0.34] | 0.046 | 0.622 |
| 0.05 | CNN (StegNet-Lite) | 0.972 [0.97, 0.98] | 0.102 [0.09, 0.11] | 0.707 | 0.892 |
| 0.05 | Ensemble (HGB + CNN) | 0.940 [0.93, 0.95] | 0.129 [0.12, 0.14] | 0.455 | 0.868 |
| 0.05 | Statistical (untrained) | 0.695 [0.68, 0.71] | 0.329 [0.31, 0.34] | 0.013 | 0.500 |
| 0.1 | Classical ML (HGB) | 0.867 [0.85, 0.88] | 0.219 [0.20, 0.23] | 0.185 | 0.775 |
| 0.1 | CNN (StegNet-Lite) | 0.990 [0.99, 0.99] | 0.060 [0.05, 0.07] | 0.849 | 0.935 |
| 0.1 | Ensemble (HGB + CNN) | 0.985 [0.98, 0.99] | 0.065 [0.06, 0.07] | 0.777 | 0.905 |
| 0.1 | Statistical (untrained) | 0.817 [0.80, 0.83] | 0.215 [0.20, 0.23] | 0.018 | 0.500 |
| 0.2 | Classical ML (HGB) | 0.967 [0.96, 0.97] | 0.094 [0.08, 0.10] | 0.696 | 0.874 |
| 0.2 | CNN (StegNet-Lite) | 0.995 [0.99, 1.00] | 0.044 [0.04, 0.05] | 0.917 | 0.946 |
| 0.2 | Ensemble (HGB + CNN) | 0.995 [0.99, 1.00] | 0.038 [0.03, 0.04] | 0.912 | 0.908 |
| 0.2 | Statistical (untrained) | 0.927 [0.92, 0.94] | 0.101 [0.09, 0.11] | 0.042 | 0.500 |
| 0.4 | Classical ML (HGB) | 0.992 [0.99, 0.99] | 0.041 [0.03, 0.05] | 0.910 | 0.895 |
| 0.4 | CNN (StegNet-Lite) | 0.996 [1.00, 1.00] | 0.034 [0.03, 0.04] | 0.930 | 0.949 |
| 0.4 | Ensemble (HGB + CNN) | 0.998 [1.00, 1.00] | 0.028 [0.02, 0.03] | 0.947 | 0.909 |
| 0.4 | Statistical (untrained) | 0.985 [0.98, 0.99] | 0.029 [0.02, 0.03] | 0.362 | 0.500 |
| 1 | Classical ML (HGB) | 0.999 [1.00, 1.00] | 0.005 [0.00, 0.01] | 0.995 | 0.899 |
| 1 | CNN (StegNet-Lite) | 0.997 [1.00, 1.00] | 0.034 [0.03, 0.04] | 0.939 | 0.950 |
| 1 | Ensemble (HGB + CNN) | 0.998 [1.00, 1.00] | 0.022 [0.02, 0.03] | 0.953 | 0.909 |
| 1 | Statistical (untrained) | 0.999 [1.00, 1.00] | 0.001 [0.00, 0.00] | 0.999 | 0.500 |

#### S-UNIWARD simulation (unseen in training), simulated embedding

| bpp | Detector | ROC-AUC | P_E | TPR @ 1% FPR | Accuracy |
|---|---|---|---|---|---|
| 0.05 | Classical ML (HGB) | 0.503 [0.47, 0.54] | 0.488 [0.45, 0.49] | 0.016 | 0.500 |
| 0.05 | CNN (StegNet-Lite) | 0.504 [0.47, 0.54] | 0.493 [0.45, 0.50] | 0.010 | 0.501 |
| 0.05 | Ensemble (HGB + CNN) | 0.503 [0.47, 0.54] | 0.491 [0.45, 0.50] | 0.014 | 0.506 |
| 0.05 | Statistical (untrained) | 0.501 [0.47, 0.53] | 0.491 [0.46, 0.50] | 0.010 | 0.500 |
| 0.1 | Classical ML (HGB) | 0.508 [0.47, 0.55] | 0.484 [0.45, 0.49] | 0.016 | 0.508 |
| 0.1 | CNN (StegNet-Lite) | 0.511 [0.47, 0.55] | 0.486 [0.45, 0.49] | 0.010 | 0.502 |
| 0.1 | Ensemble (HGB + CNN) | 0.508 [0.47, 0.54] | 0.487 [0.45, 0.49] | 0.016 | 0.502 |
| 0.1 | Statistical (untrained) | 0.504 [0.47, 0.54] | 0.486 [0.45, 0.50] | 0.010 | 0.500 |
| 0.2 | Classical ML (HGB) | 0.527 [0.49, 0.56] | 0.470 [0.44, 0.49] | 0.022 | 0.511 |
| 0.2 | CNN (StegNet-Lite) | 0.539 [0.50, 0.57] | 0.468 [0.43, 0.48] | 0.028 | 0.513 |
| 0.2 | Ensemble (HGB + CNN) | 0.533 [0.50, 0.57] | 0.465 [0.43, 0.48] | 0.028 | 0.517 |
| 0.2 | Statistical (untrained) | 0.498 [0.46, 0.53] | 0.483 [0.45, 0.50] | 0.008 | 0.500 |
| 0.4 | Classical ML (HGB) | 0.583 [0.54, 0.62] | 0.433 [0.40, 0.45] | 0.038 | 0.544 |
| 0.4 | CNN (StegNet-Lite) | 0.635 [0.60, 0.67] | 0.408 [0.37, 0.43] | 0.118 | 0.568 |
| 0.4 | Ensemble (HGB + CNN) | 0.611 [0.57, 0.64] | 0.416 [0.38, 0.44] | 0.106 | 0.570 |
| 0.4 | Statistical (untrained) | 0.503 [0.47, 0.54] | 0.482 [0.45, 0.50] | 0.008 | 0.500 |
| 1 | Classical ML (HGB) | 0.780 [0.75, 0.81] | 0.285 [0.25, 0.31] | 0.196 | 0.709 |
| 1 | CNN (StegNet-Lite) | 0.883 [0.86, 0.90] | 0.194 [0.17, 0.21] | 0.564 | 0.802 |
| 1 | Ensemble (HGB + CNN) | 0.862 [0.84, 0.89] | 0.198 [0.17, 0.22] | 0.572 | 0.789 |
| 1 | Statistical (untrained) | 0.494 [0.46, 0.53] | 0.495 [0.46, 0.50] | 0.010 | 0.500 |

### Unseen techniques

The classical model and the CNN were trained only on lsb_replace, lsb_match. The tables above also score them on: HILL simulation (unseen in training), 2-LSB replacement (unseen in training), S-UNIWARD simulation (unseen in training). Nothing was retrained for these, so the numbers show how far each detector generalises to a technique it has not seen. Thresholds and ensemble weights were fixed on validation data of the trained techniques only. Simulated schemes change pixels the way the real scheme would but carry no recoverable message (see `app/core/stego/simulate.py`); they use a fixed subset of the test covers, so their sample counts are smaller (see the sample counts in the tables).

### Where the detectors struggle on the trained techniques (computed from the results)

**Classical ML (HGB)** — lowest ROC-AUC:
- LSB matching, keyed, 0.05 bpp: ROC-AUC 0.662
- LSB matching, sequential, 0.05 bpp: ROC-AUC 0.745
- LSB matching, keyed, 0.1 bpp: ROC-AUC 0.781

**CNN (StegNet-Lite)** — lowest ROC-AUC:
- LSB replacement, sequential, 0.05 bpp: ROC-AUC 0.746
- LSB matching, sequential, 0.05 bpp: ROC-AUC 0.767
- LSB replacement, sequential, 0.1 bpp: ROC-AUC 0.810

**Ensemble (HGB + CNN)** — lowest ROC-AUC:
- LSB matching, sequential, 0.05 bpp: ROC-AUC 0.793
- LSB matching, keyed, 0.05 bpp: ROC-AUC 0.820
- LSB replacement, sequential, 0.05 bpp: ROC-AUC 0.847

### Mismatch experiment

Not run (no `cnn_mismatch_replace` model).

### Evaluation notes

- All detectors are scored on the same fixed, seeded test images (cover-disjoint from training).
- Thresholds and ensemble weights were chosen on validation data only.
- Ensemble = 0.7×classical + 0.3×CNN, weight chosen by validation ROC-AUC.
- The classical model was trained on a separate Kaggle run of the same BOSSbase split; its stego training examples used different random keys than these fixed sets.
- The statistical detector is untrained; its 0.5 threshold is a fixed rule, not tuned.
- CNN CPU inference latency: 48.3 ms per image (single 256×256 image).

<!-- RESULTS:END -->

### Intended use

An educational binary detector for distinguishing clean grayscale natural
images from images modified with the project's LSB replacement or LSB matching
embedding pipeline. It is intended for demonstration and comparative research,
not forensic proof, attribution, or consequential decisions.

### Architecture

Input is a normalized `1×256×256` grayscale image. The first layer is a
non-trainable 5×5 KV high-pass convolution with zero padding; its residual is
clamped to `[-T, T]` (`T=3` by default).

1. Stem: `Conv2d(1,16,3×3) → BatchNorm2d(16) → ReLU`.
2. Stages 1–3: three residual blocks at 16 channels. Each block contains two
   `Conv2d(16,16,3×3) → BatchNorm2d(16)` operations with a residual skip and
   ReLU; no pooling is used in these stages.
3. Stage 4: `Conv2d(16,32,3×3) → BatchNorm2d(32) → ReLU → AvgPool2d(2)`.
4. Stage 5: `Conv2d(32,64,3×3) → BatchNorm2d(64) → ReLU → AvgPool2d(2)`.
5. Stage 6: `Conv2d(64,128,3×3) → BatchNorm2d(128) → ReLU → AvgPool2d(2)`.
6. Adaptive global average pooling and `Linear(128,1)` produce one logit.

The fixed KV weights are excluded from trainable parameter counts. The code
asserts that trainable parameters remain below 2 million.

### Training and evaluation

Training forms a cover/stego pair per cover in each batch. Stego variants use
keyed embedding, a 50/50 mixture of LSB replacement and LSB matching, random
payload bytes, and payload rates sampled from 0.05, 0.1, 0.2, 0.4, and 0.8 bpp.
The first eight epochs use rates at or above 0.4 bpp. AdamW, cosine learning
rate decay, BCE-with-logits, gradient clipping, optional CUDA mixed precision,
and early stopping are used.

Validation and test variants are generated once, seeded, and stored as
hash-checked pairs. Splits are by cover ID (70/15/15); each cover and all its
variants remain in exactly one split. The best checkpoint is selected by
validation ROC-AUC with P_E as the tie-breaker. Temperature scaling is fit on
validation logits only.

Reported metrics include accuracy, precision, recall, F1, ROC-AUC, `P_E`,
TPR at 1% FPR, a validation-selected confusion matrix, and bootstrap 95%
confidence intervals for ROC-AUC and P_E. No metrics are populated by hand until
the full training/evaluation run is completed; the generated results above come only from saved output files.

### Inference and explainability

Images at least 256×256 are scored using up to 16 evenly spaced,
non-overlapping 256×256 tiles; tile logits are averaged. Smaller images are
rejected for CNN detection. RGB images are scored independently per channel;
the mean logit is the primary score and the maximum channel logit is also
reported. This RGB behavior is a limitation because training is grayscale-only.

Grad-CAM from the last convolution and a local mean absolute KV residual-energy
map are returned as PNG heatmaps. These maps indicate model response and are
not proof that hidden data is present or identify its contents.

### Limitations and risks

- Results depend on the embedding implementation, payload rate, image source,
  and train/test distribution. Generalization to unseen sources or algorithms
  is not established by this model card.
- Low-payload LSB matching is expected to be more difficult than high-payload
  LSB replacement; actual performance must come from the saved test metrics.
- The model detects statistical artifacts and can produce false positives and
  false negatives. It cannot verify signatures, decrypt messages, or prove
  covert intent.
- Fixed evaluation salts and keys are generated for offline experiments only;
  they must not be reused for live communication.
