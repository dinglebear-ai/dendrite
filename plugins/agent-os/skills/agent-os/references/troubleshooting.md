# agent-os Troubleshooting

Work top to bottom — most failures are "the VM/MCP isn't reachable," and the checks are layered from outermost (container) to innermost (the tool call). The four connection layers (server → exposure → client → gateway) and the outward repair walk are documented in the **Connection** section of `SKILL.md`; Tailscale-specific repair lives in `references/tailscale.md`.

| Symptom | Likely cause | Fix |
|---|---|---|
| `mcp__windows-mcp__*` tools missing / "server not found" | windows-mcp server or VM container down | On `$CLAUDE_PLUGIN_OPTION_AGENT_OS_VM_HOST`: `docker ps \| grep "$CLAUDE_PLUGIN_OPTION_AGENT_OS_CONTAINER_NAME"`. If absent: `docker compose -f "$CLAUDE_PLUGIN_OPTION_AGENT_OS_COMPOSE_FILE" up -d`. Then reload the gateway. |
| Gateway shows `agent-os_windows-mcp` upstream discovery timeout | guest Tailscale down/flapping, or MCP slow to list tools | `ssh -p "${CLAUDE_PLUGIN_OPTION_AGENT_OS_HOST_FORWARD_PORT:-2222}" "$CLAUDE_PLUGIN_OPTION_AGENT_OS_HOST_FORWARD_SSH" tailscale status` (host-forward path). If Tailscale is down, bring it up (see `references/tailscale.md`). Then reload the gateway. |
| `ssh agent-os` times out but host-forward SSH works | guest Tailscale is stopped/offline | Bring Tailscale up via the host-forward path — see `references/tailscale.md`. Never `tailscale down` over `ssh agent-os`. |
| Node shows `offline` in `tailscale status` but pings/SSH work on-LAN | "not in map poll" — control-plane session not held (NAT churn) | Expected on-LAN; for remote access do a clean `Restart-Service Tailscale -Force` + `tailscale up --reset` via host-forward. |
| `Snapshot`/`Screenshot` fail (Python `cv2` missing) | Windows-MCP image missing OpenCV | Capture in PowerShell instead: `System.Drawing.Graphics.CopyFromScreen` with the window rect from `user32!GetWindowRect`. |
| MCP call dies around ~120s on a long op | MCP call layer timeout (not your `timeout` arg) | Split long work into chunks; write a manifest beside outputs. Kick off via `PowerShell`, poll with `Screenshot`. |
| GUI app launches but synthetic input/focus unreliable (esp. GPUI windows) | `Start-Process` / non-interactive SSH not desktop-attached | Drive through Windows-MCP `PowerShell` with `WScript.Shell` `Run` + `AppActivate` + `SendKeys` (see "Driving native / GPUI desktop apps" in `references/recipes.md`). |
| Downloaded `.exe`/`.ps1` blocked, SmartScreen/publisher prompt | Mark-of-the-Web on copied files | `Unblock-File` the file; set `SEE_MASK_NOZONECHECKS=1` before launching child exes. |
| First run of an app raises a Windows Firewall prompt | new listener needs an allow rule | Pre-create a firewall rule, or accept once from the desktop (via noVNC) before expecting unattended runs. |
| Need to *see* the desktop to debug | — | noVNC at `http://nashost:8006/vnc.html?autoconnect=1&resize=remote` (visual only — fix through Windows-MCP). |
| Installed software/files vanished after reboot | something written outside `/storage` | Only `/storage` (the VM disk) persists; the container is reachable again after `docker compose up -d`. Re-install if it landed on an ephemeral layer. |
