# regenery Kapa-Planung

Kapazitätsplanungs-Tool als Flask-Webanwendung – Nachfolger des Excel-Gantt-Diagramms.

## Installation

```bash
cd kapa_planung
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Starten

```bash
python3 app.py
```

Beim ersten Start wird automatisch die SQLite-Datenbank `kapa.db` angelegt
(inkl. der beiden Teammitglieder Dominic Meier und Tony Freudenthal).
Danach im Browser öffnen: **http://127.0.0.1:5050**
Im lokalen Netzwerk ist die App über `http://<IP-Adresse-des-Servers>:5050` erreichbar.

## Funktionsweise

- **Projekt hinzufügen** (linke Seitenleiste): Name, Start-Quartal und Dauer
  in Quartalen festlegen. Jedes Projekt bekommt automatisch eine eigene Farbe.
- **Manntage eintragen**: Auf ein farbiges Feld in einem aktiven Quartal eines
  Projekts klicken – im Fenster können die Manntage für Dominic Meier und
  Tony Freudenthal für genau dieses Projekt/Quartal eingetragen werden.
- **Auslastung**: Unterhalb des Gantt-Diagramms werden pro Quartal die
  Summe der eingeplanten Manntage je Person sowie die Auslastung in %
  angezeigt. Die Gesamt-Kapazität je Quartal wird automatisch aus den
  tatsächlichen Arbeitstagen (Mo–Fr) berechnet, abzüglich der gesetzlichen
  Feiertage in Sachsen (inkl. Reformationstag und Buß- und Bettag). Beide
  Personen werden als Vollzeit (5 Tage/Woche) angenommen.
- **Heute-Button**: springt im Diagramm zum aktuellen Quartal (farblich
  hervorgehoben).
- Das Diagramm ist horizontal scrollbar und zeigt automatisch alle Quartale
  an, die von mindestens einem Projekt abgedeckt werden.

## Projektstruktur

```
kapa_planung/
  app.py                  Flask-Backend, Kapazitäts-/Quartalslogik
  requirements.txt
  templates/index.html    Seitenstruktur (Jinja2)
  static/css/style.css    Google-Calendar-Look
  static/js/app.js        Formular, Modal, AJAX-Speicherung
  kapa.db                 wird beim ersten Start automatisch erzeugt
```
