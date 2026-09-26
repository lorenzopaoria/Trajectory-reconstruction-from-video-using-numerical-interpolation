# Calibrazioni del piano stradale

Questa cartella riceve dall'editor GeminiPort i documenti:

- `UrbanSherbrooke.json`
- `UrbanRene.json`

I due documenti sono stati pubblicati dall'utente: 7 punti per Sherbrooke (6 inlier) e 4 per René-Lévesque. Possono essere riaperti tramite `python3 -m src.calibrate_ground`; non contengono coordinate simulate o calibrazioni copiate da altre telecamere.

`checkpoints_template.csv` contiene soltanto l'intestazione per punti di verifica indipendenti. Copiarlo in `checkpoints.csv` e inserire punti diversi da quelli usati per il fit. Vedere [calibrazione.md](../docs/calibrazione.md).
