import streamlit as st
import pandas as pd
from datetime import datetime
import urllib.parse

# 设置网页标题
st.set_page_config(page_title="SADE 采购决策支持系统", layout="centered")

# ===============================
# 1. 读取数据
# ===============================
@st.cache_data # 增加缓存，避免每次操作都重新读取Excel
def load_data():
    try:
        return pd.read_excel("contracts_b.xlsx")
    except:
        st.error("找不到 contracts_b.xlsx 文件，请确保它与脚本在同一目录下。")
        return None

contracts = load_data()

# ===============================
# 2. 采购规则函数 (保持原逻辑不变)
# ===============================
def rule_distributor_purchase(quantity, package, DE):
    return (package == "couronne" or DE < 125 or (DE < 200 and quantity < 1200))

def rule_contract_purchase(quantity, package, DE):
    return ((package == "barre" and 125 <= DE <= 200 and 1200 <= quantity)
            or (package == "barre" and 225 <= DE <= 315 and quantity < 2000))

def rule_factory_purchase(quantity, package, DE):
    return ((package == "barre" and 225 <= DE <= 315 and 2000 <= quantity) or package.lower() == "touret")

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
st.subheader("Decision Support for Pipes & Supplies")

if contracts is not None:
    # 侧边栏或主界面输入
    with st.form("purchase_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            material_choice = st.selectbox("Matériau:", sorted(contracts["Material"].dropna().unique().tolist()))
            package_choice = st.selectbox("Conditionnement:", ["couronne", "barre", "touret"])
            qty_input = st.number_input("Quantité (ml):", min_value=0, step=1)
        
        with col2:
            de_choice = st.selectbox("DE (Diamètre Extérieur):", sorted(contracts["DE"].dropna().unique().tolist()))
            pn_choice = st.selectbox("PN (Pression Nominale):", sorted(contracts["PN"].dropna().unique().tolist()))
        
        submit_btn = st.form_submit_button("Run Decision", type="primary")

    if submit_btn:
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
                
            elif rule_distributor_purchase_dipipe(qty_input, de_choice):
                result_text = "Decision: Consultation Négoce"
                
        else:
            # Touret 逻辑
           if package_choice.lower() == "touret":
                res = contracts[(contracts["Package"].str.strip().str.lower() == "touret") & (contracts["Material"] == material_choice) & (contracts["DE"] == de_choice)]
                if not res.empty:
                    row = res.iloc[0]
                    result_text = f"Supplier: {row['Supplier']}, Price: {row['Price']:.2f} €/ml\nDécision: Consultation Elydan (Délai 4-6 sem)"
                    target_supplier = "Elydan"
                else:
                    result_text = "Decision: Contact Category Manager (Zélie XIA)"

            elif rule_factory_purchase(qty_input, package_choice, de_choice):
                result_text = "Decision: Consultation Fabricant sous contrat (Elydan, Centraltubi)"
                target_supplier = "Elydan"
                ref = get_contract_price_text(material_choice, de_choice, pn_choice, today)
                if ref: result_text += f"\n\n{ref}"

    # 2️⃣ 经销商优先
          elif rule_distributor_purchase(qty_input, package_choice, de_choice):
                result_text = "Decision: Consultation Négoce"


    # 3️⃣ 合同采购
          elif rule_contract_purchase(qty_input, package_choice, de_choice):
                valid = contracts[(contracts["Material"] == material_choice) & (contracts["DE"] == de_choice) & (contracts["PN"] == pn_choice)]
                if not valid.empty:
                    top_sorted = valid_contracts.sort_values("Price").head(2)
                    text = "✅ Decision: Application tarif contractuelle\n\n"
                    for i, row in enumerate(top_sorted.itertuples(), 1):
                    text += f"Supplier top{i}: {row.Supplier}, Price top{i}: {row.Price:.2f} €/ml\n"
                    return text + "\nElydan : Supposé en stock, Expédition sous 72H, faire valider le délai par fournisseur"
                else:
                    return "❌ Decision: Contact Category Manager Achats (Zélie XIA)"
                return "ℹ️ Decision: Contact Category Manager Achats (Zélie XIA) pour analyse spécifique."


        # --- 显示结果 ---
        st.divider()
        st.success(result_text)

        # --- 邮件生成 ---
        if "Consultation" in result_text :
            st.info("📧 **Brouillon d'Email de Consultation**")
            subject, body = generate_email_template(target_supplier, material_choice, qty_input, de_choice, pn_choice, package_choice)
            
            # 邮件预览框
            st.text_area("Copier le contenu :", value=body, height=250)
            
            # Outlook 按钮
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





