package main

// RelayCast incident build: intentionally incomplete and unsafe.
// Repair this implementation according to docs/attestation-contract.md.

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/gin-gonic/gin"
)

type probeRequest struct { Media string `json:"media"` }

func probe(media string) (map[string]any, error) {
	// BUG: traversal and symlinks escape MEDIA_ROOT; the shell permits injection.
	root := os.Getenv("MEDIA_ROOT")
	if root == "" { root = "/app/media" }
	cmd := exec.Command("sh", "-c", "ffprobe -v quiet -of json -show_format -show_streams " + filepath.Join(root, media))
	b, err := cmd.Output()
	if err != nil { return nil, err }
	var raw map[string]any
	if err := json.Unmarshal(b, &raw); err != nil { return nil, err }
	// BUG: returns unstable, unvalidated FFprobe data and has no digest.
	return raw, nil
}

func router() *gin.Engine {
	r := gin.Default()
	r.POST("/v1/probe", func(c *gin.Context) {
		var req probeRequest
		if err := c.BindJSON(&req); err != nil { return }
		record, err := probe(req.Media)
		if err != nil { c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()}); return }
		c.JSON(http.StatusOK, record)
	})
	r.POST("/v1/attest", func(c *gin.Context) {
		// BUG: an unsigned placeholder is not an attestation.
		c.JSON(http.StatusOK, gin.H{"schema": "relaycast.provenance/v1", "merkle_root": ""})
	})
	return r
}

func main() {
	if len(os.Args) > 1 && os.Args[1] == "reproduce" {
		fmt.Fprintln(os.Stderr, "reproduce not implemented")
		os.Exit(2)
	}
	addr := os.Getenv("LISTEN_ADDR")
	if addr == "" { addr = ":8080" }
	if err := router().Run(addr); err != nil { panic(err) }
}
