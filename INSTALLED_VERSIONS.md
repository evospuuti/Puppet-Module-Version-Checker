# Installed Software Versions Configuration

This file documents how to configure the installed versions for PuTTY and WinSCP that are tracked by the System Tracker.

## Configuration Methods

### 1. Environment Variables (Recommended for Production)

Set these environment variables in your deployment:

```bash
export PUTTY_VERSION="0.83"
export WINSCP_VERSION="6.5"
```

In Vercel, add these as environment variables in your project settings.

### 2. Default Values (Fallback)

If no environment variables are set, the system uses these defaults:
- **PuTTY**: 0.83
- **WinSCP**: 6.5

## How Version Comparison Works

The system compares your installed version with the latest available version:

| Installed | Latest | Status |
|-----------|--------|--------|
| 0.83 | 0.83 | ✅ Aktuell |
| 0.83 | 0.84 | ⚠️ Update verfügbar |
| 0.82 | 0.83 | ⚠️ Update verfügbar |

## Updating Versions

When you update your software, simply update the environment variable:

1. **Local Development**:
   ```bash
   export PUTTY_VERSION="0.84"
   ```

2. **Vercel Deployment**:
   - Go to Settings → Environment Variables
   - Update `PUTTY_VERSION` or `WINSCP_VERSION`
   - Redeploy for changes to take effect

## Example Display

### When versions match:
```
PUTTY - Aktuell
Installierte Version: 0.83
Aktuelle Version: 0.83
```

### When update is available:
```
PUTTY - Update verfügbar
Installierte Version: 0.83
Aktuelle Version: 0.84
➡️ Update verfügbar: 0.83 → 0.84
```