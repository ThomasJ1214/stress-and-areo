# Installing Stress & Aero on Windows

Stress & Aero runs on **Windows 10 or 11 (64-bit)**. You do not need Python or any other tools —
the installer contains everything.

## System requirements
- Windows 10/11, 64-bit
- A graphics driver with OpenGL 3.2 or newer (any NVIDIA/AMD card or Intel graphics from the last ~10 years)
- About 2 GB of free disk space
- 8 GB RAM minimum; 32 GB recommended for CFD and FEA (later versions)

## Step 1 — Download the installer
1. Open the project on GitHub and click the **Actions** tab.
2. Click the most recent green **CI** run on the branch you want.
3. Scroll to **Artifacts** and download **StressAero-Setup** (a `.zip`).
4. Open the `.zip` and drag `StressAero-Setup-<version>.exe` to your Desktop.

(When releases are published, you can instead download `StressAero-Setup-<version>.exe` from the
**Releases** page.)

## Step 2 — Run the installer
1. Double-click `StressAero-Setup-<version>.exe`.
2. Windows may show **"Windows protected your PC"** because the installer is not code-signed.
   Click **More info**, then **Run anyway**.
3. Follow the wizard. The default location is your user folder, so **no administrator rights are needed**.
   Optionally tick *Create a desktop shortcut* and *Open OpenRocket .ork files with Stress & Aero*.
4. Leave *Launch Stress & Aero with the demo rocket* ticked and click **Finish**.

## Step 3 — Open your rocket
- **File → Open…** (Ctrl+O) and choose your OpenRocket `.ork` file (OpenRocket 23.09 / 24.x files and older
  are supported).
- Pick a **Flight configuration** in the toolbar.
- Click a part in the 3-D view or in the **Components** list to see its dimensions, material, mass and CG.
  Every computed number shows how it was calculated in the **Source** column.
- **View → Units** switches between Metric and US customary.
- **File → Save project** stores your work as a `.saproj` file (it embeds a copy of the `.ork`).

## Uninstalling
Windows **Settings → Apps → Installed apps → Stress & Aero → Uninstall**.

## Troubleshooting
- **Blank or black 3-D view:** update your graphics driver from the GPU vendor's website.
- **"Could not open …":** the message explains what is wrong with the file; please report it with the file
  attached if it opens fine in OpenRocket.
