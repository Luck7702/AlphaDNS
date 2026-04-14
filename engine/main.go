package main

import (
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/miekg/dns"
)

var upstreams = map[int]string{
	0: "192.168.1.1:53", // ISP (Update to your actual Gateway)
	1: "1.1.1.1:53",     // Cloudflare
	2: "8.8.8.8:53",     // Google
	3: "9.9.9.9:53",     // Quad9
}

func getFeatures(domain string) (int, int, int) {
	d := strings.TrimSuffix(domain, ".")
	isID := 0
	if strings.HasSuffix(d, ".id") {
		isID = 1
	}
	return len(d), isID, strings.Count(d, ".")
}

func handleQuery(w dns.ResponseWriter, r *dns.Msg) {
	if len(r.Question) == 0 {
		return
	}

	domain := r.Question[0].Name
	l, id, d := getFeatures(domain)
	
	// Call generated predictor
	class := predictOptimalRoute(l, id, d)
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
	server := &dns.Server{Addr: "127.0.0.1:5053", Net: "udp"}
	
	fmt.Println("[*] PathPulse Engine running on port 5053...")
	if err := server.ListenAndServe(); err != nil {
		log.Fatalf("Fatal: %s", err)
	}
}