import json
import uuid
import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path

DATA_FILE = Path("expenses.csv")
CLAIMS_DIR = Path("claims")

st.title("経費入力アプリ (デモ) - フェーズ1: 添付ファイル対応")

with st.form("expense_form"):
    date = st.date_input("日付", value=datetime.now().date())
    category = st.selectbox("カテゴリ", ["交通費", "宿泊費", "食費", "備品", "その他"])
    amount = st.number_input("金額 (JPY)", min_value=0.0, step=100.0, format="%.2f")
    note = st.text_input("備考 (任意)")
    uploaded_files = st.file_uploader(
        "領収書（複数可）",
        accept_multiple_files=True,
        type=["png", "jpg", "jpeg", "pdf"],
    )
    submitted = st.form_submit_button("追加")

if submitted:
    claim_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
    dest_dir = CLAIMS_DIR / claim_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    if uploaded_files:
        for up in uploaded_files:
            # Streamlit UploadedFile has .getbuffer() or .read()
            data = up.read()
            dest = dest_dir / up.name
            with open(dest, "wb") as f:
                f.write(data)
            saved_paths.append(str(dest.as_posix()))

    row = {
        "claim_id": claim_id,
        "date": date.isoformat(),
        "category": category,
        "amount": float(amount),
        "note": note,
        "attachments": json.dumps(saved_paths, ensure_ascii=False),
        "created_at": datetime.now().isoformat(),
    }

    if DATA_FILE.exists():
        df = pd.read_csv(DATA_FILE)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])

    df.to_csv(DATA_FILE, index=False)
    st.success("保存しました。保存先: {}".format(dest_dir.as_posix()))
    if saved_paths:
        st.write("保存したファイル:")
        for p in saved_paths:
            st.write(p)

if DATA_FILE.exists():
    if st.checkbox("履歴を表示する"):
        df = pd.read_csv(DATA_FILE)
        st.dataframe(df.sort_values("created_at", ascending=False))
else:
    st.info("まだデータがありません。上のフォームで追加してください。")
