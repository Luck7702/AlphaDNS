import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
# Using 'm2cgen' (Model 2 Code Generator) is a great trick to export ML to raw Go code!
import m2cgen as m2c 

def train_and_export_model(csv_path="data/raw_probes.csv"):
    # 1. Load Data
    df = pd.read_csv(csv_path)
    
    # Define features based on your paper (Hop Count, Time of Day, TLD Type, etc.)
    X = df[['hop_count', 'time_of_day', 'is_global_tld', 'subdomain_depth']]
    y = df['best_resolver_label'] # e.g., "Google", "Cloudflare", "ISP"

    # 2. Train the Random Forest (The Academic Upgrade)
    # n_estimators=15 is small enough for fast Go execution but accurate enough for an ensemble
    clf = RandomForestClassifier(n_estimators=15, max_depth=10, random_state=42)
    clf.fit(X, y)

    # 3. Export to Native Go Code (Solves the predictor.go bug)
    # This converts the Random Forest into native Go if-else statements!
    go_code = m2c.export_to_go(clf)
    
    with open('../engine/rf_model.go', 'w') as f:
        f.write(go_code)
    
    print("Random Forest trained and exported natively to Go!")

if __name__ == "__main__":
    train_and_export_model()