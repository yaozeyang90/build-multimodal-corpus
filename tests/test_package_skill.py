import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location('package_skill', Path(__file__).resolve().parents[1] / 'scripts/package_skill.py')
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        for name in p.TOP:
            (self.source / name).write_text('synthetic fixture', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def test_data_and_hidden_resource_forks_excluded(self):
        (self.source / 'textbook.pdf').write_bytes(b'private fixture')
        (self.source / '._SKILL.md').write_bytes(b'fork fixture')
        (self.source / 'private-data').mkdir()
        (self.source / 'private-data/private.md').write_text('private fixture')
        result = p.package(self.source, self.root / 'release')
        with zipfile.ZipFile(result['archive']) as z:
            names = z.namelist()
            self.assertEqual(len(names), len(p.TOP))
            self.assertFalse(any('private' in name or '._' in name for name in names))

    def test_credential_prevents_publication(self):
        (self.source / 'README.md').write_text('ghp_' + 'x' * 30)
        with self.assertRaises(ValueError):
            p.package(self.source, self.root / 'release')
        self.assertFalse((self.root / 'release').exists())

    def test_existing_release_untouched(self):
        out = self.root / 'release'
        p.package(self.source, out)
        before = (out / 'package-audit.json').read_bytes()
        with self.assertRaises(FileExistsError):
            p.package(self.source, out)
        self.assertEqual((out / 'package-audit.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
