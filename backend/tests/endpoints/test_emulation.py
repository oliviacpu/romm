import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    SimpleUser,
    UnauthenticatedUser,
)
from starlette.middleware.authentication import AuthenticationMiddleware

from endpoints.emulation import router
from handler.emulation.profiles import atomic_json, effective_profile, save_profile
from models.user import Role


class TestUser(SimpleUser):
    role: Role


class AuthBackend(AuthenticationBackend):
    async def authenticate(self, connection):
        role = connection.headers.get("x-test-role")
        if not role:
            return AuthCredentials(), UnauthenticatedUser()
        user = TestUser("profile-test")
        user.role = Role.ADMIN if role == "admin" else Role.USER
        scopes = ["authenticated", "logs.read", "users.write"]
        return AuthCredentials(scopes), user


class EmulationEndpointTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.env = patch.dict(os.environ, {"ROMM_EMULATION_PATH": str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.directory.cleanup)
        self.game_id = "a" * 20
        atomic_json(
            self.root / "catalog.json",
            {"games": [{"id": self.game_id, "title": "Test game", "system": "ps2"}]},
        )
        app = FastAPI()
        app.add_middleware(AuthenticationMiddleware, backend=AuthBackend())
        app.include_router(router, prefix="/api")
        self.client = TestClient(app)
        self.headers = {"x-test-role": "admin"}

    def test_authentication_and_role_required_for_reads_and_writes(self):
        for method, path, kwargs in [
            ("get", "/api/emulation", {}),
            ("get", "/api/emulation/profiles/ps2", {}),
            (
                "put",
                "/api/emulation/profiles/ps2",
                {"json": {"revision": 0, "profile": {}}},
            ),
        ]:
            self.assertEqual(
                getattr(self.client, method)(path, **kwargs).status_code, 401
            )
            self.assertEqual(
                getattr(self.client, method)(
                    path, headers={"x-test-role": "editor"}, **kwargs
                ).status_code,
                403,
            )

    def test_save_inherits_and_clears_game_override(self):
        response = self.client.put(
            "/api/emulation/profiles/ps2",
            headers=self.headers,
            json={
                "revision": 0,
                "profile": {"resolution": "1080p", "bindings": {"b": "x", "x": "b"}},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["effective"]["bindings"]["b"], "x")
        route = f"/api/emulation/profiles/ps2?game_id={self.game_id}"
        response = self.client.put(
            route,
            headers=self.headers,
            json={
                "revision": 1,
                "profile": {"resolution": "native", "bindings": {"a": "y", "y": "a"}},
            },
        )
        self.assertEqual(response.json()["effective"]["bindings"]["b"], "x")
        self.assertEqual(response.json()["effective"]["bindings"]["a"], "y")
        response = self.client.put(
            route, headers=self.headers, json={"revision": 2, "profile": {}}
        )
        self.assertEqual(response.json()["effective"]["resolution"], "1080p")
        self.assertEqual(response.json()["effective"]["bindings"]["a"], "a")

    def test_conflicting_write_does_not_overwrite_settings(self):
        save_profile(self.root, "ps2", None, {"resolution": "720p"}, 0)
        response = self.client.put(
            "/api/emulation/profiles/ps2",
            headers=self.headers,
            json={"revision": 0, "profile": {"resolution": "1440p"}},
        )
        self.assertEqual(response.status_code, 409)
        document = json.loads((self.root / "profiles.json").read_text())
        self.assertEqual(effective_profile(document, "ps2")["resolution"], "720p")

    def test_platform_change_cannot_break_existing_game_mapping(self):
        save_profile(
            self.root, "ps2", self.game_id, {"bindings": {"a": "b", "b": "a"}}, 0
        )
        response = self.client.put(
            "/api/emulation/profiles/ps2",
            headers=self.headers,
            json={"revision": 1, "profile": {"bindings": {"a": "x", "x": "a"}}},
        )
        self.assertEqual(response.status_code, 422)
        document = json.loads((self.root / "profiles.json").read_text())
        self.assertEqual(document["revision"], 1)
        self.assertEqual(
            effective_profile(document, "ps2", self.game_id)["bindings"]["a"], "b"
        )

    def test_rejects_unknown_buttons_and_unsupported_settings(self):
        for system, settings in [
            ("ps2", {"bindings": {"a": "../../secret"}}),
            ("xbox", {"resolution": "1440p"}),
            ("n64", {"aspect": "16:9"}),
            ("ps2", {"osd_scale": 500}),
            ("ps2", {"command": "touch /tmp/no"}),
        ]:
            response = self.client.put(
                f"/api/emulation/profiles/{system}",
                headers=self.headers,
                json={"revision": 0, "profile": settings},
            )
            self.assertEqual(response.status_code, 422)
        self.assertFalse((self.root / "profiles.json").exists())

    def test_game_must_belong_to_selected_platform(self):
        response = self.client.get(
            f"/api/emulation/profiles/gc?game_id={self.game_id}", headers=self.headers
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.get(
            "/api/emulation/profiles/ps2?game_id=../secret", headers=self.headers
        )
        self.assertEqual(response.status_code, 422)

    def test_corrupt_status_is_reported_as_unavailable(self):
        (self.root / "sessions.json").write_text("not JSON")
        response = self.client.get("/api/emulation", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(str(self.root), response.text)

    def test_full_multibyte_history_is_available(self):
        sessions = [
            {
                "id": str(index),
                "system": "ps2",
                "game": "game.iso",
                "started": 1,
                "ended": 2,
                "messages": [
                    {
                        "timestamp": 1,
                        "source": "PCSX2",
                        "level": "warning",
                        "text": "界" * 1500,
                    }
                    for _ in range(40)
                ],
            }
            for index in range(30)
        ]
        atomic_json(self.root / "sessions.json", sessions)
        response = self.client.get("/api/emulation", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["sessions"]), 30)

    def test_corrupt_catalog_is_unavailable_for_game_profiles(self):
        (self.root / "catalog.json").write_text("not JSON")
        route = f"/api/emulation/profiles/ps2?game_id={self.game_id}"
        for method, kwargs in [
            ("get", {}),
            ("put", {"json": {"revision": 0, "profile": {}}}),
        ]:
            response = getattr(self.client, method)(
                route, headers=self.headers, **kwargs
            )
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(str(self.root), response.text)

    def test_corrupt_profile_is_unavailable_without_exposing_paths(self):
        (self.root / "profiles.json").write_text("not JSON")
        response = self.client.get("/api/emulation/profiles/ps2", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(str(self.root), response.text)
        response = self.client.put(
            "/api/emulation/profiles/ps2",
            headers=self.headers,
            json={"revision": 0, "profile": {}},
        )
        self.assertEqual(response.status_code, 503)

    def test_integration_is_disabled_until_configured(self):
        with patch.dict(os.environ, {"ROMM_EMULATION_PATH": ""}):
            response = self.client.get("/api/emulation", headers=self.headers)
            self.assertFalse(response.json()["enabled"])
            response = self.client.get(
                "/api/emulation/profiles/ps2", headers=self.headers
            )
            self.assertEqual(response.status_code, 503)
