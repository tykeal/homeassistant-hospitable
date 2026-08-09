# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Constants for the Hospitable Public API client."""

# aislop-ignore-file ai-slop/hardcoded-url -- canonical API URL required by FR-001

BASE_URL = "https://public.api.hospitable.com/v2"
USER_PATH = "/user"
PROPERTIES_PATH = "/properties"
RESERVATIONS_PATH = "/reservations"
CALENDAR_PATH = "/properties/{id}/calendar"
REQUEST_TIMEOUT = 30.0
PER_PAGE_MAX = 100
PROPERTY_BATCH_MAX = 50
MAX_BACKOFF = 300.0
