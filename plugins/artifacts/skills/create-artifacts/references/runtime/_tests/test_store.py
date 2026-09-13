import tempfile
import unittest
from pathlib import Path
from _app.store import CatalogStore
try:                                  # `discover -s _tests`
    from test_app import fixture_root
except ImportError:                    # `discover -s _tests -t .`
    from _tests.test_app import fixture_root

class CatalogStoreTest(unittest.TestCase):
    def test_refresh_rebuilds_only_after_filesystem_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root=fixture_root(directory);store=CatalogStore(root)
            original=store.get()["signature"]
            self.assertFalse(store.refresh())
            (root/"scripts"/"new.sh").write_text("# new proof\n")
            self.assertTrue(store.refresh())
            self.assertNotEqual(original,store.get()["signature"])

if __name__=="__main__":unittest.main()
