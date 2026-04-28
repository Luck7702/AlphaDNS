package main

import (
	"fmt"
)

// DNSFeatures now matches exactly what main.go is looking for
type DNSFeatures struct {
	IsGlobalTLD    float64
	IsIDTLD        float64
	SubdomainDepth float64
	TimeOfDay      float64 // This maps to the 'hour' feature in our model
	HopCount       float64 // Added to satisfy main.go; ignored by the model for now
}

// Predict now returns 2 values: (ResolverID string, Confidence float64)
func Predict(features DNSFeatures) (string, float64) {
	// 1. Prepare input for the Random Forest
	// Note: We skip HopCount here because it wasn't in our training data
	input := []float64{
		features.IsGlobalTLD,
		features.IsIDTLD,
		features.SubdomainDepth,
		features.TimeOfDay,
	}

	// 2. Call the auto-generated 'score' function in rf_model.go
	// This returns the probability for each resolver (e.g., [0.1, 0.8, 0.05, 0.05])
	probabilities := score(input)

	// 3. Find the winner and its probability (confidence)
	bestIdx := 0
	maxProb := -1.0
	for i, prob := range probabilities {
		if prob > maxProb {
			maxProb = prob
			bestIdx = i
		}
	}

	// 4. Return the ID and the confidence score
	resolverID := fmt.Sprintf("%d", bestIdx)
	return resolverID, maxProb
}
