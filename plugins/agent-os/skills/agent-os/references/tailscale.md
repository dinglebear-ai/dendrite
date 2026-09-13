# agent-os Tailscale maintenance

Read this before bouncing the guest's Tailscale.

The guest runs its own `tailscaled`, and `ssh agent-os` connects **over that same Tailscale IP** (`198.51.100.10`). That creates a footgun:

- **Never run `tailscale down` (or restart the Tailscale service) over `ssh agent-os`.** The moment Tailscale drops, your SSH session is severed mid-command — so the follow-up `tailscale up` never executes and the node is left **stopped** (no Tailscale, MCP/gateway unreachable).
- **Do Tailscale maintenance via the host port-forward instead:** `ssh -p "${CLAUDE_PLUGIN_OPTION_AGENT_OS_HOST_FORWARD_PORT:-2222}" "${CLAUDE_PLUGIN_OPTION_AGENT_OS_HOST_FORWARD_SSH:?set agent_os_host_forward_ssh in plugin settings}"`. This path goes through Docker/host forwarding, not the guest's Tailscale, so it survives `tailscale down/up`.
- **Windows `tailscale up` won't run bare** when non-default prefs are set (this VM uses `--exit-node-allow-lan-access --unattended`). It errors and tells you to either re-list every non-default flag or use `tailscale up --reset`. Easiest reliable bounce: `Restart-Service Tailscale -Force` then `tailscale up --reset` (or re-list the flags).
- **"offline but reachable" is expected here.** The control plane can show the node `offline / not in map poll` while it's still reachable via a direct LAN route (`192.0.2.2`) — fine on-LAN (SSH/MCP work), but unreliable from a remote network. A clean `tailscale up` after a service restart re-establishes the map poll and clears it.
- If the gateway shows `agent-os_windows-mcp` as upstream discovery timed out, first check the guest's Tailscale is actually up with the configured host-forward SSH target, then reload the gateway.
