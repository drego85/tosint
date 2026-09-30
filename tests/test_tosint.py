import os
import tempfile
import unittest
from pathlib import Path

from tosint import open_download_client


class FakeSessionRevoked(Exception):
    pass


class FakeStorage:
    def __init__(self, database):
        self.database = Path(database)


class FakeClient:
    start_calls = 0
    stop_calls = 0

    def __init__(self, session_name, **kwargs):
        self.storage = FakeStorage(f"{session_name}.session")

    def start(self):
        type(self).start_calls += 1
        if type(self).start_calls == 1:
            raise FakeSessionRevoked()
        return self

    def stop(self):
        type(self).stop_calls += 1


class RevokedSessionRecoveryTests(unittest.TestCase):
    def setUp(self):
        FakeClient.start_calls = 0
        FakeClient.stop_calls = 0

    def test_revoked_bot_session_is_archived_and_recreated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_name = os.path.join(temp_dir, "tosint_bot")
            session_path = f"{session_name}.session"
            with open(session_path, "wb") as session_file:
                session_file.write(b"revoked-session")
            with open(f"{session_path}-journal", "wb") as journal_file:
                journal_file.write(b"sqlite-journal")

            recovery_info = {}
            with open_download_client(
                FakeClient,
                FakeSessionRevoked,
                session_name,
                {},
                recover_revoked_session=True,
                recovery_info=recovery_info
            ):
                pass

            self.assertEqual(FakeClient.start_calls, 2)
            self.assertEqual(FakeClient.stop_calls, 1)
            self.assertTrue(recovery_info["session_recovered"])
            archive_path = recovery_info["revoked_session_archive"]
            self.assertTrue(os.path.isfile(archive_path))
            with open(archive_path, "rb") as archive_file:
                self.assertEqual(archive_file.read(), b"revoked-session")
            with open(f"{archive_path}-journal", "rb") as journal_file:
                self.assertEqual(journal_file.read(), b"sqlite-journal")
            self.assertFalse(os.path.exists(session_path))
            self.assertFalse(os.path.exists(f"{session_path}-journal"))

    def test_revoked_user_session_is_not_archived_automatically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_name = os.path.join(temp_dir, "tosint_user")
            session_path = f"{session_name}.session"
            with open(session_path, "wb") as session_file:
                session_file.write(b"revoked-session")

            with self.assertRaises(FakeSessionRevoked):
                with open_download_client(
                    FakeClient,
                    FakeSessionRevoked,
                    session_name,
                    {},
                    recover_revoked_session=False
                ):
                    pass

            self.assertTrue(os.path.isfile(session_path))
            self.assertEqual(FakeClient.start_calls, 1)


if __name__ == "__main__":
    unittest.main()
