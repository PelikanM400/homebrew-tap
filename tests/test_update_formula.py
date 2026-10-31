"""Offline security/behaviour tests; fixtures never contain credentials."""
import hashlib
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/update_formula.py'
SPEC = importlib.util.spec_from_file_location('update_formula', SCRIPT)


def load_module():
    assert SPEC is not None and SPEC.loader is not None
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    return module



class ReleaseSelectionTests(unittest.TestCase):
    def test_selects_highest_semver_including_prerelease_flag_not_api_order(self):
        self.assertTrue(SCRIPT.exists(), 'updater is not implemented')
        module = load_module()
        releases = [
            {'tag_name': 'v0.3.0', 'draft': False, 'prerelease': True, 'assets': []},
            {'tag_name': 'v0.10.0', 'draft': False, 'prerelease': True, 'assets': []},
            {'tag_name': 'v99.0.0', 'draft': True, 'prerelease': False, 'assets': []},
            {'tag_name': 'v0.9.0', 'draft': False, 'prerelease': False, 'assets': []},
        ]
        self.assertEqual(module.select_release(releases)['tag_name'], 'v0.10.0')


class AssetValidationTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.source = b'real-test-archive-bytes-not-a-network-result'
        self.digest = hashlib.sha256(self.source).hexdigest()
        self.sums = (self.digest + '  paperdrop-0.3.1.tar.gz\n').encode()
        self.base = 'https://github.com/PelikanM400/paperdrop/releases/download/v0.3.1/'
        def asset(name, data):
            return {'name': name, 'browser_download_url': self.base + name,
                    'state': 'uploaded', 'content_type': 'application/octet-stream',
                    'size': len(data), 'digest': 'sha256:' + hashlib.sha256(data).hexdigest()}
        self.release = {'tag_name': 'v0.3.1', 'draft': False, 'prerelease': True,
                        'assets': [asset('paperdrop-0.3.1.tar.gz', self.source),
                                   asset('SHA256SUMS', self.sums)]}
        self.downloads = {self.base + 'paperdrop-0.3.1.tar.gz': self.source,
                          self.base + 'SHA256SUMS': self.sums}

    def test_verified_payload_uses_downloaded_archive_and_published_sums(self):
        self.assertTrue(hasattr(self.module, 'verified_release'), 'asset validation not implemented')
        self.assertEqual(self.module.verified_release(self.release, self.downloads.__getitem__),
                         ('0.3.1', self.base + 'paperdrop-0.3.1.tar.gz', self.digest))

    def test_portable_checksums_take_precedence_when_both_sum_assets_exist(self):
        import copy
        release = copy.deepcopy(self.release)
        downloads = dict(self.downloads)
        legacy = b'0' * 64 + b'  /builder/work/paperdrop-0.3.1.tar.gz\n'
        release['assets'][1].update(size=len(legacy), digest='sha256:' + hashlib.sha256(legacy).hexdigest())
        downloads[self.base + 'SHA256SUMS'] = legacy
        portable = self.sums
        release['assets'].append({
            'name': 'SHA256SUMS.portable',
            'browser_download_url': self.base + 'SHA256SUMS.portable',
            'state': 'uploaded', 'content_type': 'text/plain', 'size': len(portable),
            'digest': 'sha256:' + hashlib.sha256(portable).hexdigest(),
        })
        downloads[self.base + 'SHA256SUMS.portable'] = portable
        self.assertEqual(self.module.verified_release(release, downloads.__getitem__),
                         ('0.3.1', self.base + 'paperdrop-0.3.1.tar.gz', self.digest))

    def test_untrusted_asset_fields_fail_closed(self):
        import copy
        for field, value in [('browser_download_url', 'https://evil.test/source.tar.gz'),
                             ('browser_download_url', self.base + 'paperdrop-0.3.1.tar.gz?x=1'),
                             ('content_type', []), ('digest', 'sha256:' + 'X' * 64),
                             ('size', True), ('size', -1), ('state', 'new'), ('name', '../x')]:
            with self.subTest(field=field, value=value):
                release = copy.deepcopy(self.release)
                release['assets'][0][field] = value
                with self.assertRaises(ValueError):
                    self.module.verified_release(release, self.downloads.__getitem__)

    def test_checksum_mismatch_duplicate_and_bad_filename_are_refused(self):
        for sums in [b'0' * 64 + b'  paperdrop-0.3.1.tar.gz\n',
                     self.sums * 2, self.sums + b'0' * 64 + b'  ../escape\n']:
            with self.subTest(sums=sums):
                self.release['assets'][1]['size'] = len(sums)
                self.release['assets'][1]['digest'] = 'sha256:' + hashlib.sha256(sums).hexdigest()
                self.downloads[self.base + 'SHA256SUMS'] = sums
                with self.assertRaises(ValueError):
                    self.module.verified_release(self.release, self.downloads.__getitem__)


class FormulaRewriteTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.old_url = 'https://github.com/PelikanM400/paperdrop/releases/download/v0.3.0/paperdrop-0.3.0.tar.gz'
        self.new_url = self.old_url.replace('0.3.0', '0.3.1')
        self.source = ('class Paperdrop < Formula\n  url "' + self.old_url + '"\n'
                       '  version "0.3.0"\n  sha256 "' + 'a' * 64 + '"\n'
                       '  resource "pillow" do\n    url "keep"\n    sha256 "unchanged"\n  end\nend\n')

    def test_rewrites_only_main_url_version_hash(self):
        self.assertTrue(hasattr(self.module, 'rewrite_formula'), 'formula rewrite not implemented')
        updated = self.module.rewrite_formula(self.source, ('0.3.1', self.new_url, 'b' * 64))
        self.assertEqual(updated, self.source.replace(self.old_url, self.new_url)
                         .replace('version "0.3.0"', 'version "0.3.1"').replace('a' * 64, 'b' * 64))

    def test_url_inferred_version_needs_no_redundant_version_stanza(self):
        source = self.source.replace('  version "0.3.0"\n', '')
        updated = self.module.rewrite_formula(source, ('0.3.1', self.new_url, 'b' * 64))
        self.assertEqual(updated, source.replace(self.old_url, self.new_url).replace('a' * 64, 'b' * 64))
        self.assertNotIn('  version ', updated)

    def test_refuses_downgrades_same_tag_mutations_and_unexpected_formula(self):
        for source, payload in [
            (self.source, ('0.2.0', self.old_url.replace('0.3.0', '0.2.0'), 'b' * 64)),
            (self.source, ('0.3.0', self.old_url, 'b' * 64)),
            (self.source.replace('class Paperdrop', 'class Other'), ('0.3.1', self.new_url, 'b' * 64)),
            (self.source + '  sha256 "' + 'a' * 64 + '"\n', ('0.3.1', self.new_url, 'b' * 64)),
            (self.source, ('0.3.1', 'https://evil.test', 'b' * 64)),
            (self.source, ('0.3.1', self.new_url, 'B' * 64)),
        ]:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    self.module.rewrite_formula(source, payload)

    def test_dry_run_is_nonwriting_apply_is_explicit_and_symlink_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / 'paperdrop.rb'
            target.write_text(self.source)
            self.module.update_file(target, ('0.3.1', self.new_url, 'b' * 64), apply=False)
            self.assertEqual(target.read_text(), self.source)
            self.module.update_file(target, ('0.3.1', self.new_url, 'b' * 64), apply=True)
            self.assertIn('version "0.3.1"', target.read_text())
            before = target.read_bytes()
            link = pathlib.Path(directory) / 'link.rb'
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                self.module.update_file(link, ('0.3.1', self.new_url, 'b' * 64), apply=True)
            self.assertEqual(target.read_bytes(), before)


class SemVerBoundaryTests(unittest.TestCase):
    def test_semver_precedence_and_invalid_inputs(self):
        module = load_module()
        ordered = ['v1.0.0-alpha', 'v1.0.0-alpha.1', 'v1.0.0-alpha.beta',
                   'v1.0.0-beta', 'v1.0.0-beta.2', 'v1.0.0-beta.11', 'v1.0.0-rc.1', 'v1.0.0']
        self.assertEqual(sorted(reversed(ordered), key=module.version_key), ordered)
        for tag in [None, 3, '1.0.0', 'v01.0.0', 'v1.0.0-01', 'v1.0.0\n', 'v１.0.0', 'v1.0.0/evil']:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                module.version_key(tag)
        for flags in [(False, 'true'), (None, True), (0, True)]:
            with self.assertRaises(ValueError):
                module.select_release([{'tag_name': 'v1.0.0', 'draft': flags[0], 'prerelease': flags[1]}])


class NetworkBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_pagination_includes_all_pages_with_fixed_anonymous_urls(self):
        self.assertTrue(hasattr(self.module, 'fetch_releases'), 'feed retrieval not implemented')
        import json
        calls = []
        def fetch(url):
            calls.append(url)
            page = int(url.rsplit('=', 1)[1])
            return json.dumps([{'page': page}] * (100 if page == 1 else 2)).encode()
        releases = self.module.fetch_releases(fetch)
        self.assertEqual(len(releases), 102)
        self.assertEqual(calls, [
            'https://api.github.com/repos/PelikanM400/paperdrop/releases?per_page=100&page=1',
            'https://api.github.com/repos/PelikanM400/paperdrop/releases?per_page=100&page=2'])

    def test_arbitrary_hosts_credentials_ports_and_redirects_are_refused(self):
        for url in ['http://api.github.com/repos/PelikanM400/paperdrop/releases',
                    'https://api.github.com@evil.test/x', 'https://user:pass@github.com/x',
                    'https://github.com:443/PelikanM400/paperdrop/releases/download/v0.3.1/SHA256SUMS',
                    'https://github.com/other/repo/releases/download/v0.3.1/SHA256SUMS',
                    'https://api.github.com/repos/other/repo/releases?per_page=100&page=1',
                    'https://github.com/PelikanM400/paperdrop/releases/download/v0.3.1/SHA256SUMS#fragment']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.module.validate_network_url(url)
        self.module.validate_network_url(self.module.DOWNLOAD_BASE + 'v0.3.1/SHA256SUMS')
        self.module.validate_network_url(self.module.DOWNLOAD_BASE + 'v0.3.2/SHA256SUMS.portable')
        self.module.validate_network_url('https://release-assets.githubusercontent.com/github-production-release-asset/x?sig=y', redirect=True)
        with self.assertRaises(ValueError):
            self.module.validate_network_url('https://evil.test/x', redirect=True)

    def test_download_uses_anonymous_get_bounded_reads_and_no_proxy(self):
        from email.message import Message
        from unittest.mock import patch
        url = self.module.API_BASE + '1'
        class Response:
            headers = Message()
            headers['Content-Type'] = 'application/json'
            read_size = None
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return url
            def read(self, size):
                self.read_size = size
                return b'[]'
        class Opener:
            request = None
            timeout = None
            def open(self, request, timeout):
                self.request, self.timeout = request, timeout
                return response
        response, opener = Response(), Opener()
        with patch.object(self.module.urllib.request, 'build_opener', return_value=opener) as build:
            self.assertEqual(self.module.download_bytes(url), b'[]')
        self.assertEqual(build.call_args.args[0].proxies, {})
        assert opener.request is not None
        self.assertEqual(opener.request.get_method(), 'GET')
        self.assertNotIn('Authorization', opener.request.headers)
        self.assertNotIn('Cookie', opener.request.headers)
        self.assertEqual(opener.timeout, 30)
        self.assertEqual(response.read_size, 4 * 1024 * 1024 + 1)

    def test_portable_checksum_download_uses_the_small_response_bound(self):
        from email.message import Message
        from unittest.mock import patch
        url = self.module.DOWNLOAD_BASE + 'v0.3.2/SHA256SUMS.portable'
        class Response:
            headers = Message()
            headers['Content-Type'] = 'text/plain'
            read_size = None
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return url
            def read(self, size):
                self.read_size = size
                return b'checksum data'
        class Opener:
            def open(self, request, timeout):
                return response
        response = Response()
        with patch.object(self.module.urllib.request, 'build_opener', return_value=Opener()):
            self.assertEqual(self.module.download_bytes(url), b'checksum data')
        self.assertEqual(response.read_size, 65536 + 1)

    def test_more_than_pagination_cap_is_an_error_not_silent_partial_success(self):
        import json
        calls = []
        def fetch(url):
            calls.append(url)
            return json.dumps([{}] * 100).encode()
        with self.assertRaisesRegex(ValueError, 'pagination limit'):
            self.module.fetch_releases(fetch)
        self.assertEqual(len(calls), 100)

    def test_json_duplicates_and_wrong_top_level_fail_closed(self):
        for data in [b'{}', b'[{"draft":false,"draft":true}]', b'null']:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.module.fetch_releases(lambda _url: data)


class CliTests(unittest.TestCase):
    def test_default_preview_and_explicit_apply_on_real_files(self):
        import contextlib
        import io
        import json
        import tempfile
        from unittest.mock import patch
        assets = AssetValidationTests()
        assets.setUp()
        formula = FormulaRewriteTests()
        formula.setUp()
        module = assets.module
        self.assertTrue(hasattr(module, 'main'), 'CLI not implemented')
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / 'paperdrop.rb'
            target.write_text(formula.source)
            downloads = dict(assets.downloads)
            downloads[module.API_BASE + '1'] = json.dumps([assets.release]).encode()
            with patch.object(module, 'FORMULA_PATH', target), patch.object(module, 'download_bytes', downloads.__getitem__):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(module.main([]), 0)
                self.assertEqual(target.read_text(), formula.source)
                self.assertIn('DRY RUN', output.getvalue())
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(module.main(['--apply']), 0)
                self.assertIn(assets.digest, target.read_text())
                before = target.read_bytes()
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(module.main(['--apply']), 0)
                self.assertEqual(target.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
