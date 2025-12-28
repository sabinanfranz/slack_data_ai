from __future__ import annotations

import html
import re
from typing import Mapping

import bleach

_ALLOWED_TAGS = ["a", "br", "code"]
_ALLOWED_ATTRS = {"a": ["href", "rel", "target"]}
_ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

_RE_SPECIAL = re.compile(r"&lt;!(here|channel|everyone)&gt;")
_RE_USERGROUP = re.compile(r"&lt;!subteam\^[A-Z0-9]+\|@([^&]+?)&gt;")
_RE_USER = re.compile(r"&lt;@([A-Z0-9]+)(?:\|([^&]+?))?&gt;")
_RE_CHANNEL = re.compile(r"&lt;#([A-Z0-9]+)\|([^&]+?)&gt;")
_RE_CHANNEL_NO_NAME = re.compile(r"&lt;#([A-Z0-9]+)&gt;")
_RE_LINK = re.compile(r"&lt;((?:https?://|mailto:)[^|&]+?)(?:\|([^&]+?))?&gt;")
_RE_CODE = re.compile(r"`([^`]+)`")


def render_slack_text_to_safe_html(
    text: str | None,
    user_map: Mapping[str, str] | None = None,
) -> str:
    """
    Convert Slack mrkdwn-ish markup into safe HTML.
    """
    if not text:
        return ""

    user_map = user_map or {}

    s = html.escape(text)

    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\n", "<br>")

    def _special(m: re.Match) -> str:
        kind = m.group(1)
        return f"@{kind}"

    s = _RE_SPECIAL.sub(_special, s)

    s = _RE_USERGROUP.sub(lambda m: f"@{m.group(1)}", s)

    def _user(m: re.Match) -> str:
        uid = m.group(1)
        provided = (m.group(2) or "").strip()
        name = (user_map.get(uid) or "").strip() or provided or uid
        return f"@{name}"

    s = _RE_USER.sub(_user, s)

    s = _RE_CHANNEL.sub(lambda m: f"#{m.group(2)}", s)
    s = _RE_CHANNEL_NO_NAME.sub(lambda m: f"#{m.group(1)}", s)

    def _link(m: re.Match) -> str:
        url_esc = (m.group(1) or "").strip()
        label_esc = (m.group(2) or "").strip()

        url = html.unescape(url_esc)
        label = html.unescape(label_esc) if label_esc else url

        return (
            f'<a href="{html.escape(url, quote=True)}" '
            f'target="_blank" rel="noopener noreferrer">'
            f"{html.escape(label)}"
            f"</a>"
        )

    s = _RE_LINK.sub(_link, s)

    s = _RE_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", s)

    s = bleach.clean(
        s,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )

    return s
