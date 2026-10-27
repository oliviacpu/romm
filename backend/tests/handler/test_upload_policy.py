import json
from pathlib import Path

import pytest

from handler import upload_policy


@pytest.fixture
def policies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "upload-policy.json"
    path.write_text(
        json.dumps(
            {
                "dreamcast": {
                    "label": "Dreamcast",
                    "launch": [".gdi", ".cue", ".chd", ".cdi"],
                    "companions": [".iso", ".raw", ".bin"],
                },
                "ngc": {
                    "label": "GameCube",
                    "launch": [".iso", ".rvz"],
                    "companions": [],
                },
            }
        )
    )
    monkeypatch.setattr(upload_policy, "ROM_UPLOAD_POLICY_FILE", str(path))
    upload_policy.upload_policies.cache_clear()
    yield
    upload_policy.upload_policies.cache_clear()


def test_standalone_dreamcast_iso_is_blocked_but_gamecube_iso_is_allowed(
    policies: None,
) -> None:
    assert "cannot launch" in (
        upload_policy.single_upload_error("dreamcast", "JETRADIO.iso") or ""
    )
    assert upload_policy.single_upload_error("ngc", "game.iso") is None
    assert "Add folder" in (
        upload_policy.single_upload_error("dreamcast", "disc.gdi") or ""
    )


def test_complete_gdi_folder_can_include_an_iso_track(policies: None) -> None:
    assert (
        upload_policy.folder_upload_error(
            "dreamcast", ["disc.gdi", "track01.iso", "track02.raw"]
        )
        is None
    )
    assert upload_policy.folder_upload_error("dreamcast", ["JETRADIO.iso"])
    assert upload_policy.folder_upload_error(
        "dreamcast", ["Disc 1/disc.gdi", "Disc 2/track01.iso"]
    )


def test_no_policy_keeps_generic_romm_uploads_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(upload_policy, "ROM_UPLOAD_POLICY_FILE", None)
    upload_policy.upload_policies.cache_clear()
    assert upload_policy.single_upload_error("dreamcast", "game.iso") is None
    assert upload_policy.folder_upload_error("dreamcast", ["game.iso"]) is None
