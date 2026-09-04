"""
tests/test_backup_engine_list_bound.py

P0 R2 COST AUDIT FIX: agent/backup/backup_engine.py::_S3Storage.list_keys()
previously issued a fully unbounded paginated list_objects_v2 call --
_purge_old_backups() (called from every run_full_backup()) depends on it to
find expired backups, and the backup archive only ever grows over time. This
backend is only reached when CDB_BACKUP_ENABLED=true (default false) AND
CDB_BACKUP_DESTINATION is s3/r2 (default "local", which uses _LocalStorage
instead) -- both opt-in, so this was a dormant-by-default defect, not a live
incident. Found during a post-merge forensic audit of PR #369's R2 cost
containment fix and hardened proactively so a future operator enabling
off-repo backups can't unknowingly reintroduce unbounded list-scaling
behavior. These tests prove the new _MAX_LIST_PAGES ceiling holds regardless
of how large the simulated backup archive is.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agent.backup.backup_engine import _S3Storage  # noqa: E402


def _make_fake_paginator(total_pages: int, keys_per_page: int = 1000):
    """Builds a fake boto3 paginator yielding `total_pages` pages, each with
    `keys_per_page` objects -- simulates an ever-growing backup archive."""
    pages = []
    for p in range(total_pages):
        contents = [{"Key": f"backups/full/page{p}/obj{i}.json"} for i in range(keys_per_page)]
        pages.append({"Contents": contents})

    fake_paginator = MagicMock()
    fake_paginator.paginate.return_value = iter(pages)
    return fake_paginator


class TestS3StorageListKeysBounded(unittest.TestCase):
    def _storage_with_fake_client(self, total_pages: int, keys_per_page: int = 1000) -> _S3Storage:
        storage = _S3Storage(bucket="fake-backup-bucket", prefix="")
        fake_client = MagicMock()
        fake_client.get_paginator.return_value = _make_fake_paginator(total_pages, keys_per_page)
        storage._client = fake_client  # bypass _get_client()'s real boto3.client() call
        return storage

    def test_list_keys_never_exceeds_max_list_pages_regardless_of_archive_size(self):
        """The core proof: an archive with far more pages than _MAX_LIST_PAGES
        must still only ever scan _MAX_LIST_PAGES worth of objects -- this is
        the exact defect class (operation cost scaling with accumulated
        history) the R2 cost incident this PR fixes was caused by."""
        total_pages = _S3Storage._MAX_LIST_PAGES * 50  # far beyond the cap
        storage = self._storage_with_fake_client(total_pages, keys_per_page=1000)

        keys = storage.list_keys(prefix="backups/full")

        self.assertLessEqual(
            len(keys), _S3Storage._MAX_LIST_PAGES * 1000,
            f"list_keys() returned {len(keys)} keys for a {total_pages}-page archive -- "
            f"must never exceed _MAX_LIST_PAGES ({_S3Storage._MAX_LIST_PAGES}) worth of pages "
            f"regardless of how large the backup archive has grown"
        )

    def test_list_keys_within_bound_returns_everything(self):
        """Sanity check the other direction: a small archive well under the
        cap must not lose any keys -- the bound must not degrade the normal
        case, only the pathological one."""
        small_pages = 3
        storage = self._storage_with_fake_client(small_pages, keys_per_page=10)

        keys = storage.list_keys(prefix="backups/full")

        self.assertEqual(len(keys), small_pages * 10)

    def test_list_keys_logs_a_warning_when_the_cap_is_hit(self):
        total_pages = _S3Storage._MAX_LIST_PAGES + 5
        storage = self._storage_with_fake_client(total_pages, keys_per_page=100)

        with patch("agent.backup.backup_engine.logger") as mock_logger:
            storage.list_keys(prefix="backups/full")

        mock_logger.warning.assert_called_once()
        warning_args = mock_logger.warning.call_args[0]
        self.assertIn("_MAX_LIST_PAGES", warning_args[0])


if __name__ == "__main__":
    unittest.main()
