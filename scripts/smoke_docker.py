"""Vérifier l'image réelle avec des données fictives et une clé temporaire non affichée."""

import argparse
import io
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from PIL import Image, ImageDraw


def docker(*arguments, **kwargs):
    result = subprocess.run(["docker", *arguments], capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"Échec de Docker ({arguments[0]}). Vérifier le moteur et l'image.")
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="sbc-vision:local")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    identifier = "sbc-smoke-" + uuid.uuid4().hex[:12]
    volume = identifier + "-data"
    key = secrets.token_urlsafe(32)
    container_env = {**os.environ, "SBC_API_KEY": key}
    checks, timings = [], {}
    limits = [
        "--read-only",
        "--tmpfs",
        "/tmp:size=64m,mode=1777",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "2g",
        "--cpus",
        "2",
    ]
    try:
        docker("volume", "create", volume)
        docker(
            "run",
            "--rm",
            *limits,
            "-v",
            f"{volume}:/app/data/processed",
            args.image,
            "python",
            "scripts/prepare_api_demo.py",
        )
        docker(
            "run",
            "-d",
            "--name",
            identifier,
            *limits,
            "-p",
            "127.0.0.1::8000",
            "-v",
            f"{volume}:/app/data/processed",
            "--env",
            "SBC_API_KEY",
            "-e",
            "SBC_ACCESS_MODE=shared",
            "-e",
            "SBC_PERCEPTION_MODE=lab-colors",
            "-e",
            "SBC_ENGINE_MODE=demo",
            "-e",
            "SBC_ENGINE_DATABASE=/app/data/processed/api_demo/inventory.sqlite3",
            "-e",
            "SBC_ENGINE_CHALLENGE=/app/data/processed/api_demo/challenge.json",
            args.image,
            env=container_env,
        )

        def container_base():
            binding = json.loads(
                docker("inspect", "--format", "{{json .NetworkSettings.Ports}}", identifier)
            )
            return f"http://127.0.0.1:{binding['8000/tcp'][0]['HostPort']}"

        base = container_base()

        def request(path, *, method="GET", body=None, authenticated=True, media="application/json"):
            headers = {"Authorization": f"Bearer {key}"} if authenticated else {}
            if body is not None:
                headers["Content-Type"] = media
            req = urllib.request.Request(base + path, data=body, method=method, headers=headers)
            before = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=15) as response:
                    result = (response.status, json.loads(response.read()))
            except urllib.error.HTTPError as error:
                result = (error.code, json.loads(error.read()))
            timings.setdefault(path.split("?")[0], []).append(
                round((time.perf_counter() - before) * 1000, 2)
            )
            return result

        for _attempt in range(60):
            try:
                if request("/health", authenticated=False)[0] == 200:
                    break
            except (OSError, ValueError):
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Le conteneur ne devient pas sain.")
        checks.append("santé publique")
        assert request("/api/v1/sbc/workspace", authenticated=False)[0] == 401
        checks.append("refus sans clé")
        status, capabilities = request("/api/v1/capabilities")
        assert (
            status == 200
            and capabilities["solver"]
            and capabilities["perception_mode"] == "lab-colors"
        )
        assert docker("exec", identifier, "id", "-u") == "10001"
        assert "tesseract" in docker("exec", identifier, "tesseract", "--version").lower()
        checks.extend(["solveur disponible", "Tesseract installé", "utilisateur non root"])
        image = Image.new("RGB", (640, 270), "white")
        ImageDraw.Draw(image).rectangle((48, 174, 279, 231), fill=(24, 122, 211))
        png = io.BytesIO()
        image.save(png, format="PNG")
        status, perception = request(
            "/api/v1/perception/analyze?capture_id=docker-smoke",
            method="POST",
            body=png.getvalue(),
            media="image/png",
        )
        assert status == 200 and perception["elements"][0]["id"] == "lab-select"
        checks.append("PNG vers JSON dans le conteneur")
        status, workspace = request("/api/v1/sbc/workspace")
        assert status == 200 and len(workspace["items"]) == 3
        status, solution = request(
            "/api/v1/sbc/solve",
            method="POST",
            body=json.dumps(
                {
                    "expected_revision": workspace["revision"],
                    "budget": 2000,
                }
            ).encode(),
        )
        assert status == 200 and solution["report"]["verification"]["valid"]
        assert solution["report"]["solution"]["total_cost"] == 2100
        checks.append("calcul CP-SAT vérifié")
        status, updated = request(
            "/api/v1/sbc/protections",
            method="PUT",
            body=json.dumps(
                {
                    "instance_id": "demo-002",
                    "protected": True,
                    "expected_revision": workspace["revision"],
                }
            ).encode(),
        )
        assert status == 200 and updated["revision"] != workspace["revision"]
        docker(
            "run",
            "--rm",
            *limits,
            "-v",
            f"{volume}:/app/data/processed",
            args.image,
            "python",
            "scripts/prepare_api_demo.py",
            "--if-missing",
        )
        docker("restart", identifier)
        # Docker peut réattribuer le port éphémère au redémarrage.
        base = container_base()
        for _attempt in range(60):
            try:
                status, persisted = request("/api/v1/sbc/workspace")
                if status == 200:
                    break
            except (OSError, ValueError):
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Le conteneur ne redémarre pas.")
        assert next(item for item in persisted["items"] if item["key"] == "club:demo-002")[
            "protected"
        ]
        checks.append("protection conservée après réinitialisation conditionnelle et redémarrage")
        log_result = subprocess.run(["docker", "logs", identifier], capture_output=True, text=True)
        logs = log_result.stdout + log_result.stderr
        assert key not in logs and "docker-smoke" not in logs
        checks.append("pas de clé ni d’identifiant de capture dans les logs")
        report = {
            "data_kind": "synthetic",
            "image": args.image,
            "image_id": docker("image", "inspect", "--format", "{{.Id}}", args.image),
            "checks": checks,
            "latency_ms": timings,
            "note": "Mesures locales de test, pas un engagement de latence cloud.",
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        subprocess.run(["docker", "rm", "-f", identifier], capture_output=True)
        subprocess.run(["docker", "volume", "rm", volume], capture_output=True)


if __name__ == "__main__":
    main()
