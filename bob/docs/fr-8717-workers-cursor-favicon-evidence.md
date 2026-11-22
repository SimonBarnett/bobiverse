# FR #8717 / BOB-24 evidence

S1: Workers > Cursor uses the cursor.com favicon.

- Asset: `bob/tray/assets/menu-favicons/cursor.com.ico` (public `https://cursor.com/favicon.ico`, ICO magic `00 00 01 00`).
- Native tray: `TrayContext.ApplyWorkerFavicon` sets the Cursor menu image and writes tray log `worker-favicon` with `path` and `ok`.
- Headless: `bob-tray.exe --dump-worker-favicon <file> --root <bob/tray>` writes that asset path and exits before the UI.
- TipForm Workers menu (`Update-BobTrayWorkerAgentsMenu`) loads the same file and logs `worker-favicon id=cursor`.
