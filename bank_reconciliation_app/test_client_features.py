from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from client_notes import read_notes, save_notes
from reconciliacoes import find_combo_options
from reconciliation_workspace import ReconciliationWorkspace
from test_reconciliation_workspace import sample
import test_reconciliation_app


def movements(values, selected=False, dates=None):
    return pd.DataFrame({"Data": dates or [datetime(2026, 1, 1)] * len(values),
                         "Descrição": ["Movimento"] * len(values), "Valor": values, "Ver": selected},
                        index=[f"movement-{i}" for i in range(len(values))])


class CombinationTests(unittest.TestCase):
    def test_unique_combination_may_contain_multiple_rows(self):
        result = find_combo_options(movements([100], True), movements([60, 40]), "cnt", "Por total", apenas_unica=True)
        self.assertEqual(len(result), 3)
        self.assertEqual(result.loc[result["Tipo"] == "banco", "#"].nunique(), 1)

    def test_ambiguous_and_no_match_results(self):
        source, bank = movements([100], True), movements([100, 60, 40])
        all_options = find_combo_options(source, bank, "cnt", "Por total")
        self.assertEqual(all_options.loc[all_options["Tipo"] == "banco", "#"].nunique(), 2)
        self.assertEqual(find_combo_options(source, bank, "cnt", "Por total", apenas_unica=True), 0)
        self.assertEqual(find_combo_options(source, movements([20]), "cnt", "Por total", apenas_unica=True), 0)

    def test_uniqueness_is_counted_across_periods(self):
        bank = movements([100, 100], dates=[datetime(2026, 1, 1), datetime(2027, 2, 2)])
        for period in ("dia", "mes", "ano"):
            self.assertEqual(find_combo_options(movements([100], True), bank, "cnt", "Por total",
                                               periodo=period, apenas_unica=True), 0)

    def test_each_document_is_filtered_independently(self):
        source = movements([100, 50], True)
        bank = movements([100, 100, 50])
        result = find_combo_options(source, bank, "cnt", "Por documento", apenas_unica=True)
        self.assertEqual(result["Valor"].tolist(), [50, 50])
        self.assertTrue(source["Ver"].all())
        self.assertNotIn("#", source.columns)

    def test_dialog_toggle_and_hidden_identifiers(self):
        app = AppTest.from_string('from reconciliacoes import opcoes_combos\nopcoes_combos("cnt")')
        app.session_state["tbl_cnt"] = movements([100], True)
        app.session_state["tbl_banco"] = movements([100, 60, 40])
        app.run()
        next(b for b in app.button if b.label == "Ver combinações").click().run()
        self.assertFalse(app.exception)
        self.assertNotIn("#", app.dataframe[0].value.columns)
        self.assertIn("Opção", app.dataframe[0].value.columns)
        self.assertIn('"hidden": true', app.dataframe[0].proto.columns)
        app.toggle(key="combo_apenas_unica").set_value(True).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe), 0)
        self.assertTrue(app.warning)
        app.toggle(key="combo_apenas_unica").set_value(False).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe), 1)


class ClientNotesTests(unittest.TestCase):
    def test_csv_roundtrip_update_and_other_clients(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.csv"
            self.assertEqual(read_notes(path), {})
            note = 'Regra: "Referência", valor; descrição\nSegunda linha com acentuação.'
            save_notes("Cliente A", note, path)
            save_notes("Cliente B", "000123", path)
            self.assertEqual(read_notes(path)["Cliente A"]["notas"], note)
            save_notes(" cliente a ", "Nova regra", path)
            records = read_notes(path)
            self.assertEqual(len(records), 2)
            self.assertEqual(records["Cliente A"]["notas"], "Nova regra")
            self.assertEqual(records["Cliente B"]["notas"], "000123")
            with self.assertRaises(ValueError):
                save_notes(" ", "invalid", path)

    def test_manual_notes_persist_across_sessions_and_client_switches(self):
        with tempfile.TemporaryDirectory() as directory, patch("client_notes.NOTES_PATH", Path(directory) / "notes.csv"):
            workspace = ReconciliationWorkspace.from_sheets(sample())
            helper = test_reconciliation_app.InterfaceTests()
            app = helper.opened_app(workspace)
            app.selectbox[0].select("Manual").run()
            app.text_input(key="novo_cliente_notas").set_value("Cliente A")
            app.text_area[0].set_value("Regra A\nOutra regra")
            next(b for b in app.button if b.label == "Guardar notas").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.selectbox(key="cliente_notas").value, "Cliente A")
            self.assertEqual(app.text_area[0].value, "Regra A\nOutra regra")
            save_notes("Cliente B", "Regra B")
            second = helper.opened_app(workspace)
            second.selectbox[0].select("Manual").run()
            second.selectbox(key="cliente_notas").select("Cliente A").run()
            self.assertEqual(second.text_area[0].value, "Regra A\nOutra regra")
            second.selectbox(key="cliente_notas").select("Cliente B").run()
            self.assertEqual(second.text_area[0].value, "Regra B")
            second.text_area[0].set_value("Regra B atualizada")
            next(b for b in second.button if b.label == "Guardar notas").click().run()
            self.assertFalse(second.exception)
            self.assertEqual(read_notes()["Cliente B"]["notas"], "Regra B atualizada")
            self.assertEqual(read_notes()["Cliente A"]["notas"], "Regra A\nOutra regra")


if __name__ == "__main__":
    unittest.main()
