# Contributing to ConvertIt

Bug reports and contributions in English or Ukrainian are welcome.

## Report a problem

Search existing issues first, then use the bug-report form. Include your
ConvertIt version, Windows version, input/output formats, exact error and
reproduction steps. Share a small sanitized sample when possible. Never upload
private documents, credentials, personal audio or other confidential files.
Report security vulnerabilities through the private process in [SECURITY.md](SECURITY.md).

## Development

ConvertIt targets Windows 11 x64 and Python 3.14. The native Explorer extension
uses Visual C++ Build Tools; packaging uses the Windows SDK. See the build
section of the [README](../README.md) and [component notices](../licenses/THIRD_PARTY.md).
Native runtime preparation is currently manual; a source checkout does not
include the large third-party engines or a ready-to-run application.

Install the Python dependencies from `requirements.txt` and
`requirements-dev.txt`. A full build expects `vendor/`, `build-deps/`, and the
portable runtime paths listed in `build.ps1` and `tools/package_expanded.py`.

```powershell
python tools/check_repository.py
python -m unittest discover -s tests -p test_release_payload.py -v
python -m unittest discover -s tests -v
```

The first two checks use the standard library. Full integration tests require
Windows, the native runtimes and optional binary fixtures; unavailable fixtures
are skipped. CI does not download all engines or certify every conversion route.

## Pull requests

Keep changes focused and describe the user-visible behavior and validation.
Update the format registry and documentation when adding a route. Do not commit
builds, native dependency trees, test outputs, secrets or private sample files.
Preserve atomic output publication, source-file protection, overwrite consent,
all supported pages/tracks, and precision checks. Application messages belong in
the localization catalog: English by default, Ukrainian for Ukrainian Windows.

By contributing, you agree that your original contributions are licensed under
the project's AGPL-3.0-only license. Third-party code must retain its original
license and attribution. Follow the [Code of Conduct](CODE_OF_CONDUCT.md).
