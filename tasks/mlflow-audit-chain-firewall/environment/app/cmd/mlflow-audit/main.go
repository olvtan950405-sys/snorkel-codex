package main

import (
	"flag"
	"fmt"
	"os"
	"migration.local/mlflow-audit/internal/audit"
)

func main() {
	fs := flag.NewFlagSet("sanitize", flag.ExitOnError)
	in := fs.String("input", "", "input capture")
	out := fs.String("output", "", "output ledger")
	seed := fs.String("seed", "", "chain seed")
	// BUG: the subcommand and required arguments are not validated.
	_ = fs.Parse(os.Args[1:])
	if err := audit.Sanitize(*in, *out, *seed); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
