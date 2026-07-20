package main

import (
	"fmt"
	"os"

	"walrescue/internal/recoverdb"
)

func main() {
	if err := recoverdb.Run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
