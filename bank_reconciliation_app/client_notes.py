"""Persistent, editable client rules stored as UTF-8 CSV."""

import csv
from datetime import datetime, timezone
from pathlib import Path
import os
import tempfile
from threading import RLock


NOTES_PATH = Path(__file__).resolve().parent / "file" / "client_notes.csv"
FIELDS = ["cliente", "notas", "atualizado_em_utc"]
_LOCK = RLock()


def read_notes(path=None):
    path = Path(path) if path is not None else NOTES_PATH
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != FIELDS:
            raise ValueError("O CSV de notas não tem as colunas esperadas.")
        result = {}
        names = set()
        for row in reader:
            name = row["cliente"].strip()
            if not name or name.casefold() in names or None in row or row["notas"] is None:
                raise ValueError("O CSV contém clientes duplicados ou registos inválidos.")
            names.add(name.casefold())
            result[name] = row
        return result


def save_notes(client, notes, path=None):
    client = client.strip()
    if not client:
        raise ValueError("Indique o nome do cliente.")
    path = Path(path) if path is not None else NOTES_PATH
    with _LOCK:
        records = read_notes(path)
        client = next((name for name in records if name.casefold() == client.casefold()), client)
        records[client] = {"cliente": client, "notas": notes,
                           "atualizado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8-sig", newline="", dir=path.parent,
                                             prefix=".client_notes_", suffix=".csv", delete=False) as file:
                temporary = file.name
                writer = csv.DictWriter(file, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(records[name] for name in sorted(records, key=str.casefold))
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
    return client
