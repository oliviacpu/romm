import base64
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    SimpleUser,
    UnauthenticatedUser,
)
from starlette.middleware.authentication import AuthenticationMiddleware

from endpoints.roms import upload
from handler import rom_batch_upload
from handler.auth.constants import Scope
from handler.auth.rom_visibility import UNRESTRICTED
from handler.database import db_platform_handler, db_rom_handler
from handler.rom_upload import UploadDestination
from models.user import Role
from utils.zip_cache import ensure_zipfile_writable


def game_zip(platform):
    data = bytearray(32768)
    if platform == "n64":
        data[:4] = b"\x80\x37\x12\x40"
    else:
        data[0x100:0x104] = b"SEGA"
    ensure_zipfile_writable()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("unhelpful.bin", data)
    return output.getvalue()


class UploadUser(SimpleUser):
    id = 1
    role = Role.ADMIN


class UploadAuth(AuthenticationBackend):
    async def authenticate(self, connection):
        role = connection.headers.get("x-test-role")
        if not role:
            return AuthCredentials(), UnauthenticatedUser()
        scopes = (
            ["authenticated", str(Scope.ROMS_WRITE)]
            if role == "admin"
            else ["authenticated"]
        )
        return AuthCredentials(scopes), UploadUser("upload-test")


class UploadIdentificationEndpointTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.payload = game_zip("n64")
        self.destination = UploadDestination(None, "test", self.root / "game.zip")
        self.platform = SimpleNamespace(id=64, slug="n64", fs_slug="custom-n64")
        self.permissions = SimpleNamespace(
            rom_visibility=UNRESTRICTED, can_see_platform=lambda _id: True
        )
        self.record = Mock()
        self.cleanup = AsyncMock()

        async def assemble(_id, _session, staged):
            staged.write_bytes(self.payload)

        session = {
            "user_id": 1,
            "total_chunks": 1,
            "filename": "game.zip",
            "platform_id": 64,
            "rom_id": None,
            "batch_id": None,
            "overwrite": False,
        }
        cache = SimpleNamespace(
            scard=AsyncMock(return_value=1), delete=AsyncMock(return_value=1)
        )
        for target, value in [
            ("get_permissions", Mock(return_value=self.permissions)),
            ("_get_session", AsyncMock(return_value=session)),
            ("_resolve_destination", AsyncMock(return_value=self.destination)),
            ("_assemble_chunks", AsyncMock(side_effect=assemble)),
            ("_cleanup_upload_state", self.cleanup),
            ("_record_upload", self.record),
            ("async_cache", cache),
        ]:
            patcher = patch.object(upload, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        platform_patch = patch.object(
            db_platform_handler, "get_platform", return_value=self.platform
        )
        platform_patch.start()
        self.addCleanup(platform_patch.stop)
        folder_patch = patch.object(
            rom_batch_upload, "_platform_dir", return_value=self.root
        )
        folder_patch.start()
        self.addCleanup(folder_patch.stop)
        app = FastAPI()
        app.add_middleware(AuthenticationMiddleware, backend=UploadAuth())
        app.include_router(upload.router, prefix="/api/roms")
        self.client = TestClient(app)
        self.headers = {"x-test-role": "admin"}

    def test_chd_match_uses_exact_visible_file_hashes(self):
        from handler.rom_identification import Identification, identify_library_match

        digest = "ab" * 20

        def rom(slug, value):
            return SimpleNamespace(
                platform=SimpleNamespace(slug=slug),
                files=[SimpleNamespace(chd_sha1_hash=value)],
            )

        with patch.object(
            db_rom_handler,
            "get_roms_scalar",
            return_value=[rom("n64", digest), rom("ps2", "cd" * 20), rom("dc", digest)],
        ) as query:
            result = identify_library_match(
                Identification("chd", chd_sha1=digest),
                self.permissions.rom_visibility,
                1,
            )
        self.assertEqual(result.platforms, ["dc"])
        self.assertEqual(result.evidence, "library-hash")
        self.assertIs(
            query.call_args.kwargs["visibility"], self.permissions.rom_visibility
        )
        self.assertEqual(query.call_args.kwargs["user_id"], 1)
        self.assertTrue(query.call_args.kwargs["include_files"])

    def test_ambiguous_chd_library_matches_remain_unknown(self):
        from handler.rom_identification import Identification, identify_library_match

        digest = "ab" * 20
        matches = [
            SimpleNamespace(
                platform=SimpleNamespace(slug=slug),
                files=[SimpleNamespace(chd_sha1_hash=digest)],
            )
            for slug in ("ps2", "dc")
        ]
        with patch.object(db_rom_handler, "get_roms_scalar", return_value=matches):
            result = identify_library_match(
                Identification("chd", chd_sha1=digest),
                self.permissions.rom_visibility,
                1,
            )
        self.assertEqual(result.platforms, [])

    def inspect(self, payload=None, headers=None):
        data = payload or self.payload
        return self.client.post(
            "/api/roms/upload/inspect",
            headers=self.headers if headers is None else headers,
            json={
                "filename": "game.zip",
                "size": len(data),
                "head": base64.b64encode(data).decode(),
                "tail": base64.b64encode(data).decode(),
            },
        )

    def complete(self):
        return self.client.post(
            f"/api/roms/upload/{uuid4()}/complete", headers=self.headers
        )

    def test_inspection_requires_upload_scope(self):
        self.assertEqual(self.inspect(headers={}).status_code, 401)
        self.assertEqual(
            self.inspect(headers={"x-test-role": "viewer"}).status_code, 403
        )

    def test_inspection_returns_platform_from_archive_bytes(self):
        self.payload = game_zip("genesis")
        response = self.inspect()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["platforms"], ["genesis"])
        self.assertEqual(response.json()["evidence"], "archive-headers")
        self.assertFalse(self.destination.location.exists())

    def test_actual_staged_bytes_reject_wrong_platform_and_remove_staging(self):
        self.payload = game_zip("genesis")
        response = self.complete()
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("genesis, not n64", response.json()["detail"])
        self.assertFalse(self.destination.location.exists())
        self.assertEqual(list(self.root.iterdir()), [])
        self.record.assert_not_called()
        self.cleanup.assert_awaited_once()

    def test_actual_staged_bytes_accept_matching_canonical_slug_with_custom_folder(
        self,
    ):
        response = self.complete()
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.destination.location.read_bytes(), self.payload)
        self.record.assert_called_once()

    def test_invalid_zip_cannot_be_committed(self):
        self.payload = bytes(1000)
        response = self.complete()
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("invalid or incomplete", response.json()["detail"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_disc_inside_zip_is_blocked_at_preflight_and_publication(self):
        data = bytearray(16 * 2048 + 7)
        data[-7:] = b"\x01CD001\x01"
        ensure_zipfile_writable()
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("unknown.iso", data)
        self.payload = output.getvalue()
        response = self.inspect()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["platforms"], [])
        self.assertIn("n64", response.json()["incompatible_platforms"])
        response = self.complete()
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("disc image", response.json()["detail"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_rejection_preserves_existing_destination(self):
        self.payload = game_zip("genesis")
        self.destination.location.write_bytes(b"existing")
        self.assertEqual(self.complete().status_code, 400)
        self.assertEqual(self.destination.location.read_bytes(), b"existing")

    def test_folder_commit_validates_contents_before_promoting_any_file(self):
        self.payload = game_zip("genesis")
        batch = rom_batch_upload.start_batch(
            "custom-n64",
            64,
            1,
            "Wrong platform",
            [{"path": "game.zip", "size": len(self.payload)}],
        )
        stage = self.root / f".romm-upload-{batch}" / "game"
        (stage / "game.zip").write_bytes(self.payload)
        response = self.client.post(
            f"/api/roms/upload/batch/{batch}/complete",
            headers={**self.headers, "x-upload-platform": "64"},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertFalse((self.root / "Wrong platform").exists())
        self.assertEqual((stage / "game.zip").read_bytes(), self.payload)
