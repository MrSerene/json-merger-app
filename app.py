import streamlit as st
import json
import zipfile
from io import BytesIO

# =========================
# CONFIG
# =========================
USERNAME = "yash"
PASSWORD = "merger2026"

st.set_page_config(
    page_title="JSON Merger",
    page_icon="📦",
    layout="wide"
)

# =========================
# LOGIN
# =========================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:

    st.title("🔐 JSON Merger Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):

        if username == USERNAME and password == PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid username or password")

    st.stop()

# =========================
# APP HEADER
# =========================
st.title("📦 JSON Merger Pro")
st.markdown(
    "Upload multiple JSON files or ZIP files and download a merged JSON."
)

# =========================
# FILE UPLOAD
# =========================
uploaded_files = st.file_uploader(
    "Drag & Drop JSON or ZIP Files",
    type=["json", "zip"],
    accept_multiple_files=True
)

if uploaded_files:

    merged_data = []
    seen = set()

    total_files = len(uploaded_files)
    invalid_files = 0
    duplicates_removed = 0

    progress = st.progress(0)

    for index, uploaded_file in enumerate(uploaded_files):

        try:

            # =====================
            # JSON FILE
            # =====================
            if uploaded_file.name.lower().endswith(".json"):

                data = json.load(uploaded_file)

                if not isinstance(data, list):
                    data = [data]

                for item in data:

                    key = (
                        str(item.get("manufacturer", "")).strip().lower(),
                        str(item.get("model", "")).strip().lower(),
                        str(item.get("year", "")).strip()
                    )

                    if key in seen:
                        duplicates_removed += 1
                        continue

                    seen.add(key)
                    merged_data.append(item)

            # =====================
            # ZIP FILE
            # =====================
            elif uploaded_file.name.lower().endswith(".zip"):

                with zipfile.ZipFile(uploaded_file, "r") as zip_ref:

                    for file_name in zip_ref.namelist():

                        if not file_name.lower().endswith(".json"):
                            continue

                        try:

                            with zip_ref.open(file_name) as f:

                                data = json.load(f)

                                if not isinstance(data, list):
                                    data = [data]

                                for item in data:

                                    key = (
                                        str(item.get("manufacturer", "")).strip().lower(),
                                        str(item.get("model", "")).strip().lower(),
                                        str(item.get("year", "")).strip()
                                    )

                                    if key in seen:
                                        duplicates_removed += 1
                                        continue

                                    seen.add(key)
                                    merged_data.append(item)

                        except Exception:
                            invalid_files += 1

        except Exception:
            invalid_files += 1

        progress.progress((index + 1) / total_files)

    # =========================
    # SORT DATA
    # =========================
    merged_data = sorted(
        merged_data,
        key=lambda x: (
            str(x.get("manufacturer", "")),
            str(x.get("model", "")),
            str(x.get("year", ""))
        )
    )

    # =========================
    # STATS
    # =========================
    st.success("Merge Completed")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Files Uploaded", total_files)

    with col2:
        st.metric("Final Records", len(merged_data))

    with col3:
        st.metric("Duplicates Removed", duplicates_removed)

    with col4:
        st.metric("Invalid Files", invalid_files)

    # =========================
    # PREVIEW
    # =========================
    with st.expander("Preview First 10 Records"):
        st.json(merged_data[:10])

    # =========================
    # DOWNLOAD
    # =========================
    json_output = json.dumps(
        merged_data,
        indent=2,
        ensure_ascii=False
    )

    st.download_button(
        label="⬇ Download Merged JSON",
        data=json_output,
        file_name="merged_output.json",
        mime="application/json"
    )

else:
    st.info("Upload one or more JSON/ZIP files to begin.")