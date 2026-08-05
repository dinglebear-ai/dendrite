# nircmd

Drive a Windows machine over SSH via the NirCmd CLI and its NirSoft companion utilities: audio control, window management, lock, TTS, system dialogs, granular screen capture, and a curated set of scriptable NirSoft companions (CurrPorts, LastActivityView, OpenedFilesView, SearchMyFiles, ...) for inspecting Windows state from the shell.

Built on [NirSoft NirCmd](https://www.nirsoft.net/utils/nircmd.html) (~120KB binary, 115 commands) plus selected [NirSoft utilities](https://www.nirsoft.net/utils/) (200+ tools, available as a bundle via [NirLauncher](https://launcher.nirsoft.net/)).

## What it does

| Capability | One-line example |
|------------|------------------|
| Screenshot a specific window | `win-shot.sh "Visual Studio Code"` |
| Lock the workstation | `lock.sh` |
| Audio (volume/mute/per-app) | `nircmd setsysvolume 32768` |
| TTS — Windows speaks | `nircmd speak text "deploy finished"` |
| Window control (focus/min/max/close/pin) | `nircmd win activate ititle "Chrome"` |
| Region capture by coords | `nircmd savescreenshot out.png 0 0 1920 1080` |
| Multi-monitor stitched capture | `nircmd savescreenshotfull out.png` |
| Tray notification | `nircmd trayballoon "Title" "Body" "icon" 5000` |
| What's holding a port | `cports.exe /scomma C:\Temp\ports.csv` |
| Recent activity on the box | `LastActivityView.exe /scomma C:\Temp\activity.csv` |
| Which process holds this file | `OpenedFilesView.exe /filefilter "C:\path" /scomma out.csv` |
| Nearby Wi-Fi APs / signal | `WirelessNetView.exe /scomma C:\Temp\aps.csv` |
| Saved file search | `SearchMyFiles.exe /cfg saved.cfg /scomma out.csv` |

## How it works

```
[remote Linux + Claude]                       [Win11 desktop]
       │
       │  ssh winhost-wsl  ─────────────────►  WSL Ubuntu
       │                                           │
       │                                           │  shells out to
       │                                           ▼
       │                              /mnt/c/tools/nircmd/nircmd.exe
       │                                           │
       │                                           ▼
       │                              Windows clipboard / windows /
       │                                  audio / screen / etc.
       ▼
   `win-shot.sh` / `lock.sh` / etc. wrappers
```

## Prerequisites

- Passwordless SSH from the Claude host to your Windows-side WSL (`ssh winhost-wsl`).
- NirCmd installed on Windows at `C:\tools\nircmd\nircmd.exe`. To install:
  ```powershell
  Invoke-WebRequest 'https://www.nirsoft.net/utils/nircmd-x64.zip' -OutFile $env:TEMP\nircmd.zip
  Expand-Archive $env:TEMP\nircmd.zip -DestinationPath C:\tools\nircmd -Force
  ```
- **Optional but recommended** — the NirSoft companion bundle at `C:\tools\nirsoft\` (or via NirLauncher). One-shot install of all 200+ tools:
  ```powershell
  Invoke-WebRequest 'https://launcher.nirsoft.net/downloads/nirlauncher.zip' -OutFile $env:TEMP\nl.zip
  Expand-Archive $env:TEMP\nl.zip -DestinationPath C:\tools\NirLauncher -Force
  # then set NIRSOFT_DIR to /mnt/c/tools/NirLauncher/NirSoft
  ```
  Or grab individual tools from `https://www.nirsoft.net/utils/<tool>.html` into `C:\tools\nirsoft\`.

## Pointing at a different machine

```json
{
  "env": {
    "NIRCMD_HOST": "workbox",
    "NIRCMD_PATH": "/mnt/c/tools/nircmd/nircmd.exe",
    "NIRSOFT_DIR":  "/mnt/c/tools/nirsoft"
  }
}
```

in `~/.claude/settings.json` (same env-injection pattern as the `screens` skill — Claude's Bash tool doesn't pick up interactive-shell `export`s).

## Charset gotcha

NirCmd args go through Windows' ANSI codepage. Em-dashes, smart quotes, emoji, and non-Latin scripts can be mangled. For clipboard work, use the separate `clipboard` skill, which routes Unicode text through PowerShell.

## Safety

NirCmd can do destructive things. The skill enforces three tiers (see `references/safety-boundaries.md` for the full classification):

- **Auto-allowed**: clipboard, screen capture, audio, lock, speak, window listing/activation, dialogs, beep.
- **Ask first**: killprocess / closeprocess, runas / elevate, registry writes, service control, file delete.
- **Refuse without extremely explicit instruction**: shutdown / reboot / logoff / standby / hibernate.

## Files

```
nircmd/
├── SKILL.md                                Agent instructions
├── README.md                               This file
├── CHANGELOG.md
├── scripts/
│   ├── win-shot.sh                         Activate window by title, then capture
│   └── lock.sh                             Lock the workstation
└── references/
    ├── command-reference.md                All 115 NirCmd commands, categorized
    ├── window-control.md                   Window matching and manipulation
    ├── safety-boundaries.md                Auto / ask / refuse classification + rationale
    └── nirsoft-tools.md                    NirSoft companion CLIs (CurrPorts, LastActivityView, etc.)
```
