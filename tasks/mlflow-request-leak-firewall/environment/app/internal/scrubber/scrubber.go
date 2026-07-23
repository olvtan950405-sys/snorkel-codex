package scrubber

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

type request struct {
	ID      string            `json:"id"`
	Method  string            `json:"method"`
	Path    string            `json:"path"`
	Headers map[string]string `json:"headers"`
	Query   map[string]string `json:"query"`
	Body    any               `json:"body"`
}

// ScrubFile is intentionally incomplete: the migration copied requests into its log.
func ScrubFile(input, output string) error {
	in, err := os.Open(input)
	if err != nil { return err }
	defer in.Close()
	out, err := os.Create(output)
	if err != nil { return err }
	defer out.Close()
	s := bufio.NewScanner(in)
	enc := json.NewEncoder(out)
	for s.Scan() {
		if strings.TrimSpace(s.Text()) == "" { continue }
		var req request
		if err := json.Unmarshal(s.Bytes(), &req); err != nil { return fmt.Errorf("decode: %w", err) }
		// BUG: endpoint checks use substring matching and no field is scrubbed.
		route := "unknown"
		if strings.Contains(req.Path, "runs") { route = "get_run" }
		if err := enc.Encode(map[string]any{"id": req.ID, "decision": "forward", "route": route, "request": req}); err != nil { return err }
	}
	return s.Err()
}
