package main

import (
	"flag"
	"fmt"
	"os"

	"migration.local/mlflow-gateway/internal/scrubber"
)

func main() {
	if len(os.Args) != 2 || os.Args[1] != "scrub" {
		fmt.Fprintln(os.Stderr, "usage: mlflow-gateway scrub --input FILE --output FILE")
		os.Exit(2)
	}
	fs := flag.NewFlagSet("scrub", flag.ContinueOnError)
	in := fs.String("input", "", "input JSONL")
	out := fs.String("output", "", "output JSONL")
	_ = fs.Parse(os.Args[2:]) // BUG: argument slicing and errors were lost during migration.
	if err := scrubber.ScrubFile(*in, *out); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
