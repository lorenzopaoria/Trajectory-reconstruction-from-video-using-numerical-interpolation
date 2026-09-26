"""Prepare the report figures, compile locally, and package portable LaTeX sources."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
ASSETS = {
    "course_comparison.png": "reports/generated/course/course_comparison.png",
    "chebyshev_runge.png": "reports/generated/course/experiments/chebyshev_runge.png",
    "periodic.png": "reports/generated/course/experiments/periodic.png",
    "clip_rene.jpg": "reports/generated/course/clips/urban_rene_car1229_f00611.jpg",
    "calibration_coverage.png": "reports/generated/ground/calibration_coverage.png",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", help="Path to tectonic or pdflatex")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    figures = HERE / "figures"
    figures.mkdir(exist_ok=True)
    provenance = []
    for name, relative in ASSETS.items():
        source = PROJECT / relative
        if not source.is_file():
            raise FileNotFoundError(f"Missing report figure: {source}")
        target = figures / name
        shutil.copy2(source, target)
        provenance.append({"file": "figures/" + name, "source": relative,
                           "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    (HERE / "figure_sources.json").write_text(json.dumps(provenance, indent=2) + "\n")
    if not args.prepare_only:
        cached_engine = PROJECT / ".cache" / "tools" / "tectonic-0.17.0" / "tectonic"
        engine = (args.engine or shutil.which("tectonic") or shutil.which("pdflatex")
                  or (str(cached_engine) if cached_engine.is_file() else None))
        if not engine:
            parser.error("Install tectonic/pdflatex or specify --engine; figures have been prepared.")
        source = "relazione_progetto.tex"
        if engine and Path(engine).is_file():
            engine = str(Path(engine).resolve())
        environment = dict(os.environ)
        environment.setdefault("XDG_CACHE_HOME", str(PROJECT / ".cache"))
        if "tectonic" in Path(engine).name:
            subprocess.run([engine, "--keep-logs", source], cwd=HERE, env=environment, check=True)
        else:
            for _ in range(3):
                subprocess.run([engine, "-interaction=nonstopmode", "-halt-on-error", source], cwd=HERE, check=True)
        root_pdf = PROJECT / "relazione_progetto.pdf"
        shutil.copy2(HERE / "relazione_progetto.pdf", root_pdf)
    archive = HERE / "relazione_progetto_sorgenti.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in ("relazione_progetto.tex", "README.md", "figure_sources.json"):
            bundle.write(HERE / name, name)
        for name in ASSETS:
            bundle.write(figures / name, "figures/" + name)
    print(f"LaTeX: {HERE / 'relazione_progetto.tex'}")
    print(f"Sources: {archive}")
    if not args.prepare_only:
        print(f"PDF: {PROJECT / 'relazione_progetto.pdf'}")


if __name__ == "__main__":
    main()
