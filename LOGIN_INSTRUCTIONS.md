Interactive Login to X.com — Instructions
==========================================

Status: VNC container is running. Chromium is open and loading x.com.

Step 1: Connect via VNC
-----------------------
From your local machine, connect to the homelab VNC server:

   vncviewer 100.93.148.25:5900

Or use any VNC client (TigerVNC, RealVNC, Remmina) connecting to:
   Host: 100.93.148.25
   Port: 5900
   Password: (none — click Connect/OK if prompted)

Step 2: Log in to X.com
-----------------------
In the VNC window you will see a Chromium browser on x.com.

1. Click "Sign in" or "Log in"
2. Choose "Sign in with Google"
3. Enter your Google credentials
4. Complete 2FA if prompted
5. You should now be logged into X

Step 3: Save the session
------------------------
The profile is already being saved to /app/profiles/x-profile/ automatically.
Simply close the VNC window or stop the container when done.

Step 4: Stop the VNC container
------------------------------
   cd /home/orchestrator/browser-agent
   docker compose -f docker-compose.vnc.yml down

Step 5: Run authenticated headless tasks
----------------------------------------
Now you can run headless tasks using the saved profile:

   docker compose run --rm browser-agent scripts/run_task.py \
     "Go to x.com and post 'Hello from my homelab agent'" \
     --profile x-profile

Or:

   docker compose run --rm browser-agent scripts/scrape.py \
     https://x.com/home --profile x-profile \
     --extract "first 5 tweets on the timeline"

Troubleshooting
---------------
- If VNC shows a black screen: wait 10 seconds for fluxbox to start
- If Chromium crashes: check memory — the container needs ~1GB RAM
- If x.com shows a security challenge: complete it manually in VNC
- Profile permissions: the container runs as root inside, but profiles
  are saved to a host-mounted volume so they persist
