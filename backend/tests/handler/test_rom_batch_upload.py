from collections.abc import Iterator
from pathlib import Path

import pytest

from handler import rom_batch_upload, upload_policy
from handler.filesystem import fs_rom_handler
from handler.rom_upload import UploadConflictException, UploadRejectedException


@pytest.fixture
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(fs_rom_handler, "base_path", tmp_path)
    monkeypatch.setattr(
        fs_rom_handler, "get_roms_upload_path", lambda _slug: "roms/dreamcast"
    )
    return tmp_path / "roms/dreamcast"


def _files() -> dict[str, bytes]:
    return {
        f"Disc {disc}/{name}": data
        for disc in (1, 2)
        for name, data in {
            "disc.gdi": b"2\n1 0 4 2048 track01.iso 0\n2 775 0 2352 track02.raw 0\n",
            "track01.iso": b"first",
            "track02.raw": b"second",
        }.items()
    }


def _start(library: Path, files: dict[str, bytes]) -> tuple[str, Path]:
    batch_id = rom_batch_upload.start_batch(
        "dreamcast",
        1,
        7,
        "Skies of Arcadia",
        [{"path": path, "size": len(data)} for path, data in files.items()],
    )
    stage = library / f".romm-upload-{batch_id}/game"
    return batch_id, stage


@pytest.fixture
def dreamcast_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    path = tmp_path / "upload-policy.json"
    path.write_text(
        '{"dreamcast":{"label":"Dreamcast","launch":[".gdi",".cue",".chd",".cdi"],"companions":[".iso",".raw",".bin"]}}'
    )
    monkeypatch.setattr(upload_policy, "ROM_UPLOAD_POLICY_FILE", str(path))
    upload_policy.upload_policies.cache_clear()
    yield
    upload_policy.upload_policies.cache_clear()


def test_policy_blocks_standalone_iso_before_staging(
    library: Path, dreamcast_policy: None
) -> None:
    with pytest.raises(UploadRejectedException, match="cannot launch"):
        _start(library, {"JETRADIO.iso": b"game"})
    assert not library.exists()


def test_policy_accepts_gdi_iso_track_but_rejects_unreferenced_track(
    library: Path, dreamcast_policy: None
) -> None:
    files = {
        "disc.gdi": b"1\n1 0 4 2048 track01.iso 0\n",
        "track01.iso": b"track",
    }
    batch_id, stage = _start(library, files)
    for name, content in files.items():
        (stage / name).write_bytes(content)
    assert (
        rom_batch_upload.finish_batch("dreamcast", batch_id, 1, 7) == "Skies of Arcadia"
    )

    extra = {**files, "unlisted.iso": b"extra"}
    batch_id = rom_batch_upload.start_batch(
        "dreamcast",
        1,
        7,
        "Another game",
        [{"path": name, "size": len(content)} for name, content in extra.items()],
    )
    stage = library / f".romm-upload-{batch_id}/game"
    for name, content in extra.items():
        (stage / name).write_bytes(content)
    with pytest.raises(UploadRejectedException, match="not listed"):
        rom_batch_upload.finish_batch("dreamcast", batch_id, 1, 7)


def test_publishes_complete_two_disc_game_atomically(library: Path) -> None:
    files = _files()
    batch_id, stage = _start(library, files)
    for path, data in files.items():
        target = stage / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    assert not (library / "Skies of Arcadia").exists()

    assert (
        rom_batch_upload.finish_batch("dreamcast", batch_id, 1, 7) == "Skies of Arcadia"
    )
    assert (library / "Skies of Arcadia/Disc 2/track02.raw").read_bytes() == b"second"
    assert not stage.exists()


def test_rejects_missing_track_and_keeps_staging_for_recovery(library: Path) -> None:
    files = _files()
    batch_id, stage = _start(library, files)
    for path, data in files.items():
        if path == "Disc 2/track02.raw":
            continue
        target = stage / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    with pytest.raises(UploadRejectedException, match="missing or incomplete"):
        rom_batch_upload.finish_batch("dreamcast", batch_id, 1, 7)
    assert stage.exists()
    assert not (library / "Skies of Arcadia").exists()


def test_rejects_existing_game_and_foreign_account(library: Path) -> None:
    files = {"disc.cdi": b"game"}
    batch_id, _ = _start(library, files)
    with pytest.raises(UploadRejectedException, match="does not belong"):
        rom_batch_upload.load_batch("dreamcast", batch_id, 1, 8)
    (library / "Skies of Arcadia").mkdir()
    with pytest.raises(UploadConflictException, match="already exists"):
        rom_batch_upload.start_batch(
            "dreamcast", 1, 7, "Skies of Arcadia", [{"path": "disc.cdi", "size": 4}]
        )


@pytest.mark.parametrize(
    "path",
    [
        "../escape.iso",
        "Disc 1/../../escape.iso",
        "/absolute.iso",
        ".hidden/file.iso",
        "Disc 1//file.iso",
    ],
)
def test_rejects_unsafe_relative_paths(library: Path, path: str) -> None:
    with pytest.raises(UploadRejectedException):
        _start(library, {path: b"game"})
