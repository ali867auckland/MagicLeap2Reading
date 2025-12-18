import pandas as pd
from pathlib import Path

# --- 1. Load your CSVs ---
base = Path("/Users/azyl/ABI_Work/MagicLeap2Reading/HeraLeto")  # adjust if needed

rep = pd.read_csv(base / "hera_repdat1.csv")
hrtemp = pd.read_csv(base / "hera_hr_temp.csv")

# --- 2. Split the REP_DAT1 'values' string into numeric columns f1..fN ---

def split_to_numbers(value_str):
    parts = str(value_str).split(",")
    nums = []
    for p in parts:
        p = p.strip()
        if p == "":
            continue
        try:
            nums.append(float(p))
        except ValueError:
            nums.append(float("nan"))
    return nums

# parse once so we don't keep recomputing
parsed = rep["values"].apply(split_to_numbers)
max_len = parsed.map(len).max()

for i in range(max_len):
    colname = f"f{i+1}"
    rep[colname] = parsed.apply(
        lambda lst, idx=i: lst[idx] if idx < len(lst) else float("nan")
    )

# --- 3. Expose HR from REP_DAT1 (f1, ignoring sentinel values 0 and 255) ---

def extract_hr_from_f1(x):
    if pd.isna(x) or x in (0, 255):
        return float("nan")
    return x

rep["hr_from_repdat1"] = rep["f1"].apply(extract_hr_from_f1)

# --- 4. Attach HR from the standard HR characteristic for comparison ---

hr_df = hrtemp[hrtemp["type"] == "hr"].copy()

# convert to datetime + numeric
hr_df["pc_time_dt"] = pd.to_datetime(hr_df["pc_time"])
hr_df["value"] = pd.to_numeric(hr_df["value"], errors="coerce")

rep["pc_time_dt"] = pd.to_datetime(rep["pc_time"])

merged = pd.merge_asof(
    rep.sort_values("pc_time_dt"),
    hr_df[["pc_time_dt", "value"]].sort_values("pc_time_dt"),
    on="pc_time_dt",
    direction="nearest",
    tolerance=pd.Timedelta("1s"),
)

merged.rename(columns={"value": "hr_from_char"}, inplace=True)

# --- 5. Compare the two HR streams (just for sanity check) ---

mask = merged["hr_from_repdat1"].notna() & merged["hr_from_char"].notna()
merged["hr_diff"] = merged["hr_from_repdat1"] - merged["hr_from_char"]

print("Number of rows with both HRs:", mask.sum())
if mask.any():
    print("Mean difference:", merged.loc[mask, "hr_diff"].mean())
    print(
        "Min/Max difference:",
        merged.loc[mask, "hr_diff"].min(),
        merged.loc[mask, "hr_diff"].max(),
    )

# --- 6. Save a 'decoded-ish' version for further analysis ---

decoded_cols = (
    ["pc_time", "device_ts", "hr_from_repdat1", "hr_from_char", "hr_diff"]
    + [f"f{i}" for i in range(1, max_len + 1)]
)

merged[decoded_cols].to_csv(base / "hera_repdat1_decoded.csv", index=False)

print("\nSaved: hera_repdat1_decoded.csv")
print("Columns f1..fN are the raw fields from REP_DAT1.")
print("hr_from_repdat1 is your DSP heart-rate (bpm).")
