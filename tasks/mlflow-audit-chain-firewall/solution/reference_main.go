package main

import (
	"flag"
	"fmt"
	"os"
	"migration.local/mlflow-audit/internal/audit"
)

func main() {
	if len(os.Args) < 2 || os.Args[1] != "sanitize" { fmt.Fprintln(os.Stderr, "usage: mlflow-audit sanitize --input FILE --output FILE --seed HEX"); os.Exit(2) }
	fs := flag.NewFlagSet("sanitize", flag.ContinueOnError)
	in, out, seed := fs.String("input", "", "input"), fs.String("output", "", "output"), fs.String("seed", "", "seed")
	if err := fs.Parse(os.Args[2:]); err != nil || *in == "" || *out == "" || *seed == "" || fs.NArg() != 0 { os.Exit(2) }
	if err := audit.Sanitize(*in, *out, *seed); err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
}
