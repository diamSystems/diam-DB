Name:           diam-db
Version:        1.0.1
Release:        1%{?dist}
Summary:        High-performance memory-first NoSQL micro-database
License:        BSL
URL:            https://github.com/diamSystems/diam-DB
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  cargo rust

%description
diamDB is an ultra-lean, high-concurrency, memory-first NoSQL micro-database
designed explicitly to bypass traditional file locking issues. Built in Rust
using Tokio and Axum, making it incredibly fast with a sub-50MB RAM footprint.

%prep
%setup -q

%build
cargo build --release

%install
install -D -m 755 target/release/diam-db %{buildroot}%{_bindir}/diam-db

%files
%{_bindir}/diam-db

%changelog
* Sat Jun 7 2026 Zohaib Ismail <zohaib@diamsystems.co.uk> - 1.0.0-1
- Initial package
