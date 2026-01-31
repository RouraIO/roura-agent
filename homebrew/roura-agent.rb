# Homebrew formula for Roura Agent
# Install: brew install rouraio/tap/roura-agent
# Or: brew install --build-from-source ./homebrew/roura-agent.rb
#
# Note: Version and SHA256 are updated automatically by CI on release.
# Placeholders: RELEASE_VERSION, TARBALL_SHA256, SOURCE_SHA256

class RouraAgent < Formula
  desc "Local-first AI coding assistant powered by Ollama, OpenAI, or Anthropic"
  homepage "https://roura.io"
  version "RELEASE_VERSION"
  license "MIT"

  # Binary release for Apple Silicon
  if Hardware::CPU.arm?
    url "https://github.com/RouraIO/roura-agent/releases/download/vRELEASE_VERSION/roura-agent_RELEASE_VERSION_macos_arm64.tar.gz"
    sha256 "TARBALL_SHA256"
  else
    # Intel Macs - build from source
    url "https://github.com/RouraIO/roura-agent/archive/refs/tags/vRELEASE_VERSION.tar.gz"
    sha256 "SOURCE_SHA256"

    depends_on "python@3.11"

    def install
      venv = virtualenv_create(libexec, "python3.11")
      venv.pip_install_and_link buildpath
    end
  end

  def install
    if Hardware::CPU.arm?
      # Binary installation
      bin.install "roura-agent/roura-agent"

      # Install supporting files if present
      if File.directory?("roura-agent/Frameworks")
        (prefix/"Frameworks").install Dir["roura-agent/Frameworks/*"]
      end
    end
  end

  def caveats
    <<~EOS
      Roura Agent has been installed!

      To get started:
        roura-agent

      For first-time setup:
        roura-agent doctor

      Configuration is stored in:
        ~/.config/roura-agent/

      For Ollama (local LLM) support:
        brew install ollama
        ollama serve

      Documentation: https://docs.roura.io
    EOS
  end

  test do
    assert_match "Roura Agent", shell_output("#{bin}/roura-agent --version")
  end
end
