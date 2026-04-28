package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"
)

// 1. Define the exact features your Random Forest expects
// (Make sure these match the columns you used in trainer.py)
type DNSFeatures struct {
	IsGlobalTLD    float64 `json:"Is_Global_TLD"`
	IsIDTLD        float64 `json:"Is_ID_TLD"`
	SubdomainDepth float64 `json:"Subdomain_Depth"`
	TimeOfDay      float64 `json:"Time_of_Day"`
	HopCount       float64 `json:"Hop_Count"`
}

// Predict triggers the Random Forest Python script via a fast subprocess
func Predict(features DNSFeatures) (string, error) {
	// Convert the features into a JSON string
	featureJSON, err := json.Marshal(features)
	if err != nil {
		return "", fmt.Errorf("failed to encode features: %v", err)
	}

	// Execute predict_dns.py 
	// Note: Adjust the path "../ml/predict_dns.py" if your folder structure differs when running the compiled Go binary
	cmd := exec.Command("python3", "../ml/predict_dns.py", string(featureJSON))
	
	var out bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &stderr
	
	err = cmd.Run()
	if err != nil {
		return "", fmt.Errorf("ML engine error: %v | %s", err, stderr.String())
	}

	// Read the output from Python (e.g., "1.1.1.1" or "Cloudflare")
	bestResolver := strings.TrimSpace(out.String())
	
	return bestResolver, nil
}