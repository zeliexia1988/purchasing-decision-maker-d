import streamlit as st
import pandas as pd
from datetime import datetime
import urllib.parse

# 设置网页标题
st.set_page_config(page_title="SADE 采购决策支持系统", layout="centered")

# ===============================
# 1. 读取数据
# ===============================
@st.cache_data
def load_data():
    try:
        return pd.read_excel("contracts_b.xlsx")
    except:
        st.error("找不到 contracts_b.xlsx 文件，请确保它与脚本在同一目录下。")
        return None

contracts = load_data()

# ===============================
# 2. 采购规则函数
# ===============================
def rule_distributor_purchase(quantity, package, DE):
    return (package == "couronne" or DE < 125 or (DE < 200 and quantity < 1200))

def rule_contract_purchase(quantity, package, DE):
    return ((package == "barre" and 125 <= DE <= 200 and 1200 <= quantity)
            or (package == "barre" and 225 <= DE <= 315 and quantity < 2000))

def rule_factory_purchase(quantity, package, DE):
    return ((package == "barre" and 225 <= DE <= 315 and 2000 <= quantity) or package.lower() == "touret" or (package == "barre" and 315 < DE))

def rule_distributor_purchase_dipipe(quantity, DE):
    return (DE < 80)

def rule_contract_purchase_dipipe(quantity, DE):
    return ((DE >= 80 and quantity <= 968) or (DE >= 100 and quantity <= 891) or 
            (DE >= 125 and quantity <= 770) or (DE >= 150 and quantity <= 594) or 
            (DE >= 200 and quantity <= 440) or (DE >= 250 and quantity <= 396) or 
            (DE >= 300 and quantity <= 264))

def rule_factory_purchase_dipipe(quantity, DE):
    return not rule_contract_purchase_dipipe(quantity, DE) and DE >= 80

def get_contract_price_text(material, DE, PN, today, top_n=2):
    valid_contracts = contracts[
        (contracts["Material"] == material) &
        (contracts["Valid_Until"] >= today) &
        (contracts["DE"] == int(DE)) &
        (contracts["PN"] == float(PN))
    ]
    if valid_contracts.empty: return None
    top_sorted = valid_contracts.sort_values("Price").head(top_n)
    text = "Prix contractuel (pour reference) :\n"
    for i, row in enumerate(top_sorted.itertuples(), 1):
        text += f"- {row.Supplier}: {row.Price:.2f} €/ml\n"
    return text

def generate_email_template(supplier, material, quantity, de, pn, package):
    subject = f"Demande de prix - {material} - DE{de} PN{pn}"
    body = f"""Bonjour,

Dans le cadre d'un nouveau projet, nous souhaiterions obtenir votre meilleure offre de prix et délai pour le matériel suivant :

- Produit : {material}
- Diamètre Extérieur (DE) : {de}
- Pression Nominale (PN) : {pn}
- Conditionnement : {package}
- Quantité : {quantity} ml

Merci de nous préciser également :
1. Vos frais de transport Franco.
2. Votre délai de fabrication/livraison actuel.

Dans l'attente de votre retour, je reste à votre disposition.

Cordialement,
[Votre Signature]"""
    return subject, body

# ===============================
# 3. Streamlit 界面布局
# ===============================
st.title("🛡️ SADE Purchasing Decision")
st.subheader("Aide à Décision Achats Tuyaux & Fournisseur")

if contracts is not None:
    with st.form("purchase_form"):
        col1, col2 = st.columns(2)
        # 准备选项列表，在首位添加空值
        mat_options = [""] + sorted(contracts["Material"].dropna().unique().tolist())
        pkg_options = ["", "couronne", "barre", "touret"]
        de_options = [""] + sorted(contracts["DE"].dropna().unique().tolist())
        pn_options = [""] + sorted(contracts["PN"].dropna().unique().tolist())
        with col1:
            # index=0 表示默认选择列表中的第一个（即空值 ""）
            material_choice = st.selectbox("Matériau:", options=mat_options, index=0)
            package_choice = st.selectbox("Conditionnement:", options=pkg_options, index=0)
            qty_input = st.number_input("Quantité (ml):", min_value=0, step=1, value=0)
        
        with col2:
            de_choice = st.selectbox("DE (Diamètre Extérieur)/DN (Diamètre Nominal):", options=de_options, index=0)
            pn_choice = st.selectbox("PN (Pression Nominale):", options=pn_options, index=0)
        
        submit_btn = st.form_submit_button("Run Decision", type="primary")
        
    if submit_btn:
        # 增加一个校验：如果用户没有选择必填项，给出警告
        if not material_choice or not package_choice or not de_choice or not pn_choice:
            st.warning("⚠️ Veuillez remplir tous les champs (Matériau, Conditionnement, DE, PN).")
        else:
            today = datetime.today()
            result_text = ""
            target_supplier = ""

        # --- 决策逻辑 ---
        if "fonte" in material_choice.lower():
            if rule_factory_purchase_dipipe(qty_input, de_choice):
                result_text = "Decision: Consultation Electrosteel sous contrat"
                target_supplier = "Electrosteel"
            elif rule_contract_purchase_dipipe(qty_input, de_choice):
                result_text = "Decision: Application tarif contractuel Electrosteel"
                target_supplier = "Electrosteel"
            elif rule_distributor_purchase_dipipe(qty_input, de_choice):
                result_text = "Decision: Consultation Négoce"
                target_supplier = "votre contact Commercial"
        else:
            # 1️⃣ Touret 逻辑
            if package_choice.lower() == "touret":
                res = contracts[(contracts["Package"].str.strip().str.lower() == "touret") & 
                                (contracts["Material"] == material_choice) & 
                                (contracts["DE"] == de_choice)]
                if not res.empty:
                    row = res.iloc[0]
                    result_text = "✅Décision: Consultation Elydan (Délai 4-6 sem)\n" + "Prix contractuel (pour reference) :\n" + f"Supplier: {row['Supplier']}, Price: {row['Price']:.2f} €/ml"
                    target_supplier = "Elydan"
                else:
                    result_text = "Decision: Contact Category Manager (Zélie XIA)"

            # 2️⃣ 厂家优先
            elif rule_factory_purchase(qty_input, package_choice, de_choice):
                result_text = "✅Decision: Consultation Fabricant sous contrat (Elydan, Centraltubi)"
                target_supplier = "Elydan"
                ref = get_contract_price_text(material_choice, de_choice, pn_choice, today)
                if ref: result_text += f"\n\n{ref}"

            # 3️⃣ 经销商优先
            elif rule_distributor_purchase(qty_input, package_choice, de_choice):
                result_text = "✅Decision: Consultation Négoce"
                target_supplier = "votre contact Commercial"

            # 4️⃣ 合同采购
            elif rule_contract_purchase(qty_input, package_choice, de_choice):
                result_text = "✅Decision: Application tarif contractuelle\n"                                
                ref = get_contract_price_text(material_choice, de_choice, pn_choice, today)
                if ref: 
                    result_text += f"\n\n{ref}\n" + "Elydan : Supposé en stock, Expédition sous 72H, faire valider le délai par fournisseur"
                else:
                    result_text = "ℹ️ Decision: Contact Category Manager Achats (Zélie XIA) pour analyse spécifique."
            else:
                result_text = "ℹ️ Decision: Contact Category Manager Achats (Zélie XIA) pour analyse spécifique."

        # --- 显示结果 ---
        st.divider()
        if "❌" in result_text:
            st.error(result_text)
        else:
            st.success(result_text)

        # --- 邮件生成 ---
        if "Consultation" in result_text:
            st.info("📧 **Brouillon d'Email de Consultation**")
            subject, body = generate_email_template(target_supplier, material_choice, qty_input, de_choice, pn_choice, package_choice)
            
            st.text_area("Copier le contenu :", value=body, height=250)
            
            safe_subject = urllib.parse.quote(subject)
            safe_body = urllib.parse.quote(body)
            mailto_link = f"mailto:?subject={safe_subject}&body={safe_body}"
            
            st.markdown(f'''
                <a href="{mailto_link}" target="_blank">
                    <button style="
                        background-color: #0078d4;
                        color: white;
                        padding: 10px 20px;
                        border: none;
                        border-radius: 5px;
                        cursor: pointer;
                        font-weight: bold;">
                        📩 Ouvrir dans Outlook
                    </button>
                </a>
            ''', unsafe_allow_html=True)





















