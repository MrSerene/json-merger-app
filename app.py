import streamlit as st
import json
import zipfile
import time
import re
import pandas as pd
import io
# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="OEM JSON Merger Studio",
    page_icon="📦",
    layout="wide"
)

# =========================
# CLEANING ENGINE CONFIG
# =========================
REMOVE_VALUES = {"no", "not applicable", "not available", "0"}
REMOVE_EXTRA = {"available", "standard", "optional", "option", "0"}
BLANK_HEADERS = {"features", "options", "videos", "attachments"}

# =========================
# CLEANING ENGINE FUNCTIONS
# =========================
def clean_string_global(s):
    if not isinstance(s, str):
        return s
    s = s.replace("\n", " ").replace("\r", " ").replace("\t", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()

def clean_dots_spec_string(text):
    if not isinstance(text, str):
        return text
    protected = {}
    def protect_decimal(m):
        key = f"__DEC_{len(protected)}__"
        protected[key] = m.group(0)
        return key

    text = re.sub(r'\d+\.\d+|\.\d+', protect_decimal, text)
    text = re.sub(r'(?i)(?<=[a-z])\.', ' ', text)
    for k, v in protected.items():
        text = text.replace(k, v)
    return clean_string_global(text)

def normalize_text(text):
    text = clean_string_global(text)
    text = re.sub(r'^(?:\d+\s+)', '', text)
    text = re.sub(r'(?:\s+\d+)$', '', text)
    return text.lower().strip()

def is_blank_header(key, value):
    return key.lower() in BLANK_HEADERS and value in ("", None, [], {})

def is_spec_object(obj):
    return isinstance(obj, dict) and "label" in obj and "desc" in obj and isinstance(obj["desc"], str)

def is_zero_with_unit(desc):
    if not isinstance(desc, str):
        return False
    desc = desc.replace("\xa0", " ")
    desc = re.sub(r"\s+", " ", desc).lower().strip()
    numbers = re.findall(r'\d*\.?\d+', desc)
    if not numbers:
        return False
    try:
        return all(float(n) == 0 for n in numbers)
    except:
        return False

def clean_msrp_value(msrp):
    if msrp is None:
        return 0
    if isinstance(msrp, (int, float)):
        return msrp
    if isinstance(msrp, str):
        msrp = msrp.strip()
        try:
            value = float(msrp)
            return int(value) if value.is_integer() else value
        except ValueError:
            return 0
    return 0

def clean_msrp_and_countries(model):
    general = model.get("general", {})
    general["msrp"] = clean_msrp_value(general.get("msrp"))
    countries = general.get("countries", [])
    if not isinstance(countries, list) or sorted(countries) != ["CA", "US"]:
        general["countries"] = ["US", "CA"]
    model["general"] = general
    return model

def clean_specs_section(section, feature_list):
    if not isinstance(section, dict):
        return {}
    cleaned = {}
    for key, value in section.items():
        if not isinstance(value, dict):
            continue
        label = clean_string_global(value.get("label", ""))
        desc = value.get("desc", "")
        if not isinstance(desc, str):
            continue
        desc_clean = desc.strip().lower()

        if desc_clean == "yes":
            if label and label not in feature_list:
                feature_list.append(label)
        elif desc_clean in REMOVE_VALUES or desc_clean in REMOVE_EXTRA or is_zero_with_unit(desc):
            continue
        else:
            cleaned[key] = value
    return cleaned

def clean_specs_and_features(model):
    model.setdefault("general", {})
    model["general"]["msrp"] = clean_msrp_value(model["general"].get("msrp"))
    features = model.get("features", [])
    if not isinstance(features, list):
        features = []

    spec_headers = ["engine", "hydraulics", "electrical", "driveTrain", "weights", "measurements", "body", "operational", "other"]
    for header in spec_headers:
        if header in model:
            cleaned_section = clean_specs_section(model[header], features)
            if cleaned_section:
                model[header] = cleaned_section
            else:
                del model[header]
    model["features"] = features
    return model

def remove_cross_duplicates(model):
    features = model.get("features", [])
    options = model.get("options", [])
    if not isinstance(features, list): features = []
    if not isinstance(options, list): options = []

    seen = set()
    unique_features = []
    for item in features:
        norm = normalize_text(item)
        if norm and norm not in seen:
            seen.add(norm)
            unique_features.append(item)

    unique_options = []
    for item in options:
        norm = normalize_text(item)
        if norm and norm not in seen:
            seen.add(norm)
            unique_options.append(item)

    model["features"] = unique_features
    model["options"] = unique_options
    return model

def clean_meta_and_attachments(model):
    for k in ["_id", "updated_at", "created_at", "promotions"]:
        model.pop(k, None)
    general = model.get("general", {})
    if general.get("id") == 60733:
        del general["id"]
    meta = model.get("meta")
    if meta:
        if meta.get("source") == "CRS" or set(meta.keys()) == {"isAttachment", "isImplement"}:
            del model["meta"]
    return model

def clean_whole_json(obj):
    if is_spec_object(obj):
        return {k: clean_dots_spec_string(v) if isinstance(v, str) else v for k, v in obj.items()}
    if isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            cleaned_val = clean_whole_json(v)
            if is_blank_header(k, cleaned_val):
                continue
            new_dict[k] = cleaned_val
        return new_dict
    if isinstance(obj, list):
        return [clean_whole_json(x) for x in obj]
    if isinstance(obj, str):
        return clean_string_global(obj)
    return obj

def get_model_key(model):
    general = model.get("general", {})
    model_name = normalize_text(general.get("model", ""))
    year = str(general.get("year", "")).strip().lower()
    category = normalize_text(general.get("category", ""))
    return (model_name, year, category)

def remove_duplicate_models(models):
    unique_models = []
    seen = set()
    removed_rows = []
    for idx, model in enumerate(models):
        key = get_model_key(model)
        if key in seen:
            general = model.get("general", {})
            removed_rows.append({
                "Manufacturer": general.get("manufacturer", ""),
                "Model": general.get("model", ""),
                "Category": general.get("category", ""),
                "Subcategory": general.get("subcategory", ""),
                "Year": general.get("year", ""),
                "Removed Index": idx
            })
            continue
        seen.add(key)
        unique_models.append(model)
    return unique_models, removed_rows

# =========================
# CUSTOM CSS
# =========================
st.markdown("""
<style>
.block-container{ max-width:1200px; padding-top:2rem; }
.main-title{ text-align:center; font-size:42px; font-weight:700; margin-bottom:10px; }
.sub-title{ text-align:center; font-size:18px; color:#666; margin-bottom:30px; }
</style>
""", unsafe_allow_html=True)

# =========================
# HEADER
# =========================
st.markdown("""
<div class="main-title">OEM JSON Merger Studio</div>
<div class="sub-title">Upload JSON or ZIP files and generate a single merged/cleaned JSON file</div>
""", unsafe_allow_html=True)

# =========================
# TOOL MENU
# =========================
tool = st.sidebar.radio(
    "Select Tool",
    [
        "📦 JSON Merger",
        "🚀 All In One"
    ]
)

# =========================
# CORE FILE PARSER
# =========================
def parse_uploaded_files(uploaded_files):
    raw_data = []
    invalid_files = 0
    for uploaded_file in uploaded_files:
        try:
            if uploaded_file.name.lower().endswith(".json"):
                data = json.load(uploaded_file)
                if isinstance(data, list): raw_data.extend(data)
                else: raw_data.append(data)
            elif uploaded_file.name.lower().endswith(".zip"):
                with zipfile.ZipFile(uploaded_file, "r") as zip_ref:
                    for file_name in zip_ref.namelist():
                        if not file_name.lower().endswith(".json"): continue
                        try:
                            with zip_ref.open(file_name) as f:
                                data = json.load(f)
                                if isinstance(data, list): raw_data.extend(data)
                                else: raw_data.append(data)
                        except:
                            invalid_files += 1
        except:
            invalid_files += 1
    return raw_data, invalid_files

# =========================
# TOOL 1: 📦 JSON MERGER
# =========================
if tool == "📦 JSON Merger":
    uploaded_files = st.file_uploader("📂 Upload JSON or ZIP Files", type=["json", "zip"], accept_multiple_files=True, key="merger")

    if uploaded_files:
        start_time = time.time()
        total_files = len(uploaded_files)
        total_size = round(sum(file.size for file in uploaded_files) / (1024 * 1024), 2)
        
        progress = st.progress(0)
        merged_data, invalid_files = parse_uploaded_files(uploaded_files)
        progress.progress(1.0)

        # Sort Data
        merged_data = sorted(
            merged_data,
            key=lambda x: (str(x.get("manufacturer", "")), str(x.get("model", "")), str(x.get("year", "")))
        )
        elapsed = round(time.time() - start_time, 2)

        st.success(f"Successfully merged {len(merged_data):,} records from {total_files} files.")
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Files Uploaded", total_files)
        col2.metric("Final Records", len(merged_data))
        col3.metric("Invalid Files", invalid_files)
        col4.metric("Size (MB)", total_size)
        st.caption(f"Processed in {elapsed} seconds")

        with st.expander(f"Merged JSON Preview ({min(len(merged_data),10)} of {len(merged_data)} records)"):
            st.json(merged_data[:10], expanded=False)

        json_output = json.dumps(merged_data, indent=2, ensure_ascii=False)
        st.download_button(label="⬇ Download Merged JSON", data=json_output, file_name="merged_output.json", mime="application/json", use_container_width=True)
    else:
        st.info("Upload one or more JSON or ZIP files to begin merging.")

# =========================
# TOOL 2: 🚀 ALL IN ONE (MERGE + CLEAN)
# =========================
elif tool == "🚀 All In One":
    st.subheader("Processing Engine: Merge + Advanced Formatting & Cleaning")
    uploaded_files = st.file_uploader("📂 Upload JSON or ZIP Files for Deep Cleaning", type=["json", "zip"], accept_multiple_files=True, key="cleaner")

    if uploaded_files:
        start_time = time.time()
        total_files = len(uploaded_files)
        total_size = round(sum(file.size for file in uploaded_files) / (1024 * 1024), 2)
        
        progress = st.progress(0)
        raw_data, invalid_files = parse_uploaded_files(uploaded_files)
        progress.progress(0.4)

        # 1. Run Pipeline Cleaners
        cleaned_models = []
        for model in raw_data:
            model = clean_msrp_and_countries(model)
            model = clean_specs_and_features(model)
            model = remove_cross_duplicates(model)
            model = clean_meta_and_attachments(model)
            model = clean_whole_json(model)
            cleaned_models.append(model)
        
        progress.progress(0.7)

        # 2. Remove Duplicate Models
        final_cleaned_models, removed_rows = remove_duplicate_models(cleaned_models)
        
        # 3. Sort Data
        final_cleaned_models = sorted(
            final_cleaned_models,
            key=lambda x: (str(x.get("general", {}).get("manufacturer", "")), str(x.get("general", {}).get("model", "")), str(x.get("general", {}).get("year", "")))
        )
        
        progress.progress(1.0)
        elapsed = round(time.time() - start_time, 2)

        st.success(f"🔥 Optimization Complete! Processed {len(final_cleaned_models):,} clean records.")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Input Records", len(raw_data))
        col2.metric("Cleaned Records", len(final_cleaned_models))
        col3.metric("Duplicates Removed", len(removed_rows))
        col4.metric("Total Size (MB)", total_size)
        st.caption(f"Engine Runtime: {elapsed} seconds")

        # Excel Report Generation in Memory
        excel_buffer = io.BytesIO()
        if removed_rows:
            df_report = pd.DataFrame(removed_rows)
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df_report.to_excel(writer, index=False, sheet_name='Removed Duplicates')
            excel_data = excel_buffer.getvalue()
        else:
            excel_data = None

        # Download Buttons
        dl_col1, dl_col2 = st.columns(2)
        
        with dl_col1:
            json_output = json.dumps(final_cleaned_models, indent=2, ensure_ascii=False)
            st.download_button(
                label="⬇ Download Cleaned & Merged JSON",
                data=json_output,
                file_name="cleaned_oem_output.json",
                mime="application/json",
                use_container_width=True
            )
            
        with dl_col2:
            if excel_data:
                st.download_button(
                    label="📄 Download Duplicates Excel Report",
                    data=excel_data,
                    file_name="removed_duplicate_models.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                st.button("ℹ️ No Duplicates Found (Excel Empty)", disabled=True, use_container_width=True)

        with st.expander("Preview Optimized JSON (First 10 Records)"):
            st.json(final_cleaned_models[:10], expanded=False)
    else:
        st.info("Upload JSON/ZIP files inside 'All In One' mode to automatically execute cross-field parsing, MSRP formatting, string conditioning, and multi-key deduplication.")
