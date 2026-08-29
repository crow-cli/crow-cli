import webbrowser
from urllib.parse import urlencode


def open_tweet_intent(
    text: str,
    *,
    url: str | None = None,
    hashtags: list[str] | None = None,
    via: str | None = None,
    in_reply_to: str | None = None,
) -> str:
    """Open a pre-filled Twitter/X tweet intent in the default browser.

    Args:
        text: The pre-filled tweet text.
        url: An optional URL to append to the tweet.
        hashtags: An optional list of hashtags to include (without '#').
        via: An optional username to attribute the tweet to.
        in_reply_to: An optional tweet ID to reply to.

    Returns:
        The full tweet intent URL that was opened.
    """
    params: dict[str, str] = {"text": text}

    if url is not None:
        params["url"] = url
    if hashtags:
        params["hashtags"] = ",".join(hashtags)
    if via is not None:
        params["via"] = via.lstrip("@")
    if in_reply_to is not None:
        params["in_reply_to"] = in_reply_to

    tweet_url = f"https://twitter.com/intent/tweet?{urlencode(params)}"
    webbrowser.open(tweet_url)
    return tweet_url
