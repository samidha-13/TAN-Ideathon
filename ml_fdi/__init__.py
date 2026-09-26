"""
ML-assisted Fault Detection and Isolation (FDI) — shadow mode.

This package provides an Isolation Forest anomaly detector that operates
in SHADOW MODE alongside the existing deterministic FDI pipeline.

It does NOT control navigation, reject measurements, or modify EKF inputs.
All predictions are advisory and written to ml_fdi/outputs/.

Modules
-------
feature_engineering : Extract ML-safe features from export CSVs.
"""
