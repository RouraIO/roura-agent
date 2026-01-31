# Homebrew formula for Roura Agent
# Install: brew install rouraio/tap/roura-agent
# Or: brew install --build-from-source ./homebrew/roura-agent.rb

class RouraAgent < Formula
  desc "Local-first AI coding assistant powered by Ollama, OpenAI, or Anthropic"
  homepage "https://roura.io"
  version "1.7.0"
  license "MIT"

  # Binary release for Apple Silicon
  if Hardware::CPU.arm?
    url "https://github.com/RouraIO/roura-agent/releases/download/v1.7.0/roura-agent_1.7.0_macos_arm64.tar.gz"
    # SHA256 will be updated by CI after tarball is created
    sha256 "7d23fe3312792498ee41af23dd71fe4c9d878759c9c07f0d3aeecf47566d1cb0"
  else
    # Intel Macs - build from source
    url "https://github.com/RouraIO/roura-agent/archive/refs/tags/v1.7.0.tar.gz"
    sha256 "PLACEHOLDER_SOURCE_SHA256"

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
