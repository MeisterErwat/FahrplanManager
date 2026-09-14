FAHRPLAN MANAGER ULTIMATE 6
© MeisterErwat

NEU:
- Stabiler Start: Einstellungen werden vor der Theme-Anwendung geladen.
- Automatische Updateprüfung beim Start.
- Manuelle Updateprüfung im Seitenmenü.
- Updater.exe lädt eine neue FahrplanManager.exe, ersetzt die alte und startet sie erneut.
- Einstellungen, Fahrpläne und Historie bleiben beim Update erhalten.
- Darkmode, optionale IST-/ETA-Zeit und eigene Routennamen bleiben erhalten.

UPDATE-SYSTEM EINMALIG EINRICHTEN:
1. Lade release\FahrplanManager.exe und release\Updater.exe auf einen öffentlich erreichbaren Server.
2. Erstelle eine update.json mit z. B.:
   {
     "version": "6.1",
     "download_url": "https://dein-server/FahrplanManager.exe",
     "notes": "Neue Funktionen"
   }
3. Trage die URL zu dieser update.json in update_config.json ein:
   {"enabled": true, "manifest_url": "https://dein-server/update.json"}
4. Für jede neue Version erhöhst du APP_VERSION in main.py, erstellst mit build_windows.bat die neuen EXEs und ersetzt die veröffentlichte FahrplanManager.exe.
5. Die Benutzer müssen nur die alte FahrplanManager.exe einmal ersetzen, ab dann laufen weitere Updates automatisch.

WICHTIG:
Der aktuell eingetragene GitHub-Link ist nur ein Platzhalter (DEIN-USERNAME/DEIN-REPO). Solange du ihn nicht ersetzt, fragt das Programm still im Hintergrund ohne Update ab.
