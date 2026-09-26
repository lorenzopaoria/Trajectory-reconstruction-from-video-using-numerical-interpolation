# Ricostruzione di traiettorie e calibrazione del piano stradale

**Lorenzo Maria Alberto Paoria — Matricola: 1000016111**

Progetto di Analisi Numerica, Prof. Sebastiano Boscarino.

## Obiettivi e stato

1. **Traiettoria:** ricostruire le posizioni mancanti delle auto nei video Urban Tracker con telecamera fissa. Confronto in pixel già eseguito.
2. **Georeferenziazione:** calibrazione manuale del piano stradale e confronto in metri, con esportazione latitudine/longitudine. Le due calibrazioni dell'utente sono pubblicate: primo confronto eseguito su **406 gap validi**, con griglie CSV/GeoJSON.
3. **Cinematica:** velocità, accelerazione e heading sul piano metrico, valutati sui 406 gap calibrati con riferimento a differenze finite della traiettoria completa.

Le bounding box di YOLO servono a individuare il bottom center e a visualizzare l'oggetto. Non sono grandezze da ricostruire nel progetto.

## Relazione e risultati

- **[Relazione PDF](../relazione_progetto.pdf)**
- **[Sorgente LaTeX](../reports/latex/relazione_progetto.tex)** · **[ZIP per Overleaf](../reports/latex/relazione_progetto_sorgenti.zip)**
- [Report del confronto in pixel](pixel_benchmark_results.md)
- **[Report metrico e copertura delle calibrazioni](metric_benchmark_results.md)**
- [Metodi ed esperimenti](metodi_ed_esperimenti.md)
- [Calibrazione e proiezione metrica](calibrazione.md)
- [Comandi della pipeline](esecuzione.md)

## Dataset e protocollo

Due filmati completi: **Sherbrooke (4.000 frame)** e **René-Lévesque (8.501 frame)**. Tracking YOLO11n + ByteTrack, classe automobile. Le osservazioni vengono salvate prima di nascondere i punti: costituiscono un riferimento YOLO/ByteTrack, non annotazioni fisiche esatte.

Le maschere condivise contengono gap di **3, 6, 12 e 24 frame**, con quattro nodi visibili per lato. Nessun campione nascosto in un gap può essere usato come supporto di un altro. Il confronto principale comprende **5.517 gap e otto metodi**. Le clip illustrative sono selezionate per movimento e distribuzione temporale, non per errore.

## Metodi

- Vandermonde, Lagrange, Newton;
- spline S1, S3 naturale e S3 vincolata;
- S2 come estensione della definizione generale;
- razionale Floater–Hormann come costruzione aggiuntiva della famiglia razionale;
- S3 periodica e trigonometrica su dati periodici sintetici;
- esperimenti sui nodi di Chebyshev e sul supporto di 4, 6 e 8 nodi.

Formule e terminologia derivano dalle dispense di interpolazione utilizzate
nel corso. La relazione presenta per ogni metodo una definizione breve, la
formula e il codice Python essenziale.

## Geometria

Il flusso previsto è **pixel → piano locale metrico → interpolazione → WGS84 lat/lon**. La calibrazione usa punti stradali corrispondenti nell'immagine e sulla mappa. È valida per il piano e per la zona calibrata, non per qualsiasi superficie dell'inquadratura.

Il progetto riusa GeminiPort da `~/Work/GeminiPort-Master/GeminiPort`. Supporta sia la struttura con editor standalone in `ground_geometry`, sia quella con proiettore ed editor schema v2 in `trafficdetGUI/modules`. `GroundProjector` verifica sorgente, dimensioni, preprocessing e poligono valido. L'adattatore espone esplicitamente Est/Nord in metri. Le calibrazioni sono salvate in `calibration/`.

## Esecuzione rapida sui dati già disponibili

```bash
python3 -m src.benchmark
python3 -m src.course_experiments
python3 -m src.passage_clips
python3 -m src.course_report --verify-clips
python3 -m unittest discover -s tests -v
```

Tracking e codifica video usano la GPU; i piccoli sistemi degli interpolatori sono risolti da NumPy/SciPy. Per cambiare i dati o le maschere si usano nuovi percorsi di output, mentre aggiungere metodi può riutilizzare le stesse maschere.
