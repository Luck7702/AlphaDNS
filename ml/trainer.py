import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier # <--- NEW IMPORT
from sklearn.metrics import accuracy_score, classification_report

# 1. Load your telemetry data (features and target resolver)
# df = pd.read_csv('../data/raw_probes.csv')
# X = df[['Is_Global_TLD', 'Is_ID_TLD', 'Subdomain_Depth', 'Time_of_Day', 'Hop_Count']]
# y = df['Best_Resolver']

# 2. Split into training and testing
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 3. Initialize the Random Forest (The Academic Upgrade!)
# n_estimators=100 means we are building 100 trees to vote on the best route
model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)

# 4. Train the model
print("Training Random Forest model...")
model.fit(X_train, y_train)

# 5. Evaluate to ensure it reduces p99 timeouts accurately
y_pred = model.predict(X_test)
print("Accuracy:", accuracy_score(y_test, y_pred))
print(classification_report(y_test, y_pred))

# 6. Export the model artifact
joblib.dump(model, 'artifact.pkl')
print("Model successfully exported as artifact.pkl")