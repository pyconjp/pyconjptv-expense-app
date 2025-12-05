import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path

DATA_FILE = Path("expenses.csv")

st.title("経費入力アプリ (デモ)")

with st.form("expense_form"):
    date = st.date_input("日付", value=datetime.now().date())
    category = st.selectbox("カテゴリ", ["交通費", "宿泊費", "食費", "備品", "その他"])
    amount = st.number_input("金額 (JPY)", min_value=0.0, step=100.0, format="%.2f")
    note = st.text_input("備考 (任意)")
    submitted = st.form_submit_button("追加")

if submitted:
    row = {
        "date": date.isoformat(),
        "category": category,
        "amount": float(amount),
        "note": note,
        "created_at": datetime.now().isoformat(),
    }
    if DATA_FILE.exists():
        df = pd.read_csv(DATA_FILE)
        df = df.append(row, ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_csv(DATA_FILE, index=False)
    st.success("保存しました")

if DATA_FILE.exists():
    if st.checkbox("履歴を表示する"):
        df = pd.read_csv(DATA_FILE)
        st.dataframe(df.sort_values("created_at", ascending=False))
else:
    st.info("まだデータがありません。上のフォームで追加してください。")
