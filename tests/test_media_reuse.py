import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import tosint


class MediaReuseTests(unittest.TestCase):
    def message(self, message_id=42, unique_id="unique", size=3, kind="document"):
        return SimpleNamespace(
            id=message_id, date=datetime(2026, 11, 12), media=kind, text="Example",
            **{kind: SimpleNamespace(file_name="report.bin", file_unique_id=unique_id, file_size=size)}
        )

    def record(self, path, **overrides):
        record = {"chat_id": 123, "media_type": "MessageMediaType.DOCUMENT",
                  "file_unique_id": "unique", "telegram_file_size": 3,
                  "downloaded_file_size": 3, "downloaded_file": tosint.display_path(str(path))}
        record.update(overrides)
        return record

    def manifest(self, directory, records, name="2026.11.11_messages_example.jsonl"):
        Path(directory, name).write_text("\n".join(json.dumps(record) for record in records) + "\n")

    def existing_file(self, directory):
        media_dir = Path(directory, "media")
        media_dir.mkdir(exist_ok=True)
        path = media_dir / "old.bin"
        path.write_bytes(b"abc")
        return path

    def process(self, directory, message, index, skip=False, hash_media=False):
        app = Mock()

        def download(message, file_name):
            Path(file_name).write_bytes(b"abc")
            return file_name

        app.download_media.side_effect = download
        result = {"media_downloaded": 0, "media_failed": 0, "media_reused": 0,
                  "messages_exported": 0, "errors": []}
        manifest, text = io.StringIO(), io.StringIO()
        tosint.process_download_message(message, app, 123, directory, manifest, text, result,
                                        skip_media=skip, hash_media=hash_media, media_index=index)
        return app, result, json.loads(manifest.getvalue()), text.getvalue()

    def test_previous_attachment_is_reused_without_network_or_default_hashing(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = self.existing_file(directory)
            self.manifest(directory, [self.record(existing)])
            errors = []
            index = tosint.load_media_reuse_index(directory, "123", errors)
            with patch.object(tosint, "hash_file_sha256") as hashing:
                app, result, payload, text = self.process(directory, self.message(), index)
            app.download_media.assert_not_called()
            hashing.assert_not_called()
            self.assertEqual(result["media_reused"], 1)
            self.assertEqual(result["media_downloaded"], 0)
            self.assertEqual(result["media_failed"], 0)
            self.assertEqual(Path(payload["downloaded_file"]).resolve(), existing.resolve())
            self.assertEqual(payload["downloaded_file_size"], 3)
            self.assertIn(payload["downloaded_file"], text)
            self.assertEqual(errors, [])

    def test_missing_changed_or_incompletely_recorded_files_are_downloaded(self):
        for problem in ("missing", "truncated", "different_id", "different_size", "missing_size"):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as directory:
                existing = self.existing_file(directory)
                record = self.record(existing)
                if problem == "missing":
                    existing.unlink()
                elif problem == "truncated":
                    existing.write_bytes(b"a")
                elif problem == "different_id":
                    record["file_unique_id"] = "other"
                elif problem == "different_size":
                    record["telegram_file_size"] = 4
                elif problem == "missing_size":
                    record.pop("downloaded_file_size")
                self.manifest(directory, [record])
                index = tosint.load_media_reuse_index(directory, 123, [])
                app, result, _, _ = self.process(directory, self.message(), index)
                app.download_media.assert_called_once()
                self.assertEqual(result["media_reused"], 0)
                self.assertEqual(result["media_downloaded"], 1)

    def test_cached_file_is_rechecked_when_it_changes_after_indexing(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = self.existing_file(directory)
            self.manifest(directory, [self.record(existing)])
            index = tosint.load_media_reuse_index(directory, 123, [])
            existing.write_bytes(b"changed")
            app, result, _, _ = self.process(directory, self.message(), index)
            app.download_media.assert_called_once()
            self.assertEqual(result["media_reused"], 0)

    def test_files_outside_the_chat_media_directory_are_not_reused(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            external = Path(outside, "file.bin")
            external.write_bytes(b"abc")
            self.manifest(directory, [self.record(external)])
            index = tosint.load_media_reuse_index(directory, 123, [])
            self.assertEqual(index, {})
            app, _, _, _ = self.process(directory, self.message(), index)
            app.download_media.assert_called_once()

    def test_records_for_other_chats_or_media_types_are_not_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = self.existing_file(directory)
            self.manifest(directory, [self.record(existing, chat_id=456),
                                      self.record(existing, media_type="MessageMediaType.STICKER")])
            self.assertEqual(tosint.load_media_reuse_index(directory, 123, []), {})

    def test_legacy_records_and_incomplete_jsonl_do_not_prevent_valid_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = self.existing_file(directory)
            self.manifest(directory, [self.record(existing), {"message_id": 1}, []],
                          name="messages_legacy.jsonl")
            with Path(directory, "messages_legacy.jsonl").open("a") as source:
                source.write('{"partial":')
            self.manifest(directory, [self.record(existing)])
            index = tosint.load_media_reuse_index(directory, 123, [])
            self.assertEqual(sum(len(paths) for paths in index.values()), 1)
            app, result, _, _ = self.process(directory, self.message(), index)
            app.download_media.assert_not_called()
            self.assertEqual(result["media_reused"], 1)

    def test_two_messages_with_the_same_attachment_download_only_once(self):
        with tempfile.TemporaryDirectory() as directory:
            index = {}
            first_app, first_result, first, _ = self.process(directory, self.message(1), index)
            second_app, second_result, second, _ = self.process(directory, self.message(2), index)
            first_app.download_media.assert_called_once()
            second_app.download_media.assert_not_called()
            self.assertEqual(first_result["media_downloaded"], 1)
            self.assertEqual(second_result["media_reused"], 1)
            self.assertEqual(first["downloaded_file"], second["downloaded_file"])

    def test_skip_media_does_not_reuse_or_download_files(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = self.existing_file(directory)
            self.manifest(directory, [self.record(existing)])
            index = tosint.load_media_reuse_index(directory, 123, [])
            app, result, payload, _ = self.process(directory, self.message(), index, skip=True)
            app.download_media.assert_not_called()
            self.assertEqual(result["media_reused"], 0)
            self.assertIsNone(payload["downloaded_file"])

    def test_explicit_hashing_also_hashes_reused_files(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = self.existing_file(directory)
            self.manifest(directory, [self.record(existing)])
            index = tosint.load_media_reuse_index(directory, 123, [])
            with patch.object(tosint, "hash_file_sha256", return_value="digest") as hashing:
                app, result, payload, _ = self.process(directory, self.message(), index, hash_media=True)
            hashing.assert_called_once()
            self.assertEqual(Path(hashing.call_args.args[0]).resolve(), existing.resolve())
            app.download_media.assert_not_called()
            self.assertEqual(payload["sha256"], "digest")
            self.assertEqual(result["media_reused"], 1)


if __name__ == "__main__":
    unittest.main()
