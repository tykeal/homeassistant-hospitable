# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Message model extracted from ``api/models.py`` for file-size budget.

``HospitableMessage`` and ``_optional_str`` lived in ``models.py`` until
that file reached the ~440-line ``aislop`` threshold.
``HospitableMessage`` is re-exported from ``models.py`` via the
``__all__`` pattern so the documented import path
``api.models.HospitableMessage`` still resolves. ``_optional_str`` is a
private helper and is not re-exported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _optional_str(value: Any) -> str | None:
    """Return a string value, or None when absent.

    Args:
        value: Raw value of any type.

    Returns:
        The value as a string, or None when it is None.
    """
    return None if value is None else str(value)


@dataclass(frozen=True)
class HospitableMessage:
    """One message in a reservation's conversation thread.

    ``sender`` is retained as the OPAQUE upstream object because the
    reply-state derivation needs to see whatever upstream sends. It is
    never logged, never written to diagnostics, and never returned in a
    service response: the response chokepoint in
    ``actions/response.py`` drops it and keeps only ``sender_type`` and
    ``sender_role`` (FR-047a).
    """

    message_id: int | None
    platform: str | None
    conversation_id: str | None
    body: str | None
    content_type: str | None
    sender_type: str | None
    sender_role: str | None
    sender: dict[str, Any] | None
    created_at: str | None
    attachments: tuple[dict[str, Any], ...]
    source: str | None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> HospitableMessage:
        """Build a message from one item of the thread ``data`` array.

        Nothing here is required. A thread is read-only reference data,
        so a single odd item must not turn the whole call into an error.

        Args:
            payload: One message object.

        Returns:
            The parsed message.
        """
        raw_id = payload.get("id")
        raw_sender = payload.get("sender")
        raw_attachments = payload.get("attachments")
        return cls(
            message_id=raw_id if isinstance(raw_id, int) else None,
            platform=_optional_str(payload.get("platform")),
            conversation_id=_optional_str(payload.get("conversation_id")),
            body=_optional_str(payload.get("body")),
            content_type=_optional_str(payload.get("content_type")),
            sender_type=_optional_str(payload.get("sender_type")),
            sender_role=_optional_str(payload.get("sender_role")),
            sender=raw_sender if isinstance(raw_sender, dict) else None,
            created_at=_optional_str(payload.get("created_at")),
            attachments=tuple(
                item for item in raw_attachments or () if isinstance(item, dict)
            )
            if isinstance(raw_attachments, list)
            else (),
            source=_optional_str(payload.get("source")),
        )
