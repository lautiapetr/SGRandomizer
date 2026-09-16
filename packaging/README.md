# Desktop packaging

`packaging/sgrand.spec` freezes the PySide6 application without SoulGold data.
The GitHub Actions workflow publishes four independently built artifacts:

- Windows x64 directory archive;
- Linux x86_64 AppImage;
- macOS Intel application archive;
- macOS Apple Silicon application archive.

The jobs fail if a game/ROM format or a recognizable SoulGold checkout path
appears in the assembled package. They never clone SoulGold: the application
downloads the supported tag only after an end user explicitly selects a
destination.

Build a local directory bundle with:

```bash
python -m pip install '.[packaging]'
python -m PyInstaller --noconfirm --clean packaging/sgrand.spec
```

## Signing limitations

CI artifacts are currently unsigned. Windows SmartScreen can therefore show
an unknown-publisher warning. A production release needs an Authenticode
certificate held outside the repository and a signing step before archiving.

The macOS `.app` bundles are ad-hoc signed by the freezing tool, not signed with
an Apple Developer ID and not notarized. Gatekeeper may quarantine them. A
production release needs Developer ID Application signing, hardened runtime,
notarization credentials stored as protected CI secrets and stapling after
notarization. Intel and Apple Silicon are built separately rather than as a
universal binary.

## GitHub Actions

`.github/workflows/release-gui.yml` runs on pull requests, pushes to `main`,
version tags and manual dispatches. Its test gate runs pytest, Ruff and mypy,
then independently builds Windows x64, Linux x86_64 AppImage, macOS Intel and
macOS Apple Silicon packages. Superseded pull-request runs are cancelled and
successful artifacts are retained for 14 days.

Before packaging, `scripts/verify_bundle.py --tracked` rejects generated build
roots and game/ROM formats accidentally tracked by Git. Every assembled bundle
is scanned again before upload:

```bash
python scripts/verify_bundle.py --tracked
python scripts/verify_bundle.py dist/SGRand
```

The workflow deliberately has read-only repository permissions and never
downloads or builds SoulGold itself.

The Ubuntu jobs install `libegl1`, `libgl1`, `libxkbcommon-x11-0` and
`libxcb-cursor0` before importing PySide6. Setting Qt to the offscreen platform
is not sufficient by itself because QtGui resolves EGL while the Python module
is imported, before a platform plugin is selected.
