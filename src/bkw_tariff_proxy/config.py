from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bkw_endpoint: str = os.getenv(
        "BKW_ENDPOINT",
        "https://api.bkw.ch/api/dyntariffs/v1/Tariffs/energyreturn",
    )
    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL_SECONDS", "900"))
    cache_max_age_seconds: int = int(os.getenv("CACHE_MAX_AGE_SECONDS", "5400"))
    data_dir: str = os.getenv("DATA_DIR", "/data")
    timezone: str = os.getenv("TZ", "Europe/Zurich")
    require_full_horizon: bool = os.getenv("REQUIRE_FULL_HORIZON", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    test_data_mode: str = os.getenv("BKW_TEST_DATA_MODE", "off").strip().lower()
