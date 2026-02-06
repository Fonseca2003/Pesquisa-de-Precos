import streamlit as st
import json
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÃO DA API ---
def authenticate_gspread():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # 1. Pegamos a string bruta do segredo que você colou
    json_bruto = st.secrets["gcp_service_account_bruto"]
    
    # 2. Transformamos o texto em um dicionário Python (JSON)
    info = json.loads(json_bruto)
    
    # 3. Corrigimos a chave privada (trocando o texto \n por quebra de linha real)
    info["private_key"] = info["private_key"].replace("\\n", "\n")
    
    # 4. Autenticamos
    creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scope)
    return gspread.authorize(creds)

st.set_page_config(page_title="Pesquisa Mart Minas", layout="wide")

# Função auxiliar para salvar preço (Col C/3) e observação (Col E/5)
def salvar_dados(planilha, indice_original, preco, observacao):
    numero_linha_sheets = int(indice_original + 2)
    # Atualiza Coluna C (Índice 3)
    planilha.update_cell(numero_linha_sheets, 4, preco) # Note: Se Loja=A, Comprador=B, Produto=C, o Preço é D(4)? 
    # Ajuste abaixo conforme sua planilha real:
    # Se Loja(A), Comprador(B), Produto(C), Preço(D), Obs(E):
    planilha.update_cell(numero_linha_sheets, 4, preco)      # Coluna D
    planilha.update_cell(numero_linha_sheets, 5, observacao) # Coluna E

try:
    client = authenticate_gspread()
    sheet = client.open("Pesquisas de Preços").get_worksheet(0)
    
    # Lendo dados
    records = sheet.get_all_records()
    df_completo = pd.DataFrame(records)

    # MAPEAMENTO CONFORME SOLICITADO:
    # Coluna A: Loja | Coluna B: Comprador | Coluna C: Produto
    col_loja = df_completo.columns[0]
    col_comprador = df_completo.columns[1]
    col_produto = df_completo.columns[2]
    col_preco = df_completo.columns[3]
    # A coluna E pode não vir no get_all_records se estiver vazia, tratamos isso:
    col_obs_nome = df_completo.columns[4] if len(df_completo.columns) > 4 else "Observação"

    # --- FILTRO DE LOJA (COLUNA A) ---
    st.sidebar.header("Filtros")
    opcoes_loja = ["Todas"] + list(df_completo[col_loja].unique())
    loja_selecionada = st.sidebar.selectbox(f"Selecione a Loja:", opcoes_loja)

    # --- FILTRO DE COMPRADOR (COLUNA B) ---
    df_filtrado_loja = df_completo if loja_selecionada == "Todas" else df_completo[df_completo[col_loja] == loja_selecionada]
    
    opcoes_comprador = ["Todos"] + list(df_filtrado_loja[col_comprador].unique())
    comprador_selecionado = st.sidebar.selectbox(f"Filtrar por Comprador:", opcoes_comprador)

    # Aplicação final do filtro
    if comprador_selecionado != "Todos":
        df_trabalho = df_filtrado_loja[df_filtrado_loja[col_comprador] == comprador_selecionado].copy()
    else:
        df_trabalho = df_filtrado_loja.copy()

    # --- CONTROLE DE ÍNDICE ---
    if 'idx' not in st.session_state:
        st.session_state.idx = 0

    if st.session_state.idx >= len(df_trabalho):
        st.session_state.idx = 0

    if len(df_trabalho) > 0:
        linha_atual = df_trabalho.iloc[st.session_state.idx]
        
        st.title("📝 Pesquisa de Preço")
        st.subheader(f"Loja: {linha_atual[col_loja]}")
        st.caption(f"Item {st.session_state.idx + 1} de {len(df_trabalho)} | Comprador: {linha_atual[col_comprador]}")

        # Exibição compacta: Comprador e Produto (B e C)
        with st.container(border=True):
            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown(f"<p style='font-size:12px; color:gray; margin-bottom:0;'>Comprador</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-size:15px; font-weight:bold;'>{linha_atual[col_comprador]}</p>", unsafe_allow_html=True)
            with c2:
                st.markdown(f"<p style='font-size:12px; color:gray; margin-bottom:0;'>Produto</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-size:15px; font-weight:bold;'>{linha_atual[col_produto]}</p>", unsafe_allow_html=True)

        # Campos de entrada
        col_input1, col_input2 = st.columns(2)
        with col_input1:
            novo_valor_c = st.text_input(f"Preço:", value=str(linha_atual.get(col_preco, "")), key=f"p_{st.session_state.idx}")
        with col_input2:
            nova_obs = st.text_input(f"Observação (Coluna E):", value=str(linha_atual.get(col_obs_nome, "")), key=f"o_{st.session_state.idx}")

        st.divider()

        # --- BOTÕES DE NAVEGAÇÃO ---
        btn_col1, btn_col2 = st.columns(2)

        with btn_col1:
            if st.button("⬅️ Salvar e Voltar", use_container_width=True):
                if st.session_state.idx > 0:
                    salvar_dados(sheet, linha_atual.name, novo_valor_c, nova_obs)
                    st.session_state.idx -= 1
                    st.rerun()
                else:
                    st.warning("Início da lista.")

        with btn_col2:
            if st.button("Salvar e Próximo ➡️", type="primary", use_container_width=True):
                salvar_dados(sheet, linha_atual.name, novo_valor_c, nova_obs)
                if st.session_state.idx < len(df_trabalho) - 1:
                    st.session_state.idx += 1
                    st.rerun()
                else:
                    st.success("✅ Fim da lista e dados salvos!")
    else:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")

except Exception as e:

    st.error(f"Erro: {e}")




