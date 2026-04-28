import pandas as pd
import joblib
import os
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report

# 1. Setup paths to find your data correctly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, '../data/raw_probes.csv')
MODEL_PATH = os.path.join(BASE_DIR, 'artifact.pkl')

# 2. Load your telemetry data
if not os.path.exists(DATA_PATH):
    print(f"Error: Could not find {DATA_PATH}. Make sure you ran the scanner first!")
    exit(1)

df = pd.read_csv(DATA_PATH)

# 3. Define Features (X) and Target (y) based on your actual CSV headers
# We use TLD types and Subdomain Depth as our network-aware features
X = df[['Is_Global_TLD', 'Is_ID_TLD', 'Subdomain_Depth']]
y = df['Optimal_Class']

# 4. Split into training and testing (80% train, 20% test)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 5. Initialize the Random Forest (The Committee of Experts)
# n_estimators=100 means we use 100 trees to vote on the best resolver
model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)

# 6. Train the model
print("Training Random Forest model for AlphaDNS...")
model.fit(X_train, y_train)

# 7. Evaluate the performance
y_pred = model.predict(X_test)
print(f"Model Accuracy: {accuracy_score(y_test, y_pred) * 100:.2f}%")
print("\nClassification Report:\n", classification_report(y_test, y_pred))

# 8. Export the model artifact for the Go Engine to use
joblib.dump(model, MODEL_PATH)
print(f"Success! Model exported to: {MODEL_PATH}")