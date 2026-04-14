package main

import (
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/miekg/dns"
)

var upstreams = map[int]string{
	0: "202.158.3.7", // ISP (Update to your actual Gateway)
	1: "1.1.1.1:53",  // Cloudflare
	2: "8.8.8.8:53",  // Google
	3: "9.9.9.9:53",  // Quad9
}

// Updated to return float64 to match the ML decision tree requirements
func getFeatures(domain string) (float64, float64, float64) {
	d := strings.TrimSuffix(domain, ".")

	isGlobal := 0.0
	if strings.HasSuffix(d, ".com") || strings.HasSuffix(d, ".net") || strings.HasSuffix(d, ".org") {
		isGlobal = 1.0
	}

	isID := 0.0
	if strings.HasSuffix(d, ".id") {
		isID = 1.0
	}

	depth := float64(strings.Count(d, "."))

	return isGlobal, isID, depth
}

func handleQuery(w dns.ResponseWriter, r *dns.Msg) {
	if len(r.Question) == 0 {
		return
	}

	domain := r.Question[0].Name
	
	// Extract the new features as float64
	isGlobal, isID, depth := getFeatures(domain)

	// Pass variables to generated predictor
	class := Predict(isGlobal, isID, depth)
	target := upstreams[class]

	fmt.Printf("[PROX] %-25s -> Class %d (%s)\n", domain, class, target)

	c := new(dns.Client)
	c.Timeout = 1200 * time.Millisecond

	resp, _, err := c.Exchange(r, target)
	if err != nil {
		fmt.Printf("[ERR] Target %s failed: %v\n", target, err)
		dns.HandleFailed(w, r)
		return
	}

	w.WriteMsg(resp)
}

func main() {
	dns.HandleFunc(".", handleQuery)
	
	// Port 5353 used for testing to avoid needing sudo right away
	server := &dns.Server{Addr: ":5353", Net: "udp"} 
	
	fmt.Println("[*] AlphaDNS Predictive Engine listening on :5353")
	log.Fatal(server.ListenAndServe())
}