import importlib.util
from pathlib import Path
import sqlite3
import unittest

spec=importlib.util.spec_from_file_location('rules_index',Path(__file__).resolve().parents[1]/'dev-tools/rules_index.py')
rules_index=importlib.util.module_from_spec(spec);spec.loader.exec_module(rules_index)


class RulesIndexTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.addCleanup(self.db.close);rules_index.initialize(self.db)

    def test_source_groups_physical_pages_and_literal_queries(self):
        rules_index.store_pages(self.db,'book.pdf','Core','official','a',['','Initiative draws cards.','Pushing a roll.'])
        rules_index.store_pages(self.db,'variant.pdf','Variant','reforged','b',['Initiative variant.'])
        rows=rules_index.search(self.db,'инициатива','official')
        self.assertEqual([(r['title'],r['pdfPage'],r['group']) for r in rows],[('Core',2,'official')])
        self.assertEqual(rules_index.search(self.db,'пойти на риск')[0]['pdfPage'],3)
        self.assertEqual(len(rules_index.search(self.db,'initiative')),2)
        self.assertEqual(rules_index.search(self.db,'initiative OR nonexistent'),[])
        with self.assertRaises(ValueError):rules_index.search(self.db,'"*')

    def test_reindex_is_atomic_and_removes_outdated_pages(self):
        args=(self.db,'book.pdf','Core','official')
        self.assertTrue(rules_index.store_pages(*args,'a',['Old mechanic.']))
        self.assertFalse(rules_index.store_pages(*args,'a',['Old mechanic.']))
        self.assertTrue(rules_index.store_pages(*args,'b',['','New mechanic.']))
        self.assertEqual(rules_index.search(self.db,'old'),[])
        self.assertEqual(rules_index.search(self.db,'new')[0]['pdfPage'],2)
        self.assertEqual(self.db.execute('SELECT count(*) FROM books').fetchone()[0],1)


if __name__=='__main__':unittest.main()
