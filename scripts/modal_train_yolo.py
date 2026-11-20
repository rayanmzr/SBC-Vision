"""Approche B : affiner YOLO26 sur Modal et tracer le run dans MLflow.

Prérequis : le client Modal (`pip install modal`, puis `modal token new`).

Données : un export de `sbc_vision.perception.datasets.export_yolo`, envoyé une fois dans le
volume Modal sous forme d'une seule archive (lire 40 000 petits fichiers du volume prend plus
d'une heure, une archive d'un gigaoctet quelques secondes) :

    modal volume create sbc-vision-data
    tar -cf webui-desktop.tar -C <dossier parent de l'export> webui-desktop
    modal volume put sbc-vision-data webui-desktop.tar /datasets/webui-desktop.tar

Entraînement (le GPU se choisit avec SBC_TRAIN_GPU, L40S par défaut) :

    modal run scripts/modal_train_yolo.py --dataset webui-desktop \
        --run-name yolo26s-webui-1280-s0 --model yolo26s.pt --epochs 60 --imgsz 1280

Le run MLflow porte le commit Git, l'export de données, les paramètres d'Ultralytics, les
métriques par époque et les poids. Son suivi est une base SQLite rangée dans le volume
(`/mlflow/mlflow.db`, un entraînement à la fois : chacun la recopie en entier en fin de run), ses
fichiers sous `/mlflow/artifacts`. Récupération locale :

    modal volume get sbc-vision-data /mlflow ./mlflow
    mlflow ui --backend-store-uri sqlite:///mlflow/mlflow.db
"""

import json
import os
import subprocess
from pathlib import Path

import modal

APP = modal.App("sbc-vision-yolo")
VOLUME = modal.Volume.from_name("sbc-vision-data", create_if_missing=True)
IMAGE = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install("ultralytics==8.4.200", "mlflow==3.17.0", "onnx==1.19.1", "onnxslim")
)
GPU = os.environ.get("SBC_TRAIN_GPU", "L40S")
MLFLOW = Path("/vol/mlflow")
EXPERIMENT = "sbc-vision-detector"


def _git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _source_snapshot() -> bytes:
    """Archive des sources du dépôt (suivies et nouvelles), jointe au run pour le reproduire
    même avant commit."""
    import io
    import tarfile

    names = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"], text=True
    ).split()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in names:
            if Path(name).is_file():  # un fichier supprimé mais encore suivi n'existe plus
                archive.add(name)
    return buffer.getvalue()


def _git_dirty() -> bool:
    return bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())


@APP.function(
    image=IMAGE,
    gpu=GPU,
    cpu=12,
    memory=48 * 1024,
    timeout=10 * 3600,
    volumes={"/vol": VOLUME},
)
def train(
    dataset: str,
    run_name: str,
    model: str,
    epochs: int,
    imgsz: int,
    batch: int,
    seed: int,
    git_commit: str,
    git_dirty: bool,
    source_snapshot: bytes,
    overrides: dict,
) -> dict:
    import shutil

    import mlflow
    from ultralytics import settings

    # Lecture aléatoire intensive : l'archive est extraite sur le disque local du conteneur.
    root = Path("/tmp/datasets")
    root.mkdir(parents=True)
    subprocess.run(["tar", "-xf", f"/vol/datasets/{dataset}.tar", "-C", str(root)], check=True)
    local = root / dataset
    export = json.loads((local / "export.json").read_text())

    # SQLite ne doit pas vivre sur un volume réseau : la base est copiée sur le disque local du
    # conteneur pendant le run, puis remise dans le volume, même si l'entraînement échoue.
    database = Path("/tmp/mlflow.db")
    if (MLFLOW / "mlflow.db").exists():
        shutil.copy2(MLFLOW / "mlflow.db", database)
    tracking_uri = f"sqlite:///{database}"
    os.environ["MLFLOW_TRACKING_URI"] = tracking_uri
    os.environ["MLFLOW_EXPERIMENT_NAME"] = EXPERIMENT
    os.environ["MLFLOW_KEEP_RUN_ACTIVE"] = "True"
    settings.update({"mlflow": True})
    mlflow.set_tracking_uri(tracking_uri)
    if mlflow.get_experiment_by_name(EXPERIMENT) is None:
        mlflow.create_experiment(EXPERIMENT, artifact_location=str(MLFLOW / "artifacts"))
    mlflow.set_experiment(EXPERIMENT)
    try:
        return _train_run(
            local,
            export,
            run_name,
            model,
            epochs,
            imgsz,
            batch,
            seed,
            git_commit,
            git_dirty,
            source_snapshot,
            overrides,
        )
    finally:
        MLFLOW.mkdir(parents=True, exist_ok=True)
        shutil.copy2(database, MLFLOW / "mlflow.db")
        VOLUME.commit()


def _train_run(
    local: Path,
    export: dict,
    run_name: str,
    model: str,
    epochs: int,
    imgsz: int,
    batch: int,
    seed: int,
    git_commit: str,
    git_dirty: bool,
    source_snapshot: bytes,
    overrides: dict,
) -> dict:
    import mlflow
    from ultralytics import YOLO

    with mlflow.start_run(run_name=run_name) as run:
        mlflow.set_tags(
            {
                "approach": "B-yolo",
                "git_commit": git_commit,
                "git_dirty": str(git_dirty),
                "dataset": local.name,
                "gpu": GPU,
            }
        )
        mlflow.log_dict(export, "dataset/export.json")
        snapshot = Path("/tmp/source.tar.gz")
        snapshot.write_bytes(source_snapshot)
        mlflow.log_artifact(str(snapshot), "source")
        arguments = {
            "data": str(local / "data.yaml"),
            "epochs": epochs,
            "imgsz": imgsz,
            "batch": batch,
            "seed": seed,
            "deterministic": True,
            "project": "/vol/runs",
            "name": run_name,
            "exist_ok": False,
            "workers": 10,
            "fliplr": 0.0,  # un texte retourné n'existe pas dans une interface
            "patience": 20,
            "cos_lr": True,
            "plots": True,
            **overrides,
        }
        detector = YOLO(model)
        detector.train(**arguments)
        trainer = detector.trainer
        metrics = {k: float(v) for k, v in trainer.metrics.items()}
        best = Path(trainer.best)
        onnx_path = YOLO(str(best)).export(format="onnx", imgsz=imgsz, dynamic=False, simplify=True)
        # Ultralytics a déjà joint au run son dossier (courbes, results.csv, poids .pt) ; seul
        # l'ONNX, exporté après, manque.
        mlflow.log_artifact(onnx_path, "weights")
        return {
            "run_id": run.info.run_id,
            "save_dir": str(trainer.save_dir),
            "best": str(best),
            "onnx": onnx_path,
            "metrics": metrics,
        }


@APP.local_entrypoint()
def main(
    dataset: str,
    run_name: str,
    model: str = "yolo26s.pt",
    epochs: int = 60,
    imgsz: int = 1280,
    batch: int = 16,
    seed: int = 0,
    overrides: str = "{}",
):
    result = train.remote(
        dataset,
        run_name,
        model,
        epochs,
        imgsz,
        batch,
        seed,
        _git_commit(),
        _git_dirty(),
        _source_snapshot(),
        json.loads(overrides),
    )
    print(json.dumps(result, indent=2))
