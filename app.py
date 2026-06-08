import streamlit as st
import json
import zipfile
import time
import re
import io

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="OEM JSON Studio PRO",
    page_icon="🚀",
    layout="wide"
)

# =========================
# CONFIG & MAPS
# =========================
REMOVE_VALUES = {"no", "not applicable", "not available", "0"}
REMOVE_EXTRA = {"available", "standard", "optional", "option", "0"}
BLANK_HEADERS = {"features", "options", "videos", "attachments"}

NUMBER_MAP = {
    "0": "Zero", "1": "One", "2": "Two", "3": "Three",
    "4": "Four", "5": "Five", "6": "Six", "7": "Seven",
    "8": "Eight", "9": "Nine"
}

# Suffix conversion map for dynamic true-duplicates
INDEX_WORD_MAP = {
    1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 
    6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"
}

# =========================
# CAMELCASE HELPERS
# =========================
def number_to_word(num):
    return ''.join(NUMBER_MAP[d] for d in num if d in NUMBER_MAP)

def to_camel_case(text, keep_number=False):
    """
    keep_number = True  → convert to word (1→One)
    keep_number = False → remove numbers entirely
    """
    text = re.sub(r'[^a-zA-Z0-9]+', ' ', text)
    words = re.findall(r'[A-Za-z0-9]+', text)
    cleaned = []

    for word in words:
        if word.isdigit():
            if keep_number:
                cleaned.append(number_to_word(word))
            continue

        if re.search(r'[a-zA-Z]', word) and re.search(r'\d', word):
            match = re.match(r'([a-zA-Z]+)(\d+)$', word)
            if match:
                letters, digits = match.groups()
                if keep_number:
                    word = letters + number_to_word(digits)
                else:
                    word = letters
                cleaned.append(word)
            else:
                word = re.sub(r'\d+', '', word)
                if word:
                    cleaned.append(word)
        else:
            cleaned.append(word)

    if not cleaned:
        return ""

    return cleaned[0].lower() + ''.join(w.capitalize() for w in cleaned[1:])

def get_base_label(label):
    return re.sub(r'\d+', '', label).strip().lower()

# =========================
# DYNAMIC SMART CAMELCASE PROCESSOR
# =========================
def process_json_keys_to_camel(data):
    if isinstance(data, dict):
        # 1. Analyze current level to find conflicting labels with DIFFERENT desc values
        base_label_descs = {} # Format: { base_label: [desc1, desc2] }
        
        for value in data.values():
            if isinstance(value, dict) and "label" in value and "desc" in value:
                base = get_base_label(value["label"])
                desc_val = str(value["desc"]).strip()
                if base not in base_label_descs:
                    base_label_descs[base] = []
                if desc_val not in base_label_descs[base]:
                    base_label_descs[base].append(desc_val)

        # 2. Build the updated block
        new_dict = {}
        # Keep track of active word index mapping for true uniqueness tracking
        base_label_tracking = {} 

        for key, value in data.items():
            if isinstance(value, dict) and "label" in value and "desc" in value:
                label = value["label"]
                base = get_base_label(label)
                desc_val = str(value["desc"]).strip()

                # Rule Condition Check: Same base label but multiple unique descriptions exist
                if len(base_label_descs.get(base, [])) > 1:
                    # Treat as dynamic dynamic sequence (Applies word-suffixes: One, Two, Three)
                    correct_key = to_camel_case(label, keep_number=False)
                    
                    if base not in base_label_tracking:
                        base_label_tracking[base] = []
                    
                    if desc_val not in base_label_tracking[base]:
                        base_label_tracking[base].append(desc_val)
                    
                    # Match the current unique desc position to determine the text word suffix
                    idx = base_label_tracking[base].index(desc_val) + 1
                    suffix_word = INDEX_WORD_MAP.get(idx, f"Copy{idx}")
                    final_key = f"{correct_key}{suffix_word}"
                else:
                    # Same label and same desc or entirely unique normal spec item -> Strip digits safely
                    final_key = to_camel_case(label, keep_number=False)
            else:
                final_key = key

            # Run deeper node recursions
            if isinstance(value, dict):
                value = process_json_keys_to_camel(value)
            elif isinstance(value, list):
                value = [process_json_keys_to_camel(i) for i in value]

            # Direct fallback condition to strictly ensure structural integrity 
            if final_key in new_dict and isinstance(value, dict) and "desc" in value:
                if str(new_dict[final_key].get("desc")).strip() == str(value.get("desc")).strip():
                    # Exact redundant entry found -> Safely update/overwrite without duplicating suffixes
                    new_dict[final_key] = value
                    continue

            new_dict[final_key] = value
        return new_dict

    elif isinstance(data, list):
        return [process_json_keys_to_camel(i) for i in data]
        
    return data

# =========================
# GLOBAL CLEANING ENGINES
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

    # Custom specifications block sorting using context guidelines
    spec_headers = ["dimensions", "engine", "drivetrain", "operational", "hydraulics", "electrical", "weights", "measurements", "body", "other"]
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

# =========================
# UI CUSTOM GRAPHICS CSS
# =========================
st.markdown("""
<style>
.block-container{ max-width:1200px; padding-top:2rem; }
.main-title{ text-align:center; font-size:42px; font-weight:700; margin-bottom:10px; }
.sub-title{ text-align:center; font-size:18px; color:#666; margin-bottom:30px; }
</style>
""", unsafe_allow_html=True)

# =========================
# HEADER CONTROL
# =========================
st.markdown("""
<div class="main-title">🚀 OEM JSON Studio PRO</div>
<div class="sub-title">Upload files to merge, clean, parse MSRP, optimize, and standardize specs into clean conditional camelCase properties</div>
""", unsafe_allow_html=True)

# =========================
# CORE UPLOAD & EXTRACTION PARSER
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
# DYNAMIC PIPELINE VIEW
# =========================
uploaded_files = st.file_uploader("📂 Upload JSON or ZIP Files", type=["json", "zip"], accept_multiple_files=True, key="studio_pro_uploader")

if uploaded_files:
    start_time = time.time()
    total_files = len(uploaded_files)
    total_size = round(sum(file.size for file in uploaded_files) / (1024 * 1024), 2)
    
    progress = st.progress(0)
    
    # Step 1: Merge raw blocks
    raw_data, invalid_files = parse_uploaded_files(uploaded_files)
    progress.progress(0.3)

    # Step 2: Advanced Content Cleaning Engine
    cleaned_models = []
    for model in raw_data:
        model = clean_msrp_and_countries(model)
        model = clean_specs_and_features(model)
        model = remove_cross_duplicates(model)
        model = clean_meta_and_attachments(model)
        model = clean_whole_json(model)
        cleaned_models.append(model)
    
    progress.progress(0.6)
    
    # Step 3: Run Smart Conditional camelCase Key Conversion Engine
    cleaned_models = process_json_keys_to_camel(cleaned_models)
    progress.progress(0.8)
    
    # Step 4: Alpha-Numeric Sorting
    cleaned_models = sorted(
        cleaned_models,
        key=lambda x: (
            str(x.get("general", {}).get("manufacturer", "")), 
            str(x.get("general", {}).get("model", "")), 
            str(x.get("general", {}).get("year", ""))
        )
    )
    
    progress.progress(1.0)
    elapsed = round(time.time() - start_time, 2)

    st.success(f"🔥 Optimization & Refactoring Complete! Processed {len(cleaned_models):,} structured records.")

    # KPI Layout
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Files Uploaded", total_files)
    col2.metric("Optimized Records", len(cleaned_models))
    col3.metric("Invalid Files Detected", invalid_files)
    col4.metric("Total Size (MB)", total_size)
    st.caption(f"Engine Process Time: {elapsed} seconds")

    # Download Output
    json_output = json.dumps(cleaned_models, indent=2, ensure_ascii=False)
    st.download_button(
        label="⬇ Download Merged, Cleaned & CamelCase JSON",
        data=json_output,
        file_name="cleaned_camelcase_oem_output.json",
        mime="application/json",
        use_container_width=True
    )

    # Preview Sheet (Formatted Editor Raw Object Block Viewer)
    with st.expander(f"👁️ Refactored JSON Preview ({min(len(cleaned_models),10)} of {len(cleaned_models)} records)", expanded=True):
        preview_data = cleaned_models[:10]
        preview_json_string = json.dumps(preview_data, indent=2, ensure_ascii=False)
        st.code(preview_json_string, language="json")
else:
    st.info("Upload one or more files to start the automatic merge, deep content cleaning, and spec camelCase formatting engine.")
