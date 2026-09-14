import re
from client_notes import read_notes, save_notes
from reconciliation_workspace import ReconciliationWorkspace

import pandas as pd
import streamlit as st
import math
import os
from itertools import combinations
from fuzzywuzzy import fuzz


def sync_workspace():
    workspace = st.session_state.workspace
    st.session_state.ledger = workspace.view("CNT").sort_values("Data")
    st.session_state.bank = workspace.view("BANCO").sort_values("Data")
    st.session_state.conciliados = workspace.summary()
    st.session_state.num_conciliacao = workspace.next_id
    st.session_state.edit_ledger = st.session_state.ledger.copy()
    st.session_state.edit_bank = st.session_state.bank.copy()
    st.session_state.dialog_close = 1
    for key in ("Datas_Cnt", "Datas_Banco", "Min_Valor_Cnt", "Max_Valor_Cnt",
                "Min_Valor_Banco", "Max_Valor_Banco", "tbl_edit_ledger", "tbl_edit_bank", "tbl_reconciliados"):
        st.session_state.pop(key, None)


def match_transactions(ledger, bank, previous_matched=None, match_total=100, match_parcial=80):
    workspace = st.session_state.workspace
    bank_remaining = bank.copy()
    for ledger_id, ledger_row in ledger.iterrows():
        candidates = bank_remaining[bank_remaining["Valor"] == ledger_row["Valor"]]
        if candidates.empty:
            continue
        initial_score = 50 if len(candidates) == 1 else 50 - len(candidates) * 3
        ledger_desc = normalize_description(ledger_row["Descrição"])
        best_score, best_id = -1, None
        for bank_id, bank_row in candidates.iterrows():
            date_difference = abs((ledger_row["Data"] - bank_row["Data"]).days)
            score = max(initial_score - date_difference, 15)
            score += fuzz.token_sort_ratio(ledger_desc, normalize_description(bank_row["Descrição"])) / 2
            if score >= best_score:
                best_score, best_id = score, bank_id
        if best_id is not None and best_score >= match_parcial:
            note = "Match total" if best_score >= match_total else "Match parcial"
            workspace.reconcile([ledger_id], [best_id], note, action="Automatica")
            bank_remaining = bank_remaining.drop(index=best_id)
    return workspace.summary(), workspace.view("CNT"), workspace.view("BANCO")


def normalize_description(value):
    return re.sub(r"[^\w\s]", "", str(value).upper())


def download_file():
    return st.session_state.workspace.export()


def download_workspace():
    if st.button("Preparar ficheiro download"):
        st.download_button(
            label="Download ficheiro", data=download_file(), file_name="reconciliacao.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    st.caption("Guarde o ficheiro para continuar mais tarde. Inclui os movimentos, reconciliações, histórico e definições.")


def testar_combos(df, valor, max_subset_size=2, cancel_tol=1e-4, versao=None):
    df_inicio = df[['Valor']]
    valor_x_2 = valor * 2

    if valor > 0:
        df_clean = df_inicio[ (df_inicio['Valor'] <= (valor_x_2)) & (df_inicio['Valor'] >= (-valor_x_2))]
    else:
        df_clean = df_inicio[ (df_inicio['Valor'] >= (valor_x_2)) & (df_inicio['Valor'] <= (-valor_x_2))]

    rows = list(df_clean.itertuples(index=True, name=None))
    n = len(rows)
    num_combos = sum(math.comb(n, r) for r in range(1, max_subset_size+1))
    if num_combos > 2_000_000:
        return num_combos

    vals = df_clean['Valor'].to_numpy()
    idxs = df_clean.index.to_numpy()

    comb_dict = {}
    for size in range(1, max_subset_size + 1):
        for comb in combinations(range(len(vals)), size):
            combo_idxs = tuple(idxs[list(comb)])
            combo_vals = tuple(vals[list(comb)])
            combo_sum = sum(combo_vals)
            comb_dict[combo_idxs] = {'values': combo_vals, 'sum': combo_sum}
    
    matching_combos = {k: v for k, v in comb_dict.items() if abs(v['sum'] - valor) <= cancel_tol}
    all_rows = []

    for i, combo_idxs in enumerate(matching_combos.keys(), start=1):
        matching_rows = df.loc[list(combo_idxs)].copy()
        matching_rows["#"] = i
        all_rows.append(matching_rows)

    if len(all_rows) > 0:
        df_matching = pd.concat(all_rows)
        return df_matching
    else:
        return 0


def conciliar(ledger=None, bank=None, nota=None, dialog=True):
    ledger_ids = ledger.index[ledger["Ver"].eq(True)].tolist() if ledger is not None else []
    bank_ids = bank.index[bank["Ver"].eq(True)].tolist() if bank is not None else []
    try:
        st.session_state.workspace.reconcile(ledger_ids, bank_ids, nota)
    except ValueError as error:
        st.session_state.show_error = True
        st.error(str(error))
        return False
    st.session_state.show_error = False
    sync_workspace()
    return True


def filtrar_df(df, intervalo_datas, min_valor, max_valor, pesquisa, coluna_pesquisa="Descrição"):
    min_data, max_data = intervalo_datas
    min_data = pd.to_datetime(min_data).date()
    max_data = pd.to_datetime(max_data).date()
    termos_pesquisa = [term.strip() for term in pesquisa.split(";") if term.strip()]

    mask = df.copy(deep=True)

    if termos_pesquisa:
        mask = mask[
            (mask["Valor"].between(min_valor, max_valor)) &
            (mask["Data"].between(min_data, max_data)) &
            (mask[coluna_pesquisa].astype("string").str.contains(
                '|'.join(re.escape(term) for term in termos_pesquisa), case=False, na=False))
        ]

    else:
        mask = mask[
            (mask["Valor"].between(min_valor, max_valor)) &
            (mask["Data"].between(min_data, max_data))
        ]

    mask['Ver'] = False
    return mask






def find_combo_options(df, df_outra, fonte, tipo, max_subset_size=2, periodo=False, apenas_unica=False):
    outra_tbl = "banco" if fonte == "cnt" else "cnt"
    selected = df.loc[df["Ver"].eq(True)].copy()
    if selected.empty:
        return 0
    candidates = df_outra.copy()
    if periodo:
        dates = pd.to_datetime(candidates["Data"])
        frequencies = {"dia": "D", "mes": "M", "ano": "Y"}
        groups = [group for _, group in candidates.groupby(dates.dt.to_period(frequencies[periodo]))]
    else:
        groups = [candidates]
    targets = [selected] if tipo == "Por total" else [selected.loc[[i]] for i in selected.index]
    results = []
    next_option = 1
    for target in targets:
        alternatives = []
        for group in groups:
            found = testar_combos(group, round(target["Valor"].sum(), 2), max_subset_size=max_subset_size)
            if isinstance(found, int):
                if found > 0:
                    return found
                continue
            alternatives.extend(part.copy() for _, part in found.groupby("#", sort=False))
        if not alternatives or (apenas_unica and len(alternatives) != 1):
            continue
        original = target.copy()
        original["Tipo"] = fonte
        original["#"] = "Origem"
        original["Ver"] = False
        results.append(original)
        for alternative in alternatives:
            alternative["Tipo"] = outra_tbl
            alternative["#"] = str(next_option)
            alternative["Ver"] = False
            next_option += 1
            results.append(alternative)
    return pd.concat(results) if results else 0


def show_combos_por_tipo(fonte, tipo, max_subset_size=2, periodo=False, apenas_unica=False):
    source = st.session_state.tbl_cnt if fonte == "cnt" else st.session_state.tbl_banco
    other = st.session_state.tbl_banco if fonte == "cnt" else st.session_state.tbl_cnt
    return find_combo_options(source, other, fonte, tipo, max_subset_size, periodo, apenas_unica)



@st.dialog("Escolher opções", width="large")
def opcoes_combos(fonte):

    if 'show_error' not in st.session_state:
        st.session_state.show_error = False

    options = ["Por total", "Por documento"]

    col1, col2 = st.columns(2)
    with col1:
        escolher_opcao_tipo = st.selectbox("Escolher o tipo", options=options)
    with col2:
        escolher_max_doc = st.number_input("Num Documentos Máx", min_value=0, value=2)

    dia = st.checkbox("Agrupar apenas por dia")
    mes = st.checkbox("Agrupar apenas por mês")
    ano = st.checkbox("Agrupar apenas por ano")

    if dia == True:
        periodo = 'dia'
    elif mes == True:
        periodo = 'mes'
    elif ano == True:
        periodo = 'ano'
    else:
        periodo = None

    apenas_unica = st.toggle("Mostrar apenas quando existe uma combinação", key="combo_apenas_unica",
                             help="Por documento: uma alternativa por movimento. Por total: uma alternativa para o total selecionado, considerando todos os períodos.")
    params = (fonte, escolher_opcao_tipo, escolher_max_doc, periodo, apenas_unica)
    if st.button("Ver combinações") or ("combo_params" in st.session_state and st.session_state.combo_params != params):
        st.session_state.combo_params = params
        with st.spinner("A executar"):
            st.session_state.select_all = 0
            st.session_state.result_df = 0
            st.session_state.combo_clicked = 1
            st.session_state.result_df = show_combos_por_tipo(fonte, escolher_opcao_tipo, max_subset_size = escolher_max_doc, periodo=periodo, apenas_unica=apenas_unica)

        if type(st.session_state.result_df) is int:
            del st.session_state['combo_clicked']
            if st.session_state.result_df == 0:
                return st.warning("Não foram encontradas combinações para os parâmetros selecionados")
            else:
                return st.error(f"Limite ultrapassado de 2,000,000 combinações. A pesquisa tem {st.session_state.result_df:,}.")

    if 'combo_clicked' in st.session_state:
        if 'result_df' in st.session_state and type(st.session_state.result_df) is not int:
            with st.container():
                if st.session_state.get("select_all", 0) == 1:
                    st.session_state.result_df['Ver'] = True
                elif 'select_all' not in st.session_state:
                    st.session_state.result_df['Ver'] = False
                else:
                    st.session_state.result_df['Ver'] = False

                display = st.session_state.result_df[['Tipo', '#', 'Data', 'Descrição', 'Valor', 'Ver']].rename(columns={"#": "Opção"})
                matrix_combos = st.data_editor(data=display, hide_index=True,
                                              disabled=["Tipo", "Opção", "Data", "Descrição", "Valor"])

                nota = st.text_input("Nota: ", width='stretch')
                
                col1, col2 = st.columns(2)

                with col1:
                    combo_conciliar = st.button("Conciliar", width='stretch')
                
                with col2: 
                    select_all = st.button("Selecionar todos", width='stretch', help="Clickar 2x")


            if combo_conciliar:
                st.session_state.matrix_combos = matrix_combos
                if st.session_state.matrix_combos[(st.session_state.matrix_combos['Ver']==True) & (st.session_state.matrix_combos['Tipo']=="cnt")].index.has_duplicates or st.session_state.matrix_combos[(st.session_state.matrix_combos['Ver']==True) & (st.session_state.matrix_combos['Tipo']=="banco")].index.has_duplicates:
                    st.error("Não podem haver linhas duplicadas a conciliar")

                    st.warning("O mesmo movimento foi selecionado em mais de uma opção. Selecione apenas uma dessas ocorrências.")

                else:
                    exec_combo_conciliar(nota=nota)
                    if st.session_state.show_error == True:
                        st.error("A soma dos valores a conciliar não é equivalente")
                    else:
                        del st.session_state['combo_clicked']
                        del st.session_state['result_df']
                        st.session_state.dialog_close = 1
                        st.rerun()

            if select_all:
                st.session_state.select_all = 1


def exec_combo_conciliar(nota=None):
    ledger_combo = st.session_state.matrix_combos[(st.session_state.matrix_combos['Ver']==True) & (st.session_state.matrix_combos['Tipo']=='cnt')]
    bank_combo = st.session_state.matrix_combos[(st.session_state.matrix_combos['Ver']==True) & (st.session_state.matrix_combos['Tipo']=='banco')]

    ledger_combo = ledger_combo.index.tolist()
    bank_combo = bank_combo.index.tolist()

    ledger_combo = st.session_state.ledger[st.session_state.ledger.index.isin(ledger_combo)].copy()
    ledger_combo['Ver'] = True

    bank_combo = st.session_state.bank[st.session_state.bank.index.isin(bank_combo)].copy()
    bank_combo  ['Ver'] = True

    conciliar(ledger=ledger_combo, bank=bank_combo, nota=nota, dialog=False)
    del st.session_state["matrix_combos"]


def client_notes_section():
    with st.expander("Cliente e regras de reconciliação", expanded=True):
        try:
            records = read_notes()
        except (OSError, ValueError) as error:
            st.error(f"Não foi possível ler as notas dos clientes: {error}")
            return
        if "cliente_apos_gravar" in st.session_state:
            st.session_state.cliente_notas = st.session_state.pop("cliente_apos_gravar")
        options = [None] + sorted(records, key=str.casefold)
        if st.session_state.get("cliente_notas") not in options:
            st.session_state.cliente_notas = None
        client = st.selectbox("Cliente", options, format_func=lambda value: "Novo cliente" if value is None else value,
                              key="cliente_notas")
        if client is None:
            name = st.text_input("Nome do novo cliente", key="novo_cliente_notas")
        else:
            name = client
        with st.form("form_notas_cliente"):
            notes = st.text_area("Notas e regras específicas do cliente", value=records.get(client, {}).get("notas", ""),
                                 height=150, key=f"notas_cliente_{client!r}")
            if st.form_submit_button("Guardar notas"):
                try:
                    if client is None and name.strip().casefold() in {c.casefold() for c in records}:
                        raise ValueError("Esse cliente já existe. Selecione-o na lista para editar as suas notas.")
                    saved = save_notes(name, notes)
                except (OSError, ValueError) as error:
                    st.error(f"Não foi possível guardar as notas: {error}")
                else:
                    st.session_state.cliente_apos_gravar = saved
                    st.session_state.notas_guardadas = True
                    st.session_state.pop(f"notas_cliente_{saved!r}", None)
                    st.rerun()
        if st.session_state.pop("notas_guardadas", False):
            st.success("Notas do cliente guardadas.")
        st.caption("As notas são guardadas ao clicar em Guardar notas e ficam disponíveis nas próximas sessões. Servem de consulta; não alteram automaticamente a conciliação.")


def manual(ledger, bank):
    client_notes_section()

    if ledger.empty == False:
        min_data_cnt = ledger["Data"].min()
        max_data_cnt = ledger["Data"].max()
        min_valor_cnt = ledger["Valor"].min()
        max_valor_cnt = ledger["Valor"].max()
    else:
        min_data_cnt = '1900-01-01'
        max_data_cnt = '1900-01-01'
        min_valor_cnt = 0
        max_valor_cnt = 0

    if bank.empty == False:
        min_data_banco = bank["Data"].min()
        max_data_banco= bank["Data"].max()
        min_valor_banco = bank["Valor"].min()
        max_valor_banco = bank["Valor"].max()
    else:
        min_data_banco = '1900-01-01'
        max_data_banco = '1900-01-01'
        min_valor_banco = 0
        max_valor_banco = 0

    if 'dialog_close' not in st.session_state:
        st.session_state.dialog_close = 1

    with st.container():
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.subheader("Contabilidade")
            intervalo_datas_cnt = st.date_input("Datas", ( min_data_cnt, max_data_cnt ), min_data_cnt, max_data_cnt, key="Datas_Cnt", format="DD-MM-YYYY")
            colunas_cnt = ["Descrição"] + [c for c in ledger.columns if c not in ("Descrição", "Ver")]
            coluna_pesquisa_cnt = st.selectbox("Pesquisar na coluna", colunas_cnt, key="Coluna_Pesquisa_Cnt")
            pesquisa_cnt = st.text_input("Pesquisa: separar termos com ';'", key="Pesquisa_Cnt")
        with col2:
            st.subheader(" ")
            input_min_valor_cnt = st.number_input(label="Valor mínimo", min_value=min_valor_cnt, max_value=max_valor_cnt, value=min_valor_cnt, 
            key="Min_Valor_Cnt")
            input_max_valor_cnt = st.number_input(label="Valor máximo", min_value=min_valor_cnt, max_value=max_valor_cnt, value=max_valor_cnt, key="Max_Valor_Cnt")
        with col3:
            st.subheader("Banco")
            intervalo_datas_banco = st.date_input("Datas", ( min_data_banco, max_data_banco ), min_data_banco, max_data_banco, key="Datas_Banco", format='DD-MM-YYYY')
            colunas_banco = ["Descrição"] + [c for c in bank.columns if c not in ("Descrição", "Ver")]
            coluna_pesquisa_banco = st.selectbox("Pesquisar na coluna", colunas_banco, key="Coluna_Pesquisa_Banco")
            pesquisa_banco = st.text_input("Pesquisa: separar termos com ';'", key="Pesquisa_Banco")
        with col4:
            st.subheader(" ")
            input_min_valor_banco = st.number_input(label="Valor mínimo", min_value=min_valor_banco, max_value=max_valor_banco, value=min_valor_banco, 
            key="Min_Valor_Banco")
            input_max_valor_banco = st.number_input(label="Valor máximo", min_value=min_valor_banco, max_value=max_valor_banco, value=max_valor_banco, key="Max_Valor_Banco")

        col1a, col2a, col3a, col4a, col5a, col6a, col7a, col8a = st.columns([1,1,1,3,1,1,1,3])

        with col1a: filtrar_cnt = st.button("Atualizar", key="filtrar_cnt", width="stretch")
        with col2a: select_all_cnt = st.button("Selecionar", key="select_all_cnt", width="stretch")
        with col3a: deselect_all_cnt = st.button("Remover", key="deselect_all_cnt", width="stretch")
        with col4a: combos_cnt = st.button("Combinações possíveis", key="combos_cnt", width="stretch")
        with col5a: filtrar_banco = st.button("Atualizar", key="filtrar_banco", width="stretch")
        with col6a: select_all_banco = st.button("Selecionar", key="select_all_banco", width="stretch")
        with col7a: deselect_all_banco = st.button("Remover", key="deselect_all_banco", width="stretch")
        with col8a: combos_banco = st.button("Combinações possíveis", key="combos_banco", width="stretch")

        atualizar_ambos = st.session_state.dialog_close == 1
        if filtrar_cnt or 'edit_ledger' not in st.session_state or atualizar_ambos:

            st.session_state.edit_ledger = filtrar_df(ledger, st.session_state["Datas_Cnt"], st.session_state["Min_Valor_Cnt"], st.session_state["Max_Valor_Cnt"], st.session_state["Pesquisa_Cnt"], coluna_pesquisa_cnt)
        
        if filtrar_banco or 'edit_bank' not in st.session_state or atualizar_ambos:
            
            st.session_state.edit_bank = filtrar_df(bank, st.session_state["Datas_Banco"], st.session_state["Min_Valor_Banco"], st.session_state["Max_Valor_Banco"], st.session_state["Pesquisa_Banco"], coluna_pesquisa_banco)
        st.session_state.dialog_close = 0

        if select_all_cnt:
            st.session_state.edit_ledger['Ver'] = True
            st.session_state.tbl_cnt['Ver'] = True
            st.rerun()

        if deselect_all_cnt:
            st.session_state.edit_ledger['Ver'] = False
            st.session_state.tbl_cnt['Ver'] = False
            st.rerun()

        if select_all_banco:
            st.session_state.edit_bank['Ver'] = True
            st.rerun()

        if deselect_all_banco:
            st.session_state.edit_bank['Ver'] = False
            st.rerun()

    px_per_row = 35


    with st.container():
        col1, col2 = st.columns([2,2])

        with col1:
            st.session_state.tbl_cnt = st.data_editor(
                data= st.session_state.edit_ledger,
                use_container_width=True,
                height= min(35 + (px_per_row * len(st.session_state.edit_ledger)), 500),
                hide_index=True,
                disabled=[c for c in st.session_state.edit_ledger.columns if c != 'Ver'],
                key='tbl_edit_ledger'
            )

            soma_cnt = round(st.session_state.tbl_cnt['Valor'].sum(),2)
            st.markdown(f"Total {soma_cnt}")

        with col2:
            st.session_state.tbl_banco = st.data_editor(
                data=st.session_state.edit_bank,
                use_container_width=True,
                hide_index=True,
                height = min(35 + (px_per_row * len(st.session_state.edit_bank)), 500),
                disabled=[c for c in st.session_state.edit_bank.columns if c != 'Ver'],
                key='tbl_edit_bank'
            )
            soma_banco = round(st.session_state.tbl_banco['Valor'].sum(),2)
            st.markdown(f"Total {soma_banco}")

        linhas_cnt = st.session_state.tbl_cnt[st.session_state.tbl_cnt['Ver']==True]
        soma_cnt = round(linhas_cnt["Valor"].sum(),2)
        linhas_bank = st.session_state.tbl_banco[st.session_state.tbl_banco['Ver']==True]
        soma_bank = round(linhas_bank["Valor"].sum(),2)
        dif_soma = round(soma_cnt - soma_bank,2)
        opcoes_cnt = len(st.session_state.tbl_cnt.loc[(st.session_state.tbl_cnt['Valor'] == -dif_soma)])
        opcoes_banco = len(st.session_state.tbl_banco.loc[(st.session_state.tbl_banco['Valor'] == dif_soma)])

        if dif_soma != 0 and opcoes_cnt == 0 and opcoes_banco == 0:
            st.error(f"Contabilidade: {soma_cnt} | Banco: {soma_bank} | Diferença: {dif_soma}") 
        elif dif_soma == 0:
            st.success(f"Contabilidade: {soma_cnt} | Banco: {soma_bank} | Diferença: 0")
        else:
            st.warning(f"Contabilidade: {soma_cnt} | Banco: {soma_bank} | Diferença: {dif_soma} ---- Existem {opcoes_cnt} opções na contabilidade com esta diferença --- Existem {opcoes_banco} opções no banco com esta diferença")

    if combos_cnt:
        if 'combo_clicked' in st.session_state:
            del st.session_state['combo_clicked']
        if 'result_df' in st.session_state:
            del st.session_state['result_df']
        opcoes_combos("cnt")

    if combos_banco:
        if 'combo_clicked' in st.session_state:
            del st.session_state['combo_clicked']
        if 'result_df' in st.session_state:
            del st.session_state['result_df']
        opcoes_combos("banco")

    nota = st.text_input("Nota", key=f"nota_conciliacao")
    fazer_match = st.button("Conciliar", key=f'conciliar_bnt')

    if fazer_match:
        if conciliar(st.session_state.tbl_cnt, st.session_state.tbl_banco, nota):
            st.rerun()


def reconciliacao_inicial(ficheiro):
    workspace = ficheiro if isinstance(ficheiro, ReconciliationWorkspace) else ReconciliationWorkspace.from_sheets(ficheiro)
    st.session_state.workspace = workspace
    if workspace.settings:
        for key in ("saldo_i_cnt", "saldo_i_banco", "match_total", "match_parcial"):
            if key in workspace.settings:
                st.session_state[key] = workspace.settings[key]
    else:
        workspace.settings = {key: st.session_state[key] for key in
                              ("saldo_i_cnt", "saldo_i_banco", "match_total", "match_parcial")}
    if st.session_state.conciliar and not workspace.restored:
        match_transactions(workspace.view("CNT"), workspace.view("BANCO"),
                           match_total=st.session_state.match_total,
                           match_parcial=st.session_state.match_parcial)
    st.session_state.conciliar = False
    sync_workspace()


def remover_conciliacao(tbl):
    frame = pd.DataFrame(tbl)
    orders = frame.loc[frame["Remover"].eq(True), "Ordem"].tolist()
    if not orders:
        st.warning("Selecione uma reconciliação para remover.")
        return
    st.session_state.workspace.undo(orders)
    sync_workspace()
    st.session_state.remove_success = 1
    st.rerun()


def conciliados():
    if not st.session_state.conciliados:
        st.info("Não existem reconciliações ativas.")
        return
    with st.form("form_conciliados"):
        lista_keys = ['Ordem', 'DataMovimento', 'DescricaoMovimento','ValorMovimento', 'DataExtrato', 'DescricaoBanco', 'ValorBanco', 'Nota']
        conciliados_show =  [
            {k: d[k] for k in lista_keys if k in d}
            for d in st.session_state.conciliados
        ]

        for row in conciliados_show:
            row['Remover'] = False

        tbl_conciliados = st.data_editor(
            data=conciliados_show, disabled=lista_keys, key="tbl_reconciliados"
        )

        if st.form_submit_button("Remover"):
            remover_conciliacao(tbl_conciliados)

        if 'remove_success' not in st.session_state:
            st.session_state.remove_success = 0

        if st.session_state.remove_success == 1:
            st.success("Movimentos removidos com sucesso")
            st.session_state.remove_success = 0


def resumo():
    total_cnt = 0
    total_banco = 0

    for row in st.session_state.conciliados:
        val_cnt = row.get("ValorMovimento", 0)
        if isinstance(val_cnt, list): 
            total_cnt += sum(val_cnt)
        else:                      
            total_cnt += val_cnt

        val_banco = row.get("ValorBanco", 0)
        if isinstance(val_banco, list):  
            total_banco += sum(val_banco)
        else:                      
            total_banco += val_banco

    dados = [st.session_state.ledger, st.session_state.bank]
    num_docs = []
    valor_por_conciliar = []

    for info in dados:
        contagem = 0
        valor = 0
        for i, row in info.iterrows():
            val = row["Valor"]
            if isinstance(val, list):
                contagem += len(val)
                valor += val.sum()
            else:                      
                contagem += 1
                valor += val
        num_docs.append(contagem)
        valor_por_conciliar.append(valor)

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.subheader("Saldo Inicial")
        st.metric(label="Contabilidade", value=f'{st.session_state.saldo_i_cnt} €')
        st.metric(label="Banco", value=f'{st.session_state.saldo_i_banco} €')
    with col2:
        st.subheader("Contabilidade")
        st.metric(label="Por conciliar", value=f'{round(valor_por_conciliar[0],2)} €')
        st.metric(label="Por conciliar (lançamentos)", value=num_docs[0])
    with col3:
        st.subheader("Banco")
        st.metric(label="Por conciliar", value=f'{round(valor_por_conciliar[1],2)} €')
        st.metric(label="Por conciliar (lançamentos)", value=num_docs[1])
    with col4:
        st.subheader("Diferenças")
        st.metric(label="Diferença", value=f'{round((st.session_state.saldo_i_banco - st.session_state.saldo_i_cnt + valor_por_conciliar[0] - valor_por_conciliar[1]),2)} €')


def app():
    st.set_page_config(page_title="Reconciliações", page_icon=':star', layout='wide')

    if 'conciliacao_inicial' not in st.session_state:
        st.session_state.conciliacao_inicial = None
        st.session_state.conciliar = True

    if 'file' not in st.session_state:
        st.session_state.file = None

    if st.session_state.conciliacao_inicial == None:
        pag_inicial = st.empty()
        with pag_inicial.container():
            st.title("Reconciliação inicial")
            col1, col2, col3, col4, col5, col6, col7, col8 = st.columns(8)
            with col1:
                st.session_state.saldo_i_banco = st.number_input("Saldo Inicial Banco", value=0.00)
            with col2:
                st.session_state.saldo_i_cnt = st.number_input("Saldo Inicial Contabilidade", value=0.00)
            with col3:
                st.session_state.match_total = st.number_input("MatchTotal%", value=100)
            with col4:
                st.session_state.match_parcial = st.number_input("MatchParcial%", value=80)

            st.divider()
            col1, col2 = st.columns(2)

            with st.spinner("A processar..."):

                with col1:
                    st.session_state.file = st.file_uploader("Fazer upload do ficheiro. Use um ficheiro novo ou uma reconciliação guardada. CNT e BANCO devem conter Data, Descrição e Valor. As restantes colunas são preservadas", type=["xlsx", "xls"])
                    st.caption("Uma reconciliação guardada retoma o estado anterior e recupera os saldos e definições.")

                    if st.button("Executar programa"):
                        if st.session_state.file == None:
                            st.error("Não foi efetuado upload do ficheiro")
                        else:
                            try:
                                workspace = ReconciliationWorkspace.read(st.session_state.file)
                                reconciliacao_inicial(workspace)
                            except (ValueError, KeyError, TypeError) as error:
                                st.error(f"Não foi possível abrir o ficheiro: {error}")
                            else:
                                st.session_state.conciliacao_inicial = 1
                                st.rerun()

                    st.divider()

                    if st.button("Demonstração"):
                        file = os.path.join("file", "demo.xlsx")
                        st.session_state.file = ReconciliationWorkspace.read(file)
                        reconciliacao_inicial(st.session_state.file)
                        st.session_state.conciliacao_inicial = 1
                        st.rerun()

                    path_template = os.path.join("file", "template.xlsx")

                    with open(path_template, "rb") as f:
                        st.download_button(
                            label="Download Template",
                            data=f,
                            file_name="template.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

    elif st.session_state.conciliacao_inicial == 1:
        with st.container():
            opcao = st.selectbox("", options=['Resumo', 'Conciliados', 'Manual', 'Histórico'])

            if opcao == 'Conciliados':
                conciliados()
            elif opcao == 'Manual':
                manual(st.session_state.ledger, st.session_state.bank)
            elif opcao == "Resumo":
                resumo()
            elif opcao == "Histórico":
                st.dataframe(pd.DataFrame(st.session_state.workspace.history), hide_index=True, use_container_width=True)
        st.divider()
        download_workspace()


if __name__ == '__main__':
    app()
