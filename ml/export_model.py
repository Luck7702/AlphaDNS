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
    tree_ = tree.tree_
    feature_name = [
        feature_names[i] if i != _tree.TREE_UNDEFINED else "undefined!"
        for i in tree_.feature
    ]

    lines = []
    lines.append("package main")
    lines.append("")
    lines.append("// Predict returns the optimal DNS class based on the decision tree model")
    lines.append("func Predict(isGlobal float64, isID float64, depth float64) int {")

    def recurse(node, depth):
        indent = "    " * depth
        if tree_.feature[node] != _tree.TREE_UNDEFINED:
            name = feature_name[node]
            threshold = tree_.threshold[node]
            
            # Map Python feature names to Go parameter names
            go_param = {
                "Is_Global_TLD": "isGlobal",
                "Is_ID_TLD": "isID",
                "Subdomain_Depth": "depth"
            }.get(name, name)

            lines.append(f"{indent}if {go_param} <= {threshold:.2f} {{")
            recurse(tree_.children_left[node], depth + 1)
            lines.append(f"{indent}}} else {{")
            recurse(tree_.children_right[node], depth + 1)
            lines.append(f"{indent}}}")
        else:
            # Get the class with the highest value in this leaf
            import numpy as np
            value = tree_.value[node][0]
            class_idx = np.argmax(value)
            lines.append(f"{indent}return {class_idx}")

    recurse(0, 1)
    lines.append("}")
    return "\n".join(lines)

# Generate the code with updated feature names
go_code = tree_to_go(clf, ["Is_Global_TLD", "Is_ID_TLD", "Subdomain_Depth"])

# Save the Go code using the absolute path
with open(OUTPUT_FILE, "w") as f:
    f.write(go_code)

print(f"[+] Successfully exported to {OUTPUT_FILE}!")