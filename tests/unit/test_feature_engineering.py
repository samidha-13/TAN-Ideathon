"""
Unit tests for ml_fdi.feature_engineering.

Tests cover:
  - Exact 13-column output schema
  - Correct terrain observability ordinal encoding
  - Correct one-step backward deltas
  - Correct 10-step causal rolling mean calculation
  - Mission-boundary protection (each mission independent)
  - Forbidden-column exclusion
  - No mutation of the source records
  - Empty input handling
  - Missing column error
  - NaN / non-finite input handling
  - Real export CSV integration (if available)
"""

import copy
import math
import os
import sys
import unittest

# Ensure repository root is on sys.path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from ml_fdi.feature_engineering import (
    build_features,
    load_mission_features,
    FEATURE_COLUMNS,
    FORBIDDEN_COLUMNS,
    _one_step_delta,
    _causal_rolling_mean,
    _extract_float_column,
    _extract_bool_column,
    _extract_terrain_obs_column,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_record(
    tan_match_score=0.5,
    tan_valid="True",
    terrain_obs="MEDIUM",
    uncertainty_lat_m=1.0,
    uncertainty_lon_m=1.0,
    uncertainty_alt_m=0.5,
    estimated_lat=26.5,
    estimated_lon=70.5,
    **extra,
):
    """Create a minimal valid export-CSV-like record dict."""
    row = {
        "timestamp": "0.0",
        "mission_index": "0",
        "estimated_lat": str(estimated_lat),
        "estimated_lon": str(estimated_lon),
        "estimated_alt": "3000.0",
        "nav_mode": "FULL_AID",
        "gnss_accepted": "True",
        "radar_accepted": "True",
        "mag_accepted": "True",
        "tan_valid": str(tan_valid),
        "tan_match_score": str(tan_match_score),
        "tan_residual_m": "1.5",
        "terrain_obs": terrain_obs,
        "magnav_available": "False",
        "magnav_quality": "UNAVAILABLE",
        "uncertainty_lat_m": str(uncertainty_lat_m),
        "uncertainty_lon_m": str(uncertainty_lon_m),
        "uncertainty_alt_m": str(uncertainty_alt_m),
        "fdi_radar": "ACCEPTED",
        "fdi_gnss": "ACCEPTED",
        "fdi_mag": "ACCEPTED",
        "truth_lat": "26.500",
        "truth_lon": "70.500",
        "error_lat_m": "5.0",
        "error_lon_m": "5.0",
        "error_3d_m": "7.07",
        "ins_drift_m": "0.0",
    }
    row.update(extra)
    return row


def _make_records(n, **overrides):
    """Create n records with incremental estimated_lat/lon."""
    records = []
    for i in range(n):
        record_kwargs = {
            "estimated_lat": 26.5 + i * 0.001,
            "estimated_lon": 70.5 + i * 0.001,
            "uncertainty_lat_m": 1.0 + i * 0.1,
            "uncertainty_lon_m": 2.0 + i * 0.05,
            "tan_match_score": 0.5 + i * 0.01,
        }
        record_kwargs.update(overrides)
        row = _make_record(**record_kwargs)
        row["timestamp"] = str(i * 0.1)
        row["mission_index"] = str(i)
        records.append(row)
    return records


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestFeatureColumnsExact(unittest.TestCase):
    """Verify the output has exactly 13 specified feature columns."""

    def test_exact_13_columns(self):
        records = _make_records(5)
        features = build_features(records)
        self.assertEqual(len(features), 5)
        for row in features:
            self.assertEqual(len(row), 13)
            self.assertEqual(set(row.keys()), set(FEATURE_COLUMNS))

    def test_column_order_matches_constant(self):
        records = _make_records(3)
        features = build_features(records)
        for row in features:
            keys = list(row.keys())
            self.assertEqual(tuple(keys), FEATURE_COLUMNS)

    def test_all_values_are_float(self):
        records = _make_records(5)
        features = build_features(records)
        for row in features:
            for col, val in row.items():
                self.assertIsInstance(val, float, f"{col}: {val!r}")

    def test_no_nan_or_inf_in_output(self):
        records = _make_records(5)
        features = build_features(records)
        for row in features:
            for col, val in row.items():
                self.assertTrue(
                    math.isfinite(val),
                    f"{col} has non-finite value: {val}",
                )


class TestForbiddenColumnExclusion(unittest.TestCase):
    """Verify no forbidden column appears in the output."""

    def test_no_forbidden_columns_in_output(self):
        records = _make_records(5)
        features = build_features(records)
        for row in features:
            for col in row.keys():
                self.assertNotIn(
                    col, FORBIDDEN_COLUMNS,
                    f"Forbidden column '{col}' found in output",
                )

    def test_truth_columns_not_present(self):
        truth_cols = {"truth_lat", "truth_lon", "error_lat_m",
                      "error_lon_m", "error_3d_m"}
        records = _make_records(3)
        features = build_features(records)
        for row in features:
            for tc in truth_cols:
                self.assertNotIn(tc, row)

    def test_fdi_output_columns_not_present(self):
        fdi_cols = {"fdi_radar", "fdi_gnss", "fdi_mag"}
        records = _make_records(3)
        features = build_features(records)
        for row in features:
            for fc in fdi_cols:
                self.assertNotIn(fc, row)

    def test_raw_position_not_in_output(self):
        pos_cols = {"estimated_lat", "estimated_lon", "estimated_alt"}
        records = _make_records(3)
        features = build_features(records)
        for row in features:
            for pc in pos_cols:
                self.assertNotIn(pc, row)


class TestTerrainObsOrdinal(unittest.TestCase):
    """Verify terrain observability ordinal encoding."""

    def test_low_encodes_to_0(self):
        records = _make_records(1, terrain_obs="LOW")
        features = build_features(records)
        self.assertEqual(features[0]["terrain_obs_ordinal"], 0.0)

    def test_medium_encodes_to_1(self):
        records = _make_records(1, terrain_obs="MEDIUM")
        features = build_features(records)
        self.assertEqual(features[0]["terrain_obs_ordinal"], 1.0)

    def test_high_encodes_to_2(self):
        records = _make_records(1, terrain_obs="HIGH")
        features = build_features(records)
        self.assertEqual(features[0]["terrain_obs_ordinal"], 2.0)

    def test_na_encodes_to_0(self):
        records = _make_records(1, terrain_obs="N/A")
        features = build_features(records)
        self.assertEqual(features[0]["terrain_obs_ordinal"], 0.0)

    def test_unknown_encodes_to_0(self):
        records = _make_records(1, terrain_obs="UNKNOWN")
        features = build_features(records)
        self.assertEqual(features[0]["terrain_obs_ordinal"], 0.0)

    def test_case_insensitive(self):
        records = _make_records(1, terrain_obs="medium")
        features = build_features(records)
        self.assertEqual(features[0]["terrain_obs_ordinal"], 1.0)


class TestOneStepDeltas(unittest.TestCase):
    """Verify one-step backward differences."""

    def test_first_row_delta_is_zero(self):
        records = _make_records(3)
        features = build_features(records)
        self.assertEqual(features[0]["delta_unc_lat"], 0.0)
        self.assertEqual(features[0]["delta_unc_lon"], 0.0)
        self.assertEqual(features[0]["delta_est_lat"], 0.0)
        self.assertEqual(features[0]["delta_est_lon"], 0.0)

    def test_delta_unc_lat_correct(self):
        records = _make_records(3)
        # uncertainty_lat_m: 1.0, 1.1, 1.2 (from _make_records)
        features = build_features(records)
        self.assertAlmostEqual(features[1]["delta_unc_lat"], 0.1, places=10)
        self.assertAlmostEqual(features[2]["delta_unc_lat"], 0.1, places=10)

    def test_delta_unc_lon_correct(self):
        records = _make_records(3)
        # uncertainty_lon_m: 2.0, 2.05, 2.10 (from _make_records)
        features = build_features(records)
        self.assertAlmostEqual(features[1]["delta_unc_lon"], 0.05, places=10)
        self.assertAlmostEqual(features[2]["delta_unc_lon"], 0.05, places=10)

    def test_delta_est_lat_correct(self):
        records = _make_records(3)
        # estimated_lat: 26.5, 26.501, 26.502 (from _make_records)
        features = build_features(records)
        self.assertAlmostEqual(features[1]["delta_est_lat"], 0.001, places=10)
        self.assertAlmostEqual(features[2]["delta_est_lat"], 0.001, places=10)

    def test_delta_est_lon_correct(self):
        records = _make_records(3)
        features = build_features(records)
        self.assertAlmostEqual(features[1]["delta_est_lon"], 0.001, places=10)
        self.assertAlmostEqual(features[2]["delta_est_lon"], 0.001, places=10)

    def test_internal_one_step_delta(self):
        vals = [10.0, 12.0, 15.0, 11.0]
        d = _one_step_delta(vals)
        self.assertEqual(d, [0.0, 2.0, 3.0, -4.0])

    def test_delta_empty(self):
        self.assertEqual(_one_step_delta([]), [])


class TestCausalRollingMean(unittest.TestCase):
    """Verify 10-step causal rolling mean."""

    def test_single_row_uses_own_value(self):
        records = _make_records(1)
        features = build_features(records)
        # rolling_mean_unc_lat_10 for one row = that row's uncertainty_lat_m
        self.assertAlmostEqual(
            features[0]["rolling_mean_unc_lat_10"],
            1.0,  # uncertainty_lat_m for i=0 is 1.0
            places=10,
        )

    def test_window_grows_first_10_rows(self):
        vals = [float(i) for i in range(15)]
        rm = _causal_rolling_mean(vals, 10)
        # Row 0: mean([0]) = 0.0
        self.assertAlmostEqual(rm[0], 0.0)
        # Row 4: mean([0,1,2,3,4]) = 2.0
        self.assertAlmostEqual(rm[4], 2.0)
        # Row 9: mean([0,1,...,9]) = 4.5
        self.assertAlmostEqual(rm[9], 4.5)
        # Row 10: mean([1,2,...,10]) = 5.5
        self.assertAlmostEqual(rm[10], 5.5)
        # Row 14: mean([5,6,...,14]) = 9.5
        self.assertAlmostEqual(rm[14], 9.5)

    def test_rolling_mean_never_uses_future(self):
        """Verify each row's mean depends only on itself and prior rows."""
        vals = [1.0, 2.0, 100.0, 4.0, 5.0]
        rm = _causal_rolling_mean(vals, 10)
        # Row 0: mean([1.0]) = 1.0  — unaffected by future spike
        self.assertAlmostEqual(rm[0], 1.0)
        # Row 1: mean([1.0, 2.0]) = 1.5  — unaffected by future spike
        self.assertAlmostEqual(rm[1], 1.5)
        # Row 2: mean([1.0, 2.0, 100.0]) = 34.333...  — spike included
        self.assertAlmostEqual(rm[2], 103.0 / 3.0, places=6)

    def test_rolling_mean_empty(self):
        self.assertEqual(_causal_rolling_mean([], 10), [])

    def test_rolling_mean_unc_lat_in_features(self):
        """Verify rolling_mean_unc_lat_10 is computed correctly in features."""
        records = _make_records(12)
        features = build_features(records)
        # uncertainty_lat_m for i in range(12): 1.0 + i*0.1
        # Row 11: mean of rows 2..11 = mean([1.2, 1.3, ..., 2.1])
        expected_vals = [1.0 + i * 0.1 for i in range(2, 12)]
        expected_mean = sum(expected_vals) / len(expected_vals)
        self.assertAlmostEqual(
            features[11]["rolling_mean_unc_lat_10"],
            expected_mean,
            places=8,
        )


class TestUncChangeRate(unittest.TestCase):
    """Verify unc_change_rate = (delta_unc_lat + delta_unc_lon) / 2."""

    def test_unc_change_rate_formula(self):
        records = _make_records(3)
        features = build_features(records)
        for row in features:
            expected = (row["delta_unc_lat"] + row["delta_unc_lon"]) / 2.0
            self.assertAlmostEqual(
                row["unc_change_rate"], expected, places=10
            )


class TestMissionBoundaryProtection(unittest.TestCase):
    """Verify that each mission is processed independently."""

    def test_two_missions_processed_separately(self):
        """Building features for two missions separately must give the
        same result as if they were never mixed."""
        mission_a = _make_records(5)
        mission_b = _make_records(5, tan_match_score=0.9)

        feat_a = build_features(mission_a)
        feat_b = build_features(mission_b)

        # Both should have first-row deltas = 0.0
        self.assertEqual(feat_a[0]["delta_unc_lat"], 0.0)
        self.assertEqual(feat_b[0]["delta_unc_lat"], 0.0)
        self.assertEqual(feat_a[0]["delta_est_lat"], 0.0)
        self.assertEqual(feat_b[0]["delta_est_lat"], 0.0)

        # Rolling means at row 0 should be the row's own value
        self.assertAlmostEqual(
            feat_a[0]["rolling_mean_unc_lat_10"], 1.0, places=10
        )
        self.assertAlmostEqual(
            feat_b[0]["rolling_mean_unc_lat_10"], 1.0, places=10
        )

    def test_concatenated_would_differ(self):
        """Concatenating two missions and calling build_features once
        would produce different deltas at the boundary — this test
        documents that the user MUST call build_features separately
        per mission."""
        m1 = _make_records(3, uncertainty_lat_m=10.0)
        m2 = _make_records(3, uncertainty_lat_m=1.0)

        feat_sep = build_features(m2)
        combined = m1 + m2
        feat_combined = build_features(combined)

        # When processed separately, m2 row 0 delta = 0.0
        self.assertEqual(feat_sep[0]["delta_unc_lat"], 0.0)

        # When combined, row 3 (= m2 row 0) delta = m2[0] - m1[2] = 1.0 - 10.0 = -9.0
        # This is WRONG for mission-boundary safety
        self.assertNotEqual(feat_combined[3]["delta_unc_lat"], 0.0)


class TestNoMutationOfSource(unittest.TestCase):
    """Verify build_features does not modify the input records."""

    def test_source_records_unchanged(self):
        records = _make_records(5)
        original = copy.deepcopy(records)
        _ = build_features(records)
        self.assertEqual(records, original)


class TestEmptyInput(unittest.TestCase):
    """Verify empty input returns empty output."""

    def test_empty_list(self):
        features = build_features([])
        self.assertEqual(features, [])

    def test_single_row(self):
        records = _make_records(1)
        features = build_features(records)
        self.assertEqual(len(features), 1)
        self.assertEqual(len(features[0]), 13)


class TestMissingColumns(unittest.TestCase):
    """Verify ValueError on missing required columns."""

    def test_missing_tan_match_score(self):
        records = _make_records(1)
        del records[0]["tan_match_score"]
        with self.assertRaises(ValueError):
            build_features(records)

    def test_missing_uncertainty_lat_m(self):
        records = _make_records(1)
        del records[0]["uncertainty_lat_m"]
        with self.assertRaises(ValueError):
            build_features(records)


class TestNaNHandling(unittest.TestCase):
    """Verify NaN/Inf/non-finite values are handled deterministically."""

    def test_nan_tan_match_score_becomes_zero(self):
        records = _make_records(1)
        records[0]["tan_match_score"] = "nan"
        features = build_features(records)
        self.assertEqual(features[0]["tan_match_score"], 0.0)

    def test_inf_uncertainty_becomes_zero(self):
        records = _make_records(1)
        records[0]["uncertainty_lat_m"] = "inf"
        features = build_features(records)
        self.assertEqual(features[0]["uncertainty_lat_m"], 0.0)

    def test_empty_string_becomes_default(self):
        records = _make_records(1)
        records[0]["tan_match_score"] = ""
        features = build_features(records)
        self.assertEqual(features[0]["tan_match_score"], 0.0)

    def test_tan_valid_nan_becomes_false(self):
        records = _make_records(1)
        records[0]["tan_valid"] = "nan"
        features = build_features(records)
        self.assertEqual(features[0]["tan_valid"], 0.0)


class TestRowPreservation(unittest.TestCase):
    """Verify row count and ordering are preserved."""

    def test_row_count_preserved(self):
        for n in [1, 5, 20, 100]:
            records = _make_records(n)
            features = build_features(records)
            self.assertEqual(
                len(features), n,
                f"Row count mismatch for n={n}",
            )


class TestLoadMissionFeatures(unittest.TestCase):
    """Test loading from CSV file (integration with real data)."""

    _EXPORT_DIR = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "exports"
    )

    def test_load_desert_mission_if_available(self):
        csv_path = os.path.join(self._EXPORT_DIR, "desert_mission_records.csv")
        if not os.path.isfile(csv_path):
            self.skipTest(f"Export CSV not found: {csv_path}")
        features = load_mission_features(csv_path)
        self.assertGreater(len(features), 0)
        for row in features:
            self.assertEqual(len(row), 13)
            self.assertEqual(set(row.keys()), set(FEATURE_COLUMNS))
            for col, val in row.items():
                self.assertIsInstance(val, float)
                self.assertTrue(math.isfinite(val), f"{col}={val}")

    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_mission_features("/nonexistent/path.csv")


class TestBaseFeatureValues(unittest.TestCase):
    """Verify base feature pass-through values are correct."""

    def test_tan_match_score_passthrough(self):
        records = _make_records(1, tan_match_score=0.75)
        features = build_features(records)
        self.assertEqual(features[0]["tan_match_score"], 0.75)

    def test_tan_valid_true(self):
        records = _make_records(1, tan_valid="True")
        features = build_features(records)
        self.assertEqual(features[0]["tan_valid"], 1.0)

    def test_tan_valid_false(self):
        records = _make_records(1, tan_valid="False")
        features = build_features(records)
        self.assertEqual(features[0]["tan_valid"], 0.0)

    def test_uncertainty_passthrough(self):
        records = _make_records(1,
                                uncertainty_lat_m=5.5,
                                uncertainty_lon_m=3.3,
                                uncertainty_alt_m=1.1)
        features = build_features(records)
        self.assertAlmostEqual(features[0]["uncertainty_lat_m"], 5.5)
        self.assertAlmostEqual(features[0]["uncertainty_lon_m"], 3.3)
        self.assertAlmostEqual(features[0]["uncertainty_alt_m"], 1.1)


if __name__ == "__main__":
    unittest.main()
