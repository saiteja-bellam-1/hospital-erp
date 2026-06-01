"""Single source of truth for the application version.

Bumped when a release ships. Consumed by:
  - launcher.py        (upgrade-in-place detection vs data/version.txt)
  - main.py            (FastAPI app version, exposed via GET /api/system/version)
  - update_service.py  (self-update: compares this against the release manifest)
  - installer/build_installer.bat (reads APP_VERSION and passes /DAppVersion=)

Keep this as the ONLY hardcoded version string in the codebase.
"""

APP_VERSION = "1.2.2"
