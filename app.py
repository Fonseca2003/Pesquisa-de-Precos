import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ================== CONFIGURAÇÃO ==================
st.set_page_config(page_title="Pesquisa Mart Minas", layout="wide", page_icon="icon.png")

# CSS simplificado: REMOVIDA a importação e aplicação forçada da fonte Inter
# Foco em corrigir o ícone da sidebar + manter layout
st.markdown("""
    <style>
    /* Remove qualquer texto quebrado no controle da sidebar */
    [data-testid="stSidebarCollapsedControl"] > span,
    [data-testid="stSidebarCollapsedControl"] span:not(.material-symbols-outlined) {
        display: none !important;
    }

    /* Força o ícone correto (fallback visual) */
    [data-testid="stSidebarCollapsedControl"]::before {
        content: "keyboard_double_arrow_right" !important;
        font-family: "Material Symbols Outlined", "Material Icons", sans-serif !important;
        font-size: 28px !important;
        line-height: 1 !important;
        vertical-align: middle !important;
        color: inherit !important;
        display: inline-block !important;
    }

    /* Garante que o botão da sidebar use o font de ícones corretamente */
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="stSidebarCollapsedControl"] * {
        font-family: "Material Symbols Outlined", "Material Icons", sans-serif !important;
        font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 48 !important;
    }

    /* Seus estilos de layout mantidos */
    .block-container {
        max-width: 800px !important;
        padding-top: 1.5rem !important;
        margin: auto !important;
    }

    .titulo-centralizado {
        text-align: center;
        font-size: clamp(24px, 5vw, 40px);
        font-weight: 700;
        margin-top: 10px;
        margin-bottom: 15px;
        width: 100%;
        display: block;
    }

    .progresso-texto {
        text-align: center;
        width: 100%;
        margin-bottom: 5px;
    }

    .filter-info-container {
        white-space: nowrap;
        overflow-x: auto;
        font-size: clamp(12px, 2.5vw, 15px);
        margin-bottom: 15px;
        scrollbar-width: none;
        display: flex;
        justify-content: center;
        gap: 15px;
    }
    .filter-info-container::-webkit-scrollbar { display: none; }
    
    .stTextInput label, .stSelectbox label {
        text-align: left !important;
    }
    </style>
""", unsafe_allow_html=True)

# Estados de sessão
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "loja_sel" not in st.session_state:
    st.session_state.loja_sel = None
if "concorrente_sel" not in st.session_state:
    st.session_state.concorrente_sel = None
if "prod_idx" not in st.session_state:
    st.session_state.prod_idx = 0

# ================== FUNÇÕES CORE ==================
@st.cache_resource
def authenticate_gspread():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_info = dict(st.secrets["gcp_service_account"])
    return Credentials.from_service_account_info(creds_info, scopes=scopes)

@st.cache_data(ttl=60)
def fetch_data(_sheet):
    data = _sheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    df = df.loc[:, df.columns != ''] 
    return df

def salvar_dados(sheet, indice_original, preco, observacao):
    try:
        preco_limpo = str(preco).replace(",", ".").strip()
        linha_sheets = int(indice_original + 2)
        sheet.update(f"D{linha_sheets}:E{linha_sheets}", [[preco_limpo, observacao]])
        st.toast("Dados salvos!", icon="✅")
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

# ================== APP ==================
try:
    client = gspread.authorize(authenticate_gspread())
    sheet = client.open("Pesquisas de Preços").get_worksheet(0)
    df_completo = fetch_data(sheet)

    col_loja, col_comprador, col_produto, col_preco, col_obs, col_concorrente = df_completo.columns[:6]

    # --- TELA DE LOGIN ---
    if not st.session_state.autenticado:
        st.image("banner.png", use_container_width=True)
        st.markdown('<div class="titulo-centralizado">Acessar Pesquisa</div>', unsafe_allow_html=True)
        with st.container(border=True):
            loja = st.selectbox("Selecione a sua Loja:", sorted(df_completo[col_loja].unique()))
            concorrentes_disponiveis = sorted(df_completo[df_completo[col_loja] == loja][col_concorrente].unique())
            concorrente = st.selectbox("Selecione o Concorrente:", concorrentes_disponiveis)
            if st.button("Entrar na Pesquisa 🚀", use_container_width=True, type="primary"):
                st.session_state.loja_sel = loja
                st.session_state.concorrente_sel = concorrente
                st.session_state.autenticado = True
                st.rerun()
        st.stop() 

    # --- TELA DE PESQUISA ---
    if st.sidebar.button("⬅️ Trocar Loja/Concorrente"):
        st.session_state.autenticado = False
        st.rerun()

    df_f = df_completo[
        (df_completo[col_loja] == st.session_state.loja_sel) & 
        (df_completo[col_concorrente] == st.session_state.concorrente_sel)
    ]

    comp_sel = st.sidebar.selectbox("Filtrar por Setor:", ["Todos"] + sorted(df_f[col_comprador].unique()))
    if comp_sel != "Todos":
        df_f = df_f[df_f[col_comprador] == comp_sel]

    st.image("banner.png", use_container_width=True)
    st.markdown('<div class="titulo-centralizado">Pesquisa de Preço</div>', unsafe_allow_html=True)
    
    if not df_f.empty:
        total_itens = len(df_f)
        itens_preenchidos = df_f[col_preco].apply(lambda x: str(x).strip() != "").sum()
        st.markdown(f'<div class="progresso-texto"><b>Progresso:</b> {itens_preenchidos} de {total_itens}</div>', unsafe_allow_html=True)
        st.progress(itens_preenchidos / total_itens if total_itens > 0 else 0)
        st.divider()

        # Seleção de Produto
        opcoes_menu = [f"{('✅' if str(row[col_preco]).strip() != '' else '❌')} {row[col_produto]}" 
                       for _, row in df_f.sort_values(by=col_produto).iterrows()]
        
        index_atual = min(st.session_state.prod_idx, len(opcoes_menu)-1 if opcoes_menu else 0)
        
        st.write("Selecione o Produto:")
        escolha_usuario = st.selectbox("", opcoes_menu, index=index_atual, label_visibility="collapsed")
        produto_sel = escolha_usuario[2:].strip() if escolha_usuario and len(escolha_usuario) > 2 else ""
        st.session_state.prod_idx = opcoes_menu.index(escolha_usuario) if escolha_usuario in opcoes_menu else 0

        df_item = df_f[df_f[col_produto] == produto_sel]
        if not df_item.empty:
            indice_real = df_item.index[0]

            with st.container(border=True):
                st.markdown(f"""
                    <div class="filter-info-container">
                        <span>Loja: <b>{st.session_state.loja_sel}</b></span> | 
                        <span>Concorrente: <b>{st.session_state.concorrente_sel}</b></span> | 
                        <span>Setor: <b>{comp_sel if comp_sel != "Todos" else "Todos"}</b></span>
                    </div>
                    """, unsafe_allow_html=True)
                
                c1, c2 = st.columns(2)
                with c1:
                    preco_novo = st.text_input("Preço (R$):", 
                                             value=str(df_item.iloc[0].get(col_preco, "")), 
                                             key=f"pr_{produto_sel}_{indice_real}")
                with c2:
                    obs_nova = st.text_input("Observação:", 
                                           value=str(df_item.iloc[0].get(col_obs, "")), 
                                           key=f"ob_{produto_sel}_{indice_real}")

            if st.button("💾 Salvar e Avançar ➡️", type="primary", use_container_width=True):
                salvar_dados(sheet, indice_real, preco_novo, obs_nova)
                if st.session_state.prod_idx < len(opcoes_menu) - 1:
                    st.session_state.prod_idx += 1
                    st.rerun()
                else:
                    st.success("✅ Pesquisa finalizada!")
    else:
        st.warning("Nenhum dado encontrado para esta combinação de loja e concorrente.")

except Exception as e:
    st.error(f"Erro inesperado: {str(e)}")
