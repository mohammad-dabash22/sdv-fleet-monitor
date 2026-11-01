"""Container image reference parsing."""

from __future__ import annotations

from typing import NamedTuple, Optional


class ImageRef(NamedTuple):
    repository: str
    tag: Optional[str]
    digest: Optional[str]


def parse_image(ref: str) -> ImageRef:
    """Split `[registry[:port]/]path[:tag][@digest]` into its parts.

    The tag is only looked for after the last `/`, so a registry port
    (`registry:5000/app`) is never mistaken for one.
    """
    name, _, digest = ref.partition("@")
    slash = name.rfind("/")
    colon = name.rfind(":")
    if colon > slash:
        return ImageRef(name[:colon], name[colon + 1:], digest or None)
    return ImageRef(name, None, digest or None)


def resolves_to_latest(ref: str) -> bool:
    """True when the image would be pulled as `:latest` (explicitly or by default).

    A digest pins the image regardless of its tag.
    """
    image = parse_image(ref)
    if image.digest:
        return False
    return image.tag is None or image.tag == "latest"
