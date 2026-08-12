# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the Hospitable action (service-call) tests.

This module MUST NOT import any ``custom_components.hospitable`` module
at module scope. A module-level import of a not-yet-existing module in a
``conftest.py`` breaks collection for the whole directory, where no
``xfail`` marker can rescue it (Constitution Principle XII). Every
fixture that needs an integration object is therefore a FACTORY fixture
returning a callable that performs its import inside its own body.
"""

from __future__ import annotations
