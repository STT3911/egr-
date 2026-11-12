"""Exercise retention with real Bash/gzip and an isolated fake pg_dump."""

import gzip
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "db-backup.sh"


@unittest.skipUnless(
    os.name == "posix" and all(shutil.which(x) for x in ("bash", "gzip", "flock")),
    "requires Linux backup runtime",
)
class BackupScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backups = self.root / "backups with spaces"
        self.backups.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.fake_command(
            "docker",
            'printf "%s\\n" "-- test PostgreSQL dump"\nexit "${DUMP_EXIT:-0}"\n',
        )
        self.env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "EGR_BACKUP_DIR": str(self.backups),
        }

    def fake_command(self, name, body):
        command = self.bin / name
        command.write_text("#!/usr/bin/env bash\n" + body)
        command.chmod(0o755)

    def archive(self, name, payload=b"-- previous dump\n"):
        target = self.backups / name
        target.write_bytes(gzip.compress(payload))
        return target

    def run_script(self, *args, **env):
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            env={**self.env, **env},
            text=True,
            capture_output=True,
            timeout=20,
        )

    def test_success_keeps_new_dump_and_protects_unrelated_files(self):
        old = self.archive("egr_db_20200101_000000.sql.gz")
        protected = [
            self.backups / "egr_db_20200102_000000.sql.gz.tmp",
            self.backups / "egr_db_manual.sql.gz",
            self.backups / "another_database.sql.gz",
        ]
        for path in protected:
            path.write_bytes(b"untouched")
        directory = self.backups / "egr_db_20200103_000000.sql.gz"
        directory.mkdir()
        outside = self.root / "outside.gz"
        outside.write_bytes(b"untouched")
        link = self.backups / "egr_db_20200104_000000.sql.gz"
        link.symlink_to(outside)

        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(old.exists())
        self.assertTrue(all(p.read_bytes() == b"untouched" for p in protected))
        self.assertTrue(directory.is_dir())
        self.assertTrue(link.is_symlink())
        self.assertEqual(outside.read_bytes(), b"untouched")
        new = [p for p in self.backups.glob("*.sql.gz") if p.is_file() and not p.is_symlink()
               and p not in protected]
        self.assertEqual(len(new), 1)
        self.assertIn(b"PostgreSQL dump", gzip.decompress(new[0].read_bytes()))
        self.assertEqual(new[0].stat().st_mode & 0o777, 0o600)

    def test_failed_dump_preserves_old_and_removes_own_temp(self):
        old = self.archive("egr_db_20200101_000000.sql.gz")
        result = self.run_script(DUMP_EXIT="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(old.exists())
        self.assertEqual(list(self.backups.glob("*.tmp")), [])
        self.assertEqual(list(self.backups.glob("*.sql.gz")), [old])

    def test_failed_validation_preserves_old(self):
        old = self.archive("egr_db_20200101_000000.sql.gz")
        real_gzip = shutil.which("gzip")
        self.fake_command(
            "gzip", f'if [ "${{1:-}}" = "-t" ]; then exit 1; fi\nexec {real_gzip} "$@"\n'
        )
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.backups.glob("*.sql.gz")), [old])
        self.assertEqual(list(self.backups.glob("*.tmp")), [])

    def test_prune_uses_filename_date_and_never_calls_docker(self):
        old = self.archive("egr_db_20200101_000000.sql.gz")
        latest = self.archive("egr_db_20200201_000000.sql.gz")
        os.utime(latest, (1, 1))
        self.fake_command("docker", "exit 97\n")
        result = self.run_script("--prune-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(latest.exists())
        self.assertFalse(old.exists())

    def test_corrupt_latest_prevents_all_deletions(self):
        old = self.archive("egr_db_20200101_000000.sql.gz")
        latest = self.backups / "egr_db_20200201_000000.sql.gz"
        latest.write_bytes(b"corrupted")
        result = self.run_script("--prune-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(old.exists())
        self.assertEqual(latest.read_bytes(), b"corrupted")

    def test_empty_directory_is_noop(self):
        result = self.run_script("--prune-only")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_existing_target_is_never_overwritten(self):
        old = self.archive("egr_db_20200101_000000.sql.gz")
        self.fake_command("date", 'printf "20200101_000000\\n"\n')
        before = old.read_bytes()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(old.read_bytes(), before)

    def test_concurrent_run_cannot_prune(self):
        import fcntl

        old = self.archive("egr_db_20200101_000000.sql.gz")
        latest = self.archive("egr_db_20200201_000000.sql.gz")
        with (self.backups / ".db-backup.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_script("--prune-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(old.exists())
        self.assertTrue(latest.exists())

    def test_unknown_args_fail_before_creating_files(self):
        result = self.run_script("--unknown")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(list(self.backups.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
