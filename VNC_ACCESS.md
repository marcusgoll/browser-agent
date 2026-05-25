VNC Access Options for Browser Agent
=====================================

Problem: Tailscale is not running on your local machine, so 100.93.148.25
is unreachable from your Windows desktop.

Option 1: Start Tailscale (Recommended)
---------------------------------------
On your Windows machine:
1. Open Tailscale app
2. Click "Connect"
3. Wait for status to show "Connected"
4. Try VNC again: vncviewer 100.93.148.25:5900

Option 2: SSH Tunnel (No Tailscale needed)
------------------------------------------
From your local machine, create an SSH tunnel to the homelab:

   ssh -L 5900:localhost:5900 orchestrator@YOUR_HOMELAB_PUBLIC_IP

Then connect VNC to localhost:5900 on your local machine.

Note: Your homelab is behind Cloudflare Tunnel, so it may not have a
public IP exposed for SSH. Check if you can SSH directly.

Option 3: Cloudflare Tunnel (TCP)
---------------------------------
If you have a Cloudflare Tunnel set up for TCP, you could expose port 5900.
This is NOT recommended for VNC without password/auth.

Option 4: Use the Existing Social Media Agent
---------------------------------------------
You already have social-media-agent and social-agent-chrome running.
That stack may already have X authentication configured. Check:

   docker inspect social-media-agent

Option 5: Manual Cookie Export/Import
-------------------------------------
1. Log into X.com on your local browser
2. Export cookies using a browser extension (e.g., "Get cookies.txt")
3. Copy the cookie file to /home/orchestrator/browser-agent/profiles/x-profile/
4. Run headless tasks with that profile

Current Status
--------------
- VNC container is running on homelab port 5900
- Tailscale IP: 100.93.148.25 (only reachable via Tailscale)
- Your Windows desktop shows offline in Tailscale (47 days)

Recommendation
--------------
Start Tailscale on your Windows machine. It's the simplest and most secure
way to access the VNC session.
