import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÃO DA API ---
def authenticate_gspread():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Transformamos a seção do segredo em um dicionário Python real
    creds_info = dict(st.secrets["gcp_service_account"])
    
    # O Streamlit geralmente já lida com o \n, mas por segurança:
    creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
    
    # Autenticação direta usando o dicionário completo
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    return gspread.authorize(creds)

st.set_page_config(page_title="Pesquisa Mart Minas", layout="wide")

# Função auxiliar para salvar preço e observação
def salvar_dados(planilha, indice_original, preco, observacao):
    # O gspread usa base 1, e a primeira linha costuma ser o cabeçalho, então +2
    numero_linha_sheets = int(indice_original + 2)
    
    # Atualiza Coluna D (Índice 4) e Coluna E (Índice 5)
    planilha.update_cell(numero_linha_sheets, 4, preco)      
    planilha.update_cell(numero_linha_sheets, 5, observacao) 

try:
    client = authenticate_gspread()
    # Abre a planilha pelo nome (certifique-se que o e-mail da conta de serviço tem acesso a ela)
    sheet = client.open("Pesquisas de Preços").get_worksheet(0)
    
    # Lendo dados
    records = sheet.get_all_records()
    if not records:
        st.error("A planilha parece estar vazia ou sem cabeçalhos.")
        st.stop()
        
    df_completo = pd.DataFrame(records)

    # Identificação das colunas
    col_loja = df_completo.columns[0]
    col_comprador = df_completo.columns[1]
    col_produto = df_completo.columns[2]
    col_preco = df_completo.columns[3]
    col_obs_nome = df_completo.columns[4] if len(df_completo.columns) > 4 else "Observação"

    # --- FILTROS ---
    st.sidebar.header("Filtros")
    opcoes_loja = ["Todas"] + list(df_completo[col_loja].unique())
    loja_selecionada = st.sidebar.selectbox("Selecione a Loja:", opcoes_loja)

    df_filtrado_loja = df_completo if loja_selecionada == "Todas" else df_completo[df_completo[col_loja] == loja_selecionada]
    
    opcoes_comprador = ["Todos"] + list(df_filtrado_loja[col_comprador].unique())
    comprador_selecionado = st.sidebar.selectbox("Filtrar por Comprador:", opcoes_comprador)

    if comprador_selecionado != "Todos":
        df_trabalho = df_filtrado_loja[df_filtrado_loja[col_comprador] == comprador_selecionado].copy()
    else:
        df_trabalho = df_filtrado_loja.copy()

    # --- CONTROLE DE NAVEGAÇÃO ---
    if 'idx' not in st.session_state:
        st.session_state.idx = 0

    if st.session_state.idx >= len(df_trabalho):
        st.session_state.idx = 0

    if len(df_trabalho) > 0:
        linha_atual = df_trabalho.iloc[st.session_state.idx]
        
        st.title("📝 Pesquisa de Preço")
        st.subheader(f"Loja: {linha_atual[col_loja]}")
        st.caption(f"Item {st.session_state.idx + 1} de {len(df_trabalho)} | Comprador: {linha_atual[col_comprador]}")

        with st.container(border=True):
            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown("**Comprador**")
                st.write(linha_atual[col_comprador])
            with c2:
                st.markdown("**Produto**")
                st.write(linha_atual[col_produto])

        col_input1, col_input2 = st.columns(2)
        with col_input1:
            novo_valor_c = st.text_input("Preço:", value=str(linha_atual.get(col_preco, "")), key=f"p_{st.session_state.idx}")
        with col_input2:
            nova_obs = st.text_input("Observação:", value=str(linha_atual.get(col_obs_nome, "")), key=f"o_{st.session_state.idx}")

        st.divider()

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
    st.error(f"Erro de conexão ou permissão: {e}")
