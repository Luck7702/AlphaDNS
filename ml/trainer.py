import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier, plot_tree
from sklearn.metrics import accuracy_score
import matplotlib.pyplot as plt

# FIXED PATHS
FILE_NAME = "../data/raw_probes.csv"
MODEL_FILENAME = 'artifact.pkl'

df = pd.read_csv(FILE_NAME)

# FIXED FEATURES: Updated to use Is_Global_TLD instead of Length
X = df[['Is_Global_TLD', 'Is_ID_TLD', 'Subdomain_Depth']]
y = df['Optimal_Class']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

clf = DecisionTreeClassifier(max_depth=5, criterion='entropy', random_state=42)
clf.fit(X_train, y_train)

y_pred = clf.predict(X_test)
print(f"Model Accuracy: {accuracy_score(y_test, y_pred) * 100:.2f}%")

plt.figure(figsize=(20,10))
# Updated feature names for the visual graph output
plot_tree(clf, feature_names=['Global_TLD', 'Is_ID', 'Depth'], class_names=['ISP', 'CF', 'Google', 'Quad9'], filled=True)
plt.savefig('dns_decision_tree.png')

# Save as artifact
joblib.dump(clf, MODEL_FILENAME)
print(f"[+] Model saved to '{MODEL_FILENAME}'")