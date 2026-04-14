import joblib
import pandas as pd
import sys

# Load the model artifact
MODEL_PATH = 'artifact.pkl'

try:
    model = joblib.load(MODEL_PATH)
except FileNotFoundError:
    print(f"Error: {MODEL_PATH} not found. Run trainer.py first.")
    sys.exit(1)

def predict_domain(domain):
    # --- FEATURE EXTRACTION (Must match scanner.py and main.go) ---
    domain = domain.strip().lower()
    
    length = len(domain)
    is_id_tld = 1 if domain.endswith(".id") else 0
    subdomain_depth = domain.count('.')
    
    # Prepare for model (2D array)
    features = pd.DataFrame([[length, is_id_tld, subdomain_depth]], 
                            columns=['Length', 'Is_ID_TLD', 'Subdomain_Depth'])
    
    # Predict
    class_idx = model.predict(features)[0]
    
    # Map back to human-readable names
    mapping = {
        0: "ISP (Local Gateway)",
        1: "Cloudflare (1.1.1.1)",
        2: "Google (8.8.8.8)",
        3: "Quad9 (9.9.9.9)"
    }
    
    return mapping.get(class_idx, "Unknown"), class_idx

if __name__ == "__main__":
    print("--- AlphaDNS ML Predictor (Offline Mode) ---")
    
    if len(sys.argv) > 1:
        # Allow command line usage: python3 predict_dns.py google.com
        test_domain = sys.argv[1]
        result, cid = predict_domain(test_domain)
        print(f"Domain: {test_domain}")
        print(f"Prediction: {result} (Class {cid})")
    else:
        # Interactive mode
        while True:
            test_domain = input("\nEnter domain to test (or 'q' to quit): ").strip()
            if test_domain.lower() == 'q':
                break
            if not test_domain:
                continue
                
            result, cid = predict_domain(test_domain)
            print(f"Result: {result}")