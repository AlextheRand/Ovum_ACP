# Ovum ACP — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Inoffizielle Home Assistant Integration für **Ovum MIRA Wärmepumpen** mit LSM-Display und aktiviertem Modbus TCP.

Diese Integration liest automatisch alle relevanten Sensordaten aus deiner Wärmepumpe (Temperaturen, Leistung, Laufzeit) und ermöglicht es, Heizkreis-Modi und Sollwerte direkt aus Home Assistant heraus zu steuern — ganz ohne externe Skripte oder manuelle Modbus-Befehle.

---

## Voraussetzungen

- Home Assistant (empfohlen: 2024.1.0 oder neuer)
- HACS installiert ([Anleitung](https://hacs.xyz/docs/setup/download))
- Ovum MIRA Wärmepumpe mit **LSM Display** und **Modbus TCP aktiviert**
- Die Wärmepumpe muss im selben Netzwerk wie Home Assistant erreichbar sein
- Den **Modbus Login-Code** der Anlage (steht am MIRA-Display unter Einstellungen → Modbus)

---

## Installation über HACS (empfohlen)

1. HACS öffnen → oben rechts auf die **drei Punkte (⋮)** klicken → **Benutzerdefinierte Repositories**
2. URL eintragen: `https://github.com/AlextheRand/Ovum_ACP`
3. Kategorie: **Integration** auswählen → **Hinzufügen**
4. Die Integration **Ovum ACP** erscheint jetzt in der Liste → **Herunterladen**
5. Home Assistant neu starten

---

## Manuelle Installation

Falls du HACS nicht verwendest:

1. Den Ordner `custom_components/ovum_acp` aus diesem Repository herunterladen
2. Den Ordner in dein Home Assistant Konfigurationsverzeichnis kopieren: `/config/custom_components/ovum_acp/`
3. Home Assistant neu starten

---

## Einrichtung in Home Assistant

1. **Einstellungen → Geräte & Dienste → + Integration hinzufügen**
2. Nach **Ovum ACP** suchen und auswählen
3. Den Einrichtungsassistenten Schritt für Schritt ausfüllen:

### Schritt 1 — Verbindung

| Feld | Beispiel | Erklärung |
|---|---|---|
| IP-Adresse | `192.168.178.82` | IP deiner MIRA-Steuerung im Heimnetz |
| Port | `502` | Standard-Modbus-Port, normalerweise nicht ändern |
| Login-Code | `1` | Steht am LSM-Display unter Einstellungen → Modbus |

### Schritt 2 — Datentiefe (Level)

Bestimmt, wie viele Register ausgelesen werden:

| Level | Beschreibung |
|---|---|
| **L1** | Grunddaten: Temperaturen, Leistung, Laufzeit, Sollwerte — für die meisten Nutzer ausreichend |
| **L2** | Zusätzlich: Raumsoll, Heizgrenzen, erweiterte Status |
| **L3** | Vollständig: alle BMS-Register (nur für Experten / Servicetechniker) |

### Schritt 3 — Heizkreise

Anzahl der konfigurierten Heizkreise (1–4). Steht in der Dokumentation deiner Anlage oder am Display unter Heizkreis-Konfiguration.

### Schritt 4 — Heizkreis-Typen

Pro Heizkreis den Typ auswählen:
- **Fußbodenheizung** — Niedertemperatur, flache Heizkurve
- **Heizkörper** — Hochtemperatur, steilere Heizkurve
- **Pool**
- **AUS** — Heizkreis deaktiviert

### Schritt 5 — Kühlung

Aktiviere diese Option nur, wenn deine Anlage für Kühlung ausgerüstet ist (Passive Cooling / Active Cooling). Im Zweifelsfall: **Nein**.

### Schritt 6 — Anzahl Wärmepumpenmodule (WPM)

Die meisten Anlagen haben **1 WPM**. Mehrverdichter-Anlagen können 2 oder mehr haben (steht im Serviceprotokoll der Anlage).

---

## Was die Integration anlegt

Nach der Einrichtung erscheinen automatisch Sensoren und Steuerelemente unter dem Gerät **Ovum MIRA**:

### Sensoren (Auswahl)

| Name | Beschreibung |
|---|---|
| Außentemperatur | Aktuelle Außentemperatur (°C) |
| WW Speicher oben | Warmwassertemperatur oben im Speicher (°C) |
| WW Speicher unten | Warmwassertemperatur unten im Speicher (°C) |
| Heizungspuffer oben | Pufferspeicher Temperatur oben (°C) |
| Heizungspuffer unten | Pufferspeicher Temperatur unten (°C) |
| Aufnahmeleistung | Aktuelle elektrische Leistungsaufnahme des Verdichters (W) |
| Wärmeleistung | Aktuell erzeugte Wärmeleistung (W) |
| Betriebsstunden | Gesamte Verdichter-Laufzeit (h) |
| Eintrittstemperatur | Vorlauftemperatur am WPM (°C) |
| Austrittstemperatur | Rücklauftemperatur am WPM (°C) |

### Steuerelemente

| Name | Typ | Funktion |
|---|---|---|
| WW Solltemperatur | Zahl | Warmwasser-Zieltemperatur setzen (z. B. 45–55 °C) |
| HK1 Modus | Auswahl | Heizkreis 1 auf AUS / AUTOMATIK / WINTER / SOMMER schalten |
| HK2 Modus | Auswahl | Heizkreis 2 umschalten |
| EMS PV-Status | Auswahl | PV-Überschuss-Signal: Neutral / Erhöhen / Reduzieren |

> **Hinweis:** Nicht alle Sensoren sind bei jeder Anlage verkabelt. Sensoren ohne physischen Fühler zeigen den Status **Nicht verfügbar** — das ist kein Fehler.

---

## Häufige Probleme

**Integration wird nicht gefunden / "Verbindung fehlgeschlagen"**
- Prüfen ob die IP-Adresse korrekt ist (am Router nachschauen oder am MIRA-Display)
- Prüfen ob Modbus TCP am MIRA-Display aktiviert ist (Einstellungen → Kommunikation → Modbus)
- Prüfen ob Port 502 nicht durch eine Firewall blockiert wird

**Login-Code ist falsch**
- Den Code am LSM-Display ablesen: Einstellungen → Modbus → Zugangscode
- Standardwert ist meist `1` oder `0`

**Sensor zeigt "Nicht verfügbar"**
- Der Temperaturfühler an dieser Position ist nicht angeschlossen — normal bei teilbestückten Anlagen

---

## Unterstützte Hardware

- Ovum MIRA Wärmepumpen mit **LSM Display**
- Modbus TCP Protokoll V1.1.x
- HSM (Hydrauliksteuermodul, Slave-Adresse 110)
- WPM (Wärmepumpenmodul, Slave-Adressen 111–118)

Andere Ovum-Modelle ohne LSM-Display oder ohne Modbus TCP werden **nicht** unterstützt.

---

## Lizenz

MIT — kostenlos nutzbar, keine Garantie, kein offizieller Ovum-Support.
