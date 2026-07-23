package main

import (
	"flag"
	"fmt"
	"os"
	"migration.local/mlflow-gateway/internal/scrubber"
)
func main() {
	if len(os.Args) < 2 || os.Args[1] != "scrub" { fmt.Fprintln(os.Stderr,"usage: mlflow-gateway scrub --input FILE --output FILE"); os.Exit(2) }
	fs:=flag.NewFlagSet("scrub",flag.ContinueOnError); in:=fs.String("input","","input"); out:=fs.String("output","","output")
	if err:=fs.Parse(os.Args[2:]); err!=nil || *in=="" || *out=="" || fs.NArg()!=0 { os.Exit(2) }
	if err:=scrubber.ScrubFile(*in,*out); err!=nil { fmt.Fprintln(os.Stderr,err); os.Exit(1) }
}
