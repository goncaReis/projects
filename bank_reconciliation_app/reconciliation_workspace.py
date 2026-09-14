"""Workbook-backed reconciliation state, independent of the Streamlit interface."""

from datetime import datetime, timezone
from io import BytesIO
import json
from uuid import uuid4

import pandas as pd


REQUIRED = ["Data", "Descrição", "Valor"]
SIDES = ("CNT", "BANCO")
HISTORY_COLUMNS = ["Evento", "DataHoraUTC", "Acao", "Ordem", "Origem", "MovimentoID", "Nota"]
RESERVED = {"Ver", "index", "Index", "ordem", "nota", "Tipo", "#", "DateDiff"}


def positive_integer(value, label):
    try:
        number = float(value)
        if not number.is_integer() or number < 1:
            raise ValueError
        return int(number)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label}: é necessário um número inteiro positivo.") from None


def unique_column(base, occupied):
    name = base
    while name in occupied:
        name += "_"
    occupied.add(name)
    return name


def prepared(frame):
    result = frame.copy(deep=True)
    if result.empty:
        result["Data"] = pd.Series(index=result.index, dtype=object)
        result["Valor"] = pd.Series(index=result.index, dtype=float)
        return result
    result["Data"] = pd.to_datetime(result["Data"], dayfirst=True, errors="coerce", format="mixed").dt.date
    result["Valor"] = pd.to_numeric(result["Valor"], errors="coerce").round(2)
    invalid = result["Data"].isna() | result["Valor"].isna() | ~result["Valor"].between(-float("inf"), float("inf"), inclusive="neither")
    if invalid.any():
        raise ValueError("Existem movimentos com Data ou Valor inválidos. Corrija o ficheiro antes de continuar.")
    result["Descrição"] = result["Descrição"].fillna("").astype(str)
    return result


class ReconciliationWorkspace:
    def __init__(self):
        self.sources = {}
        self.pending = {}
        self.matches = {}
        self.history = []
        self.next_id = 1
        self.settings = {}
        self.metadata = {}
        self.display_names = {}
        self.restored = False

    @classmethod
    def read(cls, file):
        # Object dtype and no NA inference preserve text identifiers and literal "NA".
        sheets = pd.read_excel(file, sheet_name=None, dtype=object, keep_default_na=False)
        return cls.from_sheets(sheets)

    @classmethod
    def from_sheets(cls, sheets):
        self = cls()
        if any(side not in sheets for side in SIDES):
            raise ValueError("O ficheiro deve conter as folhas CNT e BANCO.")
        if ("MATCH CNT" in sheets) != ("MATCH BANCO" in sheets):
            raise ValueError("O ficheiro deve conter ambas as folhas MATCH CNT e MATCH BANCO.")
        config = {}
        if "CONFIGURACAO" in sheets:
            frame = sheets["CONFIGURACAO"]
            if not {"Chave", "Valor"}.issubset(frame.columns):
                raise ValueError("A folha CONFIGURACAO não tem o formato esperado.")
            config = dict(zip(frame["Chave"], frame["Valor"]))
            if config.get("aplicacao") != "reconciliacoes" or str(config.get("versao")) != "1":
                raise ValueError("Versão do ficheiro de reconciliação não suportada.")
        if config:
            self.restored = True
            self.settings = json.loads(config["definicoes"])
            if "HISTORICO" not in sheets or not set(HISTORY_COLUMNS).issubset(sheets["HISTORICO"].columns):
                raise ValueError("A folha HISTORICO está em falta ou é inválida.")
            self.history = sheets["HISTORICO"].to_dict("records")
            self.next_id = positive_integer(config["proximo_id"], "Próximo ID")

        for side in SIDES:
            pending = sheets[side].copy()
            matched = sheets.get("MATCH " + side, pd.DataFrame()).copy()
            if config:
                meta = json.loads(config["colunas_" + side])
                original_columns = json.loads(config["originais_" + side])
                # Include columns users added since the preceding download.
                original_columns += [c for f in (pending, matched) for c in f.columns
                                     if c not in original_columns and c not in meta.values()]
                original_columns = list(dict.fromkeys(original_columns))
                for frame in (pending, matched):
                    if meta["row_id"] not in frame:
                        raise ValueError(f"{side}: falta a coluna de identificação dos movimentos.")
                if not matched.empty and any(meta[k] not in matched for k in ("match_id", "note")):
                    raise ValueError(f"{side}: faltam os dados das reconciliações anteriores.")
            else:
                original_columns = list(pending.columns)
                original_columns += [c for c in matched.columns if c not in original_columns and c not in ("ordem", "nota")]
                occupied = set(original_columns)
                meta = {"row_id": unique_column("__recon_movimento_id", occupied),
                        "match_id": unique_column("ordem", occupied),
                        "note": unique_column("nota", occupied)}
                if not matched.empty:
                    if "ordem" not in matched:
                        raise ValueError(f"MATCH {side}: falta a coluna ordem.")
                    matched = matched.rename(columns={"ordem": meta["match_id"], "nota": meta["note"]})
            if not set(REQUIRED).issubset(pending.columns):
                raise ValueError(f"{side}: são necessárias as colunas Data, Descrição e Valor.")
            if not matched.empty and not set(REQUIRED).issubset(matched.columns):
                raise ValueError(f"MATCH {side}: são necessárias as colunas Data, Descrição e Valor.")
            self.metadata[side] = meta
            rows, ids, pending_ids = [], [], []
            seen_ids = set()
            for is_matched, frame in ((False, pending), (True, matched)):
                for record in frame.to_dict("records"):
                    if all(pd.isna(v) or v == "" for v in record.values()):
                        continue
                    row_id = record.get(meta["row_id"], "") if config else ""
                    row_id = str(row_id) if pd.notna(row_id) and row_id != "" else uuid4().hex
                    if row_id in seen_ids:
                        raise ValueError(f"{side}: identificador de movimento duplicado ({row_id}).")
                    seen_ids.add(row_id)
                    ids.append(row_id)
                    rows.append({c: record.get(c, "") for c in original_columns})
                    if is_matched:
                        order = positive_integer(record.get(meta["match_id"]), f"MATCH {side}: ordem")
                        match = self.matches.setdefault(order, {"CNT": [], "BANCO": [], "nota": "", "notas": {"CNT": {}, "BANCO": {}}})
                        match[side].append(row_id)
                        note = record.get(meta["note"], "")
                        match["notas"][side][row_id] = note if pd.notna(note) else ""
                        if pd.notna(note) and note != "":
                            match["nota"] = str(note)
                    else:
                        pending_ids.append(row_id)
            self.sources[side] = pd.DataFrame(rows, columns=original_columns, index=ids)
            prepared(self.sources[side])
            self.pending[side] = pending_ids
            occupied = set(original_columns) | RESERVED
            self.display_names[side] = {c: unique_column(str(c) + " (original)", occupied)
                                        for c in original_columns if c in RESERVED}
        used_ids = list(self.matches)
        used_ids += [positive_integer(e["Ordem"], "Histórico: ordem") for e in self.history]
        self.next_id = max([self.next_id] + [i + 1 for i in used_ids])
        if not config:
            for order in self.matches:
                self.record_event("Importada", order)
        return self

    def view(self, side, ids=None):
        if ids is None:
            ids = self.pending[side]
        frame = prepared(self.sources[side].loc[list(ids)]).rename(columns=self.display_names[side])
        frame["Ver"] = False
        return frame

    def record_event(self, action, order):
        match = self.matches[order]
        event = uuid4().hex
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for side in SIDES:
            for row_id in match[side]:
                note = match.get("notas", {}).get(side, {}).get(row_id, match["nota"])
                self.history.append(dict(zip(HISTORY_COLUMNS, [event, timestamp, action, order, side, row_id, note])))

    def reconcile(self, ledger_ids, bank_ids, note="", action="Manual"):
        selected = {"CNT": list(ledger_ids), "BANCO": list(bank_ids)}
        if not any(selected.values()):
            raise ValueError("Selecione pelo menos um movimento para conciliar.")
        for side, ids in selected.items():
            if len(ids) != len(set(ids)) or not set(ids).issubset(self.pending[side]):
                raise ValueError("A seleção contém movimentos duplicados ou já conciliados.")
        totals = [round(self.view(side, selected[side])["Valor"].sum(), 2) for side in SIDES]
        if totals[0] != totals[1]:
            raise ValueError("A soma dos valores a conciliar não é equivalente.")
        order = self.next_id
        self.matches[order] = {**selected, "nota": note or ""}
        self.record_event(action, order)
        for side in SIDES:
            selected_ids = set(selected[side])
            self.pending[side] = [i for i in self.pending[side] if i not in selected_ids]
        self.next_id += 1
        return order

    def undo(self, orders):
        orders = list(dict.fromkeys(orders))
        if any(order not in self.matches for order in orders):
            raise ValueError("A reconciliação selecionada já não existe.")
        for order in orders:
            self.record_event("Anulada", order)
            for side in SIDES:
                self.pending[side].extend(self.matches[order][side])
            del self.matches[order]

    def summary(self):
        result = []
        for order, match in sorted(self.matches.items()):
            row = {"Ordem": order, "Nota": match["nota"]}
            for side, suffix, description, amount in (("CNT", "Movimento", "DescricaoMovimento", "ValorMovimento"),
                                                       ("BANCO", "Extrato", "DescricaoBanco", "ValorBanco")):
                frame = self.view(side, match[side])
                row["Data" + suffix] = [d.isoformat() for d in frame["Data"]]
                row[description] = frame["Descrição"].tolist()
                row[amount] = frame["Valor"].tolist()
            result.append(row)
        return result

    def export(self):
        sheets = {}
        for side in SIDES:
            meta = self.metadata[side]
            source = self.sources[side]
            pending = source.loc[self.pending[side]].copy()
            pending[meta["row_id"]] = pending.index
            records = []
            for order, match in sorted(self.matches.items()):
                for row_id in match[side]:
                    note = match.get("notas", {}).get(side, {}).get(row_id, match["nota"])
                    records.append({**source.loc[row_id].to_dict(), meta["row_id"]: row_id,
                                    meta["match_id"]: order, meta["note"]: note})
            columns = list(source.columns) + list(meta.values())
            sheets["MATCH " + side] = pd.DataFrame(records, columns=columns)
            sheets[side] = pending
        settings = {"aplicacao": "reconciliacoes", "versao": "1", "proximo_id": self.next_id,
                    "definicoes": json.dumps(self.settings, ensure_ascii=False)}
        for side in SIDES:
            settings["colunas_" + side] = json.dumps(self.metadata[side], ensure_ascii=False)
            settings["originais_" + side] = json.dumps(list(self.sources[side].columns), ensure_ascii=False)
        sheets["HISTORICO"] = pd.DataFrame(self.history, columns=HISTORY_COLUMNS)
        sheets["CONFIGURACAO"] = pd.DataFrame(settings.items(), columns=["Chave", "Valor"])
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for name in ("MATCH CNT", "MATCH BANCO", "CNT", "BANCO", "HISTORICO", "CONFIGURACAO"):
                sheets[name].to_excel(writer, sheet_name=name, index=False)
                sheet = writer.sheets[name]
                sheet.freeze_panes = "A2"
                # Imported text must stay text, even when it starts with '='.
                for row in sheet.iter_rows():
                    for cell in row:
                        if cell.data_type == "f":
                            cell.data_type = "s"
        return output.getvalue()
