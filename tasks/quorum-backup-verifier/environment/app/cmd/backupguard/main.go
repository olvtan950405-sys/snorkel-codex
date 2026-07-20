package main

import (
	"fmt"
	"os"

	"glacier.example/backupguard/internal/verifier"
)

func main() {
	if err := verifier.Run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
}
