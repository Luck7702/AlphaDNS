import joblib
from sklearn.tree import _tree
import os

# --- DYNAMIC PATHS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_FILENAME = os.path.join(BASE_DIR, 'artifact.pkl')
OUTPUT_FILE = os.path.join(BASE_DIR, "../engine/predictor.go")

# Load the model using the absolute path
clf = joblib.load(MODEL_FILENAME)

def tree_to_go(tree, feature_names):
    # ... (Keep your exact recurse logic here) ...
    pass 

go_code = tree_to_go(clf, ["Is_Global_TLD", "Is_ID_TLD", "Subdomain_Depth"])

# Save the Go code using the absolute path
with open(OUTPUT_FILE, "w") as f:
    f.write(go_code)

print(f"[+] Successfully exported to {OUTPUT_FILE}!")
