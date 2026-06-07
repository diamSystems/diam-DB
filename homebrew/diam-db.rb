class DiamDb < Formula
  desc "High-performance memory-first NoSQL micro-database"
  homepage "https://github.com/diamSystems/diam-DB"
  url "https://github.com/diamSystems/diam-DB/archive/refs/tags/v1.0.1.tar.gz"
  sha256 "placeholder_sha256"
  license "BSL"

  depends_on "rust" => :build

  def install
    system "cargo", "install", *std_cargo_args
  end

  test do
    system "#{bin}/diam-db", "--help"
  end
end
