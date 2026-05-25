import re
import string
import sys
from typing import Optional
import requests
import time

class CustomSession(requests.Session):
    def __init__(
        self,
        max_retries: int = 3,
        min_backoff: int = 4,
        timeout: int = 10,
    ) -> None:
        super().__init__()
        self.max_retries = max_retries
        self.min_backoff = min_backoff
        self.timeout = timeout

    def request(self, method: str | bytes, url: str | bytes, **kwargs: ...) -> ...:  # pyright: ignore[reportIncompatibleMethodOverride]
        kwargs.setdefault("timeout", self.timeout)
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                response = super().request(method, url, **kwargs)
            except requests.RequestException as exc:
                last_exception = exc
                if attempt == self.max_retries:
                    raise

                time.sleep(max(4, self.min_backoff * (2**attempt)))
                continue

            if response.status_code != 429 and response.status_code < 500:
                return response

            if attempt == self.max_retries:
                return response

            response.close()
            time.sleep(max(4, self.min_backoff * (2**attempt)))

        if last_exception is not None:
            raise last_exception
        raise RuntimeError("unreachable")


def is_oneshot(chapter_name: str, chapter_subtitle: str) -> bool:
    chapter_number = chapter_name_to_int(chapter_name)

    if chapter_number is not None:
        return False

    for name in (chapter_name, chapter_subtitle):
        name = name.lower()
        if "one" in name and "shot" in name:
            return True
    return False


def chapter_name_to_int(name: str) -> Optional[int]:
    try:
        return int(name.lstrip("#"))
    except ValueError:
        return None


def escape_path(path: str) -> str:
    return re.sub(r"[^\w]+", " ", path).strip(string.punctuation + " ")


def is_windows() -> bool:
    return sys.platform == "win32"
