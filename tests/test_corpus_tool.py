import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('corpus_tool', Path(__file__).resolve().parents[1] / 'scripts/corpus_tool.py')
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.demo = self.root / 'demo'
        c.demo(self.demo)
        self.tables = c.read_tables(self.demo / 'junior_demo')

    def tearDown(self):
        self.tmp.cleanup()

    def pack(self, stage='初中'):
        out = self.root / (stage + '.sqlite')
        c.pack(self.demo / (stage + '.json'), out)
        return out

    def test_demo_valid_and_candidate(self):
        self.assertEqual(c.check_tables(self.tables), [])
        report = c.validate(self.pack())
        self.assertTrue(report['passed'])
        self.assertEqual(report['unresolved_captions'], 1)
        self.assertEqual(report['embedded_blobs_checked'], 1)

    def test_three_files_exact_union_preserves_components(self):
        junior, senior = self.pack(), self.pack('高中')
        before = [c.digest(x.read_bytes()) for x in (junior, senior)]
        merged = self.root / 'combined.sqlite'
        result = c.merge([junior, senior], merged, 'merged-demo')
        self.assertTrue(result['passed'])
        self.assertEqual(result['counts']['textbooks'], 2)
        self.assertEqual(result['counts']['blocks'], 6)
        self.assertEqual(result['embedded_blobs_checked'], 1)
        self.assertEqual(len(result['exact_union_checks']), 2)
        self.assertEqual(before, [c.digest(x.read_bytes()) for x in (junior, senior)])

    def test_duplicate_component_refused(self):
        db = self.pack()
        out = self.root / 'duplicate.sqlite'
        with self.assertRaises(sqlite3.IntegrityError):
            c.merge([db, db], out, 'invalid')
        self.assertFalse(out.exists())

    def test_no_overwrite(self):
        db = self.pack()
        before = db.read_bytes()
        with self.assertRaises(FileExistsError):
            c.pack(self.demo / '初中.json', db)
        self.assertEqual(db.read_bytes(), before)

    def test_asset_roundtrip_and_readonly_search(self):
        db = self.pack()
        before = c.digest(db.read_bytes())
        rows = c.search(db, '地', 20)
        self.assertEqual(len(rows), 1)
        self.assertEqual(c.search(db, '%', 20), [])
        image = self.root / 'out.png'
        c.extract(db, 'junior_demo:asset', image)
        self.assertEqual(image.read_bytes(), (self.demo / 'junior_demo/images/demo.png').read_bytes())
        self.assertEqual(c.digest(db.read_bytes()), before)

    def test_export_images_and_links(self):
        out = self.root / 'markdown'
        c.export(self.pack(), out)
        links = json.loads((out / 'caption_links.json').read_text())
        self.assertIsNone(links[0]['target_id'])
        index = json.loads((out / 'asset_index.json').read_text())
        for path in index.values():
            self.assertTrue((out / path).is_file())
        self.assertIn('地球🌍', next(out.glob('*.md')).read_text())

    def test_path_traversal_rejected(self):
        for name in ('../private', '/absolute', 'x/../../y', 'a\\b', 'C:/secret', 'a//b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                c.safe_file(self.demo, name)

    def test_symlink_rejected(self):
        link = self.demo / 'leak.txt'
        try:
            link.symlink_to(self.demo / 'all.json')
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unavailable')
        with self.assertRaises(ValueError):
            c.safe_file(self.demo, 'leak.txt')

    def test_unlisted_original_image_rejected(self):
        manifest = c.read_json(self.demo / '初中.json')
        manifest['books'][0]['files'].pop()
        p = self.demo / 'missing.json'
        c.write_json(p, manifest)
        with self.assertRaises(ValueError):
            c.pack(p, self.root / 'missing.sqlite')

    def test_cycle_and_wrong_owner(self):
        t = copy.deepcopy(self.tables)
        t['structure_nodes'][1]['parent_id'] = t['structure_nodes'][2]['node_id']
        self.assertTrue(any('cycle' in e for e in c.check_tables(t)))
        t = copy.deepcopy(self.tables)
        t['blocks'][0]['owner_node_id'] = t['structure_nodes'][0]['node_id']
        self.assertTrue(any('owner' in e for e in c.check_tables(t)))

    def test_duplicate_ids_and_unmapped_source(self):
        t = copy.deepcopy(self.tables)
        t['blocks'].append(t['blocks'][0])
        self.assertTrue(any('duplicate' in e for e in c.check_tables(t)))
        t = copy.deepcopy(self.tables)
        t['blocks'][0]['source_record_ids'] = []
        self.assertTrue(any('unmapped' in e for e in c.check_tables(t)))

    def test_bad_bbox_and_unicode_offsets(self):
        t = copy.deepcopy(self.tables)
        t['block_fragments'][0]['bbox'] = [0, 0, 2, 1]
        self.assertTrue(any('bbox' in e for e in c.check_tables(t)))
        t = copy.deepcopy(self.tables)
        text = t['blocks'][0]['text_raw']
        t['block_fragments'][0]['text_end'] = len(text.encode('utf-16-le')) // 2
        self.assertTrue(any('codepoint' in e for e in c.check_tables(t)))

    def test_null_caption_not_human_confirmed(self):
        t = copy.deepcopy(self.tables)
        t['structural_links'][0]['review_status'] = 'human_confirmed'
        self.assertTrue(any('unresolved' in e for e in c.check_tables(t)))

    def test_corrupted_blob_fails_audit(self):
        db = self.pack()
        with sqlite3.connect(db) as con:
            con.execute("UPDATE file_blobs SET content=x'00'")
        self.assertFalse(c.validate(db)['passed'])

    def test_component_extra_column_survives(self):
        junior, senior = self.pack(), self.pack('高中')
        with sqlite3.connect(senior) as con:
            con.execute('ALTER TABLE blocks ADD COLUMN custom_note TEXT')
            con.execute("UPDATE blocks SET custom_note='preserve me'")
        out = self.root / 'union.sqlite'
        c.merge([junior, senior], out, 'schema-union')
        with c.readonly(out) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM blocks WHERE custom_note='preserve me'").fetchone()[0], 3)

    def test_bad_interval(self):
        t = copy.deepcopy(self.tables)
        t['structure_nodes'][1]['boundary_end_exclusive'] = t['structure_nodes'][1]['boundary_start']
        self.assertTrue(any('interval' in e for e in c.check_tables(t)))


if __name__ == '__main__':
    unittest.main()
