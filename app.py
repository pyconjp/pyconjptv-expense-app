import json
import uuid
import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path

CLAIMS_DIR = Path("claims")

st.title("経費入力アプリ (デモ) — フェーズ2: 入力フォーム拡張")

# 経費明細の状態管理（items は dict のメソッド名と衝突するため避ける）
if "expense_items" not in st.session_state:
    st.session_state["expense_items"] = []

st.header("経費明細（編集可能なテーブル）")
import pandas as pd

df_items = pd.DataFrame(st.session_state.get("expense_items", []))
if df_items.empty:
    # 空DataFrameでも支払日をオブジェクト型にしておく（FLOAT推論を防ぐ）
    df_items = pd.DataFrame(
        {
            "支払日": pd.Series([], dtype="object"),
            "店名": pd.Series([], dtype="object"),
            "金額": pd.Series([], dtype="float"),
            "内容": pd.Series([], dtype="object"),
        }
    )
else:
    # NaN を None にして dtype をオブジェクトへ寄せる
    df_items = df_items.where(pd.notna(df_items), None)
    # 支払日が float/NaN の場合は None に置換し、datetime.date へ変換
    if "支払日" in df_items.columns:
        df_items["支払日"] = df_items["支払日"].apply(
            lambda v: None
            if (v is None or (isinstance(v, float) and pd.isna(v)))
            else v
        )
        try:
            dt = pd.to_datetime(df_items["支払日"], errors="coerce")
            df_items["支払日"] = dt.dt.date
        except Exception:
            # 変換失敗時はそのまま（オブジェクト型維持）
            pass

edited = st.data_editor(
    df_items,
    column_config={
        "支払日": st.column_config.DateColumn("支払日", format="YYYY-MM-DD"),
        "店名": st.column_config.TextColumn("店名"),
        "金額": st.column_config.NumberColumn("金額", step=100, format="%d"),
        "内容": st.column_config.TextColumn("内容"),
    },
    num_rows="dynamic",
    key="items_table",
)

# セッションへ反映（空行は除外）
st.session_state["expense_items"] = []
for _, row in edited.iterrows():
    store = row.get("店名")
    content = row.get("内容")
    amount = row.get("金額")
    # リストが来た場合は先頭要素に正規化
    if isinstance(store, list):
        store = store[0] if store else ""
    if isinstance(content, list):
        content = content[0] if content else ""
    if isinstance(amount, list):
        amount = amount[0] if amount else 0
    if not (store or content or amount not in [None, ""]):
        continue
    val_date = row.get("支払日")
    iso_date = val_date.isoformat() if hasattr(val_date, "isoformat") else str(val_date)
    amt = amount
    try:
        amt_f = float(amt) if amt not in [None, ""] else 0.0
    except Exception:
        amt_f = 0.0
    st.session_state["expense_items"].append(
        {
            "支払日": iso_date,
            "店名": store or "",
            "金額": amt_f,
            "内容": content or "",
        }
    )

# 合計の即時更新（明細の合計）
items_sum = sum(
    (item.get("金額", 0) or 0) for item in st.session_state.get("expense_items", [])
)
total_amount = items_sum
st.metric("合計金額 (JPY)", f"{total_amount:.0f}")

st.header("申請情報と添付ファイル")
with st.form("expense_form"):
    applicant = st.text_input("申請者名")
    title = st.text_input("タイトル (申請の概要)")
    expense_type = st.selectbox(
        "経費種別", ["旅費交通費", "消耗品費", "交際費", "雑費", "その他"]
    )
    claim_date = st.date_input("申請日", value=datetime.now().date())

    st.subheader("振込先情報")
    bank_name = st.text_input("銀行名")
    branch_name = st.text_input("支店名")
    account_type = st.selectbox("口座種別", ["普通", "当座", "貯蓄"], index=0)
    account_number = st.text_input("口座番号")
    account_holder = st.text_input("口座名義 (カナ推奨)")

    note = st.text_area("備考 (任意)")
    uploaded_files = st.file_uploader(
        "領収書（複数可）",
        accept_multiple_files=True,
        type=["png", "jpg", "jpeg", "pdf"],
    )
    submit = st.form_submit_button("申請を送信")

if submit:
    errors = []
    if not applicant:
        errors.append("申請者名は必須です。")
    if not title:
        errors.append("タイトルは必須です。")
    if not st.session_state.get("expense_items"):
        errors.append("少なくとも1件の経費項目を追加してください。")
    if not bank_name or not branch_name or not account_number or not account_holder:
        errors.append("振込先情報はすべて必須です。")

    # 厳密なバリデーション（フェーズ3）
    # 明細の各行チェック
    for i, it in enumerate(st.session_state.get("expense_items", []), start=1):
        # 日付必須
        if not it.get("支払日"):
            errors.append(f"明細 {i} の支払日は必須です。")
        # 金額は正の数
        amt = it.get("金額")
        try:
            amt_f = float(amt)
        except Exception:
            amt_f = -1
        if amt_f <= 0:
            errors.append(f"明細 {i} の金額は 0 より大きい必要があります。")

    # 口座番号は数字のみ、7桁以上
    if account_number:
        if not account_number.isdigit():
            errors.append("口座番号は数字のみで入力してください。")
        elif len(account_number) < 7:
            errors.append("口座番号は7桁以上で入力してください。")

    # 合計検算（明細合計と一致）
    calc_sum = sum(
        (it.get("金額") or 0) for it in st.session_state.get("expense_items", [])
    )
    if abs(calc_sum - total_amount) > 0.0001:
        errors.append("合計金額が明細の合計と一致していません。")

    if errors:
        for e in errors:
            st.error(e)
    else:
        claim_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
        dest_dir = CLAIMS_DIR / claim_id
        dest_dir.mkdir(parents=True, exist_ok=True)

        saved_paths = []
        if uploaded_files:
            for up in uploaded_files:
                data = up.read()
                dest = dest_dir / up.name
                with open(dest, "wb") as f:
                    f.write(data)
                saved_paths.append(str(dest.as_posix()))

        row = {
            "claim_id": claim_id,
            "申請日": claim_date.isoformat(),
            "申請者名": applicant,
            "タイトル": title,
            "経費種別": expense_type,
            "合計金額": float(calc_sum),
            "経費項目リスト": json.dumps(
                st.session_state.get("expense_items", []), ensure_ascii=False
            ),
            "備考": note,
            "attachments": json.dumps(saved_paths, ensure_ascii=False),
            "銀行名": bank_name,
            "支店名": branch_name,
            "口座種別": account_type,
            "口座番号": account_number,
            "口座名義": account_holder,
            "created_at": datetime.now().isoformat(),
        }
        # JSONへ保存（CSVは廃止）
        json_path = dest_dir / "claim.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(row, f, ensure_ascii=False, indent=2)

        st.session_state["expense_items"] = []
        st.success(f"申請を保存しました。保存先: {dest_dir.as_posix()}")
        if saved_paths:
            st.write("保存したファイル:")
            for p in saved_paths:
                st.write(p)

if st.checkbox("履歴を表示する"):
    # claims配下の各申請フォルダの claim.json を読み込んで表示
    records = []
    if CLAIMS_DIR.exists():
        for d in sorted(CLAIMS_DIR.glob("*/claim.json")):
            try:
                with open(d, "r", encoding="utf-8") as f:
                    rec = json.load(f)
                records.append(rec)
            except Exception:
                pass
    if records:
        df_hist = pd.DataFrame(records)
        df_hist = df_hist.sort_values("created_at", ascending=False)
        st.dataframe(df_hist)
    else:
        st.info("まだデータがありません。上のフォームで追加してください。")
