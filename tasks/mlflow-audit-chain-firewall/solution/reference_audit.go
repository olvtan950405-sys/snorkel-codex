package audit

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"strings"
)

const mask = "[REDACTED]"
type input struct { Seq int64; Method, Path string; Headers map[string]string; Body any }
type safe struct { Method string `json:"method"`; Path string `json:"path"`; Headers map[string]string `json:"headers"`; Body any `json:"body"` }
type base struct { Seq int64 `json:"seq"`; Decision string `json:"decision"`; Route string `json:"route,omitempty"`; Request *safe `json:"request,omitempty"`; Reason string `json:"reason,omitempty"` }
type output struct { Seq int64 `json:"seq"`; Decision string `json:"decision"`; Route string `json:"route,omitempty"`; Request *safe `json:"request,omitempty"`; Reason string `json:"reason,omitempty"`; Chain string `json:"chain"` }

var routes = map[string]map[string]string{
	"/api/2.0/mlflow/runs/log-metric":{"POST":"log_metric"},
	"/api/2.0/mlflow/runs/log-parameter":{"POST":"log_parameter"},
	"/api/2.0/mlflow/runs/set-tag":{"POST":"set_tag"},
	"/api/2.0/mlflow/runs/get":{"GET":"get_run"},
	"/api/2.0/mlflow/runs/delete":{"DELETE":"delete_run"},
}
var headerKeys = map[string]bool{"authorization":true,"cookie":true,"x-api-key":true,"x-mlflow-token":true,"x-amz-security-token":true}
var bodyKeys = map[string]bool{"password":true,"secret":true,"client_secret":true,"token":true,"access_token":true,"api_key":true,"credential":true,"x-amz-credential":true,"x-amz-signature":true,"x-amz-security-token":true}

func decodeValue(d *json.Decoder) (any,error) {
	t,err:=d.Token(); if err!=nil{return nil,err}
	if q,ok:=t.(json.Delim);ok { switch q {
	case '{': m:=map[string]any{};for d.More(){z,e:=d.Token();if e!=nil{return nil,e};k:=z.(string);if _,exists:=m[k];exists{return nil,errors.New("duplicate key")};v,e:=decodeValue(d);if e!=nil{return nil,e};m[k]=v};_,e:=d.Token();return m,e
	case '[': a:=[]any{};for d.More(){v,e:=decodeValue(d);if e!=nil{return nil,e};a=append(a,v)};_,e:=d.Token();return a,e
	default:return nil,errors.New("invalid delimiter") } }
	return t,nil
}
func parse(line []byte)(input,error){
	d:=json.NewDecoder(bytes.NewReader(line));d.UseNumber();v,e:=decodeValue(d);if e!=nil{return input{},e};if _,e=d.Token();e!=io.EOF{return input{},errors.New("trailing JSON")}
	m,ok:=v.(map[string]any);if !ok{return input{},errors.New("not object")};for k:=range m{if k!="seq"&&k!="method"&&k!="path"&&k!="headers"&&k!="body"{return input{},fmt.Errorf("unknown field %s",k)}}
	n,ok:=m["seq"].(json.Number);if !ok{return input{},errors.New("bad seq")};seq,e:=n.Int64();if e!=nil||seq<0||seq>9007199254740991{return input{},errors.New("bad seq")}
	get:=func(k string)(string,error){v,yes:=m[k];s,ok:=v.(string);if !yes||!ok||s==""{return "",fmt.Errorf("bad %s",k)};return s,nil}
	method,e:=get("method");if e!=nil{return input{},e};path,e:=get("path");if e!=nil{return input{},e};headers:=map[string]string{}
	if v,yes:=m["headers"];yes{obj,ok:=v.(map[string]any);if !ok{return input{},errors.New("bad headers")};for k,v:=range obj{s,ok:=v.(string);if !ok{return input{},errors.New("bad header value")};headers[k]=s}}
	return input{Seq:seq,Method:method,Path:path,Headers:headers,Body:m["body"]},nil
}
func tagSecret(s string)bool{l:=strings.ToLower(s);if l=="mlflow.user"||l=="mlflow.source.name"||l=="mlflow.source.git.commit"{return true};for _,p:=range []string{"password","secret","token","credential","api_key"}{if strings.Contains(l,p){return true}};return false}
func walk(v any)(any,bool){
	bad:=false
	switch x:=v.(type){
	case map[string]any:o:=map[string]any{};tag,tagged:=x["key"].(string);for k,v:=range x{if bodyKeys[strings.ToLower(k)]||(k=="value"&&tagged&&tagSecret(tag)){o[k]=mask;continue};z,b:=walk(v);o[k]=z;bad=bad||b};return o,bad
	case []any:o:=make([]any,len(x));for i,v:=range x{z,b:=walk(v);o[i]=z;bad=bad||b};return o,bad
	case string:u,e:=url.Parse(x);if e!=nil||u.Scheme==""{return x,false};scheme:=strings.ToLower(u.Scheme);allowed:=map[string]bool{"http":true,"https":true,"s3":true,"gs":true,"wasbs":true,"dbfs":true,"file":true};bad=!allowed[scheme]||u.User!=nil||(scheme=="file"&&u.Host!="");if scheme=="http"||scheme=="https"{q:=u.Query();for k:=range q{l:=strings.ToLower(k);if headerKeys[l]||bodyKeys[l]{q.Set(k,mask)}};u.RawQuery=q.Encode();return u.String(),bad};return x,bad
	default:return v,false}
}
func classify(r input)base{
	p:=r.Path;if i:=strings.IndexByte(p,'?');i>=0{p=p[:i]};if len(p)>1&&strings.HasSuffix(p,"/"){p=strings.TrimSuffix(p,"/")};method:=strings.ToUpper(r.Method);ms,known:=routes[p];if !known{return base{Seq:r.Seq,Decision:"reject",Reason:"unsupported_endpoint"}};route,ok:=ms[method];if !ok{return base{Seq:r.Seq,Decision:"reject",Reason:"method_not_allowed"}};if strings.Contains(r.Path,"?"){return base{Seq:r.Seq,Decision:"reject",Reason:"query_in_path"}}
	body,bad:=walk(r.Body);if bad{return base{Seq:r.Seq,Decision:"reject",Reason:"unsafe_uri"}};headers:=map[string]string{};for k,v:=range r.Headers{if headerKeys[strings.ToLower(k)]{headers[k]=mask}else{headers[k]=v}}
	return base{Seq:r.Seq,Decision:"forward",Route:route,Request:&safe{Method:method,Path:p,Headers:headers,Body:body}}
}
func canonical(v any)([]byte,error){var b bytes.Buffer;e:=json.NewEncoder(&b);e.SetEscapeHTML(false);if err:=e.Encode(v);err!=nil{return nil,err};z:=b.Bytes();return z[:len(z)-1],nil}
func Sanitize(inPath,outPath,seed string)error{
	if len(seed)!=64||strings.ToLower(seed)!=seed{return errors.New("bad seed")};previous,e:=hex.DecodeString(seed);if e!=nil||len(previous)!=32{return errors.New("bad seed")}
	in,e:=os.Open(inPath);if e!=nil{return e};defer in.Close();tmp,e:=os.CreateTemp(filepath.Dir(outPath),".mlflow-audit-*");if e!=nil{return e};name:=tmp.Name();done:=false;defer func(){tmp.Close();if !done{os.Remove(name)}}()
	s:=bufio.NewScanner(in);s.Buffer(make([]byte,65536),8*1024*1024);enc:=json.NewEncoder(tmp);enc.SetEscapeHTML(false);seen:=map[int64]bool{};var last int64=-1
	for s.Scan(){line:=bytes.TrimSpace(s.Bytes());if len(line)==0{continue};r,e:=parse(line);if e!=nil{return e};if seen[r.Seq]||r.Seq<last{return errors.New("invalid sequence")};seen[r.Seq]=true;last=r.Seq;b:=classify(r);raw,e:=canonical(b);if e!=nil{return e};h:=sha256.New();h.Write(previous);h.Write(raw);sum:=h.Sum(nil);o:=output{Seq:b.Seq,Decision:b.Decision,Route:b.Route,Request:b.Request,Reason:b.Reason,Chain:hex.EncodeToString(sum)};if e=enc.Encode(o);e!=nil{return e};previous=sum}
	if e=s.Err();e!=nil{return e};if e=tmp.Sync();e!=nil{return e};if e=tmp.Close();e!=nil{return e};if e=os.Rename(name,outPath);e!=nil{return e};done=true;return nil
}
