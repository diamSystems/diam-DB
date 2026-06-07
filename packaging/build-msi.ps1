# PowerShell script to build Windows MSI installer
# Requires WiX Toolset (https://wixtoolset.org/)

$VERSION = "1.0.1"
$PACKAGE_NAME = "diam-db"

# Build for Windows
Write-Host "Building for Windows..."
cargo build --release --target x86_64-pc-windows-msvc

# Create WiX source file
$wixContent = @"
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*" 
           Name="$PACKAGE_NAME" 
           Language="1033" 
           Version="$VERSION" 
           Manufacturer="diamSystems" 
           UpgradeCode="PUT-A-REAL-GUID-HERE">
    <Package InstallerVersion="200" Compressed="yes" InstallScope="perMachine" />
    
    <MajorUpgrade DowngradeErrorMessage="Downgrade not allowed." />
    
    <MediaTemplate EmbedCab="yes" />
    
    <Feature Id="ProductFeature" Title="$PACKAGE_NAME" Level="1">
      <ComponentGroupRef Id="ProductComponents" />
    </Feature>
  </Product>
  
  <Fragment>
    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="ProgramFilesFolder">
        <Directory Id="INSTALLFOLDER" Name="$PACKAGE_NAME" />
      </Directory>
    </Directory>
  </Fragment>
  
  <Fragment>
    <ComponentGroup Id="ProductComponents" Directory="INSTALLFOLDER">
      <Component Id="MainExecutable">
        <File Id="ExeFile" Source="target\x86_64-pc-windows-msvc\release\diam-db.exe" />
      </Component>
    </ComponentGroup>
  </Fragment>
</Wix>
"@

$wixContent | Out-File -FilePath "packaging\diam-db.wxs" -Encoding UTF8

# Build MSI using candle and light (WiX tools)
# candle packaging\diam-db.wxs
# light diam-db.wixobj -out diam-db-$VERSION.msi

Write-Host "WiX source file created: packaging\diam-db.wxs"
Write-Host "To build MSI, run:"
Write-Host "  candle packaging\diam-db.wxs"
Write-Host "  light diam-db.wixobj -out diam-db-$VERSION.msi"
