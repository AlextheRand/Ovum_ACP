# Modbus-Anmeldung und Plus-Freischaltung (0.4.3)

Am 07.09.2026 lieferte eine separate TCP-Verbindung für HK3 zunächst
`65535, 32767, 32767, 32704, 0, 32704, 0, 65535`. Nach FC16-Anmeldung
an Adresse 101 mit dem hinterlegten Zugangscode lieferte **dieselbe Verbindung**
Typ 3, Soll 5 °C, Ist etwa 22,22 °C und Modus 0. Auch WW-Anforderung,
Pufferstatus, Pufferladestatus und HK2-Raumtemperatur wurden lesbar.
Eine weitere Verbindung ohne eigene Anmeldung lieferte wieder ungültige Werte.
Die am Display vorgenommene Plus-Freischaltung war damit wirksam;
eine unangemeldete Direktabfrage konnte sie nicht zuverlässig beurteilen.

## Änderung

- Vor jedem Abruf meldet sich der Coordinator an HSM und den konfigurierten
  WPMs an. Das übernimmt auch nachträgliche Freischaltungen auf bestehenden
  Verbindungen, ohne einen manuellen Reload oder die bisherige 25-Minuten-Frist.
- Der pymodbus-Verbindungs-Callback verwirft die Anmeldung auch bei einer
  automatischen Wiederverbindung zwischen zwei Abrufen.
- Ändert sich die Verbindung während der Anmeldung, gilt diese als fehlgeschlagen.
- Bei einem Verbindungswechsel während des Lesens wird das Ergebnis verworfen
  und einmal nach erneuter Anmeldung gelesen. Wiederholte Abbrüche führen zu
  einem fehlgeschlagenen Update statt einer unbegrenzten Wiederholung.
- Ungültige Werte einzelner Sensoren lösen keine zusätzliche Anmeldeschleife aus.
- Nur das flüchtige Anmelderegister wird zusätzlich beschrieben. Es werden
  keine Heizungs-Sollwerte oder persistenten Parameter zur Prüfung geschrieben.

## Prüfung und Installation

- 81 Tests erfolgreich, darunter sieben neue Tests für Anmeldung und Wiederverbindung.
- Ruff-Prüfung auf Python-Fehler und `git diff --check` erfolgreich.
  Die vollständige Ruff-Konfiguration meldet unverändert 40 bestehende Befunde
  in Coordinator und Coordinator-Tests; der Fix fügt keine hinzu.
- Drei direkte Abrufe mit dem geänderten Coordinator, jeweils 32 Sekunden
  Abstand: Plus-Statuswerte und HK3 jedes Mal verfügbar.
- Installiert wurden ausschließlich `coordinator.py` und `manifest.json`.
  Dateihashes lokal und auf Home Assistant stimmen überein.
- Backup vor Installation:
  `/config/backups/ovum-before-session-fix-20260907T163830Z/ovum_acp`.
- `ha core check` erfolgreich; neuer Python-Code wird durch HA-Neustart geladen.
- Neustart erfolgreich. Vier HA-Abfragen zwischen 16:40:04 und 16:41:40 UTC,
  jeweils 32 Sekunden Abstand, bestätigten WW-Anforderung, Pufferstatus,
  Pufferladestatus, HK2-Raumtemperatur und HK3 Typ/Soll/Ist/Modus als verfügbar.
  Insgesamt 91 von 92 aktiven OVUM-Entitäten verfügbar; nur `sys_type` bleibt
  nicht verfügbar. Warmwasser änderte sich dabei von 44,41 auf 44,32 °C.
- Die bestehende Saisonsteuerung setzte HK3 von AUS auf SOMMER, per HA
  zurückgelesen. Dabei wurde einmal eine abgebrochene FC06-Anfrage an 56077
  protokolliert; die vorhandene Wiederholung stellte den Auftrag erfolgreich her.
  Die folgenden drei HA-Abfragen bestätigten SOMMER.

Für einen Rollback die beiden gesicherten Dateien aus dem Backup nach
`/config/custom_components/ovum_acp/` zurückkopieren und Home Assistant neu starten.
