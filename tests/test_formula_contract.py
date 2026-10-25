"""Static portability guard; brew install/test remains the runtime gate."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class FormulaPortabilityTests(unittest.TestCase):
    def test_pillow_build_installs_its_declared_build_system_requirements(self):
        source = (ROOT / 'Formula/paperdrop.rb').read_text()
        self.assertIn('resource "setuptools" do', source)
        self.assertIn('resource "pybind11" do', source)
        self.assertIn('venv.pip_install [resource("setuptools"), resource("pybind11")]', source)
        self.assertIn('std_pip_args(prefix: false, build_isolation: false)', source)
        self.assertIn('pip_install_and_link buildpath, build_isolation: false', source)
        self.assertNotIn('pip_install_and_link buildpath\n', source,
                         'the application build must also use the declared resources offline')

    def test_smoke_exercises_the_real_brew_ownership_and_scheduler_resolver(self):
        source = (ROOT / 'Formula/paperdrop.rb').read_text()
        self.assertIn('from paperdrop.distribution import homebrew_opt_prefix', source)
        self.assertIn('homebrew_opt_prefix() == pathlib.Path(_homebrew.OPT_PREFIX)', source)
        self.assertIn('runtime_command()', source)
        self.assertIn("'brew upgrade pelikanm400/tap/paperdrop' in", source)

    def test_macos_native_build_does_not_require_full_xcode_app(self):
        source = (ROOT / 'Formula/paperdrop.rb').read_text()
        self.assertNotIn('depends_on xcode:', source,
                         'XcodeRequirement rejects Command Line Tools-only Macs')
        self.assertIn('return unless OS.mac?', source)
        self.assertIn('system "xcrun", "swiftc"', source)
        self.assertIn('macos/Sources/paperdrop-set/main.swift', source)


if __name__ == '__main__':
    unittest.main()
