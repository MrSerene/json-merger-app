import streamlit as st
import json
import zipfile
import time
import pandas as pd

# =========================
# PAGE CONFIG
# =========================

st.set_page_config(
    page_title="OEM JSON Merger Studio",
    page_icon="🚀",
    layout="wide"
)

# =========================
# CUSTOM CSS
# =========================

st.markdown("""
<style>

.block-container{
    max-width:1200px;
    padding-top:2rem;
}

h1{
    text-align:center;
}

.main-title{
    text-align:center;
    font-size:42px;
    font-weight:700;
    margin-bottom:0;
}

.sub-title{
    text-align:center;
    font-size:18px;
    color:#999;
    margin-bottom:30px;
}

.stMetric{
    background:#262730;
    padding:15px;
    border-radius:12px;
    border:1px solid #444;
}

div[data-testid="stMetric"]{
    background:#262730;
    border:1px solid #444;
    padding:15px;
    border-radius:12px;
}

</style>
""", unsafe_allow_html=True)

# =========================
# HEADER
# =========================

st.markdown("""
<div class="main-title">
🚀 OEM JSON Merger Studio
</div>

<div class="sub-title">
Merge multiple JSON and ZIP files into a single JSON output
</div>
""", unsafe_allow_html=True)

# =========================
# FILE UPLOADER
# =========================

uploaded_files = st.file_uploader(
    "📂 Drag & Drop JSON or ZIP Files",
    type=["json", "zip"],
    accept_multiple_files=True
)

# =========================
# PROCESS FILES
# =========================

if uploaded_files:

    start_time = time.time()

    merged_data = []

    total_files = len(uploaded_files)
    invalid_files = 0

    total_size = round(
        sum(file.size for file in uploaded_files) / (1024 * 1024),
        2
    )

    progress = st.progress(0)

    for index, uploaded_file in enumerate(uploaded_files):

        try:

            # =====================
            # JSON FILE
            # =====================

            if uploaded_file.name.lower().endswith(".json"):

                data = json.load(uploaded_file)

                if isinstance(data, list):
                    merged_data.extend(data)
                else:
                    merged_data.append(data)

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

                                if isinstance(data, list):
                                    merged_data.extend(data)
                                else:
                                    merged_data.append(data)

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

    elapsed = round(time.time() - start_time, 2)

    st.success("✅ Merge Completed Successfully")

    st.balloons()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Files Uploaded", total_files)

    with col2:
        st.metric("Final Records", len(merged_data))

    with col3:
        st.metric("Invalid Files", invalid_files)

    with col4:
        st.metric("Size (MB)", total_size)

    st.info(f"⏱ Processed in {elapsed} seconds")

    # =========================
    # PREVIEW
    # =========================

    with st.expander("📋 Preview First 10 Records"):

        preview_rows = []

        for item in merged_data[:10]:

            preview_rows.append({
                "Manufacturer": item.get("manufacturer", ""),
                "Model": item.get("model", ""),
                "Year": item.get("year", "")
            })

        if preview_rows:
            st.dataframe(
                pd.DataFrame(preview_rows),
                use_container_width=True
            )
        else:
            st.write("No records found")

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
        mime="application/json",
        use_container_width=True
    )

else:

    st.info(
        "Upload one or more JSON or ZIP files to begin merging."
    )
