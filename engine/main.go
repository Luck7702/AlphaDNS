package main

import (
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/miekg/dns"
)

// Upstream resolvers mapping (The options your Random Forest chooses from)
var resolvers = map[string]string{
	"Cloudflare": "1.1.1.1:53",
	"Google":     "8.8.8.8:53",
	"Quad9":      "9.9.9.9:53",
	"ISP":        "202.134.1.10:53", // Replace with your actual Indonesian ISP DNS
}

// extractFeatures parses the incoming DNS query and builds the struct for the ML model
func extractFeatures(req *dns.Msg) DNSFeatures {
	// Initialize with default values
	features := DNSFeatures{
		IsGlobalTLD:    0.0,
		IsIDTLD:        0.0,
		SubdomainDepth: 0.0,
		TimeOfDay:      float64(time.Now().Hour()) + float64(time.Now().Minute())/60.0,
		HopCount:       12.0, // Default baseline for hops, update if using dynamic traceroute logic
	}

	if len(req.Question) > 0 {
		qname := req.Question[0].Name
		
		// 1. Identify TLD Type
		if strings.HasSuffix(qname, ".com.") || strings.HasSuffix(qname, ".net.") || strings.HasSuffix(qname, ".org.") {
			features.IsGlobalTLD = 1.0
		}
		if strings.HasSuffix(qname, ".id.") {
			features.IsIDTLD = 1.0
		}

		// 2. Calculate Subdomain Depth (e.g., api.service.example.com -> deeper depth)
		parts := strings.Split(strings.TrimSuffix(qname, "."), ".")
		features.SubdomainDepth = float64(len(parts))
	}

	return features
}

// handleDNSRequest is the main proxy logic triggered on every DNS query
func handleDNSRequest(w dns.ResponseWriter, r *dns.Msg) {
	// 1. Extract real-time telemetry from the query
	features := extractFeatures(r)

	// 2. Predict the best resolver using the ML Engine (calls predictor.go)
	bestResolverName, err := Predict(features)
	if err != nil {
		log.Printf("ML Predict Error: %v. Falling back to default (Cloudflare).", err)
		bestResolverName = "Cloudflare"
	}

	// 3. Map the ML output string to the actual IP address
	targetIP, exists := resolvers[bestResolverName]
	if !exists {
		log.Printf("Unknown resolver '%s' selected by ML. Falling back to Cloudflare.", bestResolverName)
		targetIP = resolvers["Cloudflare"]
	}

	// 4. Forward the request to the winning upstream resolver
	client := new(dns.Client)
	client.Timeout = 2 * time.Second // Aggressive timeout to protect p99 latency

	resp, _, err := client.Exchange(r, targetIP)
	if err != nil {
		log.Printf("Error forwarding to %s (%s): %v", bestResolverName, targetIP, err)
		dns.HandleFailed(w, r)
		return
	}

	// 5. Return the successfully resolved DNS answer back to the user
	resp.SetReply(r)
	w.WriteMsg(resp)
	
	// Print to console to prove the dynamic routing is working
	log.Printf("Routed %s -> %s", r.Question[0].Name, bestResolverName)
}

func main() {
	// Bind the proxy handler to all incoming DNS requests
	dns.HandleFunc(".", handleDNSRequest)

	// Start the server on the standard DNS port
	server := &dns.Server{Addr: ":53", Net: "udp"}
	fmt.Printf("AlphaDNS Hybrid Forwarder initializing...\n")
	fmt.Printf("Listening for DNS requests on UDP port 53...\n")
	
	err := server.ListenAndServe()
	defer server.Shutdown()
	if err != nil {
		log.Fatalf("Failed to start AlphaDNS server: %s\n", err.Error())
	}
}