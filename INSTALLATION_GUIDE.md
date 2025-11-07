# Installation Guide - Fyers WebSocket with SEBI Compliance

## Quick Installation Summary

This guide provides step-by-step instructions for setting up the Fyers WebSocket application with both modern (`uv`) and classical (`pip`) methods.

---

## Prerequisites

- **Python**: 3.8 or higher
- **Fyers API Credentials**: Get from [myapi.fyers.in](https://myapi.fyers.in/)
- **Operating System**: macOS, Linux, or Windows

---

## Installation Method 1: Using `uv` (Recommended)

### Why uv?
- ⚡ **10-100x faster** than pip
- 🎯 **Better dependency resolution**
- 🔒 **Reproducible builds**
- 🚀 **Modern Python tooling**

### Step 1: Install uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using Homebrew (macOS)
brew install uv

# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

### Step 2: Clone Repository

```bash
git clone https://github.com/marketcalls/fyers-websockets.git
cd fyers-websockets
```

### Step 3: Create Virtual Environment

```bash
uv venv
```

**Output:**
```
Using CPython 3.13.0 interpreter at: /usr/local/bin/python3
Creating virtual environment at: .venv
Activate with: source .venv/bin/activate
```

### Step 4: Activate Virtual Environment

```bash
# macOS/Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\activate

# Windows (Command Prompt)
.venv\Scripts\activate.bat
```

### Step 5: Install Dependencies

```bash
# Install from requirements.txt
uv pip install -r requirements.txt

# Or install from pyproject.toml
uv pip install .
```

**Output:**
```
Resolved 39 packages in 1.18s
Prepared 20 packages in 1.26s
Installed 35 packages in 104ms
 + apscheduler==3.10.4
 + flask==3.1.0
 + sqlalchemy==2.0.41
 ... (and 32 more packages)
```

### Step 6: Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit with your credentials
nano .env  # or use your favorite editor
```

### Step 7: Run Application

```bash
python app.py
```

---

## Installation Method 2: Using `pip` (Classical)

### Step 1: Clone Repository

```bash
git clone https://github.com/marketcalls/fyers-websockets.git
cd fyers-websockets
```

### Step 2: Create Virtual Environment

```bash
# macOS/Linux
python3 -m venv venv

# Windows
python -m venv venv
```

### Step 3: Activate Virtual Environment

```bash
# macOS/Linux
source venv/bin/activate

# Windows (PowerShell)
venv\Scripts\activate

# Windows (Command Prompt)
venv\Scripts\activate.bat
```

### Step 4: Upgrade pip

```bash
pip install --upgrade pip
```

### Step 5: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 6: Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit with your credentials
nano .env  # or use your favorite editor
```

### Step 7: Run Application

```bash
python app.py
```

---

## Environment Configuration

### Required Variables

Edit `.env` file with these required values:

```bash
# Fyers API Credentials (from myapi.fyers.in)
BROKER_API_KEY='YOUR-FYERS-APP-ID'
BROKER_API_SECRET='YOUR-FYERS-SECRET-KEY'
REDIRECT_URL='http://127.0.0.1:5000/fyers/callback'

# WebSocket Configuration
WEBSOCKET_URL='wss://rtsocket-api.fyers.in/versova'
SYMBOL='NSE:NIFTY25NOVFUT'

# Trading Configuration
LOT_SIZE=75

# Database
DATABASE_URL='sqlite:///fyers_depth.db'

# Security (CHANGE THESE!)
SECRET_KEY='generate-random-key-here'
API_KEY_PEPPER='generate-random-key-here'
```

### Generate Secure Keys

```bash
# Generate SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"

# Generate API_KEY_PEPPER
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Verification

### Expected Startup Output

```
[SCHEDULER] Started APScheduler for SEBI compliance
[SCHEDULER] Midnight token cleanup scheduled for 3:00 AM daily
[WEBSOCKET] WebSocket client task started (waiting for login)
 * Serving Flask app 'app'
 * Debug mode: on
WARNING: This is a development server.
 * Running on http://127.0.0.1:5000
Press CTRL+C to quit
```

### Test Installation

1. **Open Browser**: Navigate to `http://localhost:5000`
2. **Check Redirect**: Should redirect to Fyers OAuth login
3. **Verify Logs**: Console should show scheduler and WebSocket messages

---

## Comparison: uv vs pip

| Feature | uv | pip |
|---------|-----|-----|
| **Installation Speed** | ⚡ 10-100x faster | Standard |
| **Dependency Resolution** | 🎯 Advanced resolver | Basic resolver |
| **Lock Files** | ✅ Built-in support | Requires pip-tools |
| **Python Version Management** | ✅ Integrated | Needs pyenv |
| **Disk Space** | 💾 Efficient caching | More redundant |
| **Learning Curve** | 📚 Familiar to pip users | Standard |

---

## Troubleshooting

### Issue: `uv: command not found`

**Solution:**
```bash
# Reload shell configuration
source ~/.bashrc  # or ~/.zshrc

# Or install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Issue: `Permission denied` when creating venv

**Solution:**
```bash
# Ensure you're in the project directory
cd /path/to/fyers-websockets

# Use sudo only if necessary (not recommended)
chmod +x .
```

### Issue: `ModuleNotFoundError: No module named 'APScheduler'`

**Solution:**
```bash
# Ensure virtual environment is activated
source .venv/bin/activate  # for uv
# OR
source venv/bin/activate   # for pip

# Reinstall dependencies
uv pip install APScheduler==3.10.4
# OR
pip install APScheduler==3.10.4
```

### Issue: `externally-managed-environment` (pip on macOS/Linux)

**Solution:**
```bash
# ALWAYS use virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Or use uv (better solution)
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

---

## Database Setup

### First Run

On first run, the application will:
1. Create `fyers_depth.db` SQLite database
2. Initialize `users` and `auth` tables
3. Add `login_date` column for SEBI compliance

### Database Migration

If you're upgrading from an older version:

```python
# The app will automatically run migrations on startup
# Look for this message in logs:
# "Added login_date column"
```

### Manual Database Check

```bash
# Check database structure
sqlite3 fyers_depth.db ".schema auth"

# Verify login_date column exists
sqlite3 fyers_depth.db "PRAGMA table_info(auth);"
```

---

## Running the Application

### Development Mode

```bash
# Using uv
source .venv/bin/activate
python app.py

# Using pip
source venv/bin/activate
python app.py
```

### Production Mode (Gunicorn)

```bash
# Install gunicorn
uv pip install gunicorn
# OR
pip install gunicorn

# Run with gunicorn
gunicorn --bind 0.0.0.0:5000 --workers 4 app:app
```

---

## SEBI Compliance Verification

### Check Scheduler is Running

Look for these log messages on startup:

```
[SCHEDULER] Started APScheduler for SEBI compliance
[SCHEDULER] Midnight token cleanup scheduled for 3:00 AM daily
```

### Test Token Expiration

```bash
# Check current tokens
sqlite3 fyers_depth.db "SELECT name, login_date, is_revoked FROM auth;"

# Verify tokens from previous day are revoked
# Expected: is_revoked=1 for old dates
```

---

## Next Steps

1. ✅ **Configure Fyers API** credentials in `.env`
2. ✅ **Start application** with `python app.py`
3. ✅ **Login via OAuth** at `http://localhost:5000`
4. ✅ **Verify WebSocket** connection in logs
5. ✅ **Test SEBI compliance** by checking midnight cleanup

---

## Useful Commands

### uv Commands

```bash
# List installed packages
uv pip list

# Show package info
uv pip show APScheduler

# Freeze dependencies
uv pip freeze > requirements.txt

# Uninstall package
uv pip uninstall package-name

# Update all packages
uv pip install --upgrade -r requirements.txt
```

### pip Commands

```bash
# List installed packages
pip list

# Show package info
pip show APScheduler

# Freeze dependencies
pip freeze > requirements.txt

# Uninstall package
pip uninstall package-name

# Update all packages
pip install --upgrade -r requirements.txt
```

---

## Support

For issues or questions:
1. Check console logs for error messages
2. Review [SEBI_COMPLIANCE.md](SEBI_COMPLIANCE.md)
3. Verify environment variables in `.env`
4. Ensure all dependencies are installed

---

## Quick Reference Card

```bash
# UV METHOD (RECOMMENDED)
┌──────────────────────────────────────────┐
│ 1. uv venv                               │
│ 2. source .venv/bin/activate             │
│ 3. uv pip install -r requirements.txt    │
│ 4. cp .env.example .env                  │
│ 5. nano .env (add credentials)           │
│ 6. python app.py                         │
└──────────────────────────────────────────┘

# PIP METHOD (CLASSICAL)
┌──────────────────────────────────────────┐
│ 1. python3 -m venv venv                  │
│ 2. source venv/bin/activate              │
│ 3. pip install -r requirements.txt       │
│ 4. cp .env.example .env                  │
│ 5. nano .env (add credentials)           │
│ 6. python app.py                         │
└──────────────────────────────────────────┘
```

---

**Built with ❤️ for professional traders**

For detailed compliance documentation, see [SEBI_COMPLIANCE.md](SEBI_COMPLIANCE.md)
