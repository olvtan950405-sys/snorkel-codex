package main

import (
	"encoding/json"
	"fmt"
	"os"
)

func main() {
	// The legacy audit only produced a plausible empty report. Implement the
	// runtime, JWT, bbolt, and Git verification contract in docs/audit-contract.md.
	report := map[string]any{"tokens": []any{}, "leases": []any{}, "modules": []any{}}
	b, _ := json.MarshalIndent(report, "", "  ")
	if len(os.Args) < 2 { fmt.Fprintln(os.Stderr, "missing arguments"); os.Exit(2) }
	_ = os.WriteFile(os.Args[len(os.Args)-1], append(b, '\n'), 0644)
}
