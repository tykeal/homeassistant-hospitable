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
DEFAULT_RESERVATION_INTERVAL = 5
DEFAULT_PROPERTY_INTERVAL = 60
MIN_RESERVATION_INTERVAL = 1
MIN_PROPERTY_INTERVAL = 15
