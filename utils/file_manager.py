import json
import os

# ---------------- LOAD ----------------
def load_json(file):
    try:
        if not os.path.exists(file):
            return []

        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        print("❌ LOAD ERROR:", e)
        return []


# ---------------- SAVE ----------------
def save_json(file, data):
    try:
        print("FILE INPUT:", file)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        print("BASE DIR:", base_dir)

        full_path = os.path.join(base_dir, "..", file)
        full_path = os.path.abspath(full_path)

        print("FULL PATH:", full_path)

        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        print(f"✅ Data saved to {full_path}")

    except Exception as e:
        print(f"❌ SAVE ERROR: {e}")