# lightr.rb — Unix-first Homebrew formula.
#
# Owner delivery approval: #187/comment5945719224; draft 400899741 awaits promotion.
# Initial public matrix has macOS arm64 and Linux x86_64 only.

class Lightr < Formula
  desc "lightr daemonless container runtime"
  homepage "https://github.com/gmhelmold/hugr-lightr"
  version "0.1.1"
  license "Apache-2.0"

  on_macos do
    if Hardware::CPU.arm?
      # Unsigned/ad-hoc; no Developer ID; not notarized. VZ NOT EXECUTED.
      # Owner 0.1.1 waiver: R0-0.1.1-owner-waivers.md; #113 remains open.
      url "https://github.com/gmhelmold/hugr-lightr/releases/download/v0.1.1/lightr-0.1.1-darwin-arm64-unsigned.tar.gz"
      sha256 "73af74ca490a9c600cf12271162005ef837d9b89f3dc83cc7c7368edbd7aca0d"
    else
      odie "lightr initial public releases support macOS arm64 only"
    end
  end

  on_linux do
    if Hardware::CPU.intel?
      url "https://github.com/gmhelmold/hugr-lightr/releases/download/v0.1.1/lightr-0.1.1-linux-x86_64.tar.gz"
      sha256 "b8e83623b413a36b847cb4417fb623b9ab37500d5cab71bc9299fa2c2f38a6ca"
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
