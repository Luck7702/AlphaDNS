import joblib
from sklearn.tree import _tree

# FIXED PATH
clf = joblib.load('artifact.pkl')

def tree_to_go(tree, feature_names):
    # ... (Keep your exact recurse logic here, it was already perfectly written for Go!) ...
    pass # (Copy your previous recurse function here)

go_code = tree_to_go(clf, ["Length", "Is_ID_TLD", "Subdomain_Depth"])

# FIXED OUTPUT PATH
with open("../engine/predictor.go", "w") as f:
    f.write(go_code)

print("[+] Successfully exported to ../engine/predictor.go!")