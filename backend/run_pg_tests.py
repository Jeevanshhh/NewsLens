"""Runs the real-PostgreSQL RLS suite against the local server.

Credential handling (per the operator's constraints):
* The admin password is read from the existing local pgpass file INTO MEMORY and
  supplied via the in-process PGPASSWORD environment variable.
* It is NEVER embedded in a URL, NEVER printed, NEVER written to any file, and
  NEVER placed on a command line / shell history.
* The test URL therefore carries NO password; libpq authenticates via PGPASSWORD.

Results are captured in JUnit XML (pg_results.xml) so they can be read reliably
even though this sandbox's console capture is flaky.
"""
import os
import sys
import traceback

BACKEND = os.path.dirname(os.path.abspath(__file__))
os.chdir(BACKEND)
sys.path.insert(0, BACKEND)

LOG = os.path.join(BACKEND, "run_pg.log")
_fh = open(LOG, "w", encoding="utf-8")


def log(*a):
    _fh.write(" ".join(str(x) for x in a) + "\n")
    _fh.flush()


try:
    pp = os.path.expandvars(r"%APPDATA%\postgresql\pgpass.conf")
    pw = None
    for line in open(pp, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line and not line.startswith("#"):
            f = line.split(":")
            if len(f) >= 5 and f[3] == "postgres":
                pw = f[4]
                break
    if not pw:
        log("NO_ADMIN_PGPASS_ENTRY -> cannot proceed")
        sys.exit(2)
    os.environ["PGPASSWORD"] = pw
    log("password loaded from pgpass (len=%d), supplied via PGPASSWORD env only" % len(pw))

    # No password in the URL -> authenticates via PGPASSWORD. IPv4 host avoids
    # the sandbox's localhost/::1 resolution timeout.
    os.environ["NEWSELENS_PG_TEST_URL"] = "postgresql+psycopg://postgres@127.0.0.1:5432/postgres"
    log("NEWSELENS_PG_TEST_URL set (host=127.0.0.1, no inline password)")

    import pytest
    log("starting pytest ...")
    code = pytest.main([
        os.path.join(BACKEND, "tests", "test_postgres_rls_enforcement.py"),
        "-v", "-o", "addopts=", "-p", "no:cacheprovider", "--tb=short",
        "--junitxml=" + os.path.join(BACKEND, "pg_results.xml"),
    ])
    log("PYTEST_EXIT", int(code))
    sys.exit(int(code))
except SystemExit:
    raise
except BaseException:  # noqa: BLE001
    log("RUNNER_ERROR")
    log(traceback.format_exc(limit=4))
    sys.exit(1)
finally:
    _fh.close()
