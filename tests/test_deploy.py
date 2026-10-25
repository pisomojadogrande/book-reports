import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import deploy


class SyncTests(unittest.TestCase):
    def test_incremental_full_and_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / 'covers').mkdir()
            files = {'covers/old.png': b'old', 'covers/new.png': b'new',
                     'index.html': b'updated'}
            for key, content in files.items():
                (site / key).write_bytes(content)
            s3 = MagicMock()
            s3.get_paginator.return_value.paginate.return_value = [
                {'Contents': [{'Key': 'covers/old.png',
                               'ETag': '"' + hashlib.md5(b'old').hexdigest() + '"'}]},
                {'Contents': [{'Key': 'index.html', 'ETag': '"outdated"'}]},
            ]
            with patch.object(deploy, 'SITE_DIR', site), patch.object(deploy.boto3, 'Session') as session:
                session.return_value.client.return_value = s3
                deploy.sync_to_s3('bucket', False)
                self.assertEqual({call.args[2] for call in s3.upload_file.call_args_list},
                                 {'covers/new.png', 'index.html'})
                s3.reset_mock()
                deploy.sync_to_s3('bucket', False, full=True)
                self.assertEqual(s3.upload_file.call_count, 3)
                s3.get_paginator.assert_not_called()
                s3.reset_mock()
                deploy.sync_to_s3('bucket', True)
                s3.upload_file.assert_not_called()

    def test_empty_bucket(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / 'index.html').write_text('page')
            with patch.object(deploy, 'SITE_DIR', site), patch.object(deploy.boto3, 'Session') as session:
                s3 = session.return_value.client.return_value
                s3.get_paginator.return_value.paginate.return_value = [{}]
                deploy.sync_to_s3('bucket', False)
                s3.upload_file.assert_called_once()


if __name__ == '__main__':
    unittest.main()
