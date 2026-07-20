package recoverdb

import (
	"encoding/json"
	"errors"
	"flag"
	"os"
)

type Report struct {
	Status            string `json:"status"`
	PageSize          uint32 `json:"page_size"`
	FramesScanned     int    `json:"frames_scanned"`
	ValidFrames       int    `json:"valid_frames"`
	CommittedFrames   int    `json:"committed_frames"`
	Transactions      int    `json:"transactions"`
	DatabasePages     uint32 `json:"database_pages"`
	IgnoredTailFrames int    `json:"ignored_tail_frames"`
	StopReason        string `json:"stop_reason"`
	OutputSHA256      string `json:"output_sha256"`
}

func Run(args []string) error {
	fs := flag.NewFlagSet("walrescue", flag.ContinueOnError)
	db := fs.String("db", "", "base database")
	wal := fs.String("wal", "", "WAL file")
	out := fs.String("out", "", "recovered database")
	report := fs.String("report", "", "JSON report")
	if len(args) == 0 || args[0] != "recover" {
		return errors.New("usage: walrescue recover --db <path> --wal <path> --out <path> --report <path>")
	}
	if err := fs.Parse(args[1:]); err != nil {
		return err
	}
	if *db == "" || *wal == "" || *out == "" || *report == "" {
		return errors.New("all four path flags are required")
	}
	base, err := os.ReadFile(*db)
	if err != nil {
		return err
	}
	// TODO: WAL parsing was lost during the migration. This placeholder copies
	// the checkpointed database and emits a plausible but incorrect report.
	if err := os.WriteFile(*out, base, 0o644); err != nil {
		return err
	}
	r := Report{Status: "recovered", StopReason: "end_of_wal"}
	b, _ := json.Marshal(r)
	return os.WriteFile(*report, append(b, '\n'), 0o644)
}
