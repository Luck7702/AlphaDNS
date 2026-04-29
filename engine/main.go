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
// handleDNSRequest is the main proxy logic triggered on every DNS query
func handleDNSRequest(w dns.ResponseWriter, r *dns.Msg) {
	// 1. Extract Features for the Research Variables
	// FIX: We now use the extractFeatures function you already built!
	features := extractFeatures(r)
	
	domain := ""
	if len(r.Question) > 0 {
		domain = r.Question[0].Name
	}

	// 2. Predict the best resolver
	targetID, confidence := Predict(features) 
	
	// Logging for your research data collection
	log.Printf("[*] Query: %s | Selected: %s (Confidence: %.2f)", domain, targetID, confidence)

	// FIX: Changed UpstreamResolvers to resolvers to match your map declaration
	targetIP, ok := resolvers[targetID]
	if !ok {
		log.Printf("[!] Resolver ID %s not found in mapping", targetID)
		return
	}

	// 3. Perform the Forwarding (The Research Intervention)
	client := new(dns.Client)
	// 2.0s timeout aligns perfectly with our p99 methodology!
	client.Timeout = 2 * time.Second 
	
	response, _, err := client.Exchange(r, targetIP) 

	if err != nil {
		log.Printf("[!] Forwarding failed to %s: %v", targetIP, err)
		return
	}

	// 4. Return the result to the user
	if response != nil {
		w.WriteMsg(response)
	}
}

func main() {
	// Bind the proxy handler to all incoming DNS requests
	dns.HandleFunc(".", handleDNSRequest)

	// Start the server on the standard DNS port
	server := &dns.Server{Addr: ":533", Net: "udp"}
	fmt.Printf("AlphaDNS Hybrid Forwarder initializing...\n")
	fmt.Printf("Listening for DNS requests on UDP port 53...\n")
	
	err := server.ListenAndServe()
	defer server.Shutdown()
	if err != nil {
		log.Fatalf("Failed to start AlphaDNS server: %s\n", err.Error())
	}
}