# Esecuzione del progetto

Dalla directory principale della repository, con le dipendenze di `docs/requirements.txt`, FFmpeg e CUDA/NVENC disponibili:

```bash
# Download e preparazione dei due filmati a telecamera fissa.
python3 -m src.prepare_urbantracker

# Le impostazioni dei riferimenti già prodotti sono registrate nei metadati.
python3 -m src.detect_and_track --sequences urban_sherbrooke --classes 2 --imgsz 960 --device 0
python3 -m src.detect_and_track --sequences urban_rene --classes 2 --imgsz 960 --half --batch 8 --device 0

# Confronto sui riferimenti salvati: non richiede una nuova inferenza YOLO.
python3 -m src.benchmark
python3 -m src.course_experiments
python3 -m src.passage_clips
python3 -m src.course_report --verify-clips

# Test.
python3 -m unittest discover -s tests -v
```

Il tracking esporta le bounding box osservate per ricavare le posizioni e selezionare i passaggi. La ricostruzione riguarda le traiettorie; la cinematica si valuta con `python3 -m src.kinematic_benchmark` dopo la proiezione metrica.

## Calibrazione e confronto in metri

```bash
# Controlla la disponibilità delle calibrazioni, senza aprire finestre.
python3 -m src.calibrate_ground --status

# Apri l'editor e pubblica le corrispondenze scelte nell'immagine e sulla mappa.
python3 -m src.calibrate_ground

# Dopo la pubblicazione dei due documenti JSON:
python3 -m src.project_ground
python3 -m src.metric_benchmark
python3 -m src.ground_report
```

Le istruzioni per scegliere i punti e la descrizione delle unità sono in [calibrazione.md](calibrazione.md). Gli script metrici richiedono calibrazioni reali e compatibili: non sostituiscono coordinate mancanti con valori fittizi.

Il confronto sulle due calibrazioni già pubblicate è disponibile in [reports/generated/ground/RESULTS.md](reports/generated/ground/RESULTS.md).

## Cartelle

| Percorso | Contenuto |
|---|---|
| `data/urbantracker/raw/` | Video originali e annotazioni originali conservate |
| `data/urbantracker/prepared/` | Timestamp, manifest e anteprime |
| `data/urbantracker/tracks/` | Riferimenti YOLO/ByteTrack |
| `data/urbantracker/masks/full_video.json` | Maschere condivise |
| `data/urbantracker/results/course/` | Confronto degli interpolatori in pixel |
| `calibration/` | Calibrazioni manuali per camera e punti indipendenti di verifica |
| `data/urbantracker/georeferenced/` | Coordinate metriche/geografiche, validità e griglia calibrata |
| `data/urbantracker/results/ground/` | Confronto metrico e baseline in pixel sugli stessi casi validi |
| `reports/generated/course/` | Grafici, esperimenti sintetici e dodici clip |
| `reports/latex/` | Relazione sintetica, PDF e pacchetto autonomo |

La fonte dei video è [Urban Tracker](https://www.jpjodoin.com/urbantracker/dataset.html): Jodoin, Bilodeau e Saunier, WACV 2014. La georeferenziazione manuale non equivale a disporre di un GPS indipendente per ogni automobile.
