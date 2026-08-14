# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for trace header capture (D4, FR-017 to FR-022).

This module covers Deliverable 4 of spec 004: capturing the
``x-hospitable-trace`` response header on API errors and surfacing
the most recent trace ID in the diagnostics payload.
"""
