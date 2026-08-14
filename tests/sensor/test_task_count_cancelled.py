# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for the cancelled task progress bucket (D1, FR-001 to FR-008).

This module covers Deliverable 1 of spec 004: a fourth
``CANCELLED_STATUSES`` bucket on the task-count sensor so that the
four breakdown attributes sum to ``task_count`` while the upstream
vocabulary remains the known six values, plus a vocabulary drift
guard that logs unknown statuses.
"""
