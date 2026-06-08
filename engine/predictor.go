package main

import (
	"fmt"
)

// DNSFeatures mirrors the model's input contract. The fields, and the order
// they are packed into `input` below, MUST match ml/dataset.py FEATURES
// (is_global_tld, is_id_tld, subdomain_depth, hour). Changing one side
// without the other silently breaks routing. See CLAUDE.md.
type DNSFeatures struct {
	IsGlobalTLD    float64
	IsIDTLD        float64
	SubdomainDepth float64
	TimeOfDay      float64 // integer hour-of-day; the model's "hour" feature
}

// Predict returns (ResolverID string, Confidence float64) for a query.
func Predict(features DNSFeatures) (string, float64) {
	// 1. Pack features in the exact order the exported scorer expects.
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
