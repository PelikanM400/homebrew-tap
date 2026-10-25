# Maintenance and review contract

## Local updater

Requires Python 3.9+ and its standard library only. No token or login is needed;
proxy environment credentials, netrc and ambient GitHub tokens are not used.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/update_formula.py
# Only after reviewing the preview:
python3 scripts/update_formula.py --apply
```

The updater paginates the fixed official GitHub releases endpoint, rejects malformed
metadata and ambiguous SemVer precedence, excludes drafts and includes releases
marked pre-release. Selection is by SemVer, not publication timestamp/API ordering.
Tags must be canonical `vMAJOR.MINOR.PATCH[-prerelease][+build]`; matching source
assets must be named `paperdrop-VERSION.tar.gz`. A Python/PEP 440 prerelease filename
that differs from its SemVer tag deliberately requires manual review instead of
being guessed or normalized.

The source asset and `SHA256SUMS` must each occur exactly once, with canonical
repository/tag/name URLs, uploaded state, bounded positive integer sizes and
lowercase GitHub `sha256:` digests. Checksums must contain unique safe filenames;
the downloaded sdist must match both its asset digest and `SHA256SUMS`. Network
requests are HTTPS GET only with bounded responses, a timeout and restricted
GitHub release-CDN redirects. A failure never produces a partial formula update.

Only the main formula's URL, inferred version and SHA-256 may change; an existing
explicit version is maintained if present, but this formula omits a redundant
version stanza for `brew audit`. Pillow/resource hashes and native dependencies
are left byte-for-byte unchanged. Downgrades, same-version asset replacement,
unknown formula layouts and symlink targets are refused. Writes require `--apply`
and use atomic replacement. No shell command, dependency update, commit, push,
release creation or CI dispatch is performed. Published checksums share the
upstream trust boundary; they are not independent publisher signatures.

## Formula acceptance

On both a supported macOS host and Linux with Homebrew:

```sh
brew style Formula/paperdrop.rb
brew install --build-from-source pelikanm400/tap/paperdrop
brew test pelikanm400/tap/paperdrop
brew audit --strict --online pelikanm400/tap/paperdrop
brew reinstall --build-from-source pelikanm400/tap/paperdrop
brew test pelikanm400/tap/paperdrop
brew uninstall pelikanm400/tap/paperdrop
```

CI registers the checked-out revision as the tap, not a potentially older remote
branch. Actions are pinned to full commit IDs, checkout persistence is disabled,
and permissions are read-only. No stored user credentials, services, schedule
installation, source-image downloads or real-desktop wallpaper operations belong
in CI. The read-only UI test binds only loopback on an ephemeral port, tests the
onboarding page/API, checks that configuration was not created and kills its child
in `finally`.

The formula builds Pillow from its checksummed sdist inside a private virtualenv,
with JPEG/zlib/WebP roots supplied explicitly and unrelated optional codecs disabled.
Do not add Homebrew's full Pillow formula merely to avoid one Python resource: it
brings unrelated codecs and does not automatically populate this isolated venv.
Pillow's build-backend requirements (setuptools and pybind11) are declared as
checksummed resources and installed before the isolated build is disabled; a
sandboxed build must not fetch build dependencies from an undeclared package index.
The macOS branch invokes `xcrun swiftc` on the helper source shipped in the sdist;
Linux does not build/install the helper. The formula never calls `paperdrop install`,
starts services/UI or writes the user's config at install/post-install/uninstall time.

Installed `paperdrop/_homebrew.py` contains exactly the contract:

```python
OPT_PREFIX = '<the formula opt_prefix>'
```

The path is written using Python `repr`, not interpolated Python source. The app
must use it for brew upgrade guidance, stable scheduled commands
(`opt/libexec/bin/python -I -m paperdrop`), PATH (`opt/bin`, Homebrew `bin`, system
bins) and the macOS helper (`opt/bin/paperdrop-set`). A Cellar-version path in a
scheduler is a regression. An ordinary package upgrade must not rewrite schedules
or resume a paused user job. First migration from pipx is a deliberate one-time
schedule replacement, after removing the old command, never a forced overwrite.

Actual macOS helper compilation and live launchd/Xfce desktop lifecycle require
separate target-device evidence. Linux packaging tests and CI do not certify them.
Retain pre-release status until the owner accepts real-device results.

## Primary references

- Homebrew language-specific formula authoring: https://docs.brew.sh/Language-Specific-Formulae
- Formula cookbook: https://docs.brew.sh/Formula-Cookbook
- Pillow build options: https://github.com/python-pillow/Pillow/blob/13.0.0/setup.py
- GitHub release API: https://docs.github.com/en/rest/releases/releases
