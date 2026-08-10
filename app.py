import io
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

WP_ZIP_URL = "https://wordpress.org/latest.zip"

def find_xampp():
    candidates = [
        Path(r"C:\xampp"),
        Path(r"D:\xampp"),
        Path(r"E:\xampp"),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "xampp",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "xampp",
    ]
    for p in candidates:
        if (p / "htdocs").is_dir() and (p / "mysql").is_dir():
            return p
    return None

def detect_mysql_port(xampp):
    """Auto-detect MySQL port from XAMPP's my.ini configuration."""
    if not xampp:
        return 3306
    my_ini = xampp / "mysql" / "bin" / "my.ini"
    if my_ini.exists():
        try:
            content = my_ini.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("port") and "=" in line:
                    parts = line.split("=")
                    if len(parts) == 2 and parts[1].strip().isdigit():
                        return int(parts[1].strip())
        except Exception:
            pass
    return 3306

def check_mysql_socket(host, port, timeout=1.5):
    """Check if a TCP socket connection can be established."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

def find_active_mysql_port(preferred_port=3306):
    """Find an active MySQL port by checking common ports."""
    ports_to_check = []
    if preferred_port:
        ports_to_check.append(int(preferred_port))
    for p in (3306, 3307, 3308, 3309):
        if p not in ports_to_check:
            ports_to_check.append(p)

    for port in ports_to_check:
        if check_mysql_socket("127.0.0.1", port) or check_mysql_socket("localhost", port):
            return port
    return None

def mysql_exe(xampp):
    for name in ("mysql.exe", "mariadb.exe"):
        p = xampp / "mysql" / "bin" / name
        if p.exists():
            return p
    raise FileNotFoundError("MySQL/MariaDB executable not found in XAMPP directory.")

def get_subprocess_flags():
    """Hide command window popups on Windows."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}

def wait_for_mysql(xampp, port=3306, db_pass="", max_attempts=8, delay=1.5):
    """Wait for MySQL to finish initializing and responding to queries."""
    exe = mysql_exe(xampp)
    hosts_to_try = ["127.0.0.1", "localhost"]
    
    for attempt in range(1, max_attempts + 1):
        for host in hosts_to_try:
            cmd = [
                str(exe),
                "--connect-timeout=3",
                "-u", "root",
                "-h", host,
                "-P", str(port)
            ]
            if db_pass:
                cmd.append(f"-p{db_pass}")
            cmd.extend(["-e", "SELECT 1;"])

            p = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=5,
                **get_subprocess_flags()
            )

            if p.returncode == 0:
                return host  # Successfully connected and MySQL is ready

        time.sleep(delay)

    return None

def run_mysql(xampp, sql, db_pass="", port=3306, host="127.0.0.1"):
    exe = mysql_exe(xampp)
    cmd = [
        str(exe),
        "--connect-timeout=5",
        "-u", "root",
        "-h", host,
        "-P", str(port)
    ]
    if db_pass:
        cmd.append(f"-p{db_pass}")
    cmd.extend(["-e", sql])

    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=15,
        **get_subprocess_flags()
    )
    if p.returncode != 0:
        err = (p.stderr or p.stdout or "").strip()
        if "Access denied" in err:
            raise RuntimeError("MySQL access denied. Check your MySQL root password.")
        raise RuntimeError(f"MySQL error: {err}")

def sanitize_db_name(value):
    value = re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_") or "wordpress"
    if value[0].isdigit():
        value = "wp_" + value
    return value[:50]

def is_safe_path(target: Path, base: Path) -> bool:
    """Prevent Zip Slip vulnerability during extraction."""
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False

def download_wp(log):
    cache_file = Path(tempfile.gettempdir()) / "wordpress_latest.zip"
    
    # [FIX] Enhanced Zip validation to prevent crashes from partially downloaded files
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < 86400 and cache_file.stat().st_size > 10 * 1024 * 1024:
            if zipfile.is_zipfile(cache_file):
                log("Using valid cached WordPress zip archive...")
                return cache_file
            else:
                log("Cached archive is corrupted. Re-downloading...")

    log("Downloading latest WordPress archive...")
    req = urllib.request.Request(
        WP_ZIP_URL,
        headers={"User-Agent": "WordPress-XAMPP-Installer/2.0"}
    )
    
    with urllib.request.urlopen(req, timeout=90) as response, open(cache_file, "wb") as out_file:
        # [FIX] Handle empty or missing Content-Length gracefully
        try:
            total_size = int(response.headers.get("content-length", 0))
        except (ValueError, TypeError):
            total_size = 0
            
        downloaded = 0
        chunk_size = 256 * 1024  # 256KB
        
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            out_file.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                pct = int((downloaded / total_size) * 100)
                log(f"Downloading... {downloaded / 1048576:.1f} MB / {total_size / 1048576:.1f} MB ({pct}%)")
            else:
                log(f"Downloading... {downloaded / 1048576:.1f} MB")

    log("Download complete.")
    return cache_file

def escape_php_string(val):
    """[FIX] Escapes backslashes and single quotes to prevent PHP syntax fatal errors."""
    return val.replace("\\", "\\\\").replace("'", "\\'")

def write_config(site_dir, db, db_pass, port, salts, host="127.0.0.1"):
    db_host = host if str(port) == "3306" else f"{host}:{port}"
    # Secure escaping applied
    esc_db = escape_php_string(db)
    esc_db_pass = escape_php_string(db_pass)
    
    cfg = """<?php
define( 'DB_NAME', '%s' );
define( 'DB_USER', 'root' );
define( 'DB_PASSWORD', '%s' );
define( 'DB_HOST', '%s' );
define( 'DB_CHARSET', 'utf8mb4' );
define( 'DB_COLLATE', '' );

define( 'AUTH_KEY', '%s' );
define( 'SECURE_AUTH_KEY', '%s' );
define( 'LOGGED_IN_KEY', '%s' );
define( 'NONCE_KEY', '%s' );
define( 'AUTH_SALT', '%s' );
define( 'SECURE_AUTH_SALT', '%s' );
define( 'LOGGED_IN_SALT', '%s' );
define( 'NONCE_SALT', '%s' );

$table_prefix = 'wp_';
define( 'WP_DEBUG', false );

if ( ! defined( 'ABSPATH' ) ) {
    define( 'ABSPATH', __DIR__ . '/' );
}
require_once ABSPATH . 'wp-settings.php';
""" % (esc_db, esc_db_pass, db_host, *salts)
    (site_dir / "wp-config.php").write_text(cfg, encoding="utf-8")

def install_wp(xampp, site, slug, user, password, email, db_pass, preferred_port, log):
    log("Checking MySQL connection...")
    active_port = find_active_mysql_port(preferred_port)
    
    if not active_port:
        raise RuntimeError(
            "MySQL server is NOT running!\n"
            "Please open XAMPP Control Panel and click 'Start' next to MySQL."
        )

    if active_port != preferred_port:
        log(f"Port {preferred_port} closed. Automatically using active MySQL port {active_port}.")

    log("Waiting for MySQL handshake and initialization...")
    ready_host = wait_for_mysql(xampp, active_port, db_pass, max_attempts=8, delay=1.5)

    if not ready_host:
        raise RuntimeError(
            f"MySQL server on port {active_port} is not responding to queries.\n"
            "If MySQL just started, please wait a few seconds and try again."
        )

    site_dir = xampp / "htdocs" / slug
    db = sanitize_db_name(slug)

    if site_dir.exists() and any(site_dir.iterdir()):
        raise RuntimeError(f"Site folder already exists and is not empty:\n{site_dir}")

    log(f"Creating database: '{db}' on port {active_port} via {ready_host}...")
    
    # Needs to be secured just in case DB name is weird, though sanitize handles most of it.
    run_mysql(xampp, f"CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;", db_pass, active_port, host=ready_host)

    site_dir.mkdir(parents=True, exist_ok=True)
    
    zip_path = download_wp(log)
    
    log("Extracting WordPress files...")
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.namelist():
            if not member.startswith("wordpress/"):
                continue
            rel = member[len("wordpress/"):]
            if not rel:
                continue
            target = site_dir / rel
            if not is_safe_path(target, site_dir):
                continue
            if member.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

    log("Generating wp-config.php...")
    write_config(site_dir, db, db_pass, active_port, [secrets.token_urlsafe(48) for _ in range(8)], host=ready_host)

    php = xampp / "php" / "php.exe"
    if not php.exists():
        raise RuntimeError(f"PHP executable not found:\n{php}")

    script = site_dir / "_xampp_wp_install.php"
    log("Running WordPress automated setup...")
    
    try:
        # [FIX] We mock $_SERVER superglobals. Without this, WP guesses URLs wrong (http://C:/...)
        php_code = """<?php
$_SERVER['HTTP_HOST']   = 'localhost';
$_SERVER['SERVER_NAME'] = 'localhost';
$_SERVER['REQUEST_URI'] = '/__SLUG__/';
$_SERVER['PHP_SELF']    = '/__SLUG__/index.php';
define('WP_INSTALLING', true);
require_once __DIR__ . '/wp-load.php';
require_once ABSPATH . 'wp-admin/includes/upgrade.php';

$site_title = getenv('WPI_TITLE');
$user_name  = getenv('WPI_USER');
$user_email = getenv('WPI_EMAIL');
$user_pass  = getenv('WPI_PASS');

$r = wp_install($site_title, $user_name, $user_email, true, '', $user_pass);
if (is_wp_error($r)) {
    fwrite(STDERR, $r->get_error_message());
    exit(1);
}
echo "OK";
""".replace("__SLUG__", slug)

        script.write_text(php_code, encoding="utf-8")

        env = os.environ.copy()
        env.update(WPI_TITLE=site, WPI_USER=user, WPI_PASS=password, WPI_EMAIL=email)
        
        p = subprocess.run(
            [str(php), str(script)],
            cwd=str(site_dir),
            env=env,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=90,
            **get_subprocess_flags()
        )

        if p.returncode:
            err = (p.stderr or p.stdout or "WordPress installation process failed.").strip()
            raise RuntimeError(f"WordPress setup failed:\n{err}")
            
    finally:
        script.unlink(missing_ok=True)

    return f"http://localhost/{slug}/", db


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WordPress XAMPP Installer")
        self.geometry("580x760")
        self.resizable(False, False)
        
        self.apply_dark_theme()
        self.center_window(580, 760)

        self.slug_edited = False
        self.entries = {}

        # Main Container
        f = ttk.Frame(self, padding=24)
        f.pack(fill="both", expand=True)

        header = ttk.Label(f, text="WordPress Installer", font=("Segoe UI", 22, "bold"))
        header.pack(anchor="w", pady=(0, 2))
        
        ttk.Label(f, text="Automated local environment setup for XAMPP.", 
                  font=("Segoe UI", 10), foreground="#a6adc8").pack(anchor="w", pady=(0, 16))
        
        found_xampp_path = find_xampp()
        self.xampp = tk.StringVar(value=str(found_xampp_path or ""))
        
        self.status = ttk.Label(f, text="", font=("Segoe UI", 9, "bold"))
        self.status.pack(anchor="w", pady=(0, 8))

        # XAMPP Path Row
        row = ttk.Frame(f); row.pack(fill="x", pady=6)
        ttk.Label(row, text="XAMPP Folder", width=18, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.xampp_entry = ttk.Entry(row, textvariable=self.xampp)
        self.xampp_entry.pack(side="left", fill="x", expand=True)
        self.browse_btn = ttk.Button(row, text="Browse", command=self.browse, style="Accent.TButton", width=10)
        self.browse_btn.pack(side="left", padx=(8, 0))

        # Site Fields Array
        self.v = {}
        fields = [
            ("site", "Site Title", "My WordPress Site"),
            ("slug", "Folder (Slug)", "my_wordpress_site"),
            ("user", "Admin Username", "admin"),
            ("pass", "Admin Password", ""),
            ("email", "Admin Email", "admin@example.com"),
            ("db_pass", "MySQL Root Pass", ""),
            ("port", "MySQL Port", str(detect_mysql_port(found_xampp_path))),
        ]

        for key, label, default in fields:
            row = ttk.Frame(f); row.pack(fill="x", pady=6)
            ttk.Label(row, text=label, width=18, font=("Segoe UI", 10)).pack(side="left")
            self.v[key] = tk.StringVar(value=default)
            
            show_char = "•" if key in ("pass", "db_pass") else ""
            e = ttk.Entry(row, textvariable=self.v[key], show=show_char, font=("Segoe UI", 10))
            e.pack(side="left", fill="x", expand=True)
            self.entries[key] = e

        # Show Password Checkbox
        self.show_pass_var = tk.BooleanVar(value=False)
        pass_chk = ttk.Checkbutton(f, text="Show Passwords", variable=self.show_pass_var, command=self.toggle_passwords)
        pass_chk.pack(anchor="w", padx=(135, 0), pady=(4, 12))

        # Triggers
        self.v["site"].trace_add("write", self.on_site_title_change)
        self.entries["slug"].bind("<Key>", self.on_slug_keypress)

        self.progress = ttk.Progressbar(f, mode="indeterminate")
        self.progress.pack(fill="x", pady=(10, 10))

        self.install_btn = ttk.Button(f, text="INSTALL WORDPRESS", command=self.start, style="Install.TButton")
        self.install_btn.pack(fill="x", pady=(0, 12), ipady=4)

        # Output Log Box Styling
        self.logbox = ScrolledText(
            f, height=8, state="disabled", font=("Consolas", 9),
            bg="#181825", fg="#cdd6f4", insertbackground="#cdd6f4",
            relief="flat", borderwidth=0, highlightthickness=1, highlightbackground="#313244"
        )
        self.logbox.pack(fill="both", expand=True)
        
        self.refresh_status()

    def apply_dark_theme(self):
        """Creates an attractive modern Flat Dark UI natively in Tkinter."""
        style = ttk.Style()
        
        if "clam" in style.theme_names():
            style.theme_use("clam")

        # Catppuccin Dark Color Palette
        bg_color = "#1e1e2e"
        fg_color = "#cdd6f4"
        entry_bg = "#313244"
        entry_fg = "#cdd6f4"
        btn_accent = "#89b4fa"
        btn_accent_hover = "#b4befe"
        btn_primary = "#a6e3a1"
        btn_primary_hover = "#94e2d5"
        
        self.configure(bg=bg_color)
        
        style.configure(".", background=bg_color, foreground=fg_color, font=("Segoe UI", 10))
        style.configure("TFrame", background=bg_color)
        style.configure("TLabel", background=bg_color, foreground=fg_color)
        
        # Entries Styling
        style.configure("TEntry", fieldbackground=entry_bg, foreground=entry_fg, 
                        insertcolor=fg_color, borderwidth=0, padding=6)
        
        # Checkbutton Styling
        style.configure("TCheckbutton", background=bg_color, foreground=fg_color,
                        indicatorcolor=entry_bg, focuscolor=bg_color)
        style.map("TCheckbutton", indicatorcolor=[("selected", btn_accent)])

        # Buttons Styling
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=6, borderwidth=0)
        style.configure("Accent.TButton", background=btn_accent, foreground="#11111b")
        style.map("Accent.TButton", background=[("active", btn_accent_hover)])
        
        style.configure("Install.TButton", font=("Segoe UI", 12, "bold"), background=btn_primary, foreground="#11111b")
        style.map("Install.TButton", background=[("active", btn_primary_hover), ("disabled", entry_bg)])

        # Progressbar Styling
        style.configure("Horizontal.TProgressbar", background=btn_accent, troughcolor=entry_bg, borderwidth=0, thickness=4)

    def center_window(self, width, height):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def toggle_passwords(self):
        show = "" if self.show_pass_var.get() else "•"
        self.entries["pass"].config(show=show)
        self.entries["db_pass"].config(show=show)

    def on_site_title_change(self, *args):
        if not self.slug_edited:
            title = self.v["site"].get().strip().lower()
            slug = re.sub(r"[^a-z0-9_-]", "_", title)
            slug = re.sub(r"_+", "_", slug).strip("_")
            self.v["slug"].set(slug or "wordpress")

    def on_slug_keypress(self, event):
        self.slug_edited = True

    def browse(self):
        p = filedialog.askdirectory(title="Select XAMPP Installation Folder")
        if p:
            self.xampp.set(p)
            self.refresh_status()

    def refresh_status(self):
        p = Path(self.xampp.get())
        ok = (p / "htdocs").is_dir() and (p / "mysql").is_dir()
        if ok:
            self.status.config(text="✓ Valid XAMPP installation detected", foreground="#a6e3a1") # Green
            detected_port = detect_mysql_port(p)
            self.v["port"].set(str(detected_port))
        else:
            self.status.config(text="⚠ Select a valid XAMPP installation folder", foreground="#f38ba8") # Red

    def set_ui_state(self, state):
        self.browse_btn.config(state=state)
        self.install_btn.config(state=state)
        self.xampp_entry.config(state=state)
        for e in self.entries.values():
            e.config(state=state)

    def log(self, text):
        self.after(0, lambda t=text: self._log(t))

    def _log(self, text):
        self.logbox.config(state="normal")
        self.logbox.insert("end", text + "\n")
        self.logbox.see("end")
        self.logbox.config(state="disabled")

    def start(self):
        xampp = Path(self.xampp.get())
        v = {k: x.get().strip() for k, x in self.v.items()}

        if not ((xampp / "htdocs").is_dir() and (xampp / "mysql").is_dir()):
            messagebox.showerror("Invalid Path", "Please select a valid XAMPP installation directory.")
            return
            
        required_fields = ["site", "slug", "user", "pass", "email", "port"]
        if any(not v[k] for k in required_fields):
            messagebox.showerror("Missing Information", "Please fill in all required fields.")
            return

        if not v["port"].isdigit():
            messagebox.showerror("Invalid Port", "MySQL Port must be a valid number (e.g. 3306 or 3307).")
            return

        if not re.fullmatch(r"[A-Za-z0-9_-]+", v["slug"]):
            messagebox.showerror("Invalid Folder Slug", "Site folder can only contain letters, numbers, underscores, and hyphens.")
            return

        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v["email"]):
            messagebox.showerror("Invalid Email", "Please enter a valid admin email address.")
            return

        self.set_ui_state("disabled")
        self.progress.start(15)
        self.logbox.config(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.config(state="disabled")
        
        self.log("Starting installation...")

        def work():
            try:
                url, db = install_wp(
                    xampp, v["site"], v["slug"], v["user"], 
                    v["pass"], v["email"], v["db_pass"], int(v["port"]), self.log
                )
                self.after(0, lambda u=url, d=db: self.done(u, d))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda err=err_msg: self.fail(err))

        threading.Thread(target=work, daemon=True).start()

    def done(self, url, db):
        self.progress.stop()
        self.set_ui_state("normal")
        self.log(f"\n» Database: {db}")
        self.log(f"» Site URL: {url}")
        self.log("» Installation completed successfully! 🎉")
        
        if messagebox.askyesno("Success", f"WordPress site successfully created!\n\nURL: {url}\n\nWould you like to open it in your web browser now?"):
            import webbrowser
            webbrowser.open(url)

    def fail(self, msg):
        self.progress.stop()
        self.set_ui_state("normal")
        self.log("\n❌ ERROR: " + msg)
        messagebox.showerror("Installation Failed", msg)

if __name__ == "__main__":
    App().mainloop()