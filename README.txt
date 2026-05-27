PIP-BOY HEALTH COMPANION
========================
PyQt6 desktop companion for the Vault-Tec Health Tracker Android app.

REQUIREMENTS
------------
  Python 3.8+
  pip install PyQt6

FIRST-TIME SETUP
----------------
1. Install Python:
     winget install Python.Python.3.12

2. Install PyQt6:
     pip install PyQt6

3. Sign in (run once to create your session file):
     python pipboy_auth.py

   Follow the on-screen instructions to:
   - Create a Desktop OAuth client in Google Cloud Console
   - Paste CLIENT_ID and CLIENT_SECRET into pipboy_auth.py
   - Sign in via Google Device Flow

4. Run the app:
     pythonw pipboy_app.py

   (use pythonw so closing the terminal doesn't close the app)

USAGE
-----
- A compact bar appears in the bottom-right corner of your screen
- Click the > button or the bar itself to expand the full panel
- The app refreshes data from Firebase every 30 seconds
- Right-click the system tray icon to show/hide or quit
- Drag the bar to reposition -- position is saved automatically

TABS (in expanded panel)
------------------------
  HEALTH   -- Condition score, vitals, custom trackers
  SPECIAL  -- S.P.E.C.I.A.L. pillar breakdown and advisory
  LOG      -- Log water, sleep, weight, morning energy, custom trackers
  TASKS    -- View and check off tasks, add new tasks
  WRITING  -- Academic rank, defence countdown, chapter progress, log sessions
  FOCUS    -- Pomodoro timer, session log

TOKEN EXPIRY
------------
Firebase tokens expire after 1 hour. If your refresh token is saved
(run pipboy_auth.py --reauth to ensure this), the app refreshes automatically.
If you see "SESSION EXPIRED", run:
  python pipboy_auth.py --reauth

FILES
-----
  pipboy_app.py    -- Main application (single file, all UI + Firebase)
  pipboy_auth.py   -- Google sign-in (run once, or --reauth to re-login)
  ~/.pipboy_token.json   -- Saved session (auto-managed)
  ~/.pipboy_config.json  -- Window position (auto-managed)
