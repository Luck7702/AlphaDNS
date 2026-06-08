package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/miekg/dns"
)

// Upstream resolvers mapping (The options your Random Forest chooses from)
var resolvers map[string]string
var listenPort string

// dnsClient is reused across requests; *dns.Client is safe for concurrent use
var dnsClient = &dns.Client{Timeout: 2 * time.Second}

// loadConfig parses the config.json file and populates the resolvers map.
// Tries the working directory first, then falls back to the parent directory,
// since the binary may be run either from the repo root or from engine/.
func loadConfig() {
	var data []byte
	var err error
	for _, path := range []string{"config.json", "../config.json"} {
		data, err = os.ReadFile(path)
		if err == nil {
			break
		}
	}
	if err != nil {
		log.Fatalf("[!] Failed to read config file: %v", err)
	}

	var config struct {
		Resolvers map[string]string `json:"resolvers"`
		Port      int               `json:"port"`
	}

	if err := json.Unmarshal(data, &config); err != nil {
		log.Fatalf("[!] Failed to parse config JSON: %v", err)
	}

	listenPort = fmt.Sprintf(":%d", config.Port)

	resolvers = make(map[string]string)
	for id, addr := range config.Resolvers {
		// Ensure the address has a port; append :53 if missing
		if !strings.Contains(addr, ":") {
			addr = fmt.Sprintf("%s:53", addr)
		}
		resolvers[id] = addr
	}
}

// extractFeatures parses the incoming DNS query into the model's input.
// Each feature MUST be computed exactly as the Python training pipeline
// computes it (ml/dataset.py + telemetry/scanner.py), or the served
// features will not match what the model was trained on. See CLAUDE.md.
func extractFeatures(req *dns.Msg) DNSFeatures {
	features := DNSFeatures{
		// Integer hour-of-day: the training data records whole hours and the
		// exported tree splits at X.5, so passing a fractional hour (e.g.
		// 21.5 at 21:30) would cross a boundary the model never trained on.
		TimeOfDay: float64(time.Now().Hour()),
	}

	if len(req.Question) > 0 {
		qname := req.Question[0].Name

		// TLD type
		if strings.HasSuffix(qname, ".com.") || strings.HasSuffix(qname, ".net.") || strings.HasSuffix(qname, ".org.") {
			features.IsGlobalTLD = 1.0
		}
		if strings.HasSuffix(qname, ".id.") {
			features.IsIDTLD = 1.0
		}

		// subdomain_depth == number of dots in the name, matching the Python
		// scanner's domain.count('.'). DNS names are fully qualified with a
		// trailing dot, so trim it and count the gaps between labels
		// (len(labels)-1), NOT len(labels) -- that off-by-one was a real
		// train/serve skew bug.
		labels := strings.Split(strings.TrimSuffix(qname, "."), ".")
		features.SubdomainDepth = float64(len(labels) - 1)
	}

	return features
}

// handleDNSRequest is the main proxy logic triggered on every DNS query
func handleDNSRequest(w dns.ResponseWriter, r *dns.Msg) {
	// 1. Extract Features for the Research Variables
	features := extractFeatures(r)

	domain := ""
	if len(r.Question) > 0 {
		domain = r.Question[0].Name
	}

	// 2. Predict the best resolver
	targetID, confidence := Predict(features)

	// Logging for your research data collection
	log.Printf("[*] Query: %s | Selected: %s (Confidence: %.2f)", domain, targetID, confidence)

	targetIP, ok := resolvers[targetID]
	if !ok {
		log.Printf("[!] Resolver ID %s not found in mapping", targetID)
		w.WriteMsg(failureResponse(r))
		return
	}

	// 3. Perform the Forwarding (The Research Intervention)
	response, _, err := dnsClient.Exchange(r, targetIP)

	if err != nil {
		log.Printf("[!] Forwarding failed to %s: %v", targetIP, err)
		w.WriteMsg(failureResponse(r))
		return
	}

	// 4. Return the result to the user
	if response != nil {
		w.WriteMsg(response)
	}
}

// failureResponse builds a SERVFAIL reply so the client fails fast instead of timing out
func failureResponse(r *dns.Msg) *dns.Msg {
	m := new(dns.Msg)
	m.SetRcode(r, dns.RcodeServerFailure)
	return m
}

func main() {
	// Load resolvers from config.json before starting the server
	loadConfig()

	// Bind the proxy handler to all incoming DNS requests
	dns.HandleFunc(".", handleDNSRequest)

	// Start the server on the standard DNS port
	server := &dns.Server{Addr: listenPort, Net: "udp"}
	fmt.Printf("AlphaDNS Hybrid Forwarder initializing...\n")
	fmt.Printf("Listening for DNS requests on UDP port %s...\n", listenPort)
	
	if err := server.ListenAndServe(); err != nil {
		log.Fatalf("Failed to start AlphaDNS server: %s\n", err.Error())
	}
}