"""Apply the app's single version definition to the packaged Mac bundle."""

import plistlib
from pathlib import Path

from bookmatch_app import BUILD_NUMBER, __version__


def main():
    path = Path(__file__).resolve().parent.parent / "dist/BookMatch.app/Contents/Info.plist"
    with path.open("rb") as stream:
        value = plistlib.load(stream)
    value["CFBundleShortVersionString"] = __version__
    value["CFBundleVersion"] = BUILD_NUMBER
    with path.open("wb") as stream:
        plistlib.dump(value, stream)


if __name__ == "__main__":
    main()
