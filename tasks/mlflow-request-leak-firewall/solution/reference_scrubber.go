package scrubber

import (
	"bufio"
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"strings"
)

const redacted = "[REDACTED]"

type inputRequest struct { ID, Method, Path string; Headers, Query map[string]string; Body any; bodyPresent bool }
type safeRequest struct { Method string `json:"method"`; Path string `json:"path"`; Headers map[string]string `json:"headers"`; Query map[string]string `json:"query"`; Body any `json:"body"` }
type record struct { ID string `json:"id"`; Decision string `json:"decision"`; Route string `json:"route,omitempty"`; Request *safeRequest `json:"request,omitempty"`; Reason string `json:"reason,omitempty"` }

var routes=map[string]map[string]string{
	"/api/2.0/mlflow/runs/create":{"POST":"create_run"},
	"/api/2.0/mlflow/runs/log-batch":{"POST":"log_batch"},
	"/api/2.0/mlflow/runs/set-tag":{"POST":"set_tag"},
	"/api/2.0/mlflow/runs/get":{"GET":"get_run"},
	"/api/2.0/mlflow/artifacts/get-download-uri":{"GET":"artifact_uri"},
}
var direct=map[string]bool{"authorization":true,"proxy-authorization":true,"cookie":true,"set-cookie":true,"x-api-key":true,"x-mlflow-token":true,"token":true,"access_token":true,"refresh_token":true,"x-amz-credential":true,"x-amz-signature":true,"x-amz-security-token":true,"sig":true}
var bodyKeys=map[string]bool{"password":true,"passwd":true,"secret":true,"client_secret":true,"token":true,"access_token":true,"refresh_token":true,"api_key":true,"authorization":true,"credential":true,"x-amz-credential":true,"x-amz-signature":true,"x-amz-security-token":true}

func value(d *json.Decoder) (any,error) {
	t,err:=d.Token(); if err!=nil{return nil,err}
	if delim,ok:=t.(json.Delim); ok { switch delim {
	case '{': m:=map[string]any{}; for d.More(){ kt,e:=d.Token();if e!=nil{return nil,e};k,ok:=kt.(string);if !ok{return nil,errors.New("non-string key")};if _,yes:=m[k];yes{return nil,errors.New("duplicate key")};v,e:=value(d);if e!=nil{return nil,e};m[k]=v }; end,e:=d.Token();if e!=nil||end!=json.Delim('}'){return nil,errors.New("bad object")};return m,nil
	case '[': a:=[]any{};for d.More(){v,e:=value(d);if e!=nil{return nil,e};a=append(a,v)};end,e:=d.Token();if e!=nil||end!=json.Delim(']'){return nil,errors.New("bad array")};return a,nil
	default:return nil,errors.New("bad delimiter") } }
	return t,nil
}
func parse(line []byte)(inputRequest,error){
	d:=json.NewDecoder(bytes.NewReader(line));d.UseNumber();v,e:=value(d);if e!=nil{return inputRequest{},e};if _,e=d.Token();e!=io.EOF{return inputRequest{},errors.New("trailing JSON")}
	m,ok:=v.(map[string]any);if !ok{return inputRequest{},errors.New("request not object")}; allowed:=map[string]bool{"id":true,"method":true,"path":true,"headers":true,"query":true,"body":true};for k:=range m{if !allowed[k]{return inputRequest{},fmt.Errorf("unknown field %s",k)}}
	str:=func(k string)(string,error){x,yes:=m[k];if !yes{return "",fmt.Errorf("missing %s",k)};s,ok:=x.(string);if !ok||s==""{return "",fmt.Errorf("bad %s",k)};return s,nil}
	r:=inputRequest{};if r.ID,e=str("id");e!=nil{return r,e};if r.Method,e=str("method");e!=nil{return r,e};if r.Path,e=str("path");e!=nil{return r,e}
	mapstr:=func(k string)(map[string]string,error){out:=map[string]string{};x,yes:=m[k];if !yes{return out,nil};obj,ok:=x.(map[string]any);if !ok{return nil,fmt.Errorf("bad %s",k)};for n,v:=range obj{s,ok:=v.(string);if !ok{return nil,fmt.Errorf("bad %s value",k)};out[n]=s};return out,nil}
	if r.Headers,e=mapstr("headers");e!=nil{return r,e};if r.Query,e=mapstr("query");e!=nil{return r,e};r.Body,r.bodyPresent=m["body"];return r,nil
}
func sensitiveTag(s string)bool{l:=strings.ToLower(s);if l=="mlflow.user"||l=="mlflow.source.name"||l=="mlflow.source.git.commit"{return true};for _,p:=range []string{"password","secret","token","credential","api_key"}{if strings.Contains(l,p){return true}};return false}
func scrubMap(m map[string]string)map[string]string{o:=map[string]string{};for k,v:=range m{if direct[strings.ToLower(k)]{o[k]=redacted}else{o[k]=v}};return o}
func bodyWalk(v any)(any,bool){
	unsafe:=false
	switch x:=v.(type){
	case map[string]any:
		o:=map[string]any{}; tagKey,hasKey:=x["key"].(string)
		for k,z:=range x { if bodyKeys[strings.ToLower(k)] { o[k]=redacted;continue }; if k=="value"&&hasKey&&sensitiveTag(tagKey){o[k]=redacted;continue};q,b:=bodyWalk(z);unsafe=unsafe||b;o[k]=q };return o,unsafe
	case []any:o:=make([]any,len(x));for i,z:=range x{q,b:=bodyWalk(z);unsafe=unsafe||b;o[i]=q};return o,unsafe
	case string:
		u,e:=url.Parse(x);if e!=nil||u.Scheme==""{return x,false};scheme:=strings.ToLower(u.Scheme);allowed:=map[string]bool{"http":true,"https":true,"s3":true,"gs":true,"wasbs":true,"dbfs":true,"file":true};if !allowed[scheme]||u.User!=nil||(scheme=="file"&&u.Host!=""){unsafe=true};if scheme=="http"||scheme=="https"{q:=u.Query();for k:=range q{if direct[strings.ToLower(k)]{q.Set(k,redacted)}};u.RawQuery=q.Encode();return u.String(),unsafe};return x,unsafe
	default:return v,false }
}
func classify(r inputRequest)record{
	p:=r.Path;match:=p;if i:=strings.IndexByte(match,'?');i>=0{match=match[:i]};if len(match)>1&&strings.HasSuffix(match,"/"){match=strings.TrimSuffix(match,"/")};method:=strings.ToUpper(r.Method);methods,known:=routes[match];if !known{return record{ID:r.ID,Decision:"reject",Reason:"unsupported_endpoint"}};route,ok:=methods[method];if !ok{return record{ID:r.ID,Decision:"reject",Reason:"method_not_allowed"}}
	if strings.Contains(p,"?"){return record{ID:r.ID,Decision:"reject",Reason:"credential_in_path"}};if u,e:=url.Parse(p);e==nil&&u.User!=nil{return record{ID:r.ID,Decision:"reject",Reason:"credential_in_path"}}
	body,bad:=bodyWalk(r.Body);if bad{return record{ID:r.ID,Decision:"reject",Reason:"unsafe_artifact_uri"}}
	return record{ID:r.ID,Decision:"forward",Route:route,Request:&safeRequest{Method:method,Path:match,Headers:scrubMap(r.Headers),Query:scrubMap(r.Query),Body:body}}
}
func ScrubFile(input,output string)error{
	in,e:=os.Open(input);if e!=nil{return e};defer in.Close();dir:=filepath.Dir(output);tmp,e:=os.CreateTemp(dir,".mlflow-scrub-*");if e!=nil{return e};name:=tmp.Name();ok:=false;defer func(){tmp.Close();if !ok{os.Remove(name)}}()
	s:=bufio.NewScanner(in);s.Buffer(make([]byte,64*1024),8*1024*1024);enc:=json.NewEncoder(tmp);enc.SetEscapeHTML(false)
	for s.Scan(){line:=bytes.TrimSpace(s.Bytes());if len(line)==0{continue};r,e:=parse(line);if e!=nil{return e};if e=enc.Encode(classify(r));e!=nil{return e}}
	if e=s.Err();e!=nil{return e};if e=tmp.Sync();e!=nil{return e};if e=tmp.Close();e!=nil{return e};if e=os.Rename(name,output);e!=nil{return e};ok=true;return nil
}
