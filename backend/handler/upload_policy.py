"""Optional platform upload rules supplied by the deployment."""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from config import ROM_UPLOAD_POLICY_FILE


@dataclass(frozen=True)
class PlatformUploadPolicy:
    label: str
    launch: frozenset[str]
    companions: frozenset[str]


def _extensions(value: object, *, required: bool = False) -> frozenset[str]:
    if not isinstance(value, list) or (required and not value):
        raise ValueError("Upload policy extensions must be a list")
    if any(
        not isinstance(item, str)
        or not item.startswith(".")
        or item != item.lower()
        or not item[1:].isalnum()
        for item in value
    ):
        raise ValueError("Upload policy has an invalid extension")
    return frozenset(value)


@lru_cache(maxsize=1)
def upload_policies() -> dict[str, PlatformUploadPolicy]:
    if ROM_UPLOAD_POLICY_FILE is None:
        return {}
    raw = json.loads(Path(ROM_UPLOAD_POLICY_FILE).read_text())
    if not isinstance(raw, dict):
        raise TypeError("Upload policy must be an object")
    policies = {}
    for slug, value in raw.items():
        if not isinstance(slug, str) or not isinstance(value, dict):
            raise TypeError("Upload policy has an invalid platform")
        label = value.get("label")
        if not isinstance(label, str) or not label:
            raise ValueError("Upload policy platform needs a label")
        launch = _extensions(value.get("launch"), required=True)
        companions = _extensions(value.get("companions"))
        if launch & companions:
            raise ValueError("Launch and companion extensions overlap")
        policies[slug] = PlatformUploadPolicy(label, launch, companions)
    return policies


def single_upload_error(fs_slug: str, filename: str) -> str | None:
    policy = upload_policies().get(fs_slug)
    if policy is None:
        return None
    suffix = Path(filename).suffix.lower()
    if suffix in policy.launch and suffix not in {".gdi", ".cue"}:
        return None
    accepted = ", ".join(sorted(policy.launch - {".gdi", ".cue"}))
    if suffix in {".gdi", ".cue"} and suffix in policy.launch:
        return f"{suffix.upper()} needs its tracks. Use Add folder to upload the complete game."
    folder_hint = (
        ", or a complete GDI/CUE folder" if policy.launch & {".gdi", ".cue"} else ""
    )
    return f"{policy.label} {suffix or 'file'} cannot launch as a standalone game. Upload {accepted}{folder_hint}."


def folder_upload_error(fs_slug: str, paths: list[str]) -> str | None:
    policy = upload_policies().get(fs_slug)
    if policy is None:
        return None
    discs: dict[str, list[str]] = {}
    for path in paths:
        parts = Path(path).parts
        disc = (
            parts[0] if len(parts) > 1 and parts[0].lower().startswith("disc ") else ""
        )
        discs.setdefault(disc, []).append(path)
    for disc, files in discs.items():
        launch = [path for path in files if Path(path).suffix.lower() in policy.launch]
        if len(launch) != 1:
            if len(files) == 1 and not launch:
                return single_upload_error(fs_slug, files[0])
            subject = f"{disc}: " if disc else ""
            return f"{subject}Choose exactly one launchable game image per disc"
        if any(Path(path).suffix.lower() in policy.companions for path in files):
            descriptor = Path(launch[0]).suffix.lower()
            if descriptor not in {".gdi", ".cue"}:
                return (
                    "Track files need a GDI or CUE descriptor in the same disc folder"
                )
    return None
