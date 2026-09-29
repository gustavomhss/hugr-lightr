# lightr.rb — Unix-first Homebrew formula template.
#
# Owner replaces placeholders only after R0-R3 approval and G-PUBLISH. Initial
# public matrix has macOS arm64 and Linux x86_64 only.

class Lightr < Formula
  desc "lightr daemonless container runtime"
  homepage "https://github.com/HumanGuardrail/hugr-lightr"
  version "__TODO_VERSION__"
  license "Apache-2.0"

  on_macos do
    if Hardware::CPU.arm?
      # Use -unsigned URL only when release receipt records unsigned status.
      url "__TODO_URL_DARWIN_ARM64__"
      sha256 "__TODO_SHA256_DARWIN_ARM64__"
    else
      odie "lightr initial public releases support macOS arm64 only"
    end
  end

  on_linux do
    if Hardware::CPU.intel?
      url "__TODO_URL_LINUX_X86_64__"
      sha256 "__TODO_SHA256_LINUX_X86_64__"
    else
      odie "lightr initial public releases support Linux x86_64 only"
    end
  end

  def install
    bin.install "lightr"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/lightr --version")
  end
end
