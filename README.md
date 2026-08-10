# WordPress XAMPP One-Click Installer

A lightweight Windows desktop app that installs a fresh WordPress site in XAMPP from a simple graphical interface.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white)](https://www.microsoft.com/windows/)
[![WordPress](https://img.shields.io/badge/WordPress-Local%20Installer-21759B?logo=wordpress&logoColor=white)](https://wordpress.org/)
[![Python syntax check](https://github.com/Abdullah-Wp/wordpress-xampp-one-click-installer/actions/workflows/python-check.yml/badge.svg)](https://github.com/Abdullah-Wp/wordpress-xampp-one-click-installer/actions/workflows/python-check.yml)

Created by [AbdullahWp.com](https://abdullahwp.com/) — WordPress, Elementor, WooCommerce, and custom website development.

## Features

- Detects common XAMPP installation locations automatically.
- Accepts a custom XAMPP folder when it is installed elsewhere.
- Detects the configured MySQL/MariaDB port and checks common fallback ports.
- Downloads the latest WordPress package from the official WordPress website.
- Creates the local database and generates `wp-config.php` with secure random salts.
- Runs the WordPress installation automatically with the site and administrator details you provide.
- Refuses to overwrite a non-empty site folder.
- Uses safe ZIP extraction checks to prevent files from escaping the target directory.
- Provides a native dark-mode GUI with progress and error logs.
- Installs a clean WordPress site without adding third-party plugins or themes.

## Requirements

- Windows 10 or 11
- [XAMPP](https://www.apachefriends.org/) with Apache, PHP, and MySQL/MariaDB
- Internet access while WordPress is downloaded
- Python 3.10 or newer when running or building from source

Python is not required after you build a standalone executable.

## Run from source

1. Install XAMPP and Python 3.10 or newer.
2. Clone this repository:

   ```powershell
   git clone https://github.com/Abdullah-Wp/wordpress-xampp-one-click-installer.git
   cd wordpress-xampp-one-click-installer
   ```

3. Start Apache and MySQL from the XAMPP Control Panel.
4. Launch the installer:

   ```powershell
   py app.py
   ```

5. Enter the site title, local folder name, WordPress administrator details, and MySQL settings, then select **Install WordPress**.

The new site will be available at `http://localhost/<folder-name>/`.

## Build the Windows executable

Run:

```powershell
build.bat
```

The script installs or updates PyInstaller and creates:

```text
dist\WordPress-XAMPP-Installer.exe
```

The `build/` and `dist/` directories are generated locally and are intentionally excluded from source control.

## Installer fields

| Field | Purpose |
| --- | --- |
| XAMPP Folder | Path to the XAMPP installation, such as `C:\xampp` |
| Site Title | Display name for the new WordPress website |
| Folder (Slug) | Folder created inside XAMPP's `htdocs` directory |
| Admin Username | WordPress administrator login name |
| Admin Password | WordPress administrator password |
| Admin Email | Email assigned to the WordPress administrator |
| MySQL Root Pass | Existing XAMPP MySQL root password; leave empty only when XAMPP uses its default empty password |
| MySQL Port | MySQL/MariaDB port, commonly `3306` |

## What the installer changes

For the folder name `my_wordpress_site`, the installer:

1. Connects to the local XAMPP MySQL/MariaDB service.
2. Creates a database named `my_wordpress_site` if it does not already exist.
3. Creates `xampp\htdocs\my_wordpress_site`.
4. Downloads and extracts the latest official WordPress package.
5. Generates the WordPress configuration file.
6. Runs the WordPress installation through XAMPP's PHP executable.

## Important safety notes

- This utility is intended for local development environments, not production servers.
- It uses XAMPP's MySQL `root` account to create the database.
- Back up any important XAMPP databases and site files before using automation tools.
- Do not expose an unsecured XAMPP installation directly to the public internet.
- Site credentials stay on the local computer; the app only downloads WordPress from `wordpress.org`.

## Troubleshooting

### MySQL server is not running

Open the XAMPP Control Panel, start MySQL, wait a few seconds, and try again.

### MySQL access denied

Enter the current MySQL root password. A default XAMPP installation often uses an empty password, but your setup may be different.

### Site folder already exists

Choose a different folder name or manually inspect and move the existing folder. The installer will not overwrite a non-empty directory.

### The website does not open after installation

Confirm Apache is running in XAMPP and that its configured HTTP port is available.

## Project structure

```text
.
├── app.py                           # Installer application
├── build.bat                        # Windows build command
├── WordPress-XAMPP-Installer.spec   # PyInstaller configuration
├── .github/workflows/               # Automated syntax validation
├── .gitignore                       # Generated and local-only files
└── README.md                        # Project documentation
```

## Contributing

Bug reports and focused pull requests are welcome. Please avoid committing generated `build/` or `dist/` files.

## Author

[AbdullahWp.com](https://abdullahwp.com/) provides professional WordPress development, redesign, migration, Elementor, WooCommerce, performance optimization, maintenance, and custom functionality.
