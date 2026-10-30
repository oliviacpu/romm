import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "romsort", Path(__file__).with_name("romsort.py")
)
romsort = importlib.util.module_from_spec(spec)
spec.loader.exec_module(romsort)


class SorterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.inbox = self.root / "inbox"
        self.library = self.root / "library"
        self.inbox.mkdir()
        self.library.mkdir()

    def cartridge(self, name="game.bin"):
        path = self.inbox / name
        data = bytearray(32768)
        data[0x7FF0:0x7FF8] = b"TMR SEGA"
        data[0x7FFF] = 0x50
        path.write_bytes(data)
        return path

    def test_gamegear_uses_canonical_folder_and_preserves_source(self):
        path = self.cartridge()
        romsort.run(self.inbox, self.library, "auto", False, 0, {})
        self.assertTrue(path.exists())
        self.assertEqual(
            (self.library / "gamegear" / path.name).read_bytes(), path.read_bytes()
        )
        self.assertFalse((self.library / "gg").exists())

    def test_unresolved_file_stays_at_original_seeding_path(self):
        path = self.inbox / "not-a-switch.nsp"
        path.write_bytes(b"unknown")
        romsort.run(self.inbox, self.library, "auto", False, 0, {})
        self.assertTrue(path.exists())
        self.assertEqual(list(self.library.iterdir()), [])

    def test_duplicate_preserves_original_and_does_not_create_another_copy(self):
        path = self.cartridge()
        romsort.run(self.inbox, self.library, "copy", False, 0, {})
        (self.inbox / ".romsort-content-v2.json").unlink()
        romsort.run(self.inbox, self.library, "auto", False, 0, {})
        self.assertTrue(path.exists())
        self.assertEqual(len(list(self.library.rglob("*.bin"))), 1)

    def test_existing_different_file_is_not_overwritten(self):
        path = self.cartridge()
        target = self.library / "gamegear" / path.name
        target.parent.mkdir()
        target.write_bytes(b"keep me")
        romsort.run(self.inbox, self.library, "auto", False, 0, {})
        self.assertEqual(target.read_bytes(), b"keep me")
        self.assertTrue(path.exists())

    def test_folder_symlink_is_rejected(self):
        bundle = self.inbox / "bundle"
        bundle.mkdir()
        (bundle / "external").symlink_to(self.cartridge())
        with self.assertRaisesRegex(ValueError, "symlink"):
            romsort.identify(bundle, {})

    def test_descriptor_cannot_escape_bundle(self):
        bundle = self.inbox / "bundle"
        bundle.mkdir()
        (bundle / "game.cue").write_text('FILE "../outside.bin" BINARY\n')
        with self.assertRaisesRegex(ValueError, "unsafe"):
            romsort.identify(bundle, {})

    def test_disc_bundle_uses_declared_track_and_positive_boot_header(self):
        bundle = self.inbox / "bundle"
        bundle.mkdir()
        (bundle / "game.cue").write_text(
            'FILE "unhelpful.bin" BINARY\n TRACK 01 MODE1/2352\n'
        )
        (bundle / "unhelpful.bin").write_bytes(
            b"\0" + b"\xff" * 10 + b"\0" + bytes(4) + b"SEGA SEGAKATANA "
        )
        self.assertEqual(romsort.identify(bundle, {})[0], "dc")

    def test_disc_capacity_and_filename_do_not_determine_platform(self):
        path = self.inbox / "seaman.chd"
        data = bytearray(124)
        data[:8] = b"MComprHD"
        data[12:16] = (5).to_bytes(4, "big")
        path.write_bytes(data)
        self.assertIsNone(romsort.identify(path, {})[0])

    def test_changed_source_is_not_promoted(self):
        path = self.cartridge()
        before = romsort.signature(path)
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            romsort.place(path, self.library / "gamegear" / path.name, "copy", before)
        self.assertFalse((self.library / "gamegear" / path.name).exists())
        self.assertEqual(list((self.library / "gamegear").iterdir()), [])

    def test_collection_is_imported_as_individual_games(self):
        collection = self.inbox / "collection"
        collection.mkdir()
        self.cartridge("one.bin").rename(collection / "one.bin")
        self.cartridge("two.bin").rename(collection / "two.bin")
        romsort.run(self.inbox, self.library, "copy", False, 0, {})
        self.assertTrue((self.library / "gamegear/one.bin").is_file())
        self.assertTrue((self.library / "gamegear/two.bin").is_file())
        self.assertFalse((self.library / "gamegear/collection").exists())
        self.assertTrue((collection / "one.bin").exists())

    def test_mixed_folder_is_not_filed_as_first_game(self):
        bundle = self.inbox / "batch"
        bundle.mkdir()
        self.cartridge().rename(bundle / "one.bin")
        (bundle / "two.bin").write_bytes(b"\x80\x37\x12\x40")
        self.assertIsNone(romsort.identify(bundle, {})[0])


if __name__ == "__main__":
    unittest.main()
