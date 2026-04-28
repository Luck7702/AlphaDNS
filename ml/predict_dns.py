import joblib
import pandas as pd
import sys
import json

# 1. Load the Random Forest artifact
MODEL_PATH = 'artifact.pkl'
model = joblib.load(MODEL_PATH)

def predict_best_resolver(features):
    # Ensure features match the columns used in training
    df_features = pd.DataFrame([features])
    prediction = model.predict(df_features)
    return prediction[0]

if __name__ == "__main__":
    # Go engine will pass features as a JSON string argument
    if len(sys.argv) > 1:
        raw_input = sys.argv[1]
        features = json.loads(raw_input)
        
        # Output only the resolver name (e.g., "1.1.1.1" or "Cloudflare") so Go can parse it
        best_route = predict_best_resolver(features)
        print(best_route)