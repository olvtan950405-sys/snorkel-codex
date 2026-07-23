package audit

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
)

// Sanitize is the incomplete migration implementation.
func Sanitize(input, output, seed string) error {
	in, err := os.Open(input)
	if err != nil { return err }
	defer in.Close()
	out, err := os.Create(output)
	if err != nil { return err }
	defer out.Close()
	previous, _ := hex.DecodeString(seed)
	s := bufio.NewScanner(in)
	enc := json.NewEncoder(out)
	for s.Scan() {
		var request map[string]any
		if err := json.Unmarshal(s.Bytes(), &request); err != nil { return err }
		// BUG: this serializes the raw request and does not chain prior canonical records.
		h := sha256.Sum256(previous)
		request["chain"] = hex.EncodeToString(h[:])
		if err := enc.Encode(request); err != nil { return err }
	}
	return s.Err()
}
