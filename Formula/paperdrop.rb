class Paperdrop < Formula
  include Language::Python::Virtualenv

  desc "Daily wallpaper client for macOS and Linux Xfce"
  homepage "https://github.com/PelikanM400/paperdrop"
  url "https://github.com/PelikanM400/paperdrop/releases/download/v0.3.3/paperdrop-0.3.3.tar.gz"
  sha256 "274e273493be6f333db25ba15b47fa45ccad9936ffd714107b052fd47ed349c3"
  license "MIT"

  depends_on "jpeg-turbo"
  depends_on "python@3.14"
  depends_on "webp"
  depends_on "zlib"

  resource "pillow" do
    url "https://files.pythonhosted.org/packages/ce/a4/9cc30690a394a8305e8be4c9036aa16d0dfddadd09079860b582f562496d/pillow-13.0.0.tar.gz"
    sha256 "cdcd1ba258178f7356d74170c9a81ba4eab6a5d55748bc402a5a2a6fe6be3510"
  end

  # Pillow 13's PEP 517 backend needs both of these; declare them as resources
  # so a sandboxed/offline build never resolves packages from the package index.
  resource "setuptools" do
    url "https://files.pythonhosted.org/packages/ef/55/6dc6d6bb953bdfc52519a0059592c52b6e3b8ad51cf8256dffceb55b0610/setuptools-84.2.1-py3-none-any.whl"
    sha256 "ca140b45d5325a9478f880e351484f62fef15f336462e449ca0c03c873d589c2"
  end

  resource "pybind11" do
    url "https://files.pythonhosted.org/packages/33/fd/8762f7ee3e4e4be6d1d846cffb4916dd9bb02b2f800d3603718a0efe494c/pybind11-3.1.0-py3-none-any.whl"
    sha256 "b8488090f8acffbcb6b5d6a85571a6827a0a2981ffb75e5a0b27b87c4a6b7dd0"
  end

  def install
    python = formula_opt_bin("python@3.14")/"python3.14"
    ENV["JPEG_ROOT"] = formula_opt_prefix("jpeg-turbo").to_s
    ENV["ZLIB_ROOT"] = formula_opt_prefix("zlib").to_s
    ENV["WEBP_ROOT"] = formula_opt_prefix("webp").to_s
    venv = virtualenv_create(libexec, python, system_site_packages: false)
    venv.pip_install [resource("setuptools"), resource("pybind11")]
    # Bundle the Python runtime dependency from source, but use brewed native codecs.
    # Disable unused codecs explicitly to avoid undeclared host-library detection.
    resource("pillow").stage do
      settings = %w[jpeg=enable zlib=enable webp=enable avif=disable freetype=disable
                    imagequant=disable jpeg2000=disable lcms=disable raqm=disable
                    tiff=disable xcb=disable platform-guessing=disable]
      system python, "-m", "pip", "--python=#{libexec}/bin/python", "install",
             *std_pip_args(prefix: false, build_isolation: false),
             *settings.flat_map { |setting| ["-C", setting] }, "."
    end
    venv.pip_install_and_link buildpath, build_isolation: false
    system libexec/"bin/python", "-I", "-c", <<~PYTHON, opt_prefix.to_s
      import pathlib, sys, paperdrop
      marker = pathlib.Path(paperdrop.__file__).with_name('_homebrew.py')
      marker.write_text('OPT_PREFIX = ' + repr(sys.argv[1]) + '\\n', encoding='utf-8')
    PYTHON

    return unless OS.mac?

    system "xcrun", "swiftc", "-O", "-framework", "AppKit", "-framework", "Foundation",
           "-o", "paperdrop-set", "macos/Sources/paperdrop-set/main.swift"
    bin.install "paperdrop-set"
  end

  def caveats
    <<~EOS
      No UI, wallpaper change, schedule or user configuration is created by Homebrew.
      In your desktop session, run this separately to configure PaperDrop:
        paperdrop install
      Linux wallpaper support is Xfce only (xfconf-query and a user systemd session).
      Upgrade this installation with brew upgrade pelikanm400/tap/paperdrop, not pip/pipx.
      After migration to this tap, schedules use the stable opt path; ordinary brew
      upgrades do not require reinstalling schedules and do not resume a paused job.
      This is pre-release software; CI is not real-desktop acceptance testing.
    EOS
  end

  test do
    assert_match "paperdrop #{version}", shell_output("#{bin}/paperdrop --version")
    (testpath/"smoke.py").write <<~PYTHON
      import io, json, os, pathlib, re, select, subprocess, sys, time, urllib.request
      import paperdrop
      from paperdrop import _homebrew
      from paperdrop.distribution import homebrew_opt_prefix
      from paperdrop.platforms.base import runtime_command
      from PIL import Image, features

      assert paperdrop.__version__ == #{version.to_s.inspect}
      assert _homebrew.OPT_PREFIX == #{opt_prefix.to_s.inspect}
      assert homebrew_opt_prefix() == pathlib.Path(_homebrew.OPT_PREFIX)
      scheduled, scheduled_env = runtime_command()
      assert scheduled == [str(pathlib.Path(_homebrew.OPT_PREFIX) / 'libexec/bin/python'),
                           '-I', '-m', 'paperdrop']
      assert 'PYTHONPATH' not in scheduled_env
      assert 'Cellar' not in repr((scheduled, scheduled_env))
      for feature in ('jpg', 'zlib', 'webp'):
          assert features.check(feature), feature
      for format in ('JPEG', 'PNG', 'WEBP'):
          data = io.BytesIO()
          Image.new('RGB', (4, 4), 'red').save(data, format=format)
          data.seek(0)
          Image.open(data).verify()

      config = pathlib.Path.cwd() / 'not-created.json'
      argv = [sys.executable, '-I', '-m', 'paperdrop', '--config', str(config)]
      upgrade = subprocess.run(argv + ['upgrade', '--json'], capture_output=True, text=True, timeout=15)
      assert upgrade.returncode == 1, (upgrade.returncode, upgrade.stdout, upgrade.stderr)
      refusal = json.loads(upgrade.stdout)
      assert refusal['ok'] is False
      assert 'brew upgrade pelikanm400/tap/paperdrop' in refusal['error']
      assert not config.exists()
      status = subprocess.run(argv + ['status'], capture_output=True, text=True, timeout=15)
      assert status.returncode == 2, (status.returncode, status.stdout, status.stderr)
      assert not config.exists()
      env = dict(os.environ, PYTHONUNBUFFERED='1', CI='1')
      process = subprocess.Popen(argv[:1] + ['-u'] + argv[1:] +
                                 ['ui', '--no-open', '--port', '0'], env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
      try:
          output = b''
          deadline = time.monotonic() + 20
          match = None
          while time.monotonic() < deadline:
              ready, _, _ = select.select([process.stdout], [], [], 0.25)
              if ready:
                  chunk = os.read(process.stdout.fileno(), 8192)
                  assert chunk, ('UI exited early', process.poll())
                  output += chunk
                  match = re.search(rb'http://127[.]0[.]0[.]1:[0-9]+/\\?t=[A-Za-z0-9_-]+', output)
                  if match:
                      break
          assert match, 'UI did not publish a loopback URL'
          url = match[0].decode('ascii')
          opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
          with opener.open(url, timeout=5) as response:
              assert response.status == 200
              assert b'<html' in response.read().lower()
          with opener.open(url.replace('/?t=', '/api/status?t='), timeout=5) as response:
              payload = json.load(response)
          assert payload['onboarding'] is True
          assert payload['version'] == paperdrop.__version__
          assert not config.exists(), 'read-only onboarding wrote user configuration'
      finally:
          process.terminate()
          try:
              process.wait(timeout=5)
          except subprocess.TimeoutExpired:
              process.kill()
              process.wait(timeout=5)
      assert not config.exists()
      print('version/Pillow/marker/missing-config/status/UI: OK; no schedule installed')
    PYTHON
    system libexec/"bin/python", "-I", testpath/"smoke.py"
    assert_path_exists bin/"paperdrop-set" if OS.mac?
    refute_path_exists bin/"paperdrop-set" if OS.linux?
  end
end
