from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from app.config import settings


class SlackNotConfigured(RuntimeError):
    pass


@dataclass
class SlackCallError(RuntimeError):
    message: str
    error_code: str | None = None
    status_code: int | None = None

    def __str__(self) -> str:
        base = self.message
        if self.error_code:
            base += f" (error={self.error_code})"
        if self.status_code:
            base += f" (status={self.status_code})"
        return base


class SlackClient:
    def __init__(self, token: str | None = None):
        token = token or settings.slack_bot_token
        if not token:
            raise SlackNotConfigured("SLACK_BOT_TOKEN is not set")
        self.client = WebClient(token=token)

    def _call_with_retry(
        self, fn: Callable[..., Any], *, max_attempts: int = 5, **kwargs
    ) -> Any:
        last_err: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                return fn(**kwargs)
            except SlackApiError as e:
                last_err = e
                status = getattr(e.response, "status_code", None)
                headers = getattr(e.response, "headers", {}) or {}
                err_code = None

                try:
                    err_code = e.response.get("error")
                except Exception:
                    err_code = None

                if status == 429 or err_code == "ratelimited":
                    retry_after = headers.get("Retry-After")
                    try:
                        wait_s = int(retry_after) if retry_after else 1
                    except Exception:
                        wait_s = 1
                    time.sleep(wait_s)
                    continue

                raise SlackCallError(
                    message="Slack API call failed",
                    error_code=err_code,
                    status_code=status,
                ) from e
            except Exception as e:
                last_err = e
                time.sleep(min(2 ** (attempt - 1), 8))
                continue

        raise SlackCallError(message="Slack API call failed after retries") from last_err

    def get_channel_info(self, channel_id: str) -> dict:
        resp = self._call_with_retry(self.client.conversations_info, channel=channel_id)
        ch = resp.get("channel")
        if not ch:
            raise SlackCallError("Slack conversations.info returned no channel object")
        return ch

    def join_channel(self, channel_id: str) -> None:
        try:
            self._call_with_retry(self.client.conversations_join, channel=channel_id)
        except SlackCallError:
            return

    def get_user_info(self, user_id: str) -> dict:
        resp = self._call_with_retry(self.client.users_info, user=user_id)
        user = resp.get("user")
        if not user:
            raise SlackCallError("Slack users.info returned no user object")
        return user

    def conversations_history_page(
        self,
        *,
        channel_id: str,
        oldest: str,
        cursor: str | None = None,
        limit: int = 200,
        inclusive: bool = True,
    ) -> tuple[list[dict], str | None]:
        resp = self._call_with_retry(
            self.client.conversations_history,
            channel=channel_id,
            oldest=oldest,
            inclusive=inclusive,
            limit=limit,
            cursor=cursor,
        )
        messages = resp.get("messages") or []
        meta = resp.get("response_metadata") or {}
        next_cursor = (meta.get("next_cursor") or "").strip() or None
        return messages, next_cursor

    def conversations_replies_page(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        oldest: str,
        cursor: str | None = None,
        limit: int = 200,
        inclusive: bool = True,
    ) -> tuple[list[dict], str | None]:
        resp = self._call_with_retry(
            self.client.conversations_replies,
            channel=channel_id,
            ts=thread_ts,
            oldest=oldest,
            inclusive=inclusive,
            limit=limit,
            cursor=cursor,
        )
        messages = resp.get("messages") or []
        meta = resp.get("response_metadata") or {}
        next_cursor = (meta.get("next_cursor") or "").strip() or None
        return messages, next_cursor
