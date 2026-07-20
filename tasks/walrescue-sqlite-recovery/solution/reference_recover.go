package recoverdb

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"os"
	"path/filepath"
)

type Report struct {
	Status string `json:"status"`
	PageSize uint32 `json:"page_size"`
	FramesScanned int `json:"frames_scanned"`
	ValidFrames int `json:"valid_frames"`
	CommittedFrames int `json:"committed_frames"`
	Transactions int `json:"transactions"`
	DatabasePages uint32 `json:"database_pages"`
	IgnoredTailFrames int `json:"ignored_tail_frames"`
	StopReason string `json:"stop_reason"`
	OutputSHA256 string `json:"output_sha256"`
}

type frame struct { page uint32; data []byte }

func checksum(data []byte, s0, s1 uint32, little bool) (uint32, uint32) {
	for i := 0; i < len(data); i += 8 {
		var x0, x1 uint32
		if little { x0 = binary.LittleEndian.Uint32(data[i:i+4]); x1 = binary.LittleEndian.Uint32(data[i+4:i+8])
		} else { x0 = binary.BigEndian.Uint32(data[i:i+4]); x1 = binary.BigEndian.Uint32(data[i+4:i+8]) }
		s0 += x0 + s1; s1 += x1 + s0
	}
	return s0, s1
}

func decodePageSize(v uint32) (uint32, error) {
	if v == 1 { return 65536, nil }
	if v < 512 || v > 65536 || v&(v-1) != 0 { return 0, errors.New("unsupported page size") }
	return v, nil
}

func atomicWrite(path string, data []byte) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0755); err != nil { return err }
	f, err := os.CreateTemp(dir, ".walrescue-*"); if err != nil { return err }
	name := f.Name(); good := false
	defer func(){ if !good { f.Close(); os.Remove(name) } }()
	if err = f.Chmod(0644); err == nil { _, err = f.Write(data) }
	if err == nil { err = f.Sync() }; if e := f.Close(); err == nil { err = e }
	if err == nil { err = os.Rename(name, path) }; if err != nil { return err }
	d, err := os.Open(dir); if err != nil { return err }; err = d.Sync(); d.Close()
	if err == nil { good = true }; return err
}

func recoverBytes(base, wal []byte) ([]byte, Report, error) {
	var r Report
	if len(base) < 20 || string(base[:16]) != "SQLite format 3\x00" { return nil, r, errors.New("invalid base database") }
	bv := uint32(binary.BigEndian.Uint16(base[16:18])); bps, err := decodePageSize(bv)
	if err != nil || len(base)%int(bps) != 0 { return nil, r, errors.New("invalid base database page size") }
	if len(wal) < 32 { return nil, r, errors.New("truncated WAL header") }
	magic := binary.BigEndian.Uint32(wal[:4]); little := magic == 0x377f0682
	if !little && magic != 0x377f0683 { return nil, r, errors.New("unsupported WAL magic") }
	if binary.BigEndian.Uint32(wal[4:8]) != 3007000 { return nil, r, errors.New("unsupported WAL version") }
	ps, err := decodePageSize(binary.BigEndian.Uint32(wal[8:12])); if err != nil || ps != bps { return nil, r, errors.New("page size mismatch") }
	salt1, salt2 := binary.BigEndian.Uint32(wal[16:20]), binary.BigEndian.Uint32(wal[20:24])
	s0, s1 := checksum(wal[:24], 0, 0, little)
	if s0 != binary.BigEndian.Uint32(wal[24:28]) || s1 != binary.BigEndian.Uint32(wal[28:32]) { return nil, r, errors.New("bad header checksum") }

	work := append([]byte(nil), base...); var durable []byte; tx := []frame{}
	valid, committed, transactions, scanned := 0, 0, 0, 0
	var dbPages uint32; stop := "end_of_wal"; slot := 24 + int(ps); offset := 32
	for offset+slot <= len(wal) {
		scanned++; h := wal[offset:offset+24]; pg, commit := binary.BigEndian.Uint32(h[:4]), binary.BigEndian.Uint32(h[4:8])
		if pg == 0 { stop = "zero_page_number"; break }
		if binary.BigEndian.Uint32(h[8:12]) != salt1 || binary.BigEndian.Uint32(h[12:16]) != salt2 { stop = "salt_mismatch"; break }
		page := wal[offset+24:offset+slot]; input := make([]byte, 8+len(page)); copy(input, h[:8]); copy(input[8:], page)
		n0, n1 := checksum(input, s0, s1, little)
		if n0 != binary.BigEndian.Uint32(h[16:20]) || n1 != binary.BigEndian.Uint32(h[20:24]) { stop = "checksum_mismatch"; break }
		candidate := append(tx, frame{pg, append([]byte(nil), page...)})
		if commit != 0 { for _, f := range candidate { if f.page > commit { stop = "invalid_commit_size"; goto finished } } }
		s0, s1 = n0, n1; valid++; tx = candidate; offset += slot
		if commit != 0 {
			size := int(commit)*int(ps); if len(work) < size { work = append(work, make([]byte, size-len(work))...) } else { work = work[:size] }
			for _, f := range tx { start := int(f.page-1)*int(ps); copy(work[start:start+int(ps)], f.data) }
			durable = append(durable[:0], work...); committed = valid; transactions++; dbPages = commit; tx = tx[:0]
		}
	}
finished:
	if stop == "end_of_wal" && offset < len(wal) { stop = "partial_frame" }
	if transactions == 0 { return nil, r, errors.New("WAL contains no valid commit") }
	durable[18], durable[19] = 1, 1; digest := sha256.Sum256(durable)
	r = Report{"recovered", ps, scanned, valid, committed, transactions, dbPages, valid-committed, stop, hex.EncodeToString(digest[:])}
	return durable, r, nil
}

func Run(args []string) error {
	fs := flag.NewFlagSet("walrescue", flag.ContinueOnError); db := fs.String("db", "", ""); wal := fs.String("wal", "", ""); out := fs.String("out", "", ""); rp := fs.String("report", "", "")
	if len(args) == 0 || args[0] != "recover" { return errors.New("usage: walrescue recover --db <path> --wal <path> --out <path> --report <path>") }
	if err := fs.Parse(args[1:]); err != nil { return err }; if *db == "" || *wal == "" || *out == "" || *rp == "" { return errors.New("all path flags are required") }
	os.Remove(*out); os.Remove(*rp); base, err := os.ReadFile(*db); if err != nil { return err }; wb, err := os.ReadFile(*wal); if err != nil { return err }
	output, report, err := recoverBytes(base, wb); if err != nil { return err }; if err = atomicWrite(*out, output); err != nil { return err }
	j, err := json.Marshal(report); if err != nil { return err }; if err = atomicWrite(*rp, append(j, '\n')); err != nil { os.Remove(*out); return err }; return nil
}
