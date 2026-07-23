package recoverdb

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
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

func decodePageSize(v uint32) uint32 {
	if v == 1 {
		return 65536
	}
	return v
}

func checksum(data []byte, s0, s1 uint32, little bool) (uint32, uint32) {
	for i := 0; i+8 <= len(data); i += 8 {
		var x0, x1 uint32
		if little {
			x0 = binary.LittleEndian.Uint32(data[i : i+4])
			x1 = binary.LittleEndian.Uint32(data[i+4 : i+8])
		} else {
			x0 = binary.BigEndian.Uint32(data[i : i+4])
			x1 = binary.BigEndian.Uint32(data[i+4 : i+8])
		}
		s0 += x0 + s1
		s1 += x1 + s0
	}
	return s0, s1
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
	wb, err := os.ReadFile(*wal)
	if err != nil {
		return err
	}
	if len(base) < 20 || len(wb) < 32 || string(base[:16]) != "SQLite format 3\x00" {
		return errors.New("bad evidence headers")
	}

	pageSize := decodePageSize(binary.BigEndian.Uint32(wb[8:12]))
	if pageSize == 0 || int(pageSize) > len(base)*64 {
		return errors.New("unsupported page size")
	}
	magic := binary.BigEndian.Uint32(wb[:4])
	little := magic != 0x377f0683
	salt1 := binary.BigEndian.Uint32(wb[16:20])
	salt2 := binary.BigEndian.Uint32(wb[20:24])
	s0, s1 := checksum(wb[:24], 0, 0, little)

	work := append([]byte(nil), base...)
	stop := "end_of_wal"
	scanned, valid, committed, txs := 0, 0, 0, 0
	dbPages := uint32(len(base) / int(pageSize))
	slot := 24 + int(pageSize)
	for offset := 32; offset < len(wb); offset += slot {
		scanned++
		if offset+slot > len(wb) {
			stop = "partial_frame"
			break
		}
		h := wb[offset : offset+24]
		pageNo := binary.BigEndian.Uint32(h[:4])
		commit := binary.BigEndian.Uint32(h[4:8])
		page := wb[offset+24 : offset+slot]
		n0, n1 := checksum(append(append([]byte{}, h[:8]...), page...), s0, s1, little)
		valid++
		if pageNo == 0 {
			stop = "zero_page_number"
			break
		}
		if binary.BigEndian.Uint32(h[8:12]) != salt1 || binary.BigEndian.Uint32(h[12:16]) != salt2 {
			stop = "salt_mismatch"
			break
		}
		if n0 != binary.BigEndian.Uint32(h[16:20]) || n1 != binary.BigEndian.Uint32(h[20:24]) {
			stop = "checksum_mismatch"
			break
		}
		s0, s1 = n0, n1
		start := int(pageNo-1) * int(pageSize)
		if len(work) < start+int(pageSize) {
			work = append(work, make([]byte, start+int(pageSize)-len(work))...)
		}
		copy(work[start:start+int(pageSize)], page)
		if commit != 0 {
			if commit < pageNo {
				stop = "invalid_commit_size"
				break
			}
			dbPages = commit
			committed = valid
			txs++
		}
	}
	if txs == 0 {
		return errors.New("no committed frames")
	}
	if len(work) > int(dbPages)*int(pageSize) {
		work = work[:int(dbPages)*int(pageSize)]
	}
	if len(work) > 19 {
		work[18], work[19] = 1, 1
	}
	sum := sha256.Sum256(work)
	r := Report{
		Status:            "recovered",
		PageSize:          pageSize,
		FramesScanned:     scanned,
		ValidFrames:       valid,
		CommittedFrames:   committed,
		Transactions:      txs,
		DatabasePages:     dbPages,
		IgnoredTailFrames: valid - committed,
		StopReason:        stop,
		OutputSHA256:      hex.EncodeToString(sum[:]),
	}
	if err := os.WriteFile(*out, work, 0o644); err != nil {
		return err
	}
	b, _ := json.Marshal(r)
	return os.WriteFile(*report, append(b, '\n'), 0o644)
}
