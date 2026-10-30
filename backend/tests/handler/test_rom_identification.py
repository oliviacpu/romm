import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests._zipfile_shim import reload_zipfile

from handler.rom_identification import (
    HEAD_BYTES,
    TAIL_BYTES,
    identify_header,
    identify_path,
    identify_sample,
    platform_conflict,
)


def cartridge(platform):
    data = bytearray(32768)
    if platform == "n64":
        data[:4] = b"\x80\x37\x12\x40"
    elif platform == "genesis":
        data[0x100:0x104] = b"SEGA"
    else:
        data[0x7FF0:0x7FF8] = b"TMR SEGA"
        data[0x7FFF] = 0x50
    return bytes(data)


def archive(members):
    reload_zipfile()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as output:
        for name, data in members.items():
            output.writestr(name, data)
    return stream.getvalue()


class RomIdentificationTests(unittest.TestCase):
    def sample(self, name, data):
        return identify_sample(name, len(data), data[:HEAD_BYTES], data[-TAIL_BYTES:])

    def test_headers_override_misleading_game_names_and_extensions(self):
        for platform in ("n64", "genesis", "gamegear"):
            result = self.sample("Seaman.bin", cartridge(platform))
            self.assertEqual(result.platforms, [platform])
            self.assertEqual(result.evidence, "header")

    def test_all_n64_byte_orders(self):
        for value in ("80371240", "37804012", "40123780"):
            self.assertEqual(identify_header(bytes.fromhex(value)).platforms, ["n64"])

    def test_32x_and_sega_cd_are_not_mistaken_for_genesis(self):
        data = bytearray(512)
        data[0x100:0x108] = b"SEGA 32X"
        self.assertEqual(identify_header(bytes(data)).platforms, ["sega32"])
        data[:14] = b"SEGADISCSYSTEM"
        self.assertEqual(identify_header(bytes(data)).platforms, ["segacd"])

    def test_raw_cd_headers_need_the_sector_sync_marker(self):
        for offset in (16, 24):
            data = bytearray(256)
            data[offset : offset + 16] = b"SEGA SEGAKATANA "
            self.assertEqual(identify_header(bytes(data)).platforms, [])
            data[:12] = b"\0" + b"\xff" * 10 + b"\0"
            self.assertEqual(identify_header(bytes(data)).platforms, ["dc"])

    def test_zip_uses_member_contents_rather_than_outer_or_inner_extension(self):
        result = self.sample(
            "test.zip", archive({"unknown.bin": cartridge("gamegear")})
        )
        self.assertEqual(result.platforms, ["gamegear"])
        self.assertEqual(result.evidence, "archive-headers")
        self.assertTrue(platform_conflict(result, "n64"))

    def test_archive_sidecars_do_not_hide_a_known_platform(self):
        result = self.sample(
            "game.zip",
            archive(
                {
                    "game.md": cartridge("genesis"),
                    "readme.txt": b"instructions",
                    "__MACOSX/._game.md": b"metadata",
                }
            ),
        )
        self.assertEqual(result.platforms, ["genesis"])

    def test_mixed_archive_cannot_be_assigned_to_either_platform(self):
        result = self.sample(
            "mixed.zip",
            archive(
                {
                    "one.n64": cartridge("n64"),
                    "two.md": cartridge("genesis"),
                }
            ),
        )
        self.assertEqual(result.platforms, ["genesis", "n64"])
        self.assertTrue(platform_conflict(result, "n64"))
        self.assertTrue(platform_conflict(result, "genesis"))

    def test_unknown_member_prevents_positive_archive_identification(self):
        result = self.sample(
            "unknown.zip",
            archive(
                {
                    "one.n64": cartridge("n64"),
                    "unknown.bin": b"not a known header",
                }
            ),
        )
        self.assertEqual(result.platforms, [])
        self.assertFalse(result.invalid)

    def test_zero_filled_zip_is_rejected_as_an_archive(self):
        result = self.sample("Sonic.zip", bytes(100000))
        self.assertTrue(result.invalid)
        self.assertTrue(platform_conflict(result, "n64"))

    def test_chd_does_not_claim_a_platform_from_its_extension(self):
        data = bytearray(124)
        data[:8] = b"MComprHD"
        data[12:16] = b"\0\0\0\x05"
        data[84:104] = bytes(range(20))
        result = self.sample("Seaman.chd", bytes(data))
        self.assertEqual(result.platforms, [])
        self.assertEqual(result.chd_sha1, bytes(range(20)).hex())
        self.assertTrue(platform_conflict(result, "n64"))
        self.assertFalse(platform_conflict(result, "dc"))

    def test_rvz_distinguishes_gamecube_and_wii(self):
        for kind, platform in ((1, "ngc"), (2, "wii")):
            data = bytearray(128)
            data[:4] = b"RVZ\x01"
            data[0x48:0x4C] = kind.to_bytes(4, "big")
            self.assertEqual(identify_header(bytes(data)).platforms, [platform])

    def test_unknown_files_remain_unknown(self):
        result = self.sample("Shadow of the Colossus.chd", b"unrecognized")
        self.assertEqual(result.platforms, [])
        self.assertEqual(result.evidence, "unknown")

    def test_inspection_is_bounded_by_archive_member_count(self):
        result = self.sample("many.zip", archive({f"{i}.bin": b"x" for i in range(65)}))
        self.assertEqual(result.evidence, "archive-limit")
        self.assertEqual(result.members, [])

    def test_commit_inspects_actual_staged_bytes_using_the_original_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory) / ".random.uploading"
            staged.write_bytes(archive({"game.bin": cartridge("genesis")}))
            self.assertEqual(identify_path(staged, "game.zip").platforms, ["genesis"])

    def test_sample_lengths_are_validated(self):
        with self.assertRaises(ValueError):
            identify_sample("game", 1, b"longer than the file", b"")
