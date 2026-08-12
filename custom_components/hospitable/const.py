# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Constants for the Hospitable Home Assistant integration."""

from homeassistant.const import Platform

DOMAIN = "hospitable"
VERSION = 1
MINOR_VERSION = 1
PLATFORMS: list[Platform] = [Platform.SENSOR]
CONF_TOKEN = "token"
CONF_ACCOUNT_NAMESPACE = "account_namespace"
CONF_NAMESPACE_SOURCE = "namespace_source"
CONF_SELECTED_PROPERTIES = "selected_properties"
CONF_RESERVATION_INTERVAL = "reservation_interval_minutes"
CONF_PROPERTY_INTERVAL = "property_interval_minutes"
CONF_LOOKBACK_DAYS = "lookback_days"
CONF_LOOKAHEAD_DAYS = "lookahead_days"
CONF_TIMEZONE_OVERRIDES = "timezone_overrides"
# Both toggles default OFF by requirement (FR-037, FR-038b), not by
# preference. profile_picture is never exposed under any option (FR-047).
CONF_AWAITING_HOST_REPLY = "awaiting_host_reply"
DEFAULT_AWAITING_HOST_REPLY = False
CONF_GUEST_CONTACT_DETAILS = "guest_contact_details"
DEFAULT_GUEST_CONTACT_DETAILS = False
CONF_TASK_INTERVAL = "task_interval_minutes"
DEFAULT_TASK_INTERVAL = 15
MIN_TASK_INTERVAL = 5
# The task poll always sends explicit dates rather than relying on
# Hospitable's undocumented roughly-14-day default, which would make the
# meaning of task_count change silently if upstream changed it. 14 is
# the measured upstream default, so turning explicit dates on does not
# change an existing user's counts (FR-030).
CONF_TASK_WINDOW_DAYS = "task_window_days"
DEFAULT_TASK_WINDOW_DAYS = 14
DEFAULT_RESERVATION_INTERVAL = 5
DEFAULT_PROPERTY_INTERVAL = 60
MIN_RESERVATION_INTERVAL = 1
MIN_PROPERTY_INTERVAL = 15
