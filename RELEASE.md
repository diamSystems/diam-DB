# Release Guide for diamDB

This guide covers the complete process for creating and publishing a release of diamDB.

## Pre-Release Checklist

- [ ] All tests pass locally
- [ ] Version number updated in `Cargo.toml`
- [ ] Changelog updated with release notes
- [ ] License file is present (BUSL-1.1)
- [ ] All placeholder URLs are correct (diamSystems/diam-DB)
- [ ] README.md is up to date
- [ ] No uncommitted changes in working directory

## Release Process

### 1. Update Version Number

Edit `Cargo.toml` and update the version:

```toml
[package]
name = "diam-db"
version = "1.0.0"  # Update this
```

Also update the version in:
- `homebrew/diam-db.rb` (url and sha256 - sha256 will be generated after release)
- `packaging/debian/control`
- `packaging/diam-db.spec`
- `packaging/build-msi.ps1`

### 2. Update Changelog

Add release notes to `CHANGELOG.md` (create if doesn't exist):

```markdown
# Changelog

## [1.0.0] - 2024-06-07

### Added
- CLI provisioning tool
- Cross-platform builds (macOS, Linux, Windows)
- Homebrew formula
- DEB and RPM packaging

### Changed
- Updated license to BUSL-1.1

### Fixed
- Fixed tenant creation via CLI
```

### 3. Commit Changes

```bash
git add Cargo.toml CHANGELOG.md homebrew/diam-db.rb packaging/
git commit -m "Release v1.0.0"
```

### 4. Create Git Tag

```bash
git tag -a v1.0.0 -m "Release v1.0.0"
```

### 5. Push to GitHub

```bash
git push origin main
git push origin v1.0.0
```

This will automatically trigger the GitHub Actions workflow to build binaries for all platforms.

### 6. Monitor GitHub Actions

Go to: https://github.com/diamSystems/diam-DB/actions

Wait for the "Release" workflow to complete. It will:
- Build for macOS (ARM64 and x86_64)
- Build for Linux (x86_64)
- Build for Windows (x86_64)
- Create a GitHub release with all binaries attached

### 7. Verify the Release

1. Go to: https://github.com/diamSystems/diam-DB/releases
2. Check that the release has all binaries:
   - `diam-db-macos-arm64`
   - `diam-db-macos-x86_64`
   - `diam-db-linux-x86_64`
   - `diam-db-windows-x86_64.exe`

3. Download and test one binary:
   ```bash
   # Test macOS binary
   curl -L -o diam-db https://github.com/diamSystems/diam-DB/releases/download/v1.0.0/diam-db-macos-arm64
   chmod +x diam-db
   ./diam-db --help
   ./diam-db server --help
   ./diam-db create-tenant test
   ```

## Post-Release Tasks

### Update Homebrew Formula

After the release is created, update the Homebrew formula:

1. Get the SHA256 of the release tarball:
   ```bash
   curl -L https://github.com/diamSystems/diam-DB/archive/refs/tags/v1.0.0.tar.gz | shasum -a 256
   ```

2. Update `homebrew/diam-db.rb`:
   ```ruby
   url "https://github.com/diamSystems/diam-DB/archive/refs/tags/v1.0.0.tar.gz"
   sha256 "ACTUAL_SHA256_HERE"
   ```

3. Commit and push the update:
   ```bash
   git add homebrew/diam-db.rb
   git commit -m "Update Homebrew formula for v1.0.0"
   git push origin main
   ```

### Build Packages (Optional)

If you want to distribute DEB/RPM/MSI packages:

#### Build DEB Package (Linux)

```bash
# Install dpkg tools
sudo apt-get install dpkg-dev

# Build the package
./packaging/build-deb.sh
```

#### Build RPM Package (Linux)

```bash
# Install rpmbuild
sudo dnf install rpm-build

# Build the package
rpmbuild -bb packaging/diam-db.spec
```

#### Build MSI Package (Windows)

```bash
# Install WiX Toolset from https://wixtoolset.org/

# Build the package
./packaging/build-msi.ps1
```

### Announce the Release

1. Update the GitHub release description with release notes
2. Post on social media/communities
3. Update documentation if needed

## Local Build Testing

Before releasing, you can test the build locally:

### Build All Platforms

```bash
# Add cross-compilation targets
rustup target add aarch64-apple-darwin x86_64-apple-darwin x86_64-unknown-linux-gnu x86_64-pc-windows-msvc

# Run the build script
./build.sh
```

### Test CLI Locally

```bash
# Build for current platform
cargo build --release

# Test server
./target/release/diam-db server

# In another terminal, test tenant creation
./target/release/diam-db create-tenant test_tenant

# Test API
curl -X POST http://127.0.0.1:8080/api/v1/database/create -H "Content-Type: application/json" -d '{"tenant_id": "api_test"}'
curl http://127.0.0.1:8080/api/v1/api_test/collection/users
```

## Troubleshooting

### GitHub Actions Fails

Check the workflow logs at: https://github.com/diamSystems/diam-DB/actions

Common issues:
- Rust toolchain version mismatch
- Build dependencies missing
- Network issues downloading crates

### Binaries Not Attached to Release

Make sure:
- The tag is pushed with `git push origin v1.0.0`
- The workflow has permission to create releases (check repo settings)
- The tag format matches `v*` (e.g., v1.0.0, v1.1.0)

### Homebrew Formula Issues

- Ensure SHA256 matches the tarball exactly
- Check that the URL is accessible
- Test with `brew install --debug ./homebrew/diam-db.rb`

## Version Numbering

Follow semantic versioning (SemVer):

- **MAJOR** (X.0.0): Incompatible API changes
- **MINOR** (0.X.0): Backwards-compatible functionality additions
- **PATCH** (0.0.X): Backwards-compatible bug fixes

Example:
- `1.0.0` → `1.0.1` (bug fix)
- `1.0.1` → `1.1.0` (new feature)
- `1.1.0` → `2.0.0` (major release)

## Rollback Procedure

If a release has critical issues:

1. Delete the release from GitHub (keeps the tag)
2. Fix the issue in a new commit
3. Create a new tag (e.g., v0.2.1)
4. Push the new tag
5. Update the release notes to mention the fix

## Security Considerations

- Never commit API keys or secrets
- Review the release artifacts before publishing
- Check that the LICENSE file is included in the release
- Verify that no sensitive data is in the binaries
