# Ovum ACP — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Home Assistant Custom Integration für Ovum MIRA Wärmepumpen (ACP-Protokoll, Modbus TCP).

## Features

- **Vollständige Modbus-TCP-Anbindung** ohne externe Skripte
- **Automatischer Login** (FC16 auf HSM + WPM-Slaves, alle 25 Minuten erneuert)
- **Sensor-Entities** für alle relevanten Register (Temperaturen, Leistung, Status, Laufzeit)
- **Select-Entities** zum Schreiben von Heizkreis-Modi, EMS-PV-Status, WW-Schalter
- **Number-Entities** für Sollwerte (WW-Soll, Raumsoll, Puffer-Soll PV)
- **Config Flow** mit 6 Schritten: IP/Port, Level, Heizkreise, HK-Typen, Kühlung, WPM-Anzahl
- HACS-kompatibel

## Unterstützte Hardware

- Ovum MIRA Wärmepumpen (LSM Display, Modbus TCP V1.1.x)
- HSM (Hydraulikeinheit, Slave 110)
- WPM (Wärmepumpenmodul, Slave 111–118)

## Installation (HACS)

1. HACS → Integrationen → ⋮ → Benutzerdefinierte Repositories
2. URL: `https://github.com/alexander-m-py/ovum-acp-ha`
3. Kategorie: Integration
4. Hinzufügen → Ovum ACP installieren

## Manuelle Installation

```bash
cp -r custom_components/ovum_acp /config/custom_components/
```

HA neu starten, dann unter **Einstellungen → Integrationen → + Hinzufügen → Ovum ACP**.

## Konfiguration

| Feld | Standard | Beschreibung |
|---|---|---|
| Host | 192.168.178.82 | IP der MIRA-Steuerung |
| Port | 502 | Modbus-TCP-Port |
| Login-Code | 1 | 32-Bit Login-Code (siehe MIRA-Display) |
| Level | L1 | Datentiefe: L1 (Start), L2 (Plus), L3 (BMS) |
| Heizkreise | 2 | Anzahl HK (1–4) |
| HK-Typen | Fußbodenheizung | Pro HK: AUS / Fußbodenheizung / Heizkörper / Pool |
| Kühlung | Nein | Kühl-Register aktivieren |
| WPM-Anzahl | 1 | Anzahl Wärmepumpenmodule (1–8) |

## Entities (Auswahl, Level L1)

| Entity | Typ | Beschreibung |
|---|---|---|
| `sensor.ovum_mira_aussentemperatur` | Sensor | Außentemperatur (°C) |
| `sensor.ovum_mira_ww_temp_oben` | Sensor | WW-Speicher oben (°C) |
| `sensor.ovum_mira_puffer_temp_unten` | Sensor | Heizungspuffer unten (°C) |
| `sensor.ovum_mira_wpm1_aufnahmeleistung` | Sensor | Elektrische Aufnahme (W) |
| `sensor.ovum_mira_wpm1_waermeleistung` | Sensor | Wärmeleistung (W) |
| `sensor.ovum_mira_wpm1_betriebsstunden` | Sensor | Verdichter-Laufzeit (h) |
| `select.ovum_mira_hk1_mode` | Select | HK1 Modus (AUS/AUTOMATIK/WINTER/SOMMER) |
| `select.ovum_mira_ems_pvstatus` | Select | EMS PV-Status (Neutral/Erhöhen/Reduzieren) |
| `number.ovum_mira_ww_soll` | Number | WW-Solltemperatur (°C) |

## Modbus-Login

MIRA erfordert einen FC16-Login auf Adresse 101 jedes Slaves. Die Integration übernimmt das vollständig — kein externer Login-Skript notwendig. Der Login-Code steht am MIRA-Display unter Modbus-Einstellungen.

## Lizenz

MIT
