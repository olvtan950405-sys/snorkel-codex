# RelayCast attestation contract (version 1)

## Process and paths

`MEDIA_ROOT` defaults to `/app/media`. Every media name is a slash-separated **relative** path. It must be clean, must not contain an empty, `.` or `..` component, and must name a regular file below the real (symlink-resolved) media root. A symlink at any point is rejected. FFprobe is invoked directly (never through a shell) as:

`ffprobe -v error -show_entries format=format_name,duration:stream=index,codec_type,codec_name,time_base,width,height,sample_rate,channels -of json <path>`

The command path may be configured with `FFPROBE_BIN` (default `ffprobe`). Output is limited to 1 MiB. A nonzero exit, invalid JSON, unknown codec type, missing required field, duplicate stream index, or nonpositive value is invalid evidence.

## Probe records

`POST /v1/probe` accepts exactly `{"media":"relative/path.ts"}`. Unknown JSON fields and trailing JSON are errors. Exactly one video stream and zero or more audio streams are permitted; other stream types are rejected.

The normalized record has keys in this order:

```json
{"media":"cam/a.ts","format":"mpegts","duration_us":1000000,"streams":[{"index":0,"type":"video","codec":"h264","time_base":"1/90000","width":320,"height":180}]}
```

`format_name` is a comma-separated FFprobe value; trim components, remove duplicates, sort, and join with commas. Duration is a decimal number of seconds converted exactly to integer microseconds; more than six fractional digits is invalid. Stream `index` is a nonnegative decimal integer. `codec_type` is `video` or `audio`; codec names are nonempty lowercase ASCII `[a-z0-9_]+`. `time_base` is reduced to `n/d`, with `n >= 0` and `d > 0`. Video requires positive integer width/height and omits audio fields. Audio requires positive integer sample_rate/channels and omits video fields. Sort streams by index.

The successful probe response is `{"record":<record>,"digest":"<lowercase sha256 of compact record JSON>"}`.

## GraphML

`POST /v1/attest` accepts exactly `{"graphml":"/absolute/file.graphml"}`. The CLI accepts the graph path via `--graph`. The file must be regular and at most 1 MiB. The supported GraphML subset has one `<graph edgedefault="directed">`, nodes with unique nonempty IDs, and edges with unique nonempty `id`, valid `source`/`target`, and three `<data>` values. `<key for="graph" attr.name="public_key">` identifies the graph-level base64 Ed25519 public key (exactly 32 decoded bytes). Edge keys identify `media`, `probe_digest`, and `signature`. No unknown graph/edge data attributes, duplicate data values, nested graphs, or undirected graphs are accepted.

For every edge, probe its media afresh and require its lowercase hex digest to equal `probe_digest`. Decode the base64 signature to exactly 64 bytes and verify it over these bytes (`||` means concatenation and `NUL` is one zero byte):

`"relaycast-edge-v1" || NUL || edge.id || NUL || source || NUL || target || NUL || media || NUL || probe_digest`

Any failure rejects the entire topology.

## Merkle tree and report

Sort verified edges by bytewise edge ID. Each report edge is ordered as:

`{"id":...,"source":...,"target":...,"media":...,"probe_digest":...,"signature":...}`

The leaf is `SHA256("relaycast-leaf-v1" || NUL || compact-edge-JSON)`. Each parent is `SHA256("relaycast-node-v1" || NUL || left-32-bytes || right-32-bytes)`. Duplicate the final digest at an odd-sized level. A graph must contain at least one edge. The report is:

`{"schema":"relaycast.provenance/v1","graph_id":"...","public_key":"...","edges":[...],"merkle_root":"..."}`

where `graph_id` is the required nonempty graph `id`, public key/signatures retain their GraphML base64 spelling, digests are lowercase hex, and the file/CLI JSON has one trailing newline. `reproduce` creates the output parent and atomically replaces the output file.

## HTTP errors

Success is status 200. Invalid JSON/request is 400, invalid evidence/signature/GraphML is 422, and an internal failure is 500. Errors have exactly `{"error":{"code":"bad_request|invalid_evidence|internal","message":"..."}}`; messages must be nonempty and must not reveal absolute filesystem paths or command stderr. The attest success body is the report object.
