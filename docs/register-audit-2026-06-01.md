# Registerabgleich Start und Plus

Grundlage: vom Repository-Eigentümer bereitgestellte Registertabellen,
Tabellendatum 2026-06-01. Adressen sind nullbasiert; „Register“ ist die
einsbasierte Darstellung. Es wurden keine Testwerte in die Anlage geschrieben.

## Korrekturen in 0.4.2

- EMS Netz/WR/Soll-Leistung: signed INT32, je zwei Wörter ab 55072/55074/55076;
  Schreiben mit FC16 statt einzelner FC06-Wörter. Negative Netzleistung ist Einspeisung.
- Heizkreistyp: Keiner/Ungeregelt/Rücklauf/Gemischt/Cube direkt. Cube direkt nur
  für HK1 konfigurierbar; Typregister bleiben nur lesbar.
- HK1–4 PV-Offsets sind schreibbar: Plus 0…25 K, Minus −25…0 K.
- Raumsoll Heizen/Kühlen und Urlaubsvorlauf: 0…50 °C; Heizgrenze 0…100 °C.
  Urlaubsvorlauf wird als Zahl, nicht als AUS/EIN-Auswahl dargestellt.
- WW Soll/PV Soll beginnen bei 0 °C statt 10 °C.
- HK1 Raum-Isttemperatur 56152 ist bereits Start; HK2 Raum-Ist und HK3/4 sind Plus.
- Systemname und Seriennummer sind Text mit zehn Registern, keine INT16-Zahl.
  Ergänzt: System-Warmwasser/Puffertyp und WPM-Anforderung in Prozent.
- Frostschutz-Sollwerte unter dem manuellen Schreibbereich bleiben lesbar.
- Ungültige Bool-Antworten werden nicht mehr als EIN interpretiert.
- Fehlerprotokollierung meldet Lesefehler einmal und danach die Wiederherstellung.
- Leseabfragen überbrücken keine undokumentierten Adresslücken mehr. Eine
  Nur-Lese-Prüfung bestätigte Modbus-Ausnahme 02 beim übergreifenden Block
  55070…55085; dadurch können sonst auch gültige EMS-Werte verloren gehen.
  Die korrigierte Aufteilung wurde anschließend mit 22 Nur-Lese-Abfragen
  geprüft: keine Modbus-Ausnahmen.

## Bewusst begrenzte Schreibfreigaben / offene Dokumentationsfragen

- HK1/2 ACTUALVALUE steht in der Tabelle auf RW. Die Integration lässt gemessene
  Isttemperaturen weiterhin nur lesen, um keine Sensorersatzwerte zu injizieren.
- Für HK1/2 DESIREDTEMP nennt die Tabelle keinen Schreibbereich. Der bisherige
  manuelle Bereich 10…75 °C bleibt als Integrationsgrenze bestehen, gilt aber
  nicht mehr als Filter für den aktuellen Sollwert. HK3/4 DESIREDTEMP ist RO.
- HSM_PVENABLE_* nennt gleichzeitig s16 und zwei Register. Die bestehende
  Dekodierung des ersten Wortes bleibt bis zur Klärung unverändert; keine
  ungeprüfte Umstellung auf s32. Dieser Punkt ist noch nicht vollständig abgeglichen.
- Die Integration aktiviert keine Modbus-Lizenz und ändert keine PV-Quellenwahl.
  EMS-Leistungsvorgaben wirken nur bei passender Quellenwahl am Gerät.

## Migration

Bestehende Entity-IDs der EMS-Leistungsvorgaben bleiben erhalten. Für PV-Offsets
und Urlaubsvorlauftemperaturen entstehen Number-Entities statt der bisherigen
Sensor-/Select-Entities. Referenzen außerhalb der Integration müssen ggf.
angepasst werden; alte Registry-Einträge werden nicht automatisch gelöscht.
System-Seriennummern wechseln vom falschen Zahlformat auf Text.

## HK3-Befund vor Deployment

Eine direkte FC3-Leseabfrage an HSM/110 ab 56070 ergab:
`65535, 32767, 32767, 32704, 0, 32704, 0, 65535`.
Typ und Modus entsprechen −1, Soll und Ist IEEE-NaN. Die Soll-/Ist-Adressen
56073/56075 stimmen mit der Tabelle überein. Das beweist ungültige Modbus-
Antworten, nicht einen Fühlerdefekt oder eine fehlende Lizenz. Ursache offen.
