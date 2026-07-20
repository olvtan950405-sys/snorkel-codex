// Package verifier contains the GlacierVault backup verifier.
// Several security-critical checks are intentionally incomplete.
package verifier

import (
	"encoding/json"
	"errors"
	"os"
)

type verdict struct {
	BundleID       *string  `json:"bundle_id"`
	ManifestDigest *string  `json:"manifest_digest"`
	Nonce          *string  `json:"nonce"`
	Signers        []string `json:"signers"`
	Status         string   `json:"status"`
	Tenant         *string  `json:"tenant"`
}

// Run executes the command-line verifier.
func Run(args []string) error {
	if len(args) != 7 || args[0] != "verify" || args[1] != "--bundle" || args[3] != "--catalog" || args[5] != "--out" {
		return errors.New("usage: backupguard verify --bundle <directory> --catalog <sqlite-file> --out <json-file>")
	}
	// BUG: this placeholder neither validates the bundle nor consults the catalog.
	v := verdict{Signers: []string{}, Status: "accepted"}
	b, _ := json.Marshal(v)
	b = append(b, '\n')
	return os.WriteFile(args[6], b, 0o644)
}
