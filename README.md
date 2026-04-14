# NDLC-2026: Heuristic DNS Path Optimization
### Predictive Latency & Resolution Success Modeling via Decision Trees

## 🧪 The Overview
NDLC-2026 is an automated network research suite designed to solve the **"Zero-Latency Trap"** in regional ISP environments. While traditional DNS optimization focuses on raw RTT (Round Trip Time), this project utilizes a **Supervised Machine Learning** approach to predict the optimal resolver based on domain features and resolution success rates.

## 🧠 The Logic (Entropy-Based)
The core engine uses a **Decision Tree Classifier** to map high-dimensional network data. It calculates the information gain for features like:
- **TLD Origin** (Top-Level Domain)
- **Domain String Complexity**
- **ISP Filtering Heuristics** (NXDOMAIN Detection)

The model is trained to penalize censored or broken routes with a massive cost ($999ms$), forcing the tree to branch toward high-reliability anycast providers (Cloudflare/Google) for "At-Risk" traffic.

## 🛠️ Architecture
1. **The Factory (`scanner.py`)**: Asynchronous network prober with failure-state handling.
2. **The Scientist (`train_dns_ai.py`)**: ML pipeline utilizing `scikit-learn` for entropy-based classification.
3. **The Predictor (`predict_dns.py`)**: Real-time inference engine for instant resolver selection.

## 🚀 Installation
```bash
git clone [https://github.com/yourusername/NDLC-2026.git](https://github.com/yourusername/NDLC-2026.git)
pip install -r requirements.txt
python3 predict_dns.py