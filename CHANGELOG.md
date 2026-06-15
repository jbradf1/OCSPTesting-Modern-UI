# Changelog

All notable changes to this project are documented in this file.

## [v1.0.0] - 2026-06-15

### Documentation — Windows install instructions reworked

- **Corrected the false claim that Git and OpenSSL are on the Microsoft Store.**
  Neither is published there. Windows installs now use [Scoop](https://scoop.sh)
  for Git and OpenSSL, with Python from the Microsoft Store.
- **Simplified the Quick Setup Guide (Windows)** into a lean, single-terminal
  flow: install Scoop → `scoop install git openssl` → install Python from the
  Store → **download the project ZIP** (Code → Download ZIP) → extract → open the
  folder in a terminal → create venv, install dependencies, and run. Removed the
  Administrator-PowerShell + Chocolatey bootstrap and the `cd`/`mkdir`/`git clone`
  steps.
- **Removed all Chocolatey references** in favor of Scoop across the setup and
  troubleshooting sections.
- **Marked Git as optional** — the download-ZIP workflow no longer requires Git
  to run the tool (only needed for `git clone` or contributing).
- **Added the Microsoft Visual C++ Redistributable note** for the manual slproweb
  OpenSSL installer (resolves `VCRUNTIME140.dll is missing` errors).
- **Verified Windows prerequisites are complete** against the code: the only
  third-party Python dependencies are `cryptography`, `requests`, and
  `asn1crypto` (all pinned in `requirements.txt`); plus the OpenSSL CLI, Python
  3.10+, and `tkinter` (bundled with Python).
