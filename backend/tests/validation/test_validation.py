"""Required validation tests. Owner: M5. Remove the skip as each one is implemented."""

import pytest

pytestmark = pytest.mark.skip(reason="M5: validation not implemented yet")


def test_phenology_uses_only_qa_passed_points() -> None: ...
def test_test_period_untouched_by_calibration() -> None: ...
def test_coverage_reports_sample_count_and_width() -> None: ...
