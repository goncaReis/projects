import unittest

from streamlit.testing.v1 import AppTest

from reconciliation_workspace import ReconciliationWorkspace
from test_reconciliation_workspace import sample, reopen


class InterfaceTests(unittest.TestCase):
    def opened_app(self, workspace):
        app = AppTest.from_file("reconciliacoes.py")
        app.session_state["workspace"] = workspace
        app.session_state["conciliacao_inicial"] = 1
        app.session_state["ledger"] = workspace.view("CNT")
        app.session_state["bank"] = workspace.view("BANCO")
        app.session_state["conciliados"] = workspace.summary()
        app.session_state["saldo_i_cnt"] = 10.5
        app.session_state["saldo_i_banco"] = 10.5
        app.run()
        self.assertFalse(app.exception)
        return app

    def test_startup(self):
        app = AppTest.from_file("reconciliacoes.py").run()
        self.assertFalse(app.exception)

    def test_manual_search_columns_are_independent(self):
        workspace = ReconciliationWorkspace.from_sheets(sample())
        app = self.opened_app(workspace)
        app.selectbox[0].select("Manual").run()
        self.assertEqual(app.selectbox(key="Coluna_Pesquisa_Cnt").value, "Descrição")
        self.assertEqual(app.selectbox(key="Coluna_Pesquisa_Banco").value, "Descrição")
        self.assertNotIn("Ver", app.selectbox(key="Coluna_Pesquisa_Cnt").options)
        app.selectbox(key="Coluna_Pesquisa_Cnt").select("Referencia")
        app.text_input(key="Pesquisa_Cnt").set_value("000123")
        app.button(key="filtrar_cnt").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["tbl_cnt"]["Referencia"].tolist(), ["000123"])
        self.assertEqual(len(app.session_state["tbl_banco"]), 2)
        app.selectbox(key="Coluna_Pesquisa_Banco").select("BancoRef")
        app.text_input(key="Pesquisa_Banco").set_value("000002")
        app.button(key="filtrar_banco").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["tbl_banco"]["BancoRef"].tolist(), ["000002"])
        self.assertEqual(app.session_state["tbl_cnt"]["Referencia"].tolist(), ["000123"])

    def test_search_handles_numbers_and_literal_terms(self):
        from reconciliacoes import filtrar_df
        frame = ReconciliationWorkspace.from_sheets(sample()).view("CNT")
        dates = (frame["Data"].min(), frame["Data"].max())
        result = filtrar_df(frame, dates, 0, 200, "100", "Valor")
        self.assertEqual(result["Valor"].tolist(), [100])
        frame["Referencia"] = ["Ref[1]", None]
        result = filtrar_df(frame, dates, 0, 200, "ref[1]; inexistente", "Referencia")
        self.assertEqual(result.index.tolist(), [frame.index[0]])
        self.assertEqual(len(filtrar_df(frame, dates, 0, 200, "", "Referencia")), 2)
        self.assertTrue(filtrar_df(frame, dates, 0, 60, "ref[1]", "Referencia").empty)

    def test_manual_match_undo_history_and_export(self):
        workspace = ReconciliationWorkspace.from_sheets(sample())
        app = self.opened_app(workspace)
        app.selectbox[0].select("Manual").run()
        self.assertFalse(app.exception)
        for key in ("tbl_edit_ledger", "tbl_edit_bank"):
            app.session_state[key] = {"edited_rows": {0: {"Ver": True}}, "added_rows": [], "deleted_rows": []}
        app.button(key="conciliar_bnt").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(workspace.next_id, 2)
        self.assertEqual(len(workspace.matches), 1)
        app.selectbox[0].select("Conciliados").run()
        self.assertFalse(app.exception)
        app.session_state["tbl_reconciliados"] = {"edited_rows": {0: {"Remover": True}}, "added_rows": [], "deleted_rows": []}
        next(b for b in app.button if b.label == "Remover").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(workspace.matches, {})
        self.assertEqual(workspace.next_id, 2)
        app.selectbox[0].select("Histórico").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 4)
        next(b for b in app.button if b.label == "Preparar ficheiro download").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(reopen(workspace).next_id, 2)

    def test_empty_workspace_all_views_and_download(self):
        workspace = ReconciliationWorkspace.from_sheets({s: f.iloc[:0] for s, f in sample().items()})
        app = self.opened_app(workspace)
        for view in ("Manual", "Conciliados", "Histórico", "Resumo"):
            app.selectbox[0].select(view).run()
            self.assertFalse(app.exception, view)
        next(b for b in app.button if b.label == "Preparar ficheiro download").click().run()
        self.assertFalse(app.exception)

    def test_saved_workspace_resumes_without_rematching_undone_rows(self):
        workspace = ReconciliationWorkspace.from_sheets(sample())
        workspace.settings = {"saldo_i_cnt": 123, "saldo_i_banco": 456, "match_total": 100, "match_parcial": 80}
        workspace.reconcile(workspace.pending["CNT"], workspace.pending["BANCO"])
        workspace.undo([1])
        workspace = reopen(workspace)
        app = AppTest.from_string('''
import streamlit as st
from reconciliacoes import reconciliacao_inicial
st.session_state.conciliar = True
reconciliacao_inicial(st.session_state.workspace)
''')
        app.session_state["workspace"] = workspace
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(workspace.matches, {})
        self.assertEqual(app.session_state["num_conciliacao"], 2)
        self.assertEqual(app.session_state["saldo_i_cnt"], 123)

    def test_combination_selection_uses_persistent_movement_ids(self):
        sheets = sample()
        sheets["BANCO"]["Valor"] = [60, 40]
        workspace = ReconciliationWorkspace.from_sheets(sheets)
        app = AppTest.from_string('''
import pandas as pd
import streamlit as st
from reconciliacoes import exec_combo_conciliar
workspace = st.session_state.workspace
st.session_state.ledger = workspace.view("CNT")
st.session_state.bank = workspace.view("BANCO")
ledger = st.session_state.ledger.iloc[:1].assign(Tipo="cnt", Ver=True)
bank = st.session_state.bank.assign(Tipo="banco", Ver=True)
st.session_state.matrix_combos = pd.concat([ledger, bank])
exec_combo_conciliar("Combinacao")
''')
        app.session_state["workspace"] = workspace
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(workspace.matches[1]["CNT"]), 1)
        self.assertEqual(len(workspace.matches[1]["BANCO"]), 2)
        self.assertEqual(len(reopen(workspace).history), 3)


if __name__ == "__main__":
    unittest.main()
