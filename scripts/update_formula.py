#!/usr/bin/env python3
"""Review-only updater for the fixed official PaperDrop release feed."""
import re
import hashlib
import json
import pathlib
import tempfile
import urllib.parse
import urllib.request

API_BASE = 'https://api.github.com/repos/PelikanM400/paperdrop/releases?per_page=100&page='


def validate_network_url(url, *, redirect=False):
    if not isinstance(url, str) or any(ord(c) < 33 or ord(c) > 126 for c in url):
        raise ValueError('invalid URL characters')
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.username is not None or parsed.password is not None
            or parsed.port is not None or parsed.fragment):
        raise ValueError('unsafe URL authority/scheme')
    if redirect and parsed.netloc == 'release-assets.githubusercontent.com' and parsed.path.startswith('/github-production-release-asset/'):
        return
    if re.fullmatch(re.escape(API_BASE) + r'[1-9][0-9]*', url, re.ASCII):
        return
    if url.startswith(DOWNLOAD_BASE):
        tail = url[len(DOWNLOAD_BASE):].split('/')
        if len(tail) == 2:
            tag, name = tail
            version_key(tag)
            if name in ('SHA256SUMS', 'SHA256SUMS.portable', 'paperdrop-' + tag[1:] + '.tar.gz'):
                return
    raise ValueError('URL outside fixed official release endpoints')


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_network_url(newurl, redirect=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_bytes(url):
    validate_network_url(url)
    api = url.startswith(API_BASE)
    limit = 4 * 1024 * 1024 if api else (
        65536 if url.endswith(('/SHA256SUMS', '/SHA256SUMS.portable')) else MAX_ARCHIVE)
    # No ambient token, netrc, cookies or credential-bearing proxy environment.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), SafeRedirect())
    request = urllib.request.Request(url, headers={
        'Accept': 'application/vnd.github+json' if api else 'application/octet-stream',
        'User-Agent': 'paperdrop-tap-review-updater',
    }, method='GET')
    with opener.open(request, timeout=30) as response:
        validate_network_url(response.geturl(), redirect=True)
        allowed = ('application/json',) if api else ('application/octet-stream', 'application/gzip',
                                                     'application/x-gzip', 'text/plain')
        if response.headers.get_content_type() not in allowed:
            raise ValueError('unexpected HTTP content type')
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError('response exceeds size limit')
        return data


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def fetch_releases(fetch=download_bytes):
    result = []
    for page in range(1, 101):
        data = json.loads(fetch(API_BASE + str(page)), object_pairs_hook=_unique_object)
        if not isinstance(data, list) or len(data) > 100:
            raise ValueError('invalid release list')
        result.extend(data)
        if len(data) < 100:
            return result
    raise ValueError('release pagination limit reached; refusing a partial result')


DOWNLOAD_BASE = 'https://github.com/PelikanM400/paperdrop/releases/download/'
HASH = re.compile(r'[0-9a-f]{64}', re.ASCII)
MAX_ARCHIVE = 64 * 1024 * 1024


def verified_release(release, fetch):
    select_release([release])  # strict flags/tag validation
    if release['draft']:
        raise ValueError('draft release')
    tag = release['tag_name']
    version = tag[1:]
    source_name = f'paperdrop-{version}.tar.gz'
    assets = release.get('assets')
    if not isinstance(assets, list) or any(not isinstance(x, dict) for x in assets):
        raise ValueError('assets must be a list of objects')

    def download(name, maximum):
        matches = [x for x in assets if x.get('name') == name]
        if len(matches) != 1:
            raise ValueError('missing or duplicate asset: ' + name)
        asset = matches[0]
        expected = DOWNLOAD_BASE + tag + '/' + name
        if asset.get('browser_download_url') != expected:
            raise ValueError('asset URL does not match official tag/name')
        if asset.get('state') != 'uploaded':
            raise ValueError('asset is not uploaded')
        if asset.get('content_type') not in ('application/octet-stream', 'application/gzip',
                                           'application/x-gzip', 'text/plain'):
            raise ValueError('unexpected asset content type')
        size = asset.get('size')
        digest = asset.get('digest')
        if type(size) is not int or not 0 < size <= maximum:
            raise ValueError('invalid asset size')
        if not isinstance(digest, str) or not digest.startswith('sha256:') or not HASH.fullmatch(digest[7:]):
            raise ValueError('invalid GitHub asset digest')
        data = fetch(expected)
        if not isinstance(data, bytes) or len(data) != size or hashlib.sha256(data).hexdigest() != digest[7:]:
            raise ValueError('download size/digest mismatch')
        return data

    checksum_assets = [asset.get('name') for asset in assets]
    sums_name = 'SHA256SUMS.portable' if 'SHA256SUMS.portable' in checksum_assets else 'SHA256SUMS'
    sums = download(sums_name, 65536)
    try:
        lines = sums.decode('ascii').splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError('checksums must be ASCII') from exc
    hashes = {}
    for line in lines:
        match = re.fullmatch(r'([0-9a-f]{64})  (paperdrop-[0-9A-Za-z.+-]+(?:\.tar\.gz|\.whl))', line, re.ASCII)
        if not match or match[2] in hashes:
            raise ValueError('invalid/duplicate SHA256SUMS entry')
        hashes[match[2]] = match[1]
    if source_name not in hashes:
        raise ValueError('source hash missing')
    source = download(source_name, MAX_ARCHIVE)
    actual = hashlib.sha256(source).hexdigest()
    if hashes[source_name] != actual:
        raise ValueError('sdist SHA256SUMS mismatch')
    return version, DOWNLOAD_BASE + tag + '/' + source_name, actual


SEMVER = re.compile(r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?', re.ASCII)


def version_key(tag):
    if not isinstance(tag, str) or not (match := SEMVER.fullmatch(tag)):
        raise ValueError('invalid SemVer tag')
    major, minor, patch, pre, _build = match.groups()
    identifiers = []
    for item in pre.split('.') if pre else []:
        if item.isascii() and item.isdigit():
            if len(item) > 1 and item[0] == '0':
                raise ValueError('leading zero in prerelease')
            identifiers.append((0, int(item)))
        else:
            identifiers.append((1, item))
    return (int(major), int(minor), int(patch), pre is None, tuple(identifiers))


def select_release(releases):
    if not isinstance(releases, list) or not releases:
        raise ValueError('no releases')
    eligible = []
    for release in releases:
        if not isinstance(release, dict):
            raise ValueError('release must be an object')
        if type(release.get('draft')) is not bool or type(release.get('prerelease')) is not bool:
            raise ValueError('release flags must be booleans')
        if release['draft']:
            continue
        key = version_key(release.get('tag_name'))
        eligible.append((key, release))
    if not eligible:
        raise ValueError('no published releases')
    eligible.sort(key=lambda item: item[0], reverse=True)
    if len(eligible) > 1 and eligible[0][0] == eligible[1][0]:
        raise ValueError('ambiguous release precedence')
    return eligible[0][1]


def rewrite_formula(source, payload):
    version, url, digest = payload
    key = version_key('v' + version)
    if url != DOWNLOAD_BASE + 'v' + version + '/paperdrop-' + version + '.tar.gz':
        raise ValueError('invalid new source URL')
    if not isinstance(digest, str) or not HASH.fullmatch(digest):
        raise ValueError('invalid new SHA256')
    if not source.startswith('class Paperdrop < Formula\n'):
        raise ValueError('unexpected formula class')
    old = {}
    for field in ('url', 'version', 'sha256'):
        matches = list(re.finditer(r'^  ' + field + r' "([^"\r\n]+)"$', source, re.MULTILINE))
        if field == 'version' and not matches:
            match = re.fullmatch(re.escape(DOWNLOAD_BASE) + r'v([^/]+)/paperdrop-\1\.tar\.gz', old['url'])
            if not match:
                raise ValueError('cannot infer version from existing URL')
            old['version'] = match[1]
            continue
        if len(matches) != 1:
            raise ValueError('expected exactly one main ' + field)
        old[field] = matches[0][1]
        if matches[0].start() > source.find('  resource '):
            raise ValueError('main field outside header')
    old_key = version_key('v' + old['version'])
    if old['url'] != DOWNLOAD_BASE + 'v' + old['version'] + '/paperdrop-' + old['version'] + '.tar.gz':
        raise ValueError('unexpected existing URL')
    if not HASH.fullmatch(old['sha256']):
        raise ValueError('unexpected existing SHA256')
    if key < old_key:
        raise ValueError('refusing downgrade')
    if key == old_key and (url != old['url'] or digest != old['sha256']):
        raise ValueError('refusing same-version asset mutation')
    for field, value in (('url', url), ('version', version), ('sha256', digest)):
        source = re.sub(r'^  ' + field + r' "[^"\r\n]+"$',
                        lambda _match: f'  {field} "{value}"', source, count=1, flags=re.MULTILINE)
    return source


def update_file(path, payload, *, apply=False):
    import fcntl
    import os
    import stat
    import tempfile
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('formula must be a regular file, not a symlink')
    original = path.read_bytes()
    updated = rewrite_formula(original.decode('utf-8'), payload).encode('utf-8')
    if not apply or original == updated:
        return updated.decode('utf-8')
    temporary = None
    backup = None
    lock_fd = None
    try:
        # Cooperating updater processes serialize on a sidecar lock; the backup
        # link below is the second line of defence for an editor that changes the
        # formula during the replace window.
        lock_path = path.with_name('.' + path.name + '.lock')
        lock_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        if not stat.S_ISREG(path.lstat().st_mode) or path.read_bytes() != original:
            raise ValueError('formula changed during update')
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.paperdrop-', delete=False) as handle:
            temporary = handle.name
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), stat.S_IMODE(path.stat().st_mode))
        placeholder = tempfile.mkstemp(dir=path.parent, prefix='.paperdrop-backup-')[1]
        os.unlink(placeholder)
        backup = placeholder
        os.link(path, backup, follow_symlinks=False)
        if not stat.S_ISREG(path.lstat().st_mode) or path.read_bytes() != original:
            raise ValueError('formula changed during update')
        os.replace(temporary, path)
        temporary = None
        if backup is not None and pathlib.Path(backup).read_bytes() != original:
            # An uncooperative editor wrote the old inode while we replaced the
            # directory entry. Put its bytes back and fail instead of losing them.
            os.replace(backup, path)
            backup = None
            raise ValueError('formula changed during update')
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
        if backup and os.path.exists(backup):
            os.unlink(backup)
        if lock_fd is not None:
            os.close(lock_fd)
    return updated.decode('utf-8')


FORMULA_PATH = pathlib.Path(__file__).resolve().parents[1] / 'Formula' / 'paperdrop.rb'


def main(argv=None):
    import argparse
    import difflib
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='write the reviewed version/URL/hash change locally')
    args = parser.parse_args(argv)
    release = select_release(fetch_releases(download_bytes))
    payload = verified_release(release, download_bytes)
    original = FORMULA_PATH.read_text(encoding='utf-8')
    updated = update_file(FORMULA_PATH, payload, apply=args.apply)
    print(('APPLIED' if args.apply else 'DRY RUN (use --apply to write)') +
          ': ' + release['tag_name'] + (' [pre-release]' if release['prerelease'] else ''))
    print('sdist SHA-256: ' + payload[2])
    if original == updated:
        print('Formula is already current; no files changed.')
    else:
        print(''.join(difflib.unified_diff(original.splitlines(True), updated.splitlines(True),
                                         fromfile='Formula/paperdrop.rb', tofile='Formula/paperdrop.rb')), end='')
    return 0


if __name__ == '__main__':
    import sys
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print('update refused: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
