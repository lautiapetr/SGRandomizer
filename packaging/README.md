# Desktop packaging

`packaging/sgrand.spec` freezes the PySide6 application without SoulGold data.
The GitHub Actions workflow publishes four independently built artifacts:

- Windows x64 directory archive;
- Linux x86_64 AppImage;
- macOS Intel application archive;
- macOS Apple Silicon application archive.

The jobs fail if a `.gba`, `.elf` or `.map` file appears in the assembled
package. They never clone SoulGold: the application downloads the supported
tag only after an end user explicitly selects a destination.

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
